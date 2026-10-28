"""Odds conversion helpers."""

from __future__ import annotations


def american_to_decimal(price: int) -> float:
    if price == 0:
        raise ValueError("American odds cannot be 0")
    return 1 + price / 100 if price > 0 else 1 + 100 / -price


def implied_prob(price: int) -> float:
    return 1 / american_to_decimal(price)


def prob_to_american(p: float) -> int:
    if not 0 < p < 1:
        raise ValueError(f"probability out of range: {p}")
    if p > 0.5:
        return -round(100 * p / (1 - p))
    return round(100 * (1 - p) / p)


def no_vig(price_a: int, price_b: int) -> tuple[float, float]:
    """Strip the bookmaker margin from a two-way market (multiplicative method)."""
    a, b = implied_prob(price_a), implied_prob(price_b)
    total = a + b
    return a / total, b / total


def expected_value(fair_prob: float, price: int) -> float:
    """EV per unit staked of betting `price` when the true win probability is `fair_prob`."""
    return fair_prob * american_to_decimal(price) - 1
