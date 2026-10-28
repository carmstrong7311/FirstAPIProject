import pytest

from cfb_lines.sizing import (
    bonus_unit, boost_unit, cash_outlay, cash_unit, hedge_stakes, no_sweat_unit, outcomes,
)


def test_arb_split_pays_the_same_either_way():
    units = [cash_unit(-105), cash_unit(115)]
    stakes = hedge_stakes(units, total=1000)
    assert sum(stakes) == pytest.approx(1000)
    a, b = outcomes(units, stakes)
    assert a == pytest.approx(b)
    implied = 1 / 1.952381 + 1 / 2.15
    assert a == pytest.approx(1000 / implied - 1000, abs=0.01)


def test_standard_market_hedge_loses_the_vig():
    units = [cash_unit(-110), cash_unit(-110)]
    stakes = hedge_stakes(units, total=220)
    assert stakes == [pytest.approx(110), pytest.approx(110)]
    assert outcomes(units, stakes) == [pytest.approx(-10), pytest.approx(-10)]


def test_bonus_bet_conversion():
    # $100 bonus bet at +300, hedged at -350: classic ~70% conversion.
    units = [bonus_unit(300), cash_unit(-350)]
    stakes = hedge_stakes(units, fixed=(0, 100))
    assert stakes[0] == 100
    assert stakes[1] == pytest.approx(300 / (1 + 100 / 350))   # A(d-1)/h
    a, b = outcomes(units, stakes)
    assert a == pytest.approx(b)
    assert a == pytest.approx(300 * (100 / 350) / (1 + 100 / 350))
    assert cash_outlay(units, stakes) == pytest.approx(stakes[1])  # bonus stake isn't cash


def test_profit_boost_hedge():
    # 50% boost on +100 -> +150 effective; hedge at -110.
    units = [boost_unit(100, 0.5), cash_unit(-110)]
    stakes = hedge_stakes(units, fixed=(0, 50))
    a, b = outcomes(units, stakes)
    assert a == pytest.approx(b)
    d_hedge = 1 + 100 / 110
    assert a == pytest.approx(50 * 2.5 / d_hedge * (d_hedge - 1) - 50)


def test_no_sweat_refund_is_valued():
    units = [no_sweat_unit(200, 0.7), cash_unit(-220)]
    stakes = hedge_stakes(units, fixed=(0, 100))
    a, b = outcomes(units, stakes)
    assert a == pytest.approx(b)
    assert a > 0
