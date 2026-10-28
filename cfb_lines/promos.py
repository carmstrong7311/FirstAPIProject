"""Sportsbook promotions entered by the user, persisted to a JSON file.

No odds feed publishes promos in a usable form (they're personalized per account
and per state), so they're entered by hand and the analyzer finds the best way
to use each one against the live lines.
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .models import H2H, SPREADS, TOTALS

PromoType = Literal["profit_boost", "bonus_bet", "no_sweat"]


class PromoIn(BaseModel):
    book: str = Field(description="Bookmaker key, e.g. 'draftkings'")
    type: PromoType
    amount: float = Field(gt=0, description="Max stake (boost / no-sweat) or bonus bet size")
    boost_pct: float | None = Field(None, gt=0, description="Profit boost, e.g. 50 for +50%")
    conversion_pct: float = Field(70, ge=0, le=100,
                                  description="No-sweat: expected value of the refunded bonus bet")
    min_odds: int | None = Field(None, description="Lowest American odds allowed, e.g. -200")
    markets: list[Literal["h2h", "spreads", "totals"]] = Field(default_factory=lambda: [H2H, SPREADS, TOTALS])
    expires: datetime | None = None
    note: str = ""

    @model_validator(mode="after")
    def _check(self) -> "PromoIn":
        if self.type == "profit_boost" and not self.boost_pct:
            raise ValueError("profit_boost needs boost_pct")
        if not self.markets:
            raise ValueError("pick at least one market")
        return self


class Promo(PromoIn):
    id: str

    def active(self, now: datetime) -> bool:
        return self.expires is None or self.expires > now


class PromoStore:
    def __init__(self, path: str = ""):
        self.path = Path(path) if path else None
        self._lock = threading.Lock()
        self.promos: dict[str, Promo] = {}
        if self.path and self.path.is_file():
            for raw in json.loads(self.path.read_text()):
                promo = Promo.model_validate(raw)
                self.promos[promo.id] = promo

    def _save(self) -> None:
        if self.path:
            self.path.write_text(json.dumps([p.model_dump(mode="json") for p in self.promos.values()], indent=2))

    def list(self) -> list[Promo]:
        return list(self.promos.values())

    def add(self, data: PromoIn) -> Promo:
        with self._lock:
            promo = Promo(id=uuid.uuid4().hex[:8], **data.model_dump())
            self.promos[promo.id] = promo
            self._save()
            return promo

    def remove(self, promo_id: str) -> bool:
        with self._lock:
            removed = self.promos.pop(promo_id, None) is not None
            self._save()
            return removed
