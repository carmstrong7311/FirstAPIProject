"""The Odds API (https://the-odds-api.com) v4 provider."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from ..config import Settings
from ..models import FetchResult, Game, Quote


class OddsApiError(RuntimeError):
    pass


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _int_header(headers: httpx.Headers, name: str) -> int | None:
    value = headers.get(name)
    try:
        return int(float(value)) if value is not None else None
    except ValueError:
        return None


def parse_events(payload: list[dict[str, Any]]) -> list[Game]:
    games = []
    for event in payload:
        game = Game(
            id=event["id"],
            commence_time=_parse_time(event["commence_time"]),
            home=event["home_team"],
            away=event["away_team"],
        )
        for book in event.get("bookmakers", []):
            book_updated = book.get("last_update")
            for market in book.get("markets", []):
                updated = market.get("last_update") or book_updated
                if not updated:
                    continue
                for outcome in market.get("outcomes", []):
                    price = outcome.get("price")
                    if price is None or price == 0:
                        continue
                    game.quotes.append(
                        Quote(
                            book=book["key"],
                            book_title=book.get("title", book["key"]),
                            market=market["key"],
                            side=outcome["name"],
                            price=int(price),
                            point=outcome.get("point"),
                            last_update=_parse_time(updated),
                        )
                    )
        games.append(game)
    return games


class OddsApiProvider:
    name = "The Odds API"

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        if not settings.odds_api_key:
            raise OddsApiError("ODDS_API_KEY is not set")
        self.settings = settings
        self._client = client or httpx.AsyncClient(timeout=20)

    def _params(self) -> dict[str, str]:
        s = self.settings
        params = {
            "apiKey": s.odds_api_key,
            "markets": ",".join(s.markets),
            "oddsFormat": "american",
            "dateFormat": "iso",
        }
        if s.bookmakers:
            params["bookmakers"] = ",".join(s.bookmakers)
        else:
            params["regions"] = ",".join(s.regions)
        return params

    async def fetch(self) -> FetchResult:
        url = f"{self.settings.odds_api_base}/sports/{self.settings.sport_key}/odds"
        resp = await self._client.get(url, params=self._params())
        if resp.status_code != 200:
            try:
                message = resp.json().get("message", resp.text)
            except ValueError:
                message = resp.text
            raise OddsApiError(f"HTTP {resp.status_code}: {message}")
        return FetchResult(
            games=parse_events(resp.json()),
            credits_remaining=_int_header(resp.headers, "x-requests-remaining"),
            credits_used=_int_header(resp.headers, "x-requests-used"),
        )

    async def aclose(self) -> None:
        await self._client.aclose()
