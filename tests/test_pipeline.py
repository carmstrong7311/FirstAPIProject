"""Offline tests for parsing, classification and merging. Run: python -m unittest discover tests"""

import unittest

from pipeline.build import collapse_runs, merge
from pipeline.classify import is_junk, sport_for, ticketmaster_category
from pipeline.common import Event
from pipeline.sources import seatgeek, sports, ticketmaster, venues

TM_EVENT = {
    "name": "Chicago Cubs vs. St. Louis Cardinals",
    "url": "https://www.ticketmaster.com/event/123",
    "dates": {"start": {"localDate": "2027-04-09", "localTime": "13:20:00"}, "status": {"code": "onsale"}},
    "classifications": [{"segment": {"name": "Sports"}, "genre": {"name": "Baseball"}, "subGenre": {"name": "MLB"}}],
    "_embedded": {"venues": [{"name": "Wrigley Field", "city": {"name": "Chicago"}}]},
    "priceRanges": [{"min": 24.0, "max": 300.0}],
}

MLB_GAME = {
    "gameDate": "2027-04-09T18:20:00Z", "officialDate": "2027-04-09", "gameType": "R",
    "status": {"detailedState": "Scheduled"},
    "teams": {"home": {"team": {"id": 112, "name": "Chicago Cubs"}},
              "away": {"team": {"id": 138, "name": "St. Louis Cardinals"}}},
    "venue": {"name": "Wrigley Field"},
}

ESPN_EVENT = {
    "id": "1", "date": "2026-11-15T18:00Z",
    "competitions": [{
        "venue": {"fullName": "Soldier Field", "address": {"city": "Chicago", "state": "IL"}},
        "competitors": [
            {"homeAway": "home", "team": {"id": "3", "displayName": "Chicago Bears"}},
            {"homeAway": "away", "team": {"id": "9", "displayName": "Green Bay Packers"}},
        ],
        "status": {"type": {"name": "STATUS_SCHEDULED"}},
    }],
}

VENUE_HTML = """
<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@graph":[
 {"@type":"ComedyEvent","name":"Second City&#39;s Holiday Revue","startDate":"2026-12-04T19:00:00-06:00",
  "location":{"@type":"Place","name":"UP Comedy Club","address":{"addressLocality":"Chicago"}},
  "offers":{"price":"39.00"},"url":"https://www.secondcity.com/shows/x"},
 {"@type":"Event","name":"Parking Pass","startDate":"2026-12-04"},
 {"@type":"Organization","name":"The Second City"}
]}
</script></head></html>
"""


class ClassifyTests(unittest.TestCase):
    def test_sports(self):
        self.assertEqual(sport_for("NBA Basketball"), "Basketball")
        self.assertEqual(sport_for("Chicago Fire FC vs Inter Miami"), "Soccer")
        self.assertEqual(sport_for("WWE Monday Night Raw"), "Combat Sports")
        self.assertEqual(sport_for("Bank of America Chicago Marathon"), "Running")

    def test_comedy_and_holiday(self):
        self.assertEqual(ticketmaster_category("Arts & Theatre", "Comedy", "Comedy", "Nate Bargatze")[0], "comedy")
        self.assertEqual(ticketmaster_category("Arts & Theatre", "Theatre", "Ballet", "The Nutcracker")[0], "holiday")
        self.assertEqual(ticketmaster_category("Arts & Theatre", "Theatre", "Musical", "Hamilton"), ("theater", "Musical"))

    def test_junk(self):
        self.assertTrue(is_junk("PARKING: United Center Lot C"))
        self.assertFalse(is_junk("Chicago Bulls vs. Boston Celtics"))


class SourceParseTests(unittest.TestCase):
    def test_ticketmaster(self):
        e = ticketmaster.parse(TM_EVENT)
        self.assertEqual((e.category, e.subcategory, e.date, e.time), ("sports", "Baseball", "2027-04-09", "13:20"))
        self.assertEqual(e.price, "From $24")

    def test_mlb_home_only(self):
        evs = sports._mlb_game(MLB_GAME, 112, "Chicago Cubs", "x")
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0].time, "13:20")  # 18:20Z -> 1:20 PM CDT
        self.assertEqual(sports._mlb_game(MLB_GAME, 145, "Chicago White Sox", "x"), [])

    def test_espn(self):
        e = sports._espn_event(ESPN_EVENT, "3", "Football", "x")
        self.assertEqual((e.title, e.date, e.time), ("Green Bay Packers at Chicago Bears", "2026-11-15", "12:00"))
        self.assertIsNone(sports._espn_event(ESPN_EVENT, "9", "Football", "x"))

    def test_seatgeek(self):
        e = seatgeek.parse({"title": "Taylor Tomlinson", "datetime_local": "2026-11-20T19:00:00",
                            "taxonomies": [{"name": "comedy"}], "venue": {"name": "Chicago Theatre", "city": "Chicago"},
                            "stats": {"lowest_price": 55}})
        self.assertEqual((e.category, e.time, e.price), ("comedy", "19:00", "From $55"))

    def test_jsonld(self):
        evs = venues.parse_page(VENUE_HTML, "https://www.secondcity.com", "comedy", "The Second City", "Old Town")
        self.assertEqual(len(evs), 1)
        e = evs[0]
        self.assertEqual((e.title, e.category, e.date, e.time, e.venue), (
            "Second City's Holiday Revue", "comedy", "2026-12-04", "19:00", "UP Comedy Club"))


class MergeTests(unittest.TestCase):
    def test_league_and_ticket_listing_merge(self):
        official = sports._mlb_game(MLB_GAME, 112, "Chicago Cubs", "https://www.mlb.com/cubs/tickets")[0]
        tm = ticketmaster.parse(TM_EVENT)
        merged = merge([tm, official])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].title, "St. Louis Cardinals at Chicago Cubs")
        self.assertEqual(merged[0].ticket_url, "https://www.ticketmaster.com/event/123")
        self.assertEqual(set(merged[0].sources), {"sports", "ticketmaster"})

    def test_different_events_same_venue_kept(self):
        a = Event(title="Bad Bunny", category="concerts", date="2027-06-01", venue="Soldier Field", source="ticketmaster")
        b = Event(title="Chicago Fire FC vs. LA Galaxy", category="sports", subcategory="Soccer",
                  date="2027-06-01", venue="Soldier Field", source="sports")
        self.assertEqual(len(merge([a, b])), 2)

    def test_collapse_runs(self):
        shows = [Event(title="Hamilton", category="theater", date=f"2026-11-{d:02d}", time="19:30",
                       venue="CIBC Theatre", source="ticketmaster") for d in (3, 4, 5, 7)]
        out = collapse_runs(shows)
        self.assertEqual(len(out), 1)
        self.assertEqual((out[0].date, out[0].end_date, out[0].performances), ("2026-11-03", "2026-11-07", 4))


if __name__ == "__main__":
    unittest.main()
