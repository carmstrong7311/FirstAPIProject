"""Hand-curated festivals, street fests, parades and seasonal events.

Edit pipeline/data/curated_events.json to add or correct entries. Entries whose
date hasn't been announced yet carry "confirmed": false and a "date_note"; the
site labels them as estimated.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from ..common import Event

NAME = "curated"
PATH = Path(__file__).resolve().parent.parent / "data" / "curated_events.json"


def enabled() -> bool:
    return PATH.exists()


def collect(start: date, end: date) -> list[Event]:
    events = []
    for row in json.loads(PATH.read_text()):
        start_s, end_s = row["start"], row.get("end")
        ev = Event(
            title=row["title"],
            category=row["category"],
            subcategory=row.get("subcategory"),
            date=start_s[:10],
            time=start_s[11:16] or None,
            end_date=end_s[:10] if end_s and end_s[:10] > start_s[:10] else None,
            venue=row.get("venue"),
            neighborhood=row.get("neighborhood"),
            url=row.get("url"),
            price=row.get("price"),
            confirmed=bool(row.get("confirmed", True)),
            date_note=row.get("date_note"),
            source=NAME,
        )
        if ev.last_date >= start.isoformat() and ev.date <= end.isoformat():
            events.append(ev)
    return events
