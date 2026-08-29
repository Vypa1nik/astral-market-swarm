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

    def __post_init__(self) -> None:
        if min(self.ema_period, self.rsi_period, self.atr_period) < 1:
            raise ValueError("indicator periods must be positive")
        if not 0 < self.rsi_recovery < 100:
            raise ValueError("rsi_recovery must be between 0 and 100")
        if self.atr_stop_multiple <= 0 or self.take_profit_multiple <= 0:
            raise ValueError("ATR multiples must be positive")
        if self.max_hold_bars < 0:
            raise ValueError("max_hold_bars must be non-negative")
        if self.entry_mode not in {"recovery", "momentum"}:
            raise ValueError("entry_mode must be recovery or momentum")


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


def generate_signals(
    candles: Sequence[Candle],
    config: StrategyConfig,
) -> tuple[StrategySignal, ...]:
    """Generate signals using only the current candle and earlier candles."""

    if not candles:
        return ()
    closes = tuple(candle.close for candle in candles)
    ema = _ema(closes, config.ema_period)
    rsi = _rsi(closes, config.rsi_period)
    atr = _atr(candles, config.atr_period)
    signals: list[StrategySignal] = []
    in_position = False
    stop_price: Decimal | None = None
    take_profit_price: Decimal | None = None
    entry_index = 0

    for index, candle in enumerate(candles):
        if in_position:
            assert stop_price is not None
            assert take_profit_price is not None
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
            if candle.high >= take_profit_price:
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
        entry_ready = recovery if config.entry_mode == "recovery" else momentum
        if (
            current_ema is not None
            and current_atr is not None
            and entry_ready
            and candle.close > current_ema
        ):
            stop_price = candle.close - current_atr * config.atr_stop_multiple
            take_profit_price = candle.close + current_atr * config.take_profit_multiple
            if stop_price > 0:
                in_position = True
                entry_index = index
                signals.append(
                    StrategySignal(
                        candle.timestamp,
                        Action.ENTER_LONG,
                        candle.close,
                        (
                            "EMA regime + RSI recovery"
                            if config.entry_mode == "recovery"
                            else "EMA regime + momentum"
                        ),
                        stop_price,
                        take_profit_price,
                    )
                )
                continue
        signals.append(StrategySignal(candle.timestamp, Action.HOLD, candle.close, "no setup"))

    return tuple(signals)
