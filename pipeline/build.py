"""Collect events from every source, merge duplicates, and write site/data/events.json.

Run:  python -m pipeline.build
Env:  TICKETMASTER_API_KEY, SEATGEEK_CLIENT_ID (optional; sources without keys are skipped)

Each source's last good result is cached in pipeline/cache/, so a source that
is down on a given day falls back to its previous data instead of vanishing.
"""

from __future__ import annotations

import json
import logging
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

from .common import CATEGORIES, Event, norm_title, norm_venue, title_tokens, window
from .sources import curated, seatgeek, sports, ticketmaster, venues

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "pipeline" / "cache"
OUTPUT = ROOT / "site" / "data" / "events.json"

# Earlier = more authoritative when duplicates are merged.
SOURCES = [sports, curated, ticketmaster, venues, seatgeek]
PRIORITY = {s.NAME: i for i, s in enumerate(SOURCES)}

RUN_CATEGORIES = {"theater", "comedy", "family_food_expos", "holiday"}
MIN_RUN = 3

log = logging.getLogger("build")


# ----------------------------------------------------------------- collection


def run_source(src, start: date, end: date) -> tuple[list[Event], dict]:
    cache = CACHE_DIR / f"{src.NAME}.json"
    if src.enabled():
        try:
            events = src.collect(start, end)
            if events or not cache.exists():
                now = datetime.now(timezone.utc).isoformat(timespec="seconds")
                cache.write_text(json.dumps({"fetched_at": now, "events": [e.to_dict() for e in events]}, indent=1))
                return events, {"status": "ok", "count": len(events), "fetched_at": now}
            raise RuntimeError("returned 0 events")
        except Exception as e:
            log.warning("%s failed (%s); falling back to cache", src.NAME, e)
    elif not cache.exists():
        return [], {"status": "disabled", "count": 0}
    if not cache.exists():
        return [], {"status": "error", "count": 0}
    data = json.loads(cache.read_text())
    events = [Event.from_dict(d) for d in data["events"]]
    events = [e for e in events if e.last_date >= start.isoformat() and e.date <= end.isoformat()]
    status = "cached" if src.enabled() else "cached (source disabled)"
    return events, {"status": status, "count": len(events), "fetched_at": data.get("fetched_at")}


# -------------------------------------------------------------------- merging


def _same_venue(a: Event, b: Event) -> bool:
    va, vb = norm_venue(a.venue), norm_venue(b.venue)
    return not va or not vb or va == vb or va in vb or vb in va


def is_duplicate(a: Event, b: Event) -> bool:
    if a.date != b.date or not _same_venue(a, b):
        return False
    ta, tb = title_tokens(a.title), title_tokens(b.title)
    if not ta or not tb:
        return False
    overlap = len(ta & tb) / len(ta | tb)
    if overlap >= 0.5 or (len(ta & tb) >= 2 and (ta <= tb or tb <= ta)):
        return True
    # Same-day game at the same stadium: ticket sites word matchups differently.
    both_sports = a.category == b.category == "sports" and a.subcategory == b.subcategory
    return both_sports and bool(norm_venue(a.venue)) and norm_venue(a.venue) == norm_venue(b.venue) and bool(ta & tb)


def merge(events: list[Event]) -> list[Event]:
    events = sorted(events, key=lambda e: PRIORITY.get(e.source, 99))
    by_date: dict[str, list[Event]] = defaultdict(list)
    for ev in events:
        match = next((k for k in by_date[ev.date] if is_duplicate(k, ev)), None)
        if not match:
            by_date[ev.date].append(ev)
            continue
        for attr in ("time", "end_date", "ticket_url", "price", "image", "venue", "city", "neighborhood", "url"):
            if not getattr(match, attr) and getattr(ev, attr):
                setattr(match, attr, getattr(ev, attr))
        if ev.source == "ticketmaster" and ev.ticket_url:
            match.ticket_url = ev.ticket_url  # direct buy link beats a team landing page
        if ev.source not in match.sources:
            match.sources.append(ev.source)
    return [e for day in by_date.values() for e in day]


def collapse_runs(events: list[Event]) -> list[Event]:
    """Turn a show with many performances (e.g. a Broadway run) into one entry spanning its dates."""
    groups: dict[tuple, list[Event]] = defaultdict(list)
    keep: list[Event] = []
    for ev in events:
        if ev.category in RUN_CATEGORIES and not ev.end_date:
            groups[(ev.category, norm_title(ev.title), norm_venue(ev.venue))].append(ev)
        else:
            keep.append(ev)
    for group in groups.values():
        dates = sorted({e.date for e in group})
        if len(dates) < MIN_RUN:
            keep.extend(group)
            continue
        first = min(group, key=lambda e: (e.date, e.time or ""))
        first.end_date = dates[-1]
        first.performances = len(group)
        first.time = None
        for e in group:
            for s in e.sources:
                if s not in first.sources:
                    first.sources.append(s)
            for attr in ("ticket_url", "price", "image"):
                if not getattr(first, attr) and getattr(e, attr):
                    setattr(first, attr, getattr(e, attr))
        keep.append(first)
    return keep


# ---------------------------------------------------------------------- main


def build() -> dict:
    start, end = window(365)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    all_events: list[Event] = []
    status = {}
    for src in SOURCES:
        evs, st = run_source(src, start, end)
        log.info("%-13s %-25s %5d events", src.NAME, st["status"], st["count"])
        status[src.NAME] = st
        all_events.extend(evs)

    events = collapse_runs(merge(all_events))
    events.sort(key=lambda e: (e.date, e.time or "99:99", e.title.lower()))
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "categories": CATEGORIES,
        "sources": status,
        "events": [e.to_dict() for e in events],
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    out = build()
    if not out["events"]:
        log.error("no events collected; leaving existing %s untouched", OUTPUT)
        return 1
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(out, separators=(",", ":")))
    log.info("wrote %d events to %s", len(out["events"]), OUTPUT.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
