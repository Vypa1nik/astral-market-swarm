from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from astral_market_swarm.data_quality import DataQualityError, validate_dataset
from astral_market_swarm.dataset import build_manifest
from astral_market_swarm.events import Candle


def make_candle(timestamp: datetime, **overrides: object) -> Candle:
    values: dict[str, object] = {
        "symbol": "BTC/USDT",
        "timestamp": timestamp,
        "open": Decimal("100"),
        "high": Decimal("105"),
        "low": Decimal("95"),
        "close": Decimal("102"),
        "volume": Decimal("10"),
    }
    values.update(overrides)
    return Candle(**values)


START = datetime(2026, 1, 1, tzinfo=UTC)
INTERVAL = timedelta(minutes=5)


def test_validate_dataset_accepts_clean_candles() -> None:
    candles = [make_candle(START + index * INTERVAL) for index in range(3)]

    assert validate_dataset(candles, "BTC/USDT", INTERVAL) == tuple(candles)


@pytest.mark.parametrize(
    "candles,error",
    [
        (
            [make_candle(START), make_candle(START + 2 * INTERVAL)],
            "gap",
        ),
        (
            [make_candle(START), make_candle(START - INTERVAL)],
            "monotonic",
        ),
        (
            [make_candle(START, symbol="ETH/USDT")],
            "symbol",
        ),
    ],
)
def test_validate_dataset_rejects_bad_data(candles: list[Candle], error: str) -> None:
    with pytest.raises(DataQualityError, match=error):
        validate_dataset(candles, "BTC/USDT", INTERVAL)


def test_candle_rejects_non_finite_price() -> None:
    with pytest.raises(ValueError, match="finite"):
        make_candle(START, close=Decimal("NaN"))


def test_validate_dataset_rejects_stale_last_event() -> None:
    candles = [make_candle(START)]
    now = START + timedelta(hours=1)

    with pytest.raises(DataQualityError, match="stale"):
        validate_dataset(candles, "BTC/USDT", INTERVAL, latest_allowed_at=now)


def test_manifest_is_deterministic_and_contains_identity() -> None:
    candles = [make_candle(START + index * INTERVAL) for index in range(2)]

    manifest = build_manifest(candles, "BTC/USDT", "5m")

    assert manifest.symbol == "BTC/USDT"
    assert manifest.timeframe == "5m"
    assert manifest.start == START
    assert manifest.end == START + INTERVAL
    assert manifest.row_count == 2
    assert len(manifest.sha256) == 64
    assert manifest == build_manifest(candles, "BTC/USDT", "5m")
