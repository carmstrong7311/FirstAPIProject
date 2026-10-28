from datetime import datetime, timedelta, timezone

import pytest

from cfb_lines.analysis import build_snapshot
from cfb_lines.config import Settings
from cfb_lines.models import H2H, OVER, SPREADS, TOTALS, UNDER, Game, Quote

NOW = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)
HOME, AWAY = "Georgia Bulldogs", "Florida Gators"


def game(*books, kickoff=NOW + timedelta(days=3)) -> Game:
    """Each book: (key, {"spread": (home_pt, home_px, away_px), "total": (...), "ml": (h, a)}, age_s)."""
    g = Game(id="g1", commence_time=kickoff, home=HOME, away=AWAY)
    for key, mk, age in books:
        ts = NOW - timedelta(seconds=age)
        q = lambda m, side, px, pt=None: Quote(key, key.title(), m, side, px, pt, ts)  # noqa: E731
        if "spread" in mk:
            pt, hp, ap = mk["spread"]
            g.quotes += [q(SPREADS, HOME, hp, pt), q(SPREADS, AWAY, ap, -pt)]
        if "total" in mk:
            pt, op, up = mk["total"]
            g.quotes += [q(TOTALS, OVER, op, pt), q(TOTALS, UNDER, up, pt)]
        if "ml" in mk:
            hp, ap = mk["ml"]
            g.quotes += [q(H2H, HOME, hp), q(H2H, AWAY, ap)]
    return g


def opps(snapshot, type_):
    return [o for o in snapshot["opportunities"] if o["type"] == type_]


def snap(*games, **settings):
    return build_snapshot(list(games), Settings(**settings), now=NOW)


def test_ev_uses_sharp_book_as_fair():
    s = snap(game(
        ("pinnacle", {"ml": (-200, 180)}, 0),
        ("draftkings", {"ml": (-190, 165)}, 0),
        ("fanduel", {"ml": (-210, 230)}, 0),   # dog well above fair
    ))
    ev = opps(s, "EV")
    assert [(o["legs"][0]["book"], o["legs"][0]["label"]) for o in ev] == [("fanduel", f"{AWAY} ML")]
    assert "Pinnacle" in ev[0]["detail"]
    # away fair = (1/2.8) / (1/1.5 + 1/2.8) = 0.3488; 0.3488 * 3.3 - 1
    assert ev[0]["edge"] == pytest.approx(0.151, abs=1e-3)


def test_ev_falls_back_to_consensus_without_sharp():
    s = snap(game(
        ("draftkings", {"spread": (-7, -110, -110)}, 0),
        ("fanduel", {"spread": (-7, -110, -110)}, 0),
        ("betmgm", {"spread": (-7, -110, -110)}, 0),
        ("caesars", {"spread": (-7, +106, -126)}, 0),
    ))
    ev = opps(s, "EV")
    assert len(ev) == 1 and ev[0]["legs"][0]["book"] == "caesars"
    assert "consensus of 3" in ev[0]["detail"]


def test_no_fair_price_without_enough_books():
    s = snap(game(("draftkings", {"ml": (-110, -110)}, 0), ("fanduel", {"ml": (120, -100)}, 0)))
    assert opps(s, "EV") == []


def test_stale_sharp_book_is_not_used_as_fair():
    s = snap(game(
        ("pinnacle", {"ml": (-300, 250)}, 3600),
        ("draftkings", {"ml": (-150, 130)}, 0),
        ("fanduel", {"ml": (-150, 130)}, 0),
        ("betmgm", {"ml": (-150, 130)}, 0),
    ))
    # With a trusted Pinnacle the home side at -150 would look like a huge edge.
    assert all(o["legs"][0]["book"] == "pinnacle" for o in opps(s, "EV"))
    assert s["games"][0]["books"]["pinnacle"]["stale"] is True
    assert s["games"][0]["books"]["draftkings"]["stale"] is False


def test_off_market_spread_and_key_numbers():
    s = snap(game(
        ("draftkings", {"spread": (-7.5, -110, -110)}, 0),
        ("fanduel", {"spread": (-7.5, -110, -110)}, 0),
        ("betmgm", {"spread": (-7.5, -110, -110)}, 0),
        ("bovada", {"spread": (-6, -110, -110)}, 0),
    ))
    off = opps(s, "OFF_MARKET")
    assert len(off) == 1
    leg = off[0]["legs"][0]
    assert (leg["book"], leg["label"]) == ("bovada", f"{HOME} -6")
    assert off[0]["edge"] == 1.5
    assert "key number 7" in off[0]["detail"]


def test_off_market_total_picks_correct_side():
    books = [(b, {"total": (52.5, -110, -110)}, 0) for b in ("a", "b", "c")]
    s = snap(game(*books, ("d", {"total": (50, -110, -110)}, 0)))
    off = opps(s, "OFF_MARKET")
    assert [o["legs"][0]["label"] for o in off] == ["Over 50"]


def test_moneyline_arbitrage():
    s = snap(game(
        ("draftkings", {"ml": (-105, -115)}, 0),
        ("fanduel", {"ml": (-125, +115)}, 0),
    ))
    arb = opps(s, "ARB")
    assert len(arb) == 1
    assert {(l["book"], l["price"]) for l in arb[0]["legs"]} == {("draftkings", -105), ("fanduel", 115)}
    assert arb[0]["edge"] == pytest.approx(1 / (1 / 1.952381 + 1 / 2.15) - 1, abs=1e-4)


def test_spread_middle():
    s = snap(game(
        ("draftkings", {"spread": (-3, -110, -110)}, 0),
        ("fanduel", {"spread": (-4.5, -110, -110)}, 0),
    ))
    mid = opps(s, "MIDDLE")
    assert len(mid) == 1
    labels = {l["label"] for l in mid[0]["legs"]}
    assert labels == {f"{HOME} -3", f"{AWAY} +4.5"}
    assert mid[0]["edge"] == 1.5


def test_no_arb_in_efficient_market():
    s = snap(game(*[(b, {"spread": (-7, -110, -110), "total": (50, -110, -110), "ml": (-280, 230)}, 0)
                    for b in ("a", "b", "c", "d")]))
    assert s["opportunities"] == []


def test_best_line_prefers_points_then_price():
    s = snap(game(
        ("a", {"spread": (-7, -105, -115), "total": (50.5, -110, -110)}, 0),
        ("b", {"spread": (-6.5, -120, +100), "total": (51, -110, -110)}, 0),
        ("c", {"spread": (-6.5, -115, -105), "total": (51, -105, -115)}, 0),
    ))
    cons = s["games"][0]["consensus"]
    assert cons[SPREADS]["best"] == {"home": ["c"], "away": ["a"]}
    assert cons[TOTALS]["best"] == {"over": ["a"], "under": ["b"]}
    assert cons[SPREADS]["line"] == -6.5


def test_live_flag():
    s = snap(game(("a", {"ml": (-110, -110)}, 0), kickoff=NOW - timedelta(minutes=30)))
    assert s["games"][0]["live"] is True


def test_consensus_line_is_most_quoted_number():
    s = snap(game(
        ("a", {"spread": (-20, -110, -110)}, 0),
        ("b", {"spread": (-20.5, -110, -110)}, 0),
        ("c", {"spread": (-20.5, -110, -110)}, 0),
        ("d", {"spread": (-20, -110, -110)}, 0),
        ("e", {"spread": (-20.5, -110, -110)}, 0),
    ))
    cons = s["games"][0]["consensus"][SPREADS]
    assert cons["line"] == -20.5
    assert cons["fair_price_a"] == 100


def _promo(**kw):
    from cfb_lines.promos import Promo
    return Promo(id="p1", **kw)


def test_bonus_bet_finds_best_hedge():
    g = game(
        ("draftkings", {"ml": (-400, 300)}, 0),
        ("fanduel", {"ml": (-350, 280)}, 0),
        ("betmgm", {"ml": (-380, 290)}, 0),
    )
    s = build_snapshot([g], Settings(), now=NOW, promos=[_promo(book="draftkings", type="bonus_bet", amount=100)])
    plays = opps(s, "PROMO")
    assert plays, s["opportunities"]
    best = plays[0]
    # Bonus on the +300 dog at DraftKings, hedged on the favorite at FanDuel's -350.
    assert [(l["book"], l["price"]) for l in best["legs"]] == [("draftkings", 300), ("fanduel", -350)]
    assert best["legs"][0]["promo"] == "bonus bet"
    assert best["edge"] == pytest.approx(3 * (100 / 350) / (1 + 100 / 350), abs=1e-3)
    assert best["sizing"]["fixed"] == [0, 100]
    assert best["sizing"]["units"][0]["cash"] == 0


def test_promo_respects_min_odds_markets_and_expiry():
    g = game(
        ("draftkings", {"ml": (-400, 300), "spread": (-7, -110, -110)}, 0),
        ("fanduel", {"ml": (-350, 280), "spread": (-7, -110, -110)}, 0),
    )
    promo = _promo(book="draftkings", type="profit_boost", amount=50, boost_pct=50,
                   min_odds=-200, markets=["h2h"])
    plays = opps(build_snapshot([g], Settings(), now=NOW, promos=[promo]), "PROMO")
    assert [p["legs"][0]["label"] for p in plays] == [f"{AWAY} ML"]
    expired = _promo(book="draftkings", type="bonus_bet", amount=50, expires=NOW - timedelta(hours=1))
    assert opps(build_snapshot([g], Settings(), now=NOW, promos=[expired]), "PROMO") == []


def test_every_opportunity_has_sizing():
    s = snap(game(
        ("pinnacle", {"ml": (-200, 180), "spread": (-7, -105, -105)}, 0),
        ("draftkings", {"ml": (-105, -115), "spread": (-5, -110, -110)}, 0),
        ("fanduel", {"ml": (-125, 230), "spread": (-7, -110, -110)}, 0),
    ))
    assert {o["type"] for o in s["opportunities"]} >= {"ARB", "EV", "OFF_MARKET", "MIDDLE"}
    for o in s["opportunities"]:
        assert len(o["sizing"]["units"]) == len(o["legs"])
