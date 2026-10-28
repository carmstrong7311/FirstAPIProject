"""Odds data providers. Each exposes `name`, `async fetch() -> FetchResult` and `async aclose()`.

To add a feed (OpticOdds, SportsDataIO, a book's own API, ...) implement the
same interface and register it in `make_provider`.
"""

from __future__ import annotations

from typing import Protocol

from ..config import Settings
from ..models import FetchResult


class Provider(Protocol):
    name: str

    async def fetch(self) -> FetchResult: ...

    async def aclose(self) -> None: ...


def make_provider(settings: Settings) -> Provider:
    if settings.provider == "odds_api":
        from .odds_api import OddsApiProvider

        return OddsApiProvider(settings)
    if settings.provider == "demo":
        from .demo import DemoProvider

        return DemoProvider()
    raise ValueError(f"Unknown ODDS_PROVIDER: {settings.provider!r}")
