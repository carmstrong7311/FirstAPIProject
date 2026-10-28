"""Background poller: fetch -> analyze -> broadcast to every connected dashboard."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from .analysis import build_snapshot
from .config import Settings
from .history import LineHistory
from .providers import Provider

log = logging.getLogger(__name__)


class LineService:
    def __init__(self, settings: Settings, provider: Provider):
        self.settings = settings
        self.provider = provider
        self.history = LineHistory(settings.history_db)
        self.snapshot: dict[str, Any] | None = None
        self.status: dict[str, Any] = {
            "provider": provider.name,
            "poll_seconds": settings.poll_seconds,
            "fetch_cost": settings.fetch_cost if settings.provider == "odds_api" else 0,
            "last_poll": None,
            "last_error": None,
            "credits_remaining": None,
            "credits_used": None,
            "paused": None,
            "polls": 0,
        }
        self._subscribers: set[asyncio.Queue] = set()
        self._task: asyncio.Task | None = None
        self._wake = asyncio.Event()

    # ----- pub/sub -------------------------------------------------------
    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=2)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    def payload(self) -> dict[str, Any]:
        return {
            **(self.snapshot or {"games": [], "opportunities": [], "books": []}),
            "status": self.status,
            "recent_moves": list(self.history.recent)[:100],
        }

    def _broadcast(self) -> None:
        payload = self.payload()
        for q in list(self._subscribers):
            if q.full():  # slow client: drop its oldest update, it only needs the latest
                q.get_nowait()
            q.put_nowait(payload)

    # ----- polling -------------------------------------------------------
    async def poll_once(self) -> None:
        result = await self.provider.fetch()
        now = datetime.now(timezone.utc)
        moves = self.history.record(result.games, now)
        self.snapshot = build_snapshot(result.games, self.settings, now)
        self.status.update(
            last_poll=now.isoformat(),
            last_error=None,
            polls=self.status["polls"] + 1,
            moves_last_poll=len(moves),
        )
        if result.credits_remaining is not None:
            self.status["credits_remaining"] = result.credits_remaining
            self.status["credits_used"] = result.credits_used

    def _out_of_credits(self) -> bool:
        remaining = self.status["credits_remaining"]
        return remaining is not None and remaining < self.settings.min_credits_reserve + self.status["fetch_cost"]

    async def run(self) -> None:
        backoff = self.settings.poll_seconds
        while True:
            if self._out_of_credits():
                self.status["paused"] = (
                    f"Paused: {self.status['credits_remaining']} API credits left "
                    f"(reserve {self.settings.min_credits_reserve}). Use 'Refresh now' to force a poll."
                )
                self._broadcast()
            else:
                self.status["paused"] = None
                try:
                    await self.poll_once()
                    backoff = self.settings.poll_seconds
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # keep serving the last good snapshot
                    log.exception("poll failed")
                    self.status["last_error"] = f"{type(exc).__name__}: {exc}"
                    backoff = min(backoff * 2, 600)
                self._broadcast()
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=backoff)
            except asyncio.TimeoutError:
                pass
            self._wake.clear()

    async def refresh_now(self) -> None:
        """Manual poll that ignores the credit reserve."""
        try:
            await self.poll_once()
        except Exception as exc:
            self.status["last_error"] = f"{type(exc).__name__}: {exc}"
        self._broadcast()

    def start(self) -> None:
        self._task = asyncio.create_task(self.run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self.provider.aclose()
