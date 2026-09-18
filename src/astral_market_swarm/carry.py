"""Pure paired spot/perpetual carry accounting primitives."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class CarryPosition:
    symbol: str
    spot_quantity: Decimal
    short_quantity: Decimal
    spot_entry: Decimal
    perp_entry: Decimal
    collateral: Decimal
    opened_at: datetime
    accrued_funding: Decimal
    fees_paid: Decimal
    rebalance_cost: Decimal

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol must not be empty")
        if self.opened_at.tzinfo is None or self.opened_at.utcoffset() is None:
            raise ValueError("opened_at must be timezone-aware")
        if self.opened_at.tzinfo != UTC:
            object.__setattr__(self, "opened_at", self.opened_at.astimezone(UTC))
        if self.spot_quantity <= 0 or self.short_quantity <= 0:
            raise ValueError("leg quantities must be positive")
        if self.spot_entry <= 0 or self.perp_entry <= 0:
            raise ValueError("entry prices must be positive")
        if self.collateral <= 0:
            raise ValueError("collateral must be positive")


@dataclass(frozen=True, slots=True)
class CarryPnl:
    spot_pnl: Decimal
    perp_pnl: Decimal
    funding_pnl: Decimal
    fees: Decimal
    rebalance_cost: Decimal
    net_pnl: Decimal
    net_delta: Decimal
    net_delta_notional: Decimal


def basis_rate(perp_mark: Decimal, spot_mark: Decimal) -> Decimal:
    if spot_mark <= 0:
        raise ValueError("spot mark must be positive")
    if perp_mark <= 0:
        raise ValueError("perpetual mark must be positive")
    return perp_mark / spot_mark - Decimal("1")


def position_pnl(position: CarryPosition, spot_mark: Decimal, perp_mark: Decimal) -> CarryPnl:
    if spot_mark <= 0 or perp_mark <= 0:
        raise ValueError("mark prices must be positive")
    spot_pnl = (spot_mark - position.spot_entry) * position.spot_quantity
    perp_pnl = (position.perp_entry - perp_mark) * position.short_quantity
    net_delta = position.spot_quantity - position.short_quantity
    net_delta_notional = net_delta * spot_mark
    net_pnl = (
        spot_pnl
        + perp_pnl
        + position.accrued_funding
        - position.fees_paid
        - position.rebalance_cost
    )
    return CarryPnl(
        spot_pnl,
        perp_pnl,
        position.accrued_funding,
        position.fees_paid,
        position.rebalance_cost,
        net_pnl,
        net_delta,
        net_delta_notional,
    )
