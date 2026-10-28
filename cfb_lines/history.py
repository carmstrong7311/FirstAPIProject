"""Line-movement tracking, in memory and optionally in SQLite."""

from __future__ import annotations

import sqlite3
from collections import deque
from datetime import datetime
from typing import Any

from .models import Game

SCHEMA = """
CREATE TABLE IF NOT EXISTS line_moves (
    observed_at TEXT NOT NULL,
    game_id TEXT NOT NULL,
    matchup TEXT NOT NULL,
    commence_time TEXT NOT NULL,
    book TEXT NOT NULL,
    market TEXT NOT NULL,
    side TEXT NOT NULL,
    point REAL,
    price INTEGER NOT NULL,
    book_updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS line_moves_game ON line_moves (game_id, market, book);
"""


class LineHistory:
    def __init__(self, db_path: str = "", max_recent: int = 300, per_key: int = 30):
        self.last: dict[tuple[str, str, str, str], tuple[float | None, int]] = {}
        self.series: dict[tuple[str, str, str, str], deque] = {}
        self.recent: deque[dict[str, Any]] = deque(maxlen=max_recent)
        self.per_key = per_key
        self.db = sqlite3.connect(db_path, check_same_thread=False) if db_path else None
        if self.db:
            self.db.executescript(SCHEMA)

    def record(self, games: list[Game], observed_at: datetime) -> list[dict[str, Any]]:
        """Store every quote that changed since the last poll; return the moves."""
        moves, rows = [], []
        for g in games:
            matchup = f"{g.away} @ {g.home}"
            for q in g.quotes:
                key = (g.id, q.book, q.market, q.side)
                current = (q.point, q.price)
                previous = self.last.get(key)
                if previous == current:
                    continue
                self.last[key] = current
                self.series.setdefault(key, deque(maxlen=self.per_key)).append(
                    {"t": observed_at.isoformat(), "point": q.point, "price": q.price}
                )
                rows.append((observed_at.isoformat(), g.id, matchup, g.commence_time.isoformat(),
                             q.book, q.market, q.side, q.point, q.price, q.last_update.isoformat()))
                if previous is None:
                    continue  # first sighting is not a move
                move = {
                    "t": observed_at.isoformat(),
                    "game_id": g.id,
                    "matchup": matchup,
                    "book": q.book,
                    "book_title": q.book_title,
                    "market": q.market,
                    "side": q.side,
                    "from": {"point": previous[0], "price": previous[1]},
                    "to": {"point": q.point, "price": q.price},
                }
                moves.append(move)
                self.recent.appendleft(move)
        if self.db and rows:
            self.db.executemany("INSERT INTO line_moves VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
            self.db.commit()
        return moves

    def for_game(self, game_id: str) -> list[dict[str, Any]]:
        return [
            {"book": b, "market": m, "side": s, "points": list(series)}
            for (gid, b, m, s), series in self.series.items()
            if gid == game_id
        ]
