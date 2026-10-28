"""Turn raw quotes into a dashboard snapshot and a ranked list of mispricings.

Detectors:
  EV          a price beats the fair (no-vig) price at the same line by >= ev_threshold.
              Fair comes from a sharp book quoting the same line if available,
              otherwise the leave-one-out median of the other books.
  OFF_MARKET  a book's spread/total sits >= N points from the consensus line.
  ARB         best prices on opposite sides across two books guarantee profit.
  MIDDLE      opposite sides at two books leave a window where both legs win.
  Every quote also carries a `stale` flag when its book hasn't updated recently,
  since stale lines at a lagging book are the most common real mispricing.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import median
from typing import Any

from .config import Settings
from .models import H2H, OVER, SPREADS, TOTALS, UNDER, Game, Quote
from .odds import american_to_decimal, expected_value, no_vig, prob_to_american

KEY_NUMBERS = (3, 7, 10, 14, 17, 21)

# Each market is a pair of sides: (A, B). For spreads/h2h A is home, for totals A is over.
SIDES = {SPREADS: ("home", "away"), H2H: ("home", "away"), TOTALS: ("over", "under")}


@dataclass(frozen=True)
class Leg:
    book: str
    title: str
    side: str        # "home" | "away" | "over" | "under"
    price: int
    point: float | None
    last_update: datetime


def _side_key(game: Game, q: Quote) -> str | None:
    if q.market == TOTALS:
        return {OVER: "over", UNDER: "under"}.get(q.side)
    if q.side == game.home:
        return "home"
    if q.side == game.away:
        return "away"
    return None


def _fmt_point(p: float | None) -> str:
    if p is None:
        return ""
    return f"{p:+g}" if p else "PK"


def _fmt_price(p: int) -> str:
    return f"{p:+d}"


def _pair_key(market: str, leg_a: Leg) -> float | None:
    """The line a two-way pair is quoted at, from side A's perspective."""
    return None if market == H2H else leg_a.point


class GameAnalyzer:
    def __init__(self, game: Game, settings: Settings, now: datetime):
        self.g = game
        self.s = settings
        self.now = now
        # legs[market][book][side] -> Leg (first quote wins if a feed sends duplicates)
        self.legs: dict[str, dict[str, dict[str, Leg]]] = defaultdict(lambda: defaultdict(dict))
        self.titles: dict[str, str] = {}
        book_updated: dict[str, datetime] = {}
        for q in game.quotes:
            side = _side_key(game, q)
            if side is None or q.market not in SIDES:
                continue
            self.titles[q.book] = q.book_title
            self.legs[q.market][q.book].setdefault(
                side, Leg(q.book, q.book_title, side, q.price, q.point, q.last_update)
            )
            if q.book not in book_updated or q.last_update > book_updated[q.book]:
                book_updated[q.book] = q.last_update
        self.book_updated = book_updated
        freshest = max(book_updated.values(), default=now)
        self.stale = {
            b: (freshest - t).total_seconds() > settings.stale_seconds for b, t in book_updated.items()
        }

    # ----- helpers -------------------------------------------------------
    def pairs(self, market: str) -> dict[str, tuple[Leg, Leg]]:
        a, b = SIDES[market]
        out = {}
        for book, sides in self.legs[market].items():
            if a in sides and b in sides:
                la, lb = sides[a], sides[b]
                if market == SPREADS and (la.point is None or lb.point is None or la.point != -lb.point):
                    continue
                if market == TOTALS and la.point != lb.point:
                    continue
                out[book] = (la, lb)
        return out

    def fair(self, market: str, line: float | None, exclude: str) -> tuple[float, float, str] | None:
        """Fair probabilities (side A, side B) for `market` at `line`, ignoring book `exclude`."""
        pairs = {
            b: p for b, p in self.pairs(market).items() if b != exclude and _pair_key(market, p[0]) == line
        }
        for sharp in self.s.sharp_books:
            if sharp in pairs and not self.stale.get(sharp):
                la, lb = pairs[sharp]
                pa, pb = no_vig(la.price, lb.price)
                return pa, pb, self.titles.get(sharp, sharp)
        if len(pairs) < self.s.min_consensus_books:
            return None
        probs = [no_vig(la.price, lb.price)[0] for la, lb in pairs.values()]
        pa = median(probs)
        return pa, 1 - pa, f"consensus of {len(probs)}"

    def consensus_line(self, market: str) -> float | None:
        """Most-quoted line; ties go to the one nearest the median."""
        points = [p[0].point for p in self.pairs(market).values() if p[0].point is not None]
        if not points:
            return None
        counts = Counter(points)
        mid = median(points)
        return max(counts, key=lambda pt: (counts[pt], -abs(pt - mid), -pt))

    def label(self, market: str, side: str, point: float | None) -> str:
        if market == TOTALS:
            return f"{'Over' if side == 'over' else 'Under'} {point:g}"
        team = self.g.home if side == "home" else self.g.away
        return f"{team} {_fmt_point(point)}" if market == SPREADS else f"{team} ML"

    def _base(self, market: str) -> dict[str, Any]:
        return {
            "game_id": self.g.id,
            "matchup": f"{self.g.away} @ {self.g.home}",
            "commence_time": self.g.commence_time.isoformat(),
            "live": self.g.commence_time <= self.now,
            "market": market,
        }

    def _leg_json(self, leg: Leg, market: str) -> dict[str, Any]:
        return {
            "book": leg.book,
            "book_title": leg.title,
            "label": self.label(market, leg.side, leg.point),
            "price": leg.price,
            "point": leg.point,
            "stale": self.stale.get(leg.book, False),
            "last_update": leg.last_update.isoformat(),
        }

    # ----- detectors -----------------------------------------------------
    def analyze(self) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        opps: list[dict[str, Any]] = []
        books: dict[str, dict[str, Any]] = {
            b: {
                "title": self.titles[b],
                "last_update": t.isoformat(),
                "stale": self.stale[b],
                "markets": {},
            }
            for b, t in self.book_updated.items()
        }
        consensus: dict[str, Any] = {}

        for market, (side_a, side_b) in SIDES.items():
            cons_line = self.consensus_line(market) if market != H2H else None
            fair_at_cons = self.fair(market, cons_line, exclude="") if market == H2H or cons_line is not None else None
            consensus[market] = {
                "line": cons_line,
                "fair_a": round(fair_at_cons[0], 4) if fair_at_cons else None,
                "fair_price_a": prob_to_american(fair_at_cons[0]) if fair_at_cons else None,
                "fair_price_b": prob_to_american(fair_at_cons[1]) if fair_at_cons else None,
                "fair_source": fair_at_cons[2] if fair_at_cons else None,
            }

            for book, sides in self.legs[market].items():
                cell: dict[str, Any] = {}
                for side, leg in sides.items():
                    entry: dict[str, Any] = {"price": leg.price, "point": leg.point}
                    line = None if market == H2H else (leg.point if side == side_a else
                                                       (-leg.point if market == SPREADS else leg.point))
                    fair = self.fair(market, line, exclude=book) if (market == H2H or line is not None) else None
                    if fair:
                        fp = fair[0] if side == side_a else fair[1]
                        ev = expected_value(fp, leg.price)
                        entry["ev"] = round(ev, 4)
                        if ev >= self.s.ev_threshold:
                            opps.append({
                                **self._base(market),
                                "type": "EV",
                                "edge": round(ev, 4),
                                "legs": [self._leg_json(leg, market)],
                                "detail": (f"Fair {_fmt_price(prob_to_american(fp))} "
                                           f"({fp:.1%}) via {fair[2]}"),
                            })
                    cell[side] = entry
                books[book]["markets"][market] = cell

            if market != H2H and cons_line is not None:
                opps += self._off_market(market, cons_line)
            opps += self._arbs_and_middles(market)
            consensus[market]["best"] = self._best(market)

        game_json = {
            "id": self.g.id,
            "home": self.g.home,
            "away": self.g.away,
            "commence_time": self.g.commence_time.isoformat(),
            "live": self.g.commence_time <= self.now,
            "consensus": consensus,
            "books": books,
        }
        return game_json, opps

    def _off_market(self, market: str, cons: float) -> list[dict[str, Any]]:
        threshold = self.s.spread_off_market if market == SPREADS else self.s.total_off_market
        out = []
        for book, (la, lb) in self.pairs(market).items():
            diff = la.point - cons
            if abs(diff) < threshold:
                continue
            if market == SPREADS:
                # A higher home number is better for the home bettor, and vice versa.
                leg = la if diff > 0 else lb
                lo, hi = sorted((abs(la.point), abs(cons))) if la.point * cons > 0 else (0, max(abs(la.point), abs(cons)))
                keys = [k for k in KEY_NUMBERS if lo <= k <= hi]
                cons_txt = _fmt_point(cons if leg.side == "home" else -cons)
            else:
                leg = la if diff < 0 else lb  # low total -> over, high total -> under
                keys = []
                cons_txt = f"{cons:g}"
            detail = f"Market {cons_txt}, {abs(diff):g} pts better"
            if keys:
                detail += f" (through key number{'s' if len(keys) > 1 else ''} {', '.join(map(str, keys))})"
            out.append({
                **self._base(market),
                "type": "OFF_MARKET",
                "edge": round(abs(diff), 2),
                "legs": [self._leg_json(leg, market)],
                "detail": detail,
            })
        return out

    def _arbs_and_middles(self, market: str) -> list[dict[str, Any]]:
        side_a, side_b = SIDES[market]
        a_legs = [s[side_a] for s in self.legs[market].values() if side_a in s]
        b_legs = [s[side_b] for s in self.legs[market].values() if side_b in s]
        best_arb, best_mid = None, None
        for la in a_legs:
            for lb in b_legs:
                if la.book == lb.book:
                    continue
                if market == H2H:
                    width = 0.0
                elif la.point is None or lb.point is None:
                    continue
                elif market == SPREADS:
                    width = la.point + lb.point          # home -3 & away +4 -> 1 pt middle
                else:
                    width = lb.point - la.point          # over 50 & under 51.5 -> 1.5 pt middle
                if width < 0:
                    continue
                implied = 1 / american_to_decimal(la.price) + 1 / american_to_decimal(lb.price)
                if implied < 1:
                    profit = 1 / implied - 1
                    if best_arb is None or profit > best_arb[0]:
                        best_arb = (profit, la, lb, width)
                elif width >= self.s.middle_min_width and market != H2H:
                    key = (width, -implied)
                    if best_mid is None or key > best_mid[0]:
                        best_mid = (key, la, lb, implied)
        out = []
        if best_arb:
            profit, la, lb, width = best_arb
            stakes = self._stakes(la.price, lb.price)
            detail = f"Guaranteed {profit:.2%}; stake {stakes[0]:.1%} / {stakes[1]:.1%}"
            if width > 0:
                detail += f", plus {width:g}-pt middle"
            out.append({**self._base(market), "type": "ARB", "edge": round(profit, 4),
                        "legs": [self._leg_json(la, market), self._leg_json(lb, market)], "detail": detail})
        if best_mid:
            (width, neg_implied), la, lb, implied = best_mid
            out.append({**self._base(market), "type": "MIDDLE", "edge": width,
                        "legs": [self._leg_json(la, market), self._leg_json(lb, market)],
                        "detail": f"{width:g}-pt window; costs {implied - 1:.2%} if it misses"})
        return out

    @staticmethod
    def _stakes(pa: int, pb: int) -> tuple[float, float]:
        ia, ib = 1 / american_to_decimal(pa), 1 / american_to_decimal(pb)
        return ia / (ia + ib), ib / (ia + ib)

    def _best(self, market: str) -> dict[str, Any]:
        best = {}
        for side in SIDES[market]:
            legs = [s[side] for s in self.legs[market].values() if side in s]
            if not legs:
                continue

            def score(leg: Leg) -> tuple[float, float]:
                if market == H2H or leg.point is None:
                    pts = 0.0
                elif market == SPREADS:
                    pts = leg.point
                else:
                    pts = -leg.point if side == "over" else leg.point
                return pts, american_to_decimal(leg.price)

            top = max(score(l) for l in legs)
            best[side] = sorted(l.book for l in legs if score(l) == top)
        return best


def build_snapshot(games: list[Game], settings: Settings, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    game_rows, opps = [], []
    for game in sorted(games, key=lambda g: (g.commence_time, g.home)):
        row, game_opps = GameAnalyzer(game, settings, now).analyze()
        game_rows.append(row)
        opps.extend(game_opps)
    type_rank = {"ARB": 0, "EV": 1, "OFF_MARKET": 2, "MIDDLE": 3}
    opps.sort(key=lambda o: (type_rank[o["type"]], -o["edge"]))
    book_titles = {}
    for row in game_rows:
        for key, b in row["books"].items():
            book_titles[key] = b["title"]
    return {
        "generated_at": now.isoformat(),
        "books": [{"key": k, "title": book_titles[k]} for k in sorted(book_titles, key=book_titles.get)],
        "games": game_rows,
        "opportunities": opps,
    }
