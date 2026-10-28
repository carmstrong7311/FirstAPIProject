"""Shared event model, HTTP helper, and normalization utilities."""

from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

CHICAGO_TZ = ZoneInfo("America/Chicago")
CHICAGO_LATLON = (41.8781, -87.6298)
RADIUS_MILES = 40

# Category keys used by the site. Order here is the order of the filter chips.
CATEGORIES = {
    "sports": "Sports",
    "concerts": "Concerts",
    "comedy": "Comedy",
    "theater": "Theater & Performing Arts",
    "festivals": "Festivals & Street Fests",
    "holiday": "Holiday & Seasonal",
    "family_food_expos": "Family, Food & Expos",
}

USER_AGENT = "ChicagolandEventsBot/1.0 (+https://github.com/carmstrong7311/firstapiproject)"


@dataclass
class Event:
    title: str
    category: str
    date: str  # local Chicago date, YYYY-MM-DD
    source: str
    time: str | None = None  # local Chicago time, HH:MM
    end_date: str | None = None  # last day, YYYY-MM-DD, for multi-day events
    subcategory: str | None = None
    venue: str | None = None
    neighborhood: str | None = None
    city: str | None = None
    url: str | None = None
    ticket_url: str | None = None
    price: str | None = None
    image: str | None = None
    confirmed: bool = True
    date_note: str | None = None
    performances: int | None = None  # set when several shows were collapsed into one run
    sources: list[str] = field(default_factory=list)
    id: str = ""

    def __post_init__(self) -> None:
        if self.category not in CATEGORIES:
            raise ValueError(f"unknown category {self.category!r} for {self.title!r}")
        self.title = clean_text(self.title)
        if not self.sources:
            self.sources = [self.source]
        if not self.id:
            key = f"{norm_title(self.title)}|{self.date}|{norm_venue(self.venue)}"
            self.id = hashlib.sha1(key.encode()).hexdigest()[:12]

    @property
    def last_date(self) -> str:
        return self.end_date or self.date

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("source")
        return {k: v for k, v in d.items() if v not in (None, [], "")}

    @classmethod
    def from_dict(cls, d: dict) -> "Event":
        d = dict(d)
        d.setdefault("source", (d.get("sources") or ["cache"])[0])
        return cls(**d)


# --------------------------------------------------------------------------- HTTP


def fetch(url: str, params: dict | None = None, *, as_json: bool = True, retries: int = 3,
          headers: dict | None = None, timeout: int = 30):
    """GET a URL with retries/backoff. Returns parsed JSON or text."""
    if params:
        url = f"{url}{'&' if '?' in url else '?'}{urllib.parse.urlencode(params)}"
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json" if as_json else "text/html,*/*"}
    hdrs.update(headers or {})
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode(resp.headers.get_content_charset() or "utf-8", "replace")
            return json.loads(body) if as_json else body
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code not in (429, 500, 502, 503, 504):
                break
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            last_err = e
        time.sleep(2 ** attempt)
    raise RuntimeError(f"fetch failed for {redact(url)}: {last_err}")


def redact(url: str) -> str:
    return re.sub(r"(apikey|client_id|client_secret)=[^&]+", r"\1=***", url)


# ------------------------------------------------------------------- normalization


def clean_text(s: str | None) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


_STOP = {"the", "a", "an", "vs", "v", "at", "and", "&", "with", "presents", "live", "in", "of",
         "tour", "show", "concert", "chicago"}


def title_tokens(title: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", title.lower())
    return {w for w in words if w not in _STOP}


def norm_title(title: str) -> str:
    return " ".join(sorted(title_tokens(title)))


_VENUE_ALIASES = {
    "guaranteed rate field": "rate field",
    "chicago white sox ballpark": "rate field",
    "the chicago theatre": "chicago theatre",
    "wintrust arena at mccormick square": "wintrust arena",
    "united center chicago": "united center",
    "soldier field stadium": "soldier field",
    "the second city": "second city",
    "second city mainstage": "second city",
}


def norm_venue(venue: str | None) -> str:
    v = re.sub(r"[^a-z0-9 ]", "", (venue or "").lower())
    v = re.sub(r"\s+", " ", v).strip()
    v = re.sub(r"^the ", "", v)
    return _VENUE_ALIASES.get(v, _VENUE_ALIASES.get(f"the {v}", v))


def to_local(dt_str: str) -> datetime:
    """Parse an ISO timestamp (UTC 'Z' or with offset) and convert to Chicago time."""
    dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=CHICAGO_TZ)
    return dt.astimezone(CHICAGO_TZ)


def split_local(dt: datetime) -> tuple[str, str]:
    return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")


def today_chicago() -> date:
    return datetime.now(CHICAGO_TZ).date()


def window(days: int = 365) -> tuple[date, date]:
    start = today_chicago()
    return start, start + timedelta(days=days)
