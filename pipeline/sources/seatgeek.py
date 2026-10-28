"""SeatGeek Platform API (fills gaps: AXS venues, smaller clubs, resale-only listings).

Free client id: https://seatgeek.com/account/develop -> set SEATGEEK_CLIENT_ID.
"""

from __future__ import annotations

import os
import time
from datetime import date

from ..classify import is_junk, seatgeek_category
from ..common import CHICAGO_LATLON, RADIUS_MILES, Event, fetch

NAME = "seatgeek"
API = "https://api.seatgeek.com/2/events"
PER_PAGE = 500
MAX_PAGES = 40


def enabled() -> bool:
    return bool(os.environ.get("SEATGEEK_CLIENT_ID"))


def collect(start: date, end: date) -> list[Event]:
    events: list[Event] = []
    for page in range(1, MAX_PAGES + 1):
        data = fetch(API, {
            "client_id": os.environ["SEATGEEK_CLIENT_ID"],
            "lat": CHICAGO_LATLON[0],
            "lon": CHICAGO_LATLON[1],
            "range": f"{RADIUS_MILES}mi",
            "datetime_local.gte": start.isoformat(),
            "datetime_local.lte": f"{end.isoformat()}T23:59:59",
            "sort": "datetime_local.asc",
            "per_page": PER_PAGE,
            "page": page,
        })
        batch = data.get("events", [])
        events.extend(e for e in (parse(r) for r in batch) if e)
        total = data.get("meta", {}).get("total", 0)
        if not batch or page * PER_PAGE >= total:
            break
        time.sleep(0.25)
    return events


def parse(ev: dict) -> Event | None:
    title = ev.get("title") or ev.get("short_title") or ""
    if is_junk(title) or ev.get("date_tbd") or not ev.get("datetime_local"):
        return None
    cat = seatgeek_category([t.get("name", "") for t in ev.get("taxonomies") or []], title)
    if not cat:
        return None
    local_date, local_time = ev["datetime_local"][:10], ev["datetime_local"][11:16]
    venue = ev.get("venue") or {}
    performer = (ev.get("performers") or [{}])[0]
    lowest = (ev.get("stats") or {}).get("lowest_price")
    return Event(
        title=title,
        category=cat[0],
        subcategory=cat[1],
        date=local_date,
        time=None if ev.get("time_tbd") else local_time,
        venue=venue.get("name"),
        city=venue.get("city"),
        url=ev.get("url"),
        ticket_url=ev.get("url"),
        price=f"From ${lowest:,.0f}" if isinstance(lowest, (int, float)) else None,
        image=performer.get("image"),
        source=NAME,
    )
