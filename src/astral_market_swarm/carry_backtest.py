"""Small deterministic paired carry backtest primitive for validation."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .carry import CarryPosition


@dataclass(frozen=True, slots=True)
class CarryBacktestConfig:
    total_execution_cost_rate: Decimal

    def __post_init__(self) -> None:
        if self.total_execution_cost_rate < 0:
            raise ValueError("total_execution_cost_rate must be non-negative")


@dataclass(frozen=True, slots=True)
class CarryBacktestResult:
    spot_pnl: Decimal
    perp_pnl: Decimal
    funding_pnl: Decimal
    execution_cost: Decimal
    net_pnl: Decimal


def run_carry_backtest(
    position: CarryPosition,
    exit_spot: Decimal,
    exit_perp: Decimal,
    funding_rates: tuple[Decimal, ...],
    config: CarryBacktestConfig,
) -> CarryBacktestResult:
    if exit_spot <= 0 or exit_perp <= 0:
        raise ValueError("exit marks must be positive")
    spot_pnl = (exit_spot - position.spot_entry) * position.spot_quantity
    perp_pnl = (position.perp_entry - exit_perp) * position.short_quantity
    funding_pnl = sum(
        (rate * exit_perp * position.short_quantity for rate in funding_rates),
        Decimal("0"),
    )
    executed_notional = (
        position.spot_entry * position.spot_quantity
        + position.perp_entry * position.short_quantity
        + exit_spot * position.spot_quantity
        + exit_perp * position.short_quantity
    )
    execution_cost = executed_notional * config.total_execution_cost_rate
    net_pnl = spot_pnl + perp_pnl + funding_pnl - execution_cost
    return CarryBacktestResult(spot_pnl, perp_pnl, funding_pnl, execution_cost, net_pnl)
