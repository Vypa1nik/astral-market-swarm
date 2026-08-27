from datetime import UTC, datetime
from decimal import Decimal

import pytest

from astral_market_swarm.exchange import ExecutionMode, RuntimeConfig


def test_runtime_defaults_to_isolated_paper_mode() -> None:
    config = RuntimeConfig()

    assert config.mode is ExecutionMode.PAPER
    assert config.demo_cash == Decimal("5000")
    assert config.account_id == "astral-demo-5000-usdt"


def test_live_mode_is_rejected_in_v1() -> None:
    with pytest.raises(ValueError, match="live"):
        RuntimeConfig(mode=ExecutionMode.LIVE)


def test_quote_requires_aware_positive_prices() -> None:
    from astral_market_swarm.exchange import Quote

    with pytest.raises(ValueError, match="timezone"):
        Quote("BTC/USDT", Decimal("100"), Decimal("101"), datetime(2026, 1, 1))
    with pytest.raises(ValueError, match="positive"):
        Quote("BTC/USDT", Decimal("0"), Decimal("101"), datetime(2026, 1, 1, tzinfo=UTC))
