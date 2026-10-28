"""Stake sizing across the legs of a play.

Each leg is described per $1 staked by a `Unit`: what it nets if it wins, what it
loses if it doesn't, and how much real cash it ties up. That covers cash bets,
bonus (free) bets, profit boosts and no-sweat refunds with one formula.

Equalizing every outcome for two opposite legs gives stake_i proportional to
1 / (win_i + loss_i). static/index.html mirrors this math for the live bet-size box.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .odds import american_to_decimal


@dataclass(frozen=True)
class Unit:
    win: float   # net gain per $1 if this leg wins
    loss: float  # net loss per $1 if this leg loses
    cash: float  # cash outlay per $1 (0 for a bonus bet)

    def to_json(self) -> dict[str, float]:
        return {k: round(v, 6) for k, v in asdict(self).items()}


def cash_unit(price: int) -> Unit:
    return Unit(american_to_decimal(price) - 1, 1.0, 1.0)


def bonus_unit(price: int) -> Unit:
    """Bonus bet: the stake isn't yours and isn't returned, only the winnings are."""
    return Unit(american_to_decimal(price) - 1, 0.0, 0.0)


def boost_unit(price: int, boost: float) -> Unit:
    """Profit boost: winnings multiplied by (1 + boost)."""
    return Unit((american_to_decimal(price) - 1) * (1 + boost), 1.0, 1.0)


def no_sweat_unit(price: int, conversion: float) -> Unit:
    """Losing stake refunded as a bonus bet you expect to convert at `conversion`."""
    return Unit(american_to_decimal(price) - 1, 1.0 - conversion, 1.0)


def hedge_stakes(units: list[Unit], total: float | None = None,
                 fixed: tuple[int, float] | None = None) -> list[float]:
    """Stakes that make every outcome pay the same.

    Either `total` cash is split across the legs, or leg `fixed[0]` is pinned to
    `fixed[1]` (e.g. the size of a bonus bet) and the rest scale off it.
    """
    weights = [1 / (u.win + u.loss) for u in units]
    if fixed is not None:
        idx, amount = fixed
        scale = amount / weights[idx]
    else:
        if total is None:
            raise ValueError("need total or fixed")
        scale = total / sum(w * u.cash for w, u in zip(weights, units))
    return [w * scale for w in weights]


def outcomes(units: list[Unit], stakes: list[float]) -> list[float]:
    """Net result if leg i wins and every other leg loses."""
    losses = [s * u.loss for s, u in zip(stakes, units)]
    total_loss = sum(losses)
    return [s * u.win - (total_loss - losses[i]) for i, (s, u) in enumerate(zip(stakes, units))]


def cash_outlay(units: list[Unit], stakes: list[float]) -> float:
    return sum(s * u.cash for s, u in zip(stakes, units))
