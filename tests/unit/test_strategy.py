from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from astral_market_swarm.events import Candle
from astral_market_swarm.risk import RiskConfig, RiskContext, RiskRejected, size_entry
from astral_market_swarm.strategy import (
    Action,
    StrategyConfig,
    generate_latest_signal,
    generate_signals,
)

START = datetime(2026, 1, 1, tzinfo=UTC)


def candles(closes: list[str]) -> list[Candle]:
    result: list[Candle] = []
    for index, close in enumerate(closes):
        value = Decimal(close)
        result.append(
            Candle(
                symbol="BTC/USDT",
                timestamp=START + timedelta(minutes=5 * index),
                open=value,
                high=value + Decimal("1"),
                low=value - Decimal("1"),
                close=value,
                volume=Decimal("10"),
            )
        )
    return result


def test_strategy_emits_long_entry_only_after_causal_warmup() -> None:
    data = candles(["100", "102", "100", "98", "99", "102"])
    config = StrategyConfig(ema_period=2, rsi_period=2, atr_period=2, rsi_recovery=30)

    signals = generate_signals(data, config)

    assert signals[0].action is Action.HOLD
    assert all(signal.timestamp <= data[-1].timestamp for signal in signals)
    assert any(signal.action is Action.ENTER_LONG for signal in signals)
    entry = next(signal for signal in signals if signal.action is Action.ENTER_LONG)
    assert entry.stop_price is not None
    assert entry.take_profit_price is not None
    assert entry.stop_price < entry.price < entry.take_profit_price


def test_strategy_signal_for_prefix_matches_same_timestamps_in_full_run() -> None:
    data = candles(["100", "102", "100", "98", "99", "102", "101"])
    config = StrategyConfig(ema_period=2, rsi_period=2, atr_period=2, rsi_recovery=30)

    prefix = generate_signals(data[:6], config)
    full = generate_signals(data, config)[:6]

    assert prefix == full


def test_momentum_mode_emits_a_causal_breakout_entry() -> None:
    data = candles(["100", "101", "102", "101"])
    config = StrategyConfig(
        ema_period=2,
        rsi_period=2,
        atr_period=2,
        entry_mode="momentum",
        max_hold_bars=2,
    )

    signals = generate_signals(data, config)

    assert any(signal.action is Action.ENTER_LONG for signal in signals)
    entry = next(signal for signal in signals if signal.action is Action.ENTER_LONG)
    assert entry.reason == "EMA regime + momentum"


def test_latest_signal_does_not_inherit_historical_position_when_runtime_is_flat() -> None:
    data = candles(["100", "101", "102", "103", "104"])
    config = StrategyConfig(ema_period=2, rsi_period=2, atr_period=2, entry_mode="momentum")

    signal = generate_latest_signal(data, config, in_position=False)

    assert signal.action is Action.ENTER_LONG
    assert signal.reason == "EMA regime + momentum"


def context(**overrides: object) -> RiskContext:
    values: dict[str, object] = {
        "equity": Decimal("10000"),
        "cash": Decimal("10000"),
        "gross_exposure": Decimal("0"),
        "peak_equity": Decimal("10000"),
        "daily_pnl": Decimal("0"),
        "signal_timestamp": START,
        "now": START + timedelta(minutes=1),
        "kill_switch": False,
    }
    values.update(overrides)
    return RiskContext(**values)


def test_risk_sizes_by_stop_distance_and_caps_exposure() -> None:
    decision = size_entry(
        entry_price=Decimal("100"),
        stop_price=Decimal("95"),
        context=context(),
        config=RiskConfig(risk_per_trade=Decimal("0.005")),
    )

    assert decision.approved is True
    assert decision.quantity == Decimal("10")
    assert decision.notional == Decimal("1000")


def test_risk_leverage_can_expand_cash_headroom_but_respects_exposure_cap() -> None:
    decision = size_entry(
        entry_price=Decimal("100"),
        stop_price=Decimal("99.5"),
        context=context(),
        config=RiskConfig(
            risk_per_trade=Decimal("0.01"),
            leverage=Decimal("3"),
            max_position_fraction=Decimal("1.5"),
            max_gross_exposure_fraction=Decimal("1.5"),
        ),
    )

    assert decision.approved is True
    assert decision.notional == Decimal("15000")
    assert decision.notional > context().cash


@pytest.mark.parametrize(
    "overrides,error",
    [
        ({"kill_switch": True}, "kill switch"),
        ({"now": START + timedelta(minutes=20)}, "stale"),
        ({"daily_pnl": Decimal("-400")}, "daily loss"),
        ({"equity": Decimal("8000")}, "drawdown"),
    ],
)
def test_risk_rejects_account_and_signal_guards(overrides: dict[str, object], error: str) -> None:
    with pytest.raises(RiskRejected, match=error):
        size_entry(
            entry_price=Decimal("100"),
            stop_price=Decimal("95"),
            context=context(**overrides),
            config=RiskConfig(max_drawdown=Decimal("0.1")),
        )


def test_risk_rejects_invalid_stop_and_no_cash() -> None:
    with pytest.raises(RiskRejected, match="stop"):
        size_entry(Decimal("100"), Decimal("100"), context(), RiskConfig())

    with pytest.raises(RiskRejected, match="cash"):
        size_entry(
            Decimal("100"),
            Decimal("95"),
            context(cash=Decimal("0")),
            RiskConfig(),
        )
