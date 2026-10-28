"""Normalized, provider-independent representation of games and quotes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

SPREADS = "spreads"
TOTALS = "totals"
H2H = "h2h"
OVER = "Over"
UNDER = "Under"


@dataclass(frozen=True)
class Quote:
    book: str            # provider key, e.g. "draftkings"
    book_title: str      # display name, e.g. "DraftKings"
    market: str          # SPREADS | TOTALS | H2H
    side: str            # team name, OVER or UNDER
    price: int           # American odds
    point: float | None  # spread/total line; None for moneyline
    last_update: datetime


@dataclass
class Game:
    id: str
    commence_time: datetime
    home: str
    away: str
    quotes: list[Quote] = field(default_factory=list)


@dataclass
class FetchResult:
    games: list[Game]
    # Remaining/used credits reported by the provider, when it reports them.
    credits_remaining: int | None = None
    credits_used: int | None = None
