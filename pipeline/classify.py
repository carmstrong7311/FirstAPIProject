"""Map source-specific genres/taxonomies onto the site's categories and sport sub-filters."""

from __future__ import annotations

import re

# Canonical sport sub-filters, matched by keyword against genre names / titles.
_SPORT_KEYWORDS = [
    ("Baseball", r"baseball|\bmlb\b|softball"),
    ("Basketball", r"basketball|\bnba\b|\bwnba\b|\bncaab\b"),
    ("Football", r"(?<!australian )football(?! club)|\bnfl\b|\bncaaf\b"),
    ("Hockey", r"hockey|\bnhl\b|\bahl\b"),
    ("Soccer", r"soccer|\bmls\b|\bnwsl\b|futbol|\bfc\b"),
    ("Combat Sports", r"boxing|wrestling|\bwwe\b|\baew\b|\bufc\b|mixed martial|\bmma\b"),
    ("Motorsports", r"motorsport|nascar|racing|monster jam|supercross|motocross|indycar"),
    ("Tennis", r"tennis"),
    ("Golf", r"golf|\bpga\b|\blpga\b"),
    ("Running", r"marathon|half marathon|\b5k\b|\b10k\b|\b15k\b|shamrock shuffle|turkey trot"),
    ("Volleyball", r"volleyball"),
    ("Rugby", r"rugby"),
    ("Lacrosse", r"lacrosse"),
    ("Rodeo", r"rodeo|\bpbr\b|bull riding"),
]


def sport_for(*texts: str | None) -> str:
    blob = " ".join(t for t in texts if t).lower()
    for name, pattern in _SPORT_KEYWORDS:
        if re.search(pattern, blob):
            return name
    return "Other Sports"


_HOLIDAY = re.compile(
    r"christmas|holiday|santa|nutcracker|hanukkah|kwanzaa|new year'?s|\bnye\b|halloween|"
    r"haunted|thanksgiving|christkindl|tree lighting|lights festival|zoo ?lights|lightscape|"
    r"st\.? patrick|easter|winter ?wonder", re.I)
_FESTIVAL = re.compile(r"\bfest(ival)?\b|\bfair\b|street fest|block party|parade", re.I)
_EXPO = re.compile(r"\bexpo\b|convention|\bshow\b.*(auto|boat|home|garden|travel)|auto show|"
                   r"comic con|\bc2e2\b|\bcon\b", re.I)
_FOOD = re.compile(r"food|taste of|wine|beer|brew|culinary|gourmet|tasting", re.I)


def is_holiday(title: str) -> bool:
    return bool(_HOLIDAY.search(title))


def ticketmaster_category(segment: str, genre: str, subgenre: str, title: str) -> tuple[str, str | None] | None:
    """Return (category, subcategory) for a Ticketmaster classification, or None to drop it."""
    seg, gen, sub = (segment or "").lower(), (genre or "").lower(), (subgenre or "").lower()
    if seg == "sports":
        return "sports", sport_for(genre, subgenre, title)
    if seg == "music":
        if _FESTIVAL.search(title) and "fest" in title.lower():
            return "festivals", "Music Festival"
        return "concerts", genre if genre and genre.lower() not in ("undefined", "other") else None
    if seg == "arts & theatre":
        if "comedy" in (gen, sub) or "comedy" in gen:
            return "comedy", subgenre if sub not in ("", "undefined", "comedy") else None
        if is_holiday(title):
            return "holiday", "Holiday Show"
        return "theater", _theater_sub(gen, sub)
    if seg in ("family", "miscellaneous", "film", ""):
        return _misc_category(title, genre)
    return None


def _theater_sub(gen: str, sub: str) -> str | None:
    blob = f"{gen} {sub}"
    for label, kw in (("Opera", "opera"), ("Classical", "classical"), ("Dance & Ballet", "dance"),
                      ("Dance & Ballet", "ballet"), ("Musical", "musical"), ("Magic & Illusion", "magic"),
                      ("Circus", "circus"), ("Play", "theatre"), ("Play", "theater")):
        if kw in blob:
            return label
    return None


def _misc_category(title: str, genre: str | None) -> tuple[str, str | None] | None:
    if is_holiday(title):
        return "holiday", None
    if _FESTIVAL.search(title):
        return "festivals", None
    if _EXPO.search(title):
        return "family_food_expos", "Expo & Convention"
    if _FOOD.search(title):
        return "family_food_expos", "Food & Drink"
    return "family_food_expos", "Family" if genre and "family" in genre.lower() else None


# SeatGeek taxonomy names -> category
def seatgeek_category(taxonomies: list[str], title: str) -> tuple[str, str | None] | None:
    names = [t.lower() for t in taxonomies]
    blob = " ".join(names)
    if "sports" in names or any(n in blob for n in ("mlb", "nba", "nfl", "nhl", "mls", "ncaa", "wnba",
                                                     "soccer", "boxing", "wrestling", "racing")):
        return "sports", sport_for(blob, title)
    if "comedy" in blob:
        return "comedy", None
    if "music_festival" in blob:
        return "festivals", "Music Festival"
    if "concert" in blob:
        return "concerts", None
    if any(n in blob for n in ("theater", "broadway", "classical", "opera", "dance", "cirque")):
        if is_holiday(title):
            return "holiday", "Holiday Show"
        return "theater", _theater_sub(blob, "")
    if "parking" in blob:
        return None
    return _misc_category(title, blob)


# Ticket-site listings that aren't actual events.
_JUNK = re.compile(
    r"\bparking\b|\bsuite\b|gift card|\bupgrade\b|season ticket|\bvoucher\b|add-?on|"
    r"\bpremium seating\b|\bhospitality\b|\bmembership\b|\btailgate pass\b|\bshuttle\b|"
    r"\bcoat check\b|\bdeposit\b|\bpackage\b.*\b(vip|hotel)\b|\bmeet ?(&|and) ?greet\b|\btest event\b", re.I)


def is_junk(title: str) -> bool:
    return bool(_JUNK.search(title))
