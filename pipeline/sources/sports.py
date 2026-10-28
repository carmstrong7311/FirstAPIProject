"""Official home-game schedules for Chicago teams via free, keyless league APIs.

These are authoritative for dates/times, so they win over ticket-site listings
when duplicates are merged.
"""

from __future__ import annotations

import logging
from datetime import date

from ..common import Event, fetch, split_local, to_local

NAME = "sports"
log = logging.getLogger(__name__)

MLB_TEAMS = {112: ("Chicago Cubs", "https://www.mlb.com/cubs/tickets"),
             145: ("Chicago White Sox", "https://www.mlb.com/whitesox/tickets")}

# ESPN site API: (sport, league, team name match, sub-filter, team page)
ESPN_TEAMS = [
    ("football", "nfl", "Chicago Bears", "Football", "https://www.chicagobears.com/tickets/"),
    ("basketball", "nba", "Chicago Bulls", "Basketball", "https://www.nba.com/bulls/tickets"),
    ("basketball", "wnba", "Chicago Sky", "Basketball", "https://sky.wnba.com/tickets/"),
    ("soccer", "usa.1", "Chicago Fire", "Soccer", "https://www.chicagofirefc.com/tickets/"),
    ("soccer", "usa.nwsl", "Chicago", "Soccer", "https://chicagostarsfc.com/tickets/"),
    ("football", "college-football", "Northwestern Wildcats", "Football", "https://nusports.com/tickets"),
    ("basketball", "mens-college-basketball", "Northwestern Wildcats", "Basketball", "https://nusports.com/tickets"),
    ("basketball", "mens-college-basketball", "DePaul Blue Demons", "Basketball", "https://depaulbluedemons.com/tickets"),
    ("basketball", "mens-college-basketball", "Loyola Chicago Ramblers", "Basketball", "https://loyolaramblers.com/tickets"),
    ("basketball", "womens-college-basketball", "DePaul Blue Demons", "Basketball", "https://depaulbluedemons.com/tickets"),
    ("basketball", "womens-college-basketball", "Northwestern Wildcats", "Basketball", "https://nusports.com/tickets"),
]

ESPN = "https://site.api.espn.com/apis/site/v2/sports"


def enabled() -> bool:
    return True


def collect(start: date, end: date) -> list[Event]:
    events: list[Event] = []
    for fn in (_mlb, _nhl, _espn):
        try:
            events.extend(fn(start, end))
        except Exception as e:  # one league failing shouldn't sink the rest
            log.warning("sports/%s failed: %s", fn.__name__, e)
    return [e for e in events if start.isoformat() <= e.date <= end.isoformat()]


# ------------------------------------------------------------------------- MLB


def _mlb(start: date, end: date) -> list[Event]:
    out = []
    for team_id, (team, tickets) in MLB_TEAMS.items():
        data = fetch("https://statsapi.mlb.com/api/v1/schedule", {
            "sportId": 1, "teamId": team_id, "startDate": start.isoformat(), "endDate": end.isoformat(),
            "gameType": "R,F,D,L,W",
        })
        for d in data.get("dates", []):
            for g in d.get("games", []):
                out.extend(_mlb_game(g, team_id, team, tickets))
    return out


def _mlb_game(g: dict, team_id: int, team: str, tickets: str) -> list[Event]:
    home, away = g["teams"]["home"]["team"], g["teams"]["away"]["team"]
    if home.get("id") != team_id or g.get("status", {}).get("detailedState") in ("Postponed", "Cancelled"):
        return []
    local_date, local_time = split_local(to_local(g["gameDate"]))
    if g.get("status", {}).get("startTimeTBD"):
        local_time = None
    label = {"F": "Wild Card: ", "D": "Division Series: ", "L": "LCS: ", "W": "World Series: "}.get(g.get("gameType"), "")
    return [Event(
        title=f"{label}{away['name']} at {team}",
        category="sports", subcategory="Baseball",
        date=g.get("officialDate", local_date), time=local_time,
        venue=g.get("venue", {}).get("name"), city="Chicago",
        url=tickets, ticket_url=tickets, source=NAME,
    )]


# ------------------------------------------------------------------------- NHL


def _nhl(start: date, end: date) -> list[Event]:
    out = []
    for season in (f"{y}{y + 1}" for y in range(start.year - 1, end.year + 1)):
        try:
            data = fetch(f"https://api-web.nhle.com/v1/club-schedule-season/CHI/{season}")
        except RuntimeError as e:
            log.info("NHL season %s unavailable: %s", season, e)
            continue
        for g in data.get("games", []):
            if g.get("homeTeam", {}).get("abbrev") != "CHI" or g.get("gameType") not in (2, 3):
                continue
            local_date, local_time = split_local(to_local(g["startTimeUTC"]))
            away = g.get("awayTeam", {})
            away_name = " ".join(filter(None, [(away.get("placeName") or {}).get("default"),
                                               (away.get("commonName") or {}).get("default")])) or away.get("abbrev", "")
            prefix = "Playoffs: " if g.get("gameType") == 3 else ""
            out.append(Event(
                title=f"{prefix}{away_name} at Chicago Blackhawks",
                category="sports", subcategory="Hockey",
                date=local_date, time=None if g.get("gameScheduleState") == "TBD" else local_time,
                venue=(g.get("venue") or {}).get("default", "United Center"), city="Chicago",
                url="https://www.nhl.com/blackhawks/tickets", ticket_url="https://www.nhl.com/blackhawks/tickets",
                source=NAME,
            ))
    return out


# ------------------------------------------------------------------------ ESPN


def _espn_team_id(sport: str, league: str, match: str) -> str | None:
    data = fetch(f"{ESPN}/{sport}/{league}/teams", {"limit": 1000})
    for entry in data.get("sports", [{}])[0].get("leagues", [{}])[0].get("teams", []):
        t = entry.get("team", {})
        if t.get("displayName", "").startswith(match) or t.get("location") == match:
            return t.get("id")
    return None


def _espn(start: date, end: date) -> list[Event]:
    out: list[Event] = []
    for sport, league, match, sub, tickets in ESPN_TEAMS:
        try:
            team_id = _espn_team_id(sport, league, match)
            if not team_id:
                log.warning("ESPN: no team matching %r in %s", match, league)
                continue
            seen: set[str] = set()
            for season in sorted({start.year, end.year}):
                params = {"season": season}
                if league == "nfl" or "college" in league:
                    params["seasontype"] = 2
                try:
                    data = fetch(f"{ESPN}/{sport}/{league}/teams/{team_id}/schedule", params)
                except RuntimeError:
                    continue
                for ev in data.get("events", []):
                    if ev.get("id") in seen:
                        continue
                    seen.add(ev.get("id"))
                    e = _espn_event(ev, team_id, sub, tickets)
                    if e:
                        out.append(e)
        except Exception as e:
            log.warning("ESPN %s/%s failed: %s", league, match, e)
    return out


def _espn_event(ev: dict, team_id: str, sub: str, tickets: str) -> Event | None:
    comp = (ev.get("competitions") or [{}])[0]
    competitors = comp.get("competitors", [])
    home = next((c for c in competitors if c.get("homeAway") == "home"), None)
    away = next((c for c in competitors if c.get("homeAway") == "away"), None)
    if not home or not away or str(home.get("team", {}).get("id")) != str(team_id):
        return None
    status = (comp.get("status") or {}).get("type", {})
    if status.get("name") in ("STATUS_POSTPONED", "STATUS_CANCELED"):
        return None
    venue = comp.get("venue") or {}
    address = venue.get("address") or {}
    # Neutral-site "home" games far from Chicago (e.g., London) are skipped.
    if address.get("state") and address.get("state") not in ("IL", "Illinois", "IN", "WI"):
        return None
    local_date, local_time = split_local(to_local(ev["date"]))
    return Event(
        title=f"{away['team'].get('displayName')} at {home['team'].get('displayName')}",
        category="sports", subcategory=sub,
        date=local_date, time=None if comp.get("timeValid") is False else local_time,
        venue=venue.get("fullName"), city=address.get("city"),
        url=tickets, ticket_url=tickets, source=NAME,
    )
