import asyncio
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from cfb_lines.app import create_app
from cfb_lines.config import Settings
from cfb_lines.history import LineHistory
from cfb_lines.models import H2H, FetchResult, Game, Quote
from cfb_lines.providers.demo import DemoProvider
from cfb_lines.service import LineService

T0 = datetime(2026, 10, 28, tzinfo=timezone.utc)


def _game(price: int) -> Game:
    g = Game("g1", T0 + timedelta(days=1), "Home U", "Away St")
    g.quotes = [Quote("dk", "DK", H2H, "Home U", price, None, T0), Quote("dk", "DK", H2H, "Away St", 100, None, T0)]
    return g


def test_history_records_only_changes(tmp_path):
    h = LineHistory(str(tmp_path / "lines.sqlite3"))
    assert h.record([_game(-120)], T0) == []           # first sighting
    assert h.record([_game(-120)], T0) == []           # unchanged
    moves = h.record([_game(-130)], T0 + timedelta(seconds=30))
    assert len(moves) == 1 and moves[0]["from"]["price"] == -120 and moves[0]["to"]["price"] == -130
    assert h.db.execute("select count(*) from line_moves").fetchone()[0] == 3
    assert len(h.for_game("g1")) == 2


class FakeProvider:
    name = "fake"

    def __init__(self, remaining):
        self.remaining = remaining
        self.calls = 0

    async def fetch(self):
        self.calls += 1
        return FetchResult([_game(-120)], credits_remaining=self.remaining, credits_used=1)

    async def aclose(self):
        pass


def test_poller_pauses_when_credits_run_low():
    async def scenario():
        provider = FakeProvider(remaining=10)
        settings = Settings(provider="odds_api", poll_seconds=0.01, min_credits_reserve=50, promos_file="")
        svc = LineService(settings, provider)
        svc.start()
        await asyncio.sleep(0.1)
        await svc.stop()
        return provider.calls, svc.status

    calls, status = asyncio.run(scenario())
    assert calls == 1
    assert status["paused"].startswith("Paused: 10 API credits left")


def test_api_endpoints():
    svc = LineService(Settings(promos_file=""), DemoProvider(seed=3))
    app = create_app(svc, autostart=False)
    with TestClient(app) as client:
        assert client.get("/").status_code == 200
        client.post("/api/refresh")
        client.post("/api/refresh")
        data = client.get("/api/snapshot").json()
        assert len(data["games"]) == 12
        assert data["status"]["polls"] == 2
        assert {b["key"] for b in data["books"]} >= {"pinnacle", "draftkings", "fanduel"}
        game_id = data["games"][0]["id"]
        assert client.get(f"/api/games/{game_id}/history").status_code == 200
        assert client.get("/api/games/nope/history").status_code == 404
        for o in client.get("/api/opportunities", params={"type": "arb,ev"}).json():
            assert o["type"] in {"ARB", "EV"}


def test_promo_api_round_trip(tmp_path):
    from cfb_lines.promos import PromoStore

    path = tmp_path / "promos.json"
    svc = LineService(Settings(), DemoProvider(seed=3), PromoStore(str(path)))
    app = create_app(svc, autostart=False)
    with TestClient(app) as client:
        client.post("/api/refresh")
        bad = client.post("/api/promos", json={"book": "draftkings", "type": "profit_boost", "amount": 25})
        assert bad.status_code == 422  # boost needs boost_pct
        created = client.post("/api/promos", json={"book": "draftkings", "type": "bonus_bet", "amount": 100}).json()
        snap = client.get("/api/snapshot").json()
        assert [p["id"] for p in snap["promos"]] == [created["id"]]
        plays = [o for o in snap["opportunities"] if o["type"] == "PROMO"]
        assert 1 <= len(plays) <= 3
        assert all(o["legs"][0]["book"] == "draftkings" for o in plays)
        assert PromoStore(str(path)).list()[0].id == created["id"]  # persisted
        assert client.delete(f"/api/promos/{created['id']}").status_code == 204
        assert client.delete(f"/api/promos/{created['id']}").status_code == 404
        assert not [o for o in client.get("/api/snapshot").json()["opportunities"] if o["type"] == "PROMO"]
