"""Scrape venue and organizer calendars that publish schema.org Event data (JSON-LD).

Most venue sites built on common CMS/ticketing platforms embed
<script type="application/ld+json"> Event objects for search engines; reading
those is far more stable than scraping page layout. Pages that render their
calendar purely client-side yield nothing and are simply logged with a 0 count.
Add a venue by appending to VENUES.
"""

from __future__ import annotations

import html
import json
import logging
import re
from datetime import date

from ..classify import is_holiday, is_junk, sport_for, _misc_category
from ..common import Event, clean_text, fetch, split_local, to_local

NAME = "venues"
log = logging.getLogger(__name__)

# (url, default category or "auto", default venue name, neighborhood)
VENUES = [
    # Comedy
    ("https://www.secondcity.com/shows/chicago", "comedy", "The Second City", "Old Town"),
    ("https://chicago.zanies.com/", "comedy", "Zanies Chicago", "Old Town"),
    ("https://www.laughfactory.com/chicago", "comedy", "Laugh Factory Chicago", "Lakeview"),
    ("https://ioimprov.com/shows/", "comedy", "iO Theater", "Goose Island"),
    ("https://www.comedybarchicago.com/", "comedy", "Comedy Bar", "River North"),
    # Theater & performing arts
    ("https://www.broadwayinchicago.com/shows/", "theater", None, "Loop"),
    ("https://www.lyricopera.org/shows/upcoming/", "theater", "Lyric Opera House", "Loop"),
    ("https://cso.org/performances/calendar/", "theater", "Symphony Center", "Loop"),
    ("https://www.goodmantheatre.org/season/", "theater", "Goodman Theatre", "Loop"),
    ("https://www.steppenwolf.org/tickets--events/", "theater", "Steppenwolf Theatre", "Lincoln Park"),
    ("https://chicagoshakes.com/plays-and-events/", "theater", "Chicago Shakespeare Theater", "Navy Pier"),
    ("https://joffrey.org/performances/", "theater", "Lyric Opera House", "Loop"),
    ("https://www.auditoriumtheatre.org/events/", "auto", "Auditorium Theatre", "Loop"),
    ("https://www.harristheaterchicago.org/events", "theater", "Harris Theater", "Loop"),
    # Concert halls & clubs
    ("https://metrochicago.com/events", "concerts", "Metro", "Wrigleyville"),
    ("https://www.thaliahallchicago.com/shows", "concerts", "Thalia Hall", "Pilsen"),
    ("https://www.emptybottle.com/", "concerts", "Empty Bottle", "Ukrainian Village"),
    ("https://lh-st.com/", "concerts", None, "Lincoln Park"),
    ("https://www.saltshedchicago.com/events", "concerts", "The Salt Shed", "Goose Island"),
    ("https://www.oldtownschool.org/concerts/", "concerts", "Old Town School of Folk Music", "Lincoln Square"),
    ("https://www.ravinia.org/calendar", "auto", "Ravinia", "Highland Park"),
    ("https://www.citywinery.com/chicago/events", "concerts", "City Winery Chicago", "West Loop"),
    ("https://www.hideoutchicago.com/events", "concerts", "The Hideout", "Goose Island"),
    # Civic / festivals / expos
    ("https://navypier.org/events/", "auto", "Navy Pier", "Streeterville"),
    ("https://www.chicagoparkdistrict.com/events", "auto", None, None),
    ("https://www.choosechicago.com/events/", "auto", None, None),
    ("https://www.mccormickplace.com/events/", "family_food_expos", "McCormick Place", "Near South Side"),
    ("https://www.chicago.gov/city/en/depts/dca/supp_info/events.html", "auto", None, None),
]

_LD_RE = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S | re.I)
_EVENT_TYPES = {"Event", "MusicEvent", "ComedyEvent", "TheaterEvent", "DanceEvent", "SportsEvent", "Festival",
                "FoodEvent", "ChildrensEvent", "ExhibitionEvent", "SocialEvent", "LiteraryEvent",
                "ScreeningEvent", "VisualArtsEvent", "EducationEvent", "BusinessEvent"}
_TYPE_CATEGORY = {"MusicEvent": "concerts", "ComedyEvent": "comedy", "TheaterEvent": "theater",
                  "DanceEvent": "theater", "SportsEvent": "sports", "Festival": "festivals",
                  "FoodEvent": "family_food_expos", "ChildrensEvent": "family_food_expos",
                  "ExhibitionEvent": "family_food_expos", "BusinessEvent": "family_food_expos"}


def enabled() -> bool:
    return True


def collect(start: date, end: date) -> list[Event]:
    events: list[Event] = []
    for url, default_cat, venue, hood in VENUES:
        try:
            page = fetch(url, as_json=False, retries=2, headers={"User-Agent": "Mozilla/5.0 (compatible; ChicagolandEventsBot/1.0)"})
        except Exception as e:
            log.warning("venue %s failed: %s", url, e)
            continue
        found = [ev for ev in parse_page(page, url, default_cat, venue, hood)
                 if start.isoformat() <= ev.last_date and ev.date <= end.isoformat()]
        log.info("venue %s: %d events", url, len(found))
        events.extend(found)
    return events


def parse_page(page: str, page_url: str, default_cat: str, venue: str | None, hood: str | None) -> list[Event]:
    out = []
    for block in _LD_RE.findall(page):
        try:
            data = json.loads(html.unescape(block.strip()))
        except json.JSONDecodeError:
            continue
        for obj in _walk(data):
            ev = _to_event(obj, page_url, default_cat, venue, hood)
            if ev:
                out.append(ev)
    return out


def _walk(data):
    """Yield every dict with an Event @type, descending into @graph, ItemList, lists, subEvent."""
    if isinstance(data, list):
        for d in data:
            yield from _walk(d)
    elif isinstance(data, dict):
        types = data.get("@type")
        types = set(types) if isinstance(types, list) else {types}
        if types & _EVENT_TYPES:
            yield data
        for key in ("@graph", "itemListElement", "item", "subEvent", "subEvents", "event", "events"):
            if key in data:
                yield from _walk(data[key])


def _parse_dt(s: str | None) -> tuple[str | None, str | None]:
    if not s or not isinstance(s, str):
        return None, None
    s = s.strip()
    if len(s) == 10:
        return s, None
    try:
        if re.search(r"(Z|[+-]\d\d:?\d\d)$", s):
            return split_local(to_local(s))
        return s[:10], s[11:16] or None
    except ValueError:
        return None, None


def _to_event(obj: dict, page_url: str, default_cat: str, venue: str | None, hood: str | None) -> Event | None:
    title = clean_text(html.unescape(str(obj.get("name") or "")))
    if not title or is_junk(title):
        return None
    status = str(obj.get("eventStatus", ""))
    if "Cancelled" in status or "Postponed" in status:
        return None
    start_date, start_time = _parse_dt(obj.get("startDate"))
    if not start_date:
        return None
    end_date, _ = _parse_dt(obj.get("endDate"))

    loc = obj.get("location")
    loc = loc[0] if isinstance(loc, list) and loc else loc
    loc_name = clean_text(html.unescape(loc.get("name", ""))) if isinstance(loc, dict) else None
    addr = loc.get("address") if isinstance(loc, dict) else None
    city = addr.get("addressLocality") if isinstance(addr, dict) else None

    category, sub = _category(obj, title, default_cat)
    offers = obj.get("offers")
    offers = offers[0] if isinstance(offers, list) and offers else offers
    price = None
    if isinstance(offers, dict):
        p = offers.get("price") or offers.get("lowPrice")
        try:
            price = "Free" if float(p) == 0 else f"From ${float(p):,.0f}"
        except (TypeError, ValueError):
            pass
    image = obj.get("image")
    if isinstance(image, list):
        image = image[0] if image else None
    if isinstance(image, dict):
        image = image.get("url")
    url = obj.get("url") if isinstance(obj.get("url"), str) else page_url
    return Event(
        title=title, category=category, subcategory=sub,
        date=start_date, time=start_time,
        end_date=end_date if end_date and end_date > start_date else None,
        venue=loc_name or venue, neighborhood=hood, city=city,
        url=url, price=price, image=image if isinstance(image, str) else None,
        source=NAME,
    )


def _category(obj: dict, title: str, default_cat: str) -> tuple[str, str | None]:
    types = obj.get("@type")
    types = types if isinstance(types, list) else [types]
    typed = next((_TYPE_CATEGORY[t] for t in types if t in _TYPE_CATEGORY), None)
    cat = default_cat if default_cat != "auto" else typed
    if cat == "sports":
        return "sports", sport_for(title)
    if cat in (None, "theater", "family_food_expos", "festivals") and is_holiday(title):
        return "holiday", None
    if cat:
        return cat, None
    return _misc_category(title, None) or ("family_food_expos", None)
