"""Independent risk sizing and hard account guards."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal


class RiskRejected(ValueError):
    """Raised when an entry cannot pass the risk gate."""


@dataclass(frozen=True, slots=True)
class RiskConfig:
    risk_per_trade: Decimal = Decimal("0.0025")
    max_position_fraction: Decimal = Decimal("0.25")
    max_gross_exposure_fraction: Decimal = Decimal("0.75")
    max_daily_loss: Decimal = Decimal("0.03")
    max_drawdown: Decimal = Decimal("0.15")
    max_signal_age: timedelta = timedelta(minutes=15)
    leverage: Decimal = Decimal("1")

    def __post_init__(self) -> None:
        fractions = (self.risk_per_trade, self.max_daily_loss, self.max_drawdown)
        if any(value <= 0 or value > 1 for value in fractions):
            raise ValueError("risk fractions must be in the interval (0, 1]")
        if self.max_position_fraction <= 0 or self.max_gross_exposure_fraction <= 0:
            raise ValueError("exposure fractions must be positive")
        if self.leverage < 1 or self.leverage > 3:
            raise ValueError("paper leverage must be between 1 and 3")
        if self.max_signal_age <= timedelta(0):
            raise ValueError("max_signal_age must be positive")


@dataclass(frozen=True, slots=True)
class RiskContext:
    equity: Decimal
    cash: Decimal
    gross_exposure: Decimal
    peak_equity: Decimal
    daily_pnl: Decimal
    signal_timestamp: datetime
    now: datetime
    kill_switch: bool = False


@dataclass(frozen=True, slots=True)
class RiskDecision:
    approved: bool
    quantity: Decimal
    notional: Decimal
    risk_cash: Decimal


def _reject(reason: str) -> None:
    raise RiskRejected(reason)


def size_entry(
    entry_price: Decimal,
    stop_price: Decimal,
    context: RiskContext,
    config: RiskConfig,
) -> RiskDecision:
    """Calculate a long spot size, rejecting unsafe entries before sizing."""

    if context.kill_switch:
        _reject("kill switch is active")
    if entry_price <= 0:
        _reject("entry price must be positive")
    if stop_price <= 0 or stop_price >= entry_price:
        _reject("stop must be positive and below entry")
    if context.equity <= 0 or context.peak_equity <= 0:
        _reject("equity must be positive")
    if context.cash <= 0:
        _reject("cash is insufficient")
    if context.signal_timestamp.tzinfo is None or context.now.tzinfo is None:
        _reject("timestamps must be timezone-aware")
    age = context.now - context.signal_timestamp
    if age < timedelta(0) or age > config.max_signal_age:
        _reject("signal is stale or from the future")
    drawdown = (context.peak_equity - context.equity) / context.peak_equity
    if drawdown >= config.max_drawdown:
        _reject("drawdown limit reached")
    if context.daily_pnl <= -(context.equity * config.max_daily_loss):
        _reject("daily loss limit reached")

    risk_cash = context.equity * config.risk_per_trade
    stop_distance = entry_price - stop_price
    quantity_by_risk = risk_cash / stop_distance
    quantity_by_position = context.equity * config.max_position_fraction / entry_price
    gross_headroom = context.equity * config.max_gross_exposure_fraction - context.gross_exposure
    if gross_headroom <= 0:
        _reject("gross exposure limit reached")
    quantity_by_exposure = gross_headroom / entry_price
    quantity_by_cash = context.cash * config.leverage / entry_price
    quantity = min(quantity_by_risk, quantity_by_position, quantity_by_exposure, quantity_by_cash)
    if quantity <= 0:
        _reject("cash or exposure is insufficient")

    return RiskDecision(True, quantity, quantity * entry_price, risk_cash)
