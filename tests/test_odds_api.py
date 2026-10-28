import asyncio
import json
from pathlib import Path

import httpx
import pytest

from cfb_lines.config import Settings
from cfb_lines.models import SPREADS
from cfb_lines.providers.odds_api import OddsApiError, OddsApiProvider, parse_events

SAMPLE = json.loads((Path(__file__).parent / "sample_odds_api.json").read_text())


def test_parse_events():
    games = parse_events(SAMPLE)
    assert len(games) == 1
    g = games[0]
    assert (g.home, g.away) == ("Georgia Bulldogs", "Florida Gators")
    assert {q.book for q in g.quotes} == {"draftkings", "fanduel", "pinnacle"}
    dk_spread = [q for q in g.quotes if q.book == "draftkings" and q.market == SPREADS]
    assert {(q.side, q.point, q.price) for q in dk_spread} == {
        ("Georgia Bulldogs", -14.5, -110),
        ("Florida Gators", 14.5, -110),
    }


def _provider(handler, **overrides) -> OddsApiProvider:
    settings = Settings(provider="odds_api", odds_api_key="k", **overrides)
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return OddsApiProvider(settings, client)


def test_fetch_builds_request_and_reads_quota_headers():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = request.url
        return httpx.Response(
            200, json=SAMPLE, headers={"x-requests-remaining": "480", "x-requests-used": "20"}
        )

    result = asyncio.run(_provider(handler).fetch())
    assert seen["url"].path == "/v4/sports/americanfootball_ncaaf/odds"
    params = dict(seen["url"].params)
    assert params["regions"] == "us,us2"
    assert params["markets"] == "h2h,spreads,totals"
    assert params["oddsFormat"] == "american"
    assert result.credits_remaining == 480 and result.credits_used == 20
    assert len(result.games) == 1


def test_bookmakers_override_regions():
    seen = {}

    def handler(request):
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json=[])

    asyncio.run(_provider(handler, bookmakers=["draftkings", "pinnacle"]).fetch())
    assert seen["params"]["bookmakers"] == "draftkings,pinnacle"
    assert "regions" not in seen["params"]


def test_error_message_is_surfaced():
    def handler(request):
        return httpx.Response(401, json={"message": "API key is not valid"})

    with pytest.raises(OddsApiError, match="401: API key is not valid"):
        asyncio.run(_provider(handler).fetch())


def test_fetch_cost():
    assert Settings().fetch_cost == 6  # 2 regions x 3 markets
    assert Settings(bookmakers=["a"] * 12).fetch_cost == 6  # 12 books = 2 region units
    assert Settings(bookmakers=["a"] * 5, markets=["spreads"]).fetch_cost == 1
