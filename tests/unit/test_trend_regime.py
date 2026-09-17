"""Tests for the trend_stack entry mode and the trailing/breakeven exit logic."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from astral_market_swarm.events import Candle
from astral_market_swarm.service import profile_config
from astral_market_swarm.strategy import (
    Action,
    StrategyConfig,
    generate_latest_signal,
    generate_signals,
)

START = datetime(2026, 1, 1, tzinfo=UTC)


def candles(closes: list[str], *, spread: str = "0.5") -> list[Candle]:
    out: list[Candle] = []
    for index, close in enumerate(closes):
        value = Decimal(close)
        pad = Decimal(spread)
        out.append(
            Candle(
                symbol="BTC/USDT",
                timestamp=START + timedelta(hours=4 * index),
                open=value,
                high=value + pad,
                low=value - pad,
                close=value,
                volume=Decimal("10"),
            )
        )
    return out


def trend_config(**overrides: object) -> StrategyConfig:
    base: dict[str, object] = {
        "ema_period": 5,
        "ema_fast_period": 2,
        "ema_mid_period": 3,
        "rsi_period": 2,
        "atr_period": 2,
        "atr_stop_multiple": Decimal("3"),
        "take_profit_multiple": Decimal("0"),
        "trail_atr_multiple": Decimal("8"),
        "breakeven_at_r": Decimal("1"),
        "max_hold_bars": 96,
        "entry_mode": "trend_stack",
    }
    base.update(overrides)
    return StrategyConfig(**base)


def test_trend_stack_requires_ordered_ema_periods() -> None:
    with pytest.raises(ValueError, match="trend_stack requires"):
        trend_config(ema_fast_period=50, ema_mid_period=20)


def test_unknown_entry_mode_is_rejected() -> None:
    with pytest.raises(ValueError, match="entry_mode must be one of"):
        StrategyConfig(entry_mode="moon")


def test_take_profit_may_be_disabled_for_pure_trailing_exits() -> None:
    config = trend_config()
    assert config.take_profit_multiple == Decimal("0")
    signals = generate_signals(candles([str(100 + i) for i in range(30)]), config)
    entries = [s for s in signals if s.action is Action.ENTER_LONG]
    assert entries, "a rising series must produce at least one entry"
    assert all(entry.take_profit_price is None for entry in entries)


def test_trend_stack_enters_on_a_stacked_uptrend() -> None:
    signals = generate_signals(candles([str(100 + i * 2) for i in range(30)]), trend_config())
    entry = next(s for s in signals if s.action is Action.ENTER_LONG)
    assert entry.reason == "EMA stack trend regime"
    assert entry.stop_price is not None
    assert entry.stop_price < entry.price


def test_trend_stack_does_not_enter_in_a_downtrend() -> None:
    signals = generate_signals(candles([str(200 - i * 2) for i in range(30)]), trend_config())
    assert not [s for s in signals if s.action is Action.ENTER_LONG]


def test_signals_stay_causal_under_trailing_exits() -> None:
    data = candles([str(100 + i) for i in range(40)])
    config = trend_config()
    assert generate_signals(data[:20], config) == generate_signals(data, config)[:20]


def test_trailing_stop_only_ratchets_upward() -> None:
    """A rise then a fall must exit at a stop above the original stop."""
    closes = [str(100 + i * 3) for i in range(25)] + [str(172 - i * 12) for i in range(10)]
    signals = generate_signals(candles(closes), trend_config(trail_atr_multiple=Decimal("2")))
    entry = next(s for s in signals if s.action is Action.ENTER_LONG)
    exits = [s for s in signals if s.action is Action.EXIT_LONG]
    assert exits, "the sharp reversal must trigger a stop exit"
    assert entry.stop_price is not None
    assert exits[0].price > entry.stop_price


def test_latest_signal_supports_trend_stack() -> None:
    signal = generate_latest_signal(
        candles([str(100 + i * 2) for i in range(30)]), trend_config(), in_position=False
    )
    assert signal.action is Action.ENTER_LONG
    assert signal.reason == "EMA stack trend regime"
    assert signal.take_profit_price is None


def test_latest_signal_matches_batch_signals_for_trend_stack() -> None:
    data = candles([str(100 + i * 2) for i in range(30)])
    config = trend_config()
    batch = generate_signals(data, config)[-1]
    latest = generate_latest_signal(data, config, in_position=False)
    if batch.action is Action.ENTER_LONG:
        assert latest.action is Action.ENTER_LONG


def test_trend_regime_profile_is_validated_on_four_hour_bars() -> None:
    profile = profile_config("trend-regime")
    assert profile.interval == "4h"
    assert profile.strategy.entry_mode == "trend_stack"
    assert profile.strategy.trail_atr_multiple == Decimal("8")
    assert profile.strategy.breakeven_at_r == Decimal("1")
    assert profile.strategy.take_profit_multiple == Decimal("0")
    assert profile.risk.risk_per_trade == Decimal("0.03")
    assert profile.risk.leverage == Decimal("3")
    assert profile.risk.max_signal_age == timedelta(hours=5)


def test_adaptive_regime_exits_an_open_long_when_bear_regime_is_confirmed() -> None:
    config = trend_config(entry_mode="adaptive_regime")
    rising = [str(100 + index * 2) for index in range(25)]
    falling = [str(146 - index * 6) for index in range(16)]
    closes = rising + falling

    signals = generate_signals(candles(closes), config)

    assert any(
        signal.action is Action.EXIT_LONG and signal.reason == "adaptive bear-regime exit to cash"
        for signal in signals
    )


def test_adaptive_regime_profile_uses_bounded_long_or_cash_risk() -> None:
    profile = profile_config("adaptive-regime-paper")

    assert profile.interval == "4h"
    assert profile.strategy.entry_mode == "adaptive_regime"
    assert profile.risk.risk_per_trade == Decimal("0.01")
    assert profile.risk.leverage == Decimal("2")
    assert profile.risk.max_drawdown == Decimal("0.15")


def test_existing_profiles_still_load() -> None:
    assert profile_config("paper-blast").strategy.entry_mode == "momentum"
    assert profile_config("conservative").strategy.entry_mode == "recovery"
    with pytest.raises(ValueError, match="unknown strategy profile"):
        profile_config("live-blast")
