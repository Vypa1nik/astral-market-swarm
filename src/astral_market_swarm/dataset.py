"""Reproducible identity for validated market data."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from .events import Candle, ensure_monotonic


@dataclass(frozen=True, slots=True)
class DatasetManifest:
    symbol: str
    timeframe: str
    start: datetime
    end: datetime
    row_count: int
    sha256: str


def _canonical_row(candle: Candle) -> str:
    values = (
        candle.symbol,
        candle.timestamp.isoformat(),
        *(
            format(value, "f")
            for value in (
                candle.open,
                candle.high,
                candle.low,
                candle.close,
                candle.volume,
            )
        ),
    )
    return "|".join(values)


def build_manifest(
    candles: Sequence[Candle],
    symbol: str,
    timeframe: str,
) -> DatasetManifest:
    """Create a stable identity from ordered candle content."""

    if not timeframe.strip():
        raise ValueError("timeframe must not be empty")
    ordered = ensure_monotonic(list(candles))
    if not ordered:
        raise ValueError("dataset must not be empty")
    if any(candle.symbol != symbol for candle in ordered):
        raise ValueError("dataset contains an unexpected symbol")

    payload = "\n".join(_canonical_row(candle) for candle in ordered).encode("utf-8")
    return DatasetManifest(
        symbol=symbol,
        timeframe=timeframe,
        start=ordered[0].timestamp,
        end=ordered[-1].timestamp,
        row_count=len(ordered),
        sha256=hashlib.sha256(payload).hexdigest(),
    )
