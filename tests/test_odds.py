import pytest

from cfb_lines.odds import american_to_decimal, expected_value, implied_prob, no_vig, prob_to_american


def test_american_to_decimal():
    assert american_to_decimal(100) == 2.0
    assert american_to_decimal(-110) == pytest.approx(1.9091, abs=1e-4)
    assert american_to_decimal(250) == 3.5


def test_no_vig_standard_market_is_fifty_fifty():
    a, b = no_vig(-110, -110)
    assert a == pytest.approx(0.5) and b == pytest.approx(0.5)


def test_no_vig_sums_to_one():
    a, b = no_vig(-250, 205)
    assert a + b == pytest.approx(1)
    assert a > implied_prob(205)


@pytest.mark.parametrize("price", [-450, -110, 100, 135, 1200])
def test_prob_round_trip(price):
    assert prob_to_american(implied_prob(price)) == pytest.approx(price, abs=1)


def test_expected_value():
    assert expected_value(0.5, 100) == pytest.approx(0)
    assert expected_value(0.5, 110) == pytest.approx(0.05)
    assert expected_value(0.5, -110) < 0
