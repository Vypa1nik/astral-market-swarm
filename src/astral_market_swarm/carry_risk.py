"""Independent conservative pre-trade risk checks for paired carry positions."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class CarryRiskConfig:
    max_pair_notional_fraction: Decimal = Decimal("0.20")
    max_total_collateral_fraction: Decimal = Decimal("0.60")
    minimum_cash_reserve_fraction: Decimal = Decimal("0.40")
    minimum_margin_buffer_multiple: Decimal = Decimal("2.5")

    def __post_init__(self) -> None:
        fractions = (
            self.max_pair_notional_fraction,
            self.max_total_collateral_fraction,
            self.minimum_cash_reserve_fraction,
        )
        if any(value <= 0 or value > 1 for value in fractions):
            raise ValueError("risk fractions must be in the interval (0, 1]")
        if self.minimum_margin_buffer_multiple <= 0:
            raise ValueError("margin buffer multiple must be positive")


@dataclass(frozen=True, slots=True)
class CarryRiskContext:
    equity: Decimal
    cash: Decimal
    existing_collateral: Decimal
    target_notional: Decimal
    proposed_collateral: Decimal
    maintenance_margin: Decimal


@dataclass(frozen=True, slots=True)
class CarryRiskDecision:
    approved: bool
    reason: str


def approve_pair(context: CarryRiskContext, config: CarryRiskConfig) -> CarryRiskDecision:
    if min(
        context.equity,
        context.cash,
        context.target_notional,
        context.proposed_collateral,
        context.maintenance_margin,
    ) <= 0 or context.existing_collateral < 0:
        return CarryRiskDecision(False, "invalid_risk_context")
    if context.target_notional > context.equity * config.max_pair_notional_fraction:
        return CarryRiskDecision(False, "max_pair_notional")
    total_collateral = context.existing_collateral + context.proposed_collateral
    if total_collateral > context.equity * config.max_total_collateral_fraction:
        return CarryRiskDecision(False, "max_total_collateral")
    available_cash = context.cash - context.proposed_collateral
    required_reserve = context.equity * config.minimum_cash_reserve_fraction
    if available_cash < required_reserve:
        return CarryRiskDecision(False, "minimum_cash_reserve")
    required_margin_buffer = context.maintenance_margin * config.minimum_margin_buffer_multiple
    if context.proposed_collateral < required_margin_buffer:
        return CarryRiskDecision(False, "margin_buffer_low")
    return CarryRiskDecision(True, "approved")
