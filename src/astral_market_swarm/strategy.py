"""Causal EMA/RSI/ATR spot strategy hypothesis."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from .events import Candle


class Action(Enum):
    HOLD = "hold"
    ENTER_LONG = "enter_long"
    EXIT_LONG = "exit_long"


ENTRY_MODES = frozenset({"recovery", "momentum", "trend_stack"})


@dataclass(frozen=True, slots=True)
class StrategyConfig:
    ema_period: int = 200
    rsi_period: int = 14
    atr_period: int = 14
    rsi_recovery: Decimal = Decimal("30")
    atr_stop_multiple: Decimal = Decimal("2")
    take_profit_multiple: Decimal = Decimal("2")
    max_hold_bars: int = 0
    entry_mode: str = "recovery"
    ema_fast_period: int = 20
    ema_mid_period: int = 50
    trail_atr_multiple: Decimal = Decimal("0")
    breakeven_at_r: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if min(self.ema_period, self.rsi_period, self.atr_period) < 1:
            raise ValueError("indicator periods must be positive")
        if min(self.ema_fast_period, self.ema_mid_period) < 1:
            raise ValueError("indicator periods must be positive")
        if not 0 < self.rsi_recovery < 100:
            raise ValueError("rsi_recovery must be between 0 and 100")
        if self.atr_stop_multiple <= 0:
            raise ValueError("ATR multiples must be positive")
        if self.take_profit_multiple < 0:
            raise ValueError("take_profit_multiple must be non-negative")
        if self.trail_atr_multiple < 0 or self.breakeven_at_r < 0:
            raise ValueError("trail and breakeven multiples must be non-negative")
        if self.max_hold_bars < 0:
            raise ValueError("max_hold_bars must be non-negative")
        if self.entry_mode not in ENTRY_MODES:
            raise ValueError(f"entry_mode must be one of {sorted(ENTRY_MODES)}")
        if self.entry_mode == "trend_stack" and not (
            self.ema_fast_period < self.ema_mid_period < self.ema_period
        ):
            raise ValueError("trend_stack requires ema_fast < ema_mid < ema_period")


@dataclass(frozen=True, slots=True)
class StrategySignal:
    timestamp: datetime
    action: Action
    price: Decimal
    reason: str
    stop_price: Decimal | None = None
    take_profit_price: Decimal | None = None


def _sma(values: Sequence[Decimal], period: int) -> tuple[Decimal | None, ...]:
    result: list[Decimal | None] = [None] * len(values)
    if len(values) < period:
        return tuple(result)
    window_sum = sum(values[:period], Decimal("0"))
    result[period - 1] = window_sum / period
    for index in range(period, len(values)):
        window_sum += values[index] - values[index - period]
        result[index] = window_sum / period
    return tuple(result)


def _ema(values: Sequence[Decimal], period: int) -> tuple[Decimal | None, ...]:
    result: list[Decimal | None] = [None] * len(values)
    seed = _sma(values, period)
    if len(values) < period or seed[period - 1] is None:
        return tuple(result)
    seed_value = seed[period - 1]
    if seed_value is None:
        return tuple(result)
    previous = seed_value
    result[period - 1] = previous
    alpha = Decimal("2") / Decimal(period + 1)
    for index in range(period, len(values)):
        previous = (values[index] - previous) * alpha + previous
        result[index] = previous
    return tuple(result)


def _rsi(closes: Sequence[Decimal], period: int) -> tuple[Decimal | None, ...]:
    result: list[Decimal | None] = [None] * len(closes)
    if len(closes) <= period:
        return tuple(result)

    gains = [Decimal("0")] * len(closes)
    losses = [Decimal("0")] * len(closes)
    for index in range(1, len(closes)):
        change = closes[index] - closes[index - 1]
        gains[index] = max(change, Decimal("0"))
        losses[index] = max(-change, Decimal("0"))

    average_gain = sum(gains[1 : period + 1], Decimal("0")) / period
    average_loss = sum(losses[1 : period + 1], Decimal("0")) / period
    result[period] = _rsi_value(average_gain, average_loss)
    for index in range(period + 1, len(closes)):
        average_gain = (average_gain * (period - 1) + gains[index]) / period
        average_loss = (average_loss * (period - 1) + losses[index]) / period
        result[index] = _rsi_value(average_gain, average_loss)
    return tuple(result)


def _rsi_value(average_gain: Decimal, average_loss: Decimal) -> Decimal:
    if average_loss == 0:
        return Decimal("100") if average_gain > 0 else Decimal("50")
    return Decimal("100") - Decimal("100") / (Decimal("1") + average_gain / average_loss)


def _atr(candles: Sequence[Candle], period: int) -> tuple[Decimal | None, ...]:
    result: list[Decimal | None] = [None] * len(candles)
    if len(candles) < period:
        return tuple(result)
    true_ranges: list[Decimal] = []
    for index, candle in enumerate(candles):
        if index == 0:
            true_ranges.append(candle.high - candle.low)
            continue
        previous_close = candles[index - 1].close
        true_ranges.append(
            max(
                candle.high - candle.low,
                abs(candle.high - previous_close),
                abs(candle.low - previous_close),
            )
        )

    average = sum(true_ranges[:period], Decimal("0")) / period
    result[period - 1] = average
    for index in range(period, len(candles)):
        average = (average * (period - 1) + true_ranges[index]) / period
        result[index] = average
    return tuple(result)


def _entry_reason(entry_mode: str) -> str:
    if entry_mode == "recovery":
        return "EMA regime + RSI recovery"
    if entry_mode == "momentum":
        return "EMA regime + momentum"
    return "EMA stack trend regime"


def generate_signals(
    candles: Sequence[Candle],
    config: StrategyConfig,
) -> tuple[StrategySignal, ...]:
    """Generate signals using only the current candle and earlier candles."""

    if not candles:
        return ()
    closes = tuple(candle.close for candle in candles)
    ema = _ema(closes, config.ema_period)
    ema_fast = _ema(closes, config.ema_fast_period)
    ema_mid = _ema(closes, config.ema_mid_period)
    rsi = _rsi(closes, config.rsi_period)
    atr = _atr(candles, config.atr_period)
    signals: list[StrategySignal] = []
    in_position = False
    stop_price: Decimal | None = None
    take_profit_price: Decimal | None = None
    entry_index = 0
    entry_price = Decimal("0")
    risk_unit = Decimal("0")
    trail_distance = Decimal("0")
    run_high = Decimal("0")

    for index, candle in enumerate(candles):
        if in_position:
            assert stop_price is not None
            # Trailing stop and breakeven ratchet: both only ever raise the stop.
            if candle.high > run_high:
                run_high = candle.high
            if trail_distance > 0:
                trailed = run_high - trail_distance
                if trailed > stop_price:
                    stop_price = trailed
            if config.breakeven_at_r > 0 and risk_unit > 0:
                trigger = entry_price + risk_unit * config.breakeven_at_r
                if run_high >= trigger and entry_price > stop_price:
                    stop_price = entry_price
            if candle.low <= stop_price:
                signals.append(
                    StrategySignal(
                        candle.timestamp,
                        Action.EXIT_LONG,
                        stop_price,
                        "protective stop",
                    )
                )
                in_position = False
                stop_price = None
                take_profit_price = None
                continue
            if take_profit_price is not None and candle.high >= take_profit_price:
                signals.append(
                    StrategySignal(
                        candle.timestamp,
                        Action.EXIT_LONG,
                        take_profit_price,
                        "take profit",
                    )
                )
                in_position = False
                stop_price = None
                take_profit_price = None
                continue
            if config.max_hold_bars and index - entry_index >= config.max_hold_bars:
                signals.append(
                    StrategySignal(candle.timestamp, Action.EXIT_LONG, candle.close, "time stop")
                )
                in_position = False
                stop_price = None
                take_profit_price = None
                continue
            signals.append(
                StrategySignal(candle.timestamp, Action.HOLD, candle.close, "in position")
            )
            continue

        previous_rsi = rsi[index - 1] if index > 0 else None
        current_ema = ema[index]
        current_rsi = rsi[index]
        current_atr = atr[index]
        recovery = (
            previous_rsi is not None
            and current_rsi is not None
            and previous_rsi <= config.rsi_recovery
            and current_rsi > config.rsi_recovery
        )
        momentum = (
            index > 0
            and current_ema is not None
            and candle.close > current_ema
            and candle.close > candles[index - 1].close
        )
        trend_stack = (
            index > 0
            and current_ema is not None
            and ema_fast[index] is not None
            and ema_mid[index] is not None
            and candle.close > current_ema
            and ema_fast[index] > ema_mid[index] > current_ema  # type: ignore[operator]
            and candle.close > candles[index - 1].close
        )
        if config.entry_mode == "recovery":
            entry_ready = recovery
        elif config.entry_mode == "momentum":
            entry_ready = momentum
        else:
            entry_ready = trend_stack
        if (
            current_ema is not None
            and current_atr is not None
            and entry_ready
            and candle.close > current_ema
        ):
            stop_price = candle.close - current_atr * config.atr_stop_multiple
            take_profit_price = (
                candle.close + current_atr * config.take_profit_multiple
                if config.take_profit_multiple > 0
                else None
            )
            if stop_price > 0:
                in_position = True
                entry_index = index
                entry_price = candle.close
                risk_unit = current_atr * config.atr_stop_multiple
                trail_distance = current_atr * config.trail_atr_multiple
                run_high = candle.high
                signals.append(
                    StrategySignal(
                        candle.timestamp,
                        Action.ENTER_LONG,
                        candle.close,
                        _entry_reason(config.entry_mode),
                        stop_price,
                        take_profit_price,
                    )
                )
                continue
        signals.append(StrategySignal(candle.timestamp, Action.HOLD, candle.close, "no setup"))

    return tuple(signals)


def generate_latest_signal(
    candles: Sequence[Candle],
    config: StrategyConfig,
    in_position: bool,
) -> StrategySignal:
    """Evaluate only the latest bar using the executor's real position state."""

    if not candles:
        raise ValueError("candles must not be empty")
    signals = generate_signals(candles, config)
    latest = signals[-1]
    if in_position:
        if latest.action is Action.EXIT_LONG:
            return latest
        return StrategySignal(candles[-1].timestamp, Action.HOLD, candles[-1].close, "in position")
    if latest.action is Action.ENTER_LONG:
        return latest
    if len(candles) < 2:
        return latest
    closes = tuple(candle.close for candle in candles)
    ema = _ema(closes, config.ema_period)[-1]
    atr = _atr(candles, config.atr_period)[-1]
    if ema is None or atr is None or candles[-1].close <= ema:
        return StrategySignal(candles[-1].timestamp, Action.HOLD, candles[-1].close, "no setup")
    previous_rsi = _rsi(closes, config.rsi_period)[-2]
    current_rsi = _rsi(closes, config.rsi_period)[-1]
    recovery = (
        previous_rsi is not None
        and current_rsi is not None
        and previous_rsi <= config.rsi_recovery
        and current_rsi > config.rsi_recovery
    )
    momentum = candles[-1].close > candles[-2].close
    if config.entry_mode == "recovery":
        entry_ready = recovery
    elif config.entry_mode == "momentum":
        entry_ready = momentum
    else:
        fast = _ema(closes, config.ema_fast_period)[-1]
        mid = _ema(closes, config.ema_mid_period)[-1]
        entry_ready = fast is not None and mid is not None and fast > mid > ema and momentum
    if not entry_ready:
        return StrategySignal(candles[-1].timestamp, Action.HOLD, candles[-1].close, "no setup")
    stop = candles[-1].close - atr * config.atr_stop_multiple
    take_profit = (
        candles[-1].close + atr * config.take_profit_multiple
        if config.take_profit_multiple > 0
        else None
    )
    if stop <= 0:
        return StrategySignal(candles[-1].timestamp, Action.HOLD, candles[-1].close, "invalid stop")
    return StrategySignal(
        candles[-1].timestamp,
        Action.ENTER_LONG,
        candles[-1].close,
        _entry_reason(config.entry_mode),
        stop,
        take_profit,
    )
