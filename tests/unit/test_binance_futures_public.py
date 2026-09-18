import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from astral_market_swarm.binance_futures_public import (
    BinanceFuturesPublicData,
    FuturesPublicDataError,
)


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self.payload = json.dumps(payload).encode()

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


def test_fetch_perpetual_snapshot_normalizes_prices_and_times(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "symbol": "BTCUSDT",
        "markPrice": "78010.25",
        "indexPrice": "78000.00",
        "lastFundingRate": "0.00010000",
        "nextFundingTime": 1767225600000,
        "time": 1767222000000,
    }
    monkeypatch.setattr(
        "astral_market_swarm.binance_futures_public.urlopen",
        lambda request, timeout: FakeResponse(payload),
    )

    snapshot = BinanceFuturesPublicData().fetch_perpetual_snapshot(
        "BTC/USDT", now=datetime(2026, 1, 1, tzinfo=UTC)
    )

    assert snapshot.symbol == "BTC/USDT"
    assert snapshot.mark_price == Decimal("78010.25")
    assert snapshot.index_price == Decimal("78000.00")
    assert snapshot.last_funding_rate == Decimal("0.00010000")
    assert snapshot.timestamp.tzinfo == UTC
    assert snapshot.next_funding_time.tzinfo == UTC


def test_fetch_funding_history_sorts_deduplicates_and_excludes_future_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = [
        {
            "symbol": "BTCUSDT",
            "fundingRate": "0.0002",
            "fundingTime": 1767225600000,
            "markPrice": "101",
        },
        {
            "symbol": "BTCUSDT",
            "fundingRate": "0.0001",
            "fundingTime": 1767196800000,
            "markPrice": "100",
        },
        {
            "symbol": "BTCUSDT",
            "fundingRate": "0.0003",
            "fundingTime": 1767196800000,
            "markPrice": "100",
        },
        {
            "symbol": "BTCUSDT",
            "fundingRate": "0.0004",
            "fundingTime": 1767312000000,
            "markPrice": "102",
        },
    ]
    monkeypatch.setattr(
        "astral_market_swarm.binance_futures_public.urlopen",
        lambda request, timeout: FakeResponse(payload),
    )

    settlements = BinanceFuturesPublicData().fetch_funding_history(
        "BTCUSDT", limit=4, now=datetime(2026, 1, 1, 8, tzinfo=UTC)
    )

    assert [item.rate for item in settlements] == [Decimal("0.0001"), Decimal("0.0002")]
    assert [item.mark_price for item in settlements] == [Decimal("100"), Decimal("101")]


def test_futures_adapter_rejects_untrusted_inputs_and_malformed_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = BinanceFuturesPublicData()
    with pytest.raises(FuturesPublicDataError, match="symbol"):
        adapter.fetch_perpetual_snapshot("BTCUSDT;drop")
    with pytest.raises(FuturesPublicDataError, match="limit"):
        adapter.fetch_funding_history("BTCUSDT", limit=0)

    monkeypatch.setattr(
        "astral_market_swarm.binance_futures_public.urlopen",
        lambda request, timeout: FakeResponse({"symbol": "BTCUSDT"}),
    )
    with pytest.raises(FuturesPublicDataError, match="snapshot"):
        adapter.fetch_perpetual_snapshot("BTCUSDT")
