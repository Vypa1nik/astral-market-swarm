from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from astral_market_swarm.events import Candle, ensure_monotonic


def candle(**overrides: object) -> Candle:
    values: dict[str, object] = {
        "symbol": "BTC/USDT",
        "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
        "open": Decimal("100"),
        "high": Decimal("105"),
        "low": Decimal("95"),
        "close": Decimal("102"),
        "volume": Decimal("10"),
    }
    values.update(overrides)
    return Candle(**values)


def test_candle_accepts_valid_utc_values() -> None:
    result = candle()

    assert result.timestamp.tzinfo == UTC
    assert result.close == Decimal("102")


@pytest.mark.parametrize(
    "field,value",
    [
        ("timestamp", datetime(2026, 1, 1)),
        ("open", Decimal("0")),
        ("high", Decimal("0")),
        ("low", Decimal("0")),
        ("close", Decimal("0")),
        ("volume", Decimal("-1")),
    ],
)
def test_candle_rejects_invalid_values(field: str, value: object) -> None:
    with pytest.raises(ValueError):
        candle(**{field: value})


def test_candle_rejects_invalid_ohlc_relationship() -> None:
    with pytest.raises(ValueError, match="high"):
        candle(high=Decimal("99"))

    with pytest.raises(ValueError, match="low"):
        candle(low=Decimal("103"))


def test_ensure_monotonic_rejects_out_of_order_events() -> None:
    first = candle(timestamp=datetime(2026, 1, 1, tzinfo=UTC))
    second = candle(timestamp=first.timestamp - timedelta(minutes=5))

    with pytest.raises(ValueError, match="monotonic"):
        ensure_monotonic([first, second])


def test_ensure_monotonic_returns_tuple_for_valid_events() -> None:
    first = candle(timestamp=datetime(2026, 1, 1, tzinfo=UTC))
    second = candle(timestamp=first.timestamp + timedelta(minutes=5))

    assert ensure_monotonic([first, second]) == (first, second)
