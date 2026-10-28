"""Ticketmaster Discovery API (covers most arenas, theaters and clubs, incl. Live Nation venues).

Free key: https://developer.ticketmaster.com/ -> set TICKETMASTER_API_KEY.
Deep paging is capped at 1,000 results per query, so the date window is split
recursively until each slice fits.
"""

from __future__ import annotations

import os
import time
from datetime import date, datetime, timedelta

from ..classify import is_junk, ticketmaster_category
from ..common import CHICAGO_LATLON, RADIUS_MILES, Event, fetch

NAME = "ticketmaster"
API = "https://app.ticketmaster.com/discovery/v2/events.json"
PAGE_SIZE = 200
MAX_DEEP = 1000


def enabled() -> bool:
    return bool(os.environ.get("TICKETMASTER_API_KEY"))


def collect(start: date, end: date) -> list[Event]:
    raw: list[dict] = []
    _collect_range(start, end, raw)
    events = [e for e in (parse(r) for r in raw) if e]
    return events


def _query(start: date, end: date, page: int) -> dict:
    time.sleep(0.25)  # stay under 5 req/s
    return fetch(API, {
        "apikey": os.environ["TICKETMASTER_API_KEY"],
        "latlong": f"{CHICAGO_LATLON[0]},{CHICAGO_LATLON[1]}",
        "radius": RADIUS_MILES,
        "unit": "miles",
        "locale": "*",
        "size": PAGE_SIZE,
        "page": page,
        "sort": "date,asc",
        "startDateTime": f"{start.isoformat()}T00:00:00Z",
        "endDateTime": f"{end.isoformat()}T23:59:59Z",
    })


def _collect_range(start: date, end: date, out: list[dict]) -> None:
    first = _query(start, end, 0)
    total = first.get("page", {}).get("totalElements", 0)
    if total > MAX_DEEP and end > start:
        mid = start + (end - start) / 2
        _collect_range(start, mid, out)
        _collect_range(mid + timedelta(days=1), end, out)
        return
    out.extend(first.get("_embedded", {}).get("events", []))
    pages = min(first.get("page", {}).get("totalPages", 1), MAX_DEEP // PAGE_SIZE)
    for p in range(1, pages):
        out.extend(_query(start, end, p).get("_embedded", {}).get("events", []))


def parse(ev: dict) -> Event | None:
    name = ev.get("name", "")
    dates = ev.get("dates", {})
    if dates.get("status", {}).get("code") in ("cancelled", "canceled", "offsale") or is_junk(name):
        return None
    start = dates.get("start", {})
    local_date = start.get("localDate")
    if not local_date or start.get("dateTBA") or start.get("dateTBD"):
        return None
    cls = (ev.get("classifications") or [{}])[0]
    cat = ticketmaster_category(cls.get("segment", {}).get("name", ""), cls.get("genre", {}).get("name", ""),
                                cls.get("subGenre", {}).get("name", ""), name)
    if not cat:
        return None
    venue = (ev.get("_embedded", {}).get("venues") or [{}])[0]
    local_time = None if start.get("timeTBA") or start.get("noSpecificTime") else (start.get("localTime") or "")[:5] or None
    end_local = (dates.get("end") or {}).get("localDate")
    return Event(
        title=name,
        category=cat[0],
        subcategory=cat[1],
        date=local_date,
        time=local_time,
        end_date=end_local if end_local and end_local > local_date else None,
        venue=venue.get("name"),
        city=(venue.get("city") or {}).get("name"),
        url=ev.get("url"),
        ticket_url=ev.get("url"),
        price=_price(ev),
        image=_image(ev),
        source=NAME,
    )


def _price(ev: dict) -> str | None:
    ranges = ev.get("priceRanges") or []
    mins = [r["min"] for r in ranges if isinstance(r.get("min"), (int, float))]
    if not mins:
        return None
    return "Free" if min(mins) == 0 else f"From ${min(mins):,.0f}"


def _image(ev: dict) -> str | None:
    imgs = [i for i in ev.get("images") or [] if i.get("ratio") == "16_9" and 400 <= i.get("width", 0) <= 800]
    return imgs[0]["url"] if imgs else None


if __name__ == "__main__":  # manual smoke test
    import json
    s = datetime.now().date()
    print(json.dumps([e.to_dict() for e in collect(s, s + timedelta(days=3))][:5], indent=2))
