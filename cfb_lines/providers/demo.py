"""Synthetic market so the dashboard can be run without an API key.

Each game has a hidden "true" spread and total that random-walk between polls.
Books follow it with noise and lag, and occasionally post a mispriced line,
which exercises every detector in analysis.py.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from ..models import H2H, OVER, SPREADS, TOTALS, UNDER, FetchResult, Game, Quote
from ..odds import prob_to_american

BOOKS = [
    ("pinnacle", "Pinnacle"),
    ("draftkings", "DraftKings"),
    ("fanduel", "FanDuel"),
    ("betmgm", "BetMGM"),
    ("williamhill_us", "Caesars"),
    ("espnbet", "ESPN BET"),
    ("betrivers", "BetRivers"),
    ("fanatics", "Fanatics"),
    ("bovada", "Bovada"),
    ("betonlineag", "BetOnline.ag"),
]

MATCHUPS = [
    ("Georgia Bulldogs", "Florida Gators"),
    ("Ohio State Buckeyes", "Penn State Nittany Lions"),
    ("Texas Longhorns", "Vanderbilt Commodores"),
    ("Oregon Ducks", "Wisconsin Badgers"),
    ("Alabama Crimson Tide", "LSU Tigers"),
    ("Notre Dame Fighting Irish", "Navy Midshipmen"),
    ("Miami Hurricanes", "SMU Mustangs"),
    ("Michigan Wolverines", "Purdue Boilermakers"),
    ("Tennessee Volunteers", "Oklahoma Sooners"),
    ("BYU Cougars", "Iowa State Cyclones"),
    ("Texas Tech Red Raiders", "Kansas State Wildcats"),
    ("Ole Miss Rebels", "South Carolina Gamecocks"),
]

SPREAD_SD = 15.5  # CFB final margin std. dev. used to turn spreads into win probabilities


def _round_half(x: float) -> float:
    return round(x * 2) / 2


def _home_win_prob(home_spread: float) -> float:
    return 0.5 * (1 + math.erf(-home_spread / (SPREAD_SD * math.sqrt(2))))


@dataclass
class _Truth:
    spread: float  # home spread, negative = home favored
    total: float


@dataclass
class _BookState:
    spread: float
    total: float
    spread_juice: int = 0   # shifts home side price; away gets the mirror
    total_juice: int = 0
    ml_shade: float = 0.0
    win_prob: float = 0.5
    updated: datetime | None = None


class DemoProvider:
    name = "Demo (synthetic data)"

    def __init__(self, seed: int | None = None, n_games: int = len(MATCHUPS)):
        self.rng = random.Random(seed)
        now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        self.games: list[tuple[str, datetime, str, str]] = []
        self.truth: dict[str, _Truth] = {}
        self.books: dict[tuple[str, str], _BookState] = {}
        for i, (home, away) in enumerate(MATCHUPS[:n_games]):
            gid = f"demo-{i:02d}"
            kickoff = now + timedelta(hours=2 + 3 * (i % 4), days=i // 4)
            self.games.append((gid, kickoff, home, away))
            truth = _Truth(
                spread=self.rng.choice([-1, 1]) * self.rng.uniform(1, 24),
                total=self.rng.uniform(41, 66),
            )
            self.truth[gid] = truth
            for key, _ in BOOKS:
                self.books[(gid, key)] = _BookState(
                    spread=_round_half(truth.spread), total=_round_half(truth.total),
                    win_prob=_home_win_prob(truth.spread), updated=now,
                )

    def _step(self, now: datetime) -> None:
        rng = self.rng
        for gid, *_ in self.games:
            truth = self.truth[gid]
            truth.spread += rng.gauss(0, 0.25)
            truth.total += rng.gauss(0, 0.3)
            for key, _ in BOOKS:
                state = self.books[(gid, key)]
                # Sharp books move every tick; retail books lag.
                if key != "pinnacle" and rng.random() < 0.35:
                    continue
                state.spread = _round_half(truth.spread + rng.gauss(0, 0.15))
                state.total = _round_half(truth.total + rng.gauss(0, 0.2))
                state.spread_juice = rng.choice([0] * 6 + [-5, 5, -5, 5, -10, 10])
                state.total_juice = rng.choice([0] * 6 + [-5, 5])
                state.ml_shade = rng.gauss(0, 0.03)  # log-odds
                state.win_prob = _home_win_prob(truth.spread)
                # Occasional real mispricing at retail books; the sharp book stays honest.
                roll = rng.random() if key != "pinnacle" else 1.0
                if roll < 0.015:
                    state.spread += rng.choice([-1.5, 1.5, 2.0, -2.0])
                elif roll < 0.03:
                    state.total += rng.choice([-2.0, 2.5, -2.5])
                elif roll < 0.045:
                    state.ml_shade += rng.choice([-0.2, 0.2])
                state.updated = now

    def _quotes(self, gid: str, home: str, away: str) -> list[Quote]:
        quotes = []
        for key, title in BOOKS:
            s = self.books[(gid, key)]
            vig = 0.025 if key == "pinnacle" else 0.045
            ts = s.updated

            def q(market: str, side: str, price: int, point: float | None) -> Quote:
                return Quote(key, title, market, side, price, point, ts)

            hp = -110 + s.spread_juice if key != "pinnacle" else -105 + s.spread_juice
            ap = -110 - s.spread_juice if key != "pinnacle" else -105 - s.spread_juice
            quotes += [q(SPREADS, home, hp, s.spread), q(SPREADS, away, ap, -s.spread)]
            op = (-110 if key != "pinnacle" else -105) + s.total_juice
            up = (-110 if key != "pinnacle" else -105) - s.total_juice
            quotes += [q(TOTALS, OVER, op, s.total), q(TOTALS, UNDER, up, s.total)]
            logit = math.log(s.win_prob / (1 - s.win_prob)) + s.ml_shade
            p_home = min(max(1 / (1 + math.exp(-logit)), 0.02), 0.98)
            quotes += [
                q(H2H, home, prob_to_american(min(p_home * (1 + vig), 0.99)), None),
                q(H2H, away, prob_to_american(min((1 - p_home) * (1 + vig), 0.99)), None),
            ]
        return quotes

    async def fetch(self) -> FetchResult:
        now = datetime.now(timezone.utc)
        self._step(now)
        games = [
            Game(id=gid, commence_time=kickoff, home=home, away=away,
                 quotes=self._quotes(gid, home, away))
            for gid, kickoff, home, away in self.games
        ]
        return FetchResult(games=games)

    async def aclose(self) -> None:
        pass
