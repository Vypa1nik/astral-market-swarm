import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from astral_market_swarm.binance_public import BinancePublicData, PublicDataError


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self.payload = json.dumps(payload).encode()

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


def test_fetch_klines_normalizes_and_discards_open_candle(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = [
        [1767225600000, "100", "105", "95", "102", "10", 1767225899999],
        [1767225900000, "102", "106", "101", "104", "11", 1767226199999],
        [1767226200000, "104", "107", "103", "105", "12", 1767226499999],
    ]
    monkeypatch.setattr(
        "astral_market_swarm.binance_public.urlopen",
        lambda request, timeout: FakeResponse(payload),
    )
    adapter = BinancePublicData()

    candles = adapter.fetch_klines(
        "BTC/USDT",
        "5m",
        limit=3,
        now=datetime(2026, 1, 1, 0, 14, tzinfo=UTC),
    )

    assert len(candles) == 2
    assert candles[0].symbol == "BTC/USDT"
    assert candles[0].close == Decimal("102")
    assert candles[-1].timestamp < datetime(2026, 1, 1, 0, 14, tzinfo=UTC)


def test_fetch_klines_rejects_untrusted_parameters() -> None:
    adapter = BinancePublicData()

    with pytest.raises(PublicDataError, match="symbol"):
        adapter.fetch_klines("BTC/USDT;drop", "5m")
    with pytest.raises(PublicDataError, match="interval"):
        adapter.fetch_klines("BTCUSDT", "7m")
    with pytest.raises(PublicDataError, match="limit"):
        adapter.fetch_klines("BTCUSDT", "5m", limit=0)


def test_fetch_klines_rejects_malformed_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "astral_market_swarm.binance_public.urlopen",
        lambda request, timeout: FakeResponse([[1, "bad"]]),
    )

    with pytest.raises(PublicDataError, match="row"):
        BinancePublicData().fetch_klines("BTCUSDT", "5m")
