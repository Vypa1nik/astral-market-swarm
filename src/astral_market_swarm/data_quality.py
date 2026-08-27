"""Strict validation for normalized market datasets."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta

from .events import Candle, ensure_monotonic


class DataQualityError(ValueError):
    """Raised when market data cannot be trusted for simulation."""


def validate_dataset(
    candles: Sequence[Candle],
    expected_symbol: str,
    interval: timedelta,
    latest_allowed_at: datetime | None = None,
) -> tuple[Candle, ...]:
    """Validate a complete, ordered candle sequence without repairing it."""

    if not candles:
        raise DataQualityError("dataset must not be empty")
    if interval <= timedelta(0):
        raise DataQualityError("interval must be positive")

    try:
        ordered = ensure_monotonic(list(candles))
    except ValueError as error:
        raise DataQualityError(str(error)) from error

    if any(candle.symbol != expected_symbol for candle in ordered):
        raise DataQualityError("dataset contains an unexpected symbol")

    for previous, current in zip(ordered, ordered[1:], strict=False):
        if current.timestamp - previous.timestamp != interval:
            raise DataQualityError("dataset contains a gap or wrong interval")

    if latest_allowed_at is not None:
        if latest_allowed_at.tzinfo is None or latest_allowed_at.utcoffset() is None:
            raise DataQualityError("latest_allowed_at must be timezone-aware")
        if latest_allowed_at - ordered[-1].timestamp > interval:
            raise DataQualityError("last candle is stale")

    return ordered
