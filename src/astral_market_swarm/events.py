"""Causal, validated market event primitives."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class Candle:
    """One completed OHLCV candle with an aware timestamp."""

    symbol: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol must not be empty")
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        if self.timestamp.tzinfo != UTC:
            object.__setattr__(self, "timestamp", self.timestamp.astimezone(UTC))

        for field_name in ("open", "high", "low", "close", "volume"):
            try:
                value = Decimal(str(getattr(self, field_name)))
            except (ArithmeticError, ValueError) as error:
                raise ValueError(f"{field_name} must be a decimal number") from error
            if not value.is_finite():
                raise ValueError(f"{field_name} must be finite")
            object.__setattr__(self, field_name, value)

        prices = (self.open, self.high, self.low, self.close)
        if any(price <= 0 for price in prices):
            raise ValueError("OHLC prices must be positive")
        if self.volume < 0:
            raise ValueError("volume must be non-negative")
        if self.high < max(self.open, self.close):
            raise ValueError("high must be at least open and close")
        if self.low > min(self.open, self.close):
            raise ValueError("low must be at most open and close")


def ensure_monotonic(events: list[Candle]) -> tuple[Candle, ...]:
    """Return events as an immutable tuple if timestamps are strictly ordered."""

    for previous, current in zip(events, events[1:], strict=False):
        if current.timestamp <= previous.timestamp:
            raise ValueError("candle timestamps must be strictly monotonic")
    return tuple(events)
