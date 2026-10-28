"""Settings loaded from environment variables (and an optional .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader so we don't need python-dotenv. Real env vars win."""
    if not path.is_file():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _csv(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


@dataclass
class Settings:
    # Data source: "odds_api" (live) or "demo" (synthetic data, no key needed).
    provider: str = "demo"
    odds_api_key: str = ""
    odds_api_base: str = "https://api.the-odds-api.com/v4"
    sport_key: str = "americanfootball_ncaaf"
    regions: list[str] = field(default_factory=lambda: ["us", "us2"])
    # If set, overrides regions. Every 10 books cost the same as one region.
    bookmakers: list[str] = field(default_factory=list)
    markets: list[str] = field(default_factory=lambda: ["h2h", "spreads", "totals"])

    poll_seconds: float = 60.0
    # Stop polling the paid API when the remaining credit balance drops below this.
    min_credits_reserve: int = 50

    # Books treated as the "true" price when they quote the same line.
    sharp_books: list[str] = field(default_factory=lambda: ["pinnacle", "circasports", "lowvig"])

    # Mispricing thresholds.
    ev_threshold: float = 0.02          # flag quotes with >= 2% expected value vs fair
    spread_off_market: float = 1.0      # points away from consensus spread
    total_off_market: float = 1.5       # points away from consensus total
    middle_min_width: float = 1.0       # minimum middle window in points
    stale_seconds: float = 300.0        # book hasn't updated in this long vs freshest book
    min_consensus_books: int = 2        # other books needed at same line to build a fair price

    history_db: str = ""                # optional SQLite path to log every line move
    promos_file: str = "promos.json"    # where hand-entered promos are saved; "" = memory only

    @property
    def fetch_cost(self) -> int:
        """Credits charged by The Odds API per odds call."""
        if self.bookmakers:
            region_units = -(-len(self.bookmakers) // 10)
        else:
            region_units = len(self.regions)
        return region_units * len(self.markets)

    @classmethod
    def from_env(cls, dotenv: Path | None = Path(".env")) -> "Settings":
        if dotenv is not None:
            _load_dotenv(dotenv)
        env = os.environ
        s = cls()
        s.odds_api_key = env.get("ODDS_API_KEY", "")
        s.provider = env.get("ODDS_PROVIDER", "odds_api" if s.odds_api_key else "demo")
        s.odds_api_base = env.get("ODDS_API_BASE", s.odds_api_base)
        s.sport_key = env.get("SPORT_KEY", s.sport_key)
        if "REGIONS" in env:
            s.regions = _csv(env["REGIONS"])
        if "BOOKMAKERS" in env:
            s.bookmakers = _csv(env["BOOKMAKERS"])
        if "MARKETS" in env:
            s.markets = _csv(env["MARKETS"])
        if "SHARP_BOOKS" in env:
            s.sharp_books = _csv(env["SHARP_BOOKS"])
        for name, cast in (
            ("poll_seconds", float),
            ("min_credits_reserve", int),
            ("ev_threshold", float),
            ("spread_off_market", float),
            ("total_off_market", float),
            ("middle_min_width", float),
            ("stale_seconds", float),
            ("min_consensus_books", int),
        ):
            if name.upper() in env:
                setattr(s, name, cast(env[name.upper()]))
        s.history_db = env.get("HISTORY_DB", s.history_db)
        s.promos_file = env.get("PROMOS_FILE", s.promos_file)
        return s
