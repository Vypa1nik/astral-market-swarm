"""Selective, cost-covered market-neutral carry entry decisions."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum

from .binance_futures_public import FundingSettlement, PerpetualSnapshot
from .carry import basis_rate


class CarryAction(Enum):
    HOLD_CASH = "hold_cash"
    OPEN_PAIR = "open_pair"
    HOLD_PAIR = "hold_pair"
    REBALANCE_PAIR = "rebalance_pair"
    CLOSE_PAIR = "close_pair"


@dataclass(frozen=True, slots=True)
class CarryConfig:
    round_trip_cost_rate: Decimal = Decimal("0.006")
    safety_hurdle_rate: Decimal = Decimal("0.001")
    expected_funding_events: int = 3
    minimum_positive_events: int = 5
    maximum_data_age_seconds: int = 120

    def __post_init__(self) -> None:
        if self.round_trip_cost_rate < 0 or self.safety_hurdle_rate < 0:
            raise ValueError("cost and hurdle rates must be non-negative")
        if self.expected_funding_events < 1:
            raise ValueError("expected_funding_events must be positive")
        if self.minimum_positive_events < 1:
            raise ValueError("minimum_positive_events must be positive")
        if self.maximum_data_age_seconds < 1:
            raise ValueError("maximum_data_age_seconds must be positive")


@dataclass(frozen=True, slots=True)
class CarryContext:
    symbol: str
    spot_mark: Decimal
    snapshot: PerpetualSnapshot
    funding_history: tuple[FundingSettlement, ...]
    now: datetime
    has_open_position: bool
    adl_risk: str

    def __post_init__(self) -> None:
        if not self.symbol.strip() or self.spot_mark <= 0:
            raise ValueError("symbol and spot_mark must be positive")
        if self.now.tzinfo is None or self.now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        if self.now.tzinfo != UTC:
            object.__setattr__(self, "now", self.now.astimezone(UTC))
        if self.snapshot.symbol != self.symbol:
            raise ValueError("snapshot symbol does not match context")
        if any(item.symbol != self.symbol for item in self.funding_history):
            raise ValueError("funding symbol does not match context")


@dataclass(frozen=True, slots=True)
class CarryDecision:
    action: CarryAction
    reason: str
    basis: Decimal
    expected_net_edge: Decimal


def decide(context: CarryContext, config: CarryConfig) -> CarryDecision:
    basis = basis_rate(context.snapshot.mark_price, context.spot_mark)
    if context.has_open_position:
        return CarryDecision(CarryAction.HOLD_PAIR, "paired_position_open", basis, Decimal("0"))
    if context.adl_risk.lower() != "low":
        return CarryDecision(CarryAction.HOLD_CASH, "adl_risk_high", basis, Decimal("0"))
    snapshot_age = (context.now - context.snapshot.timestamp).total_seconds()
    if snapshot_age < 0 or snapshot_age > config.maximum_data_age_seconds:
        return CarryDecision(CarryAction.HOLD_CASH, "data_stale", basis, Decimal("0"))
    history = context.funding_history[-7:]
    positive_events = sum(1 for item in history if item.rate > 0)
    if len(history) < 7 or positive_events < config.minimum_positive_events:
        return CarryDecision(CarryAction.HOLD_CASH, "funding_not_persistent", basis, Decimal("0"))
    average_funding = sum((item.rate for item in history), Decimal("0")) / len(history)
    expected_edge = basis + average_funding * config.expected_funding_events
    all_in_hurdle = config.round_trip_cost_rate + config.safety_hurdle_rate
    net_edge = expected_edge - all_in_hurdle
    if net_edge <= 0:
        return CarryDecision(CarryAction.HOLD_CASH, "edge_below_cost_hurdle", basis, net_edge)
    return CarryDecision(CarryAction.OPEN_PAIR, "cost_covered_carry_edge", basis, net_edge)
