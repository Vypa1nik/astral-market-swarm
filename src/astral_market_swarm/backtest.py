"""Causal event-driven backtesting for the standalone spot engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from .data_quality import validate_dataset
from .dataset import DatasetManifest, build_manifest
from .events import Candle
from .fills import FillModel, Order, OrderSide, OrderType
from .metrics import BacktestMetrics, TradeRecord, calculate_metrics
from .risk import RiskConfig, RiskContext, RiskRejected, size_entry
from .strategy import Action, StrategyConfig, StrategySignal, generate_signals


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    interval_minutes: int = 5
    initial_cash: Decimal = Decimal("5000")
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    fill_model: FillModel = field(default_factory=FillModel)

    def __post_init__(self) -> None:
        if self.interval_minutes <= 0:
            raise ValueError("interval_minutes must be positive")
        if self.initial_cash <= 0:
            raise ValueError("initial_cash must be positive")

    @property
    def interval(self) -> timedelta:
        return timedelta(minutes=self.interval_minutes)

    @property
    def timeframe(self) -> str:
        return f"{self.interval_minutes}m"


@dataclass(frozen=True, slots=True)
class BacktestResult:
    manifest: DatasetManifest
    trades: tuple[TradeRecord, ...]
    equity_curve: tuple[Decimal, ...]
    metrics: BacktestMetrics


@dataclass(slots=True)
class _OpenPosition:
    entry_timestamp: datetime
    entry_price: Decimal
    quantity: Decimal
    borrowed_notional: Decimal
    entry_fee: Decimal
    stop_price: Decimal
    take_profit_price: Decimal | None


def _trade_from_exit(
    position: _OpenPosition,
    fill_price: Decimal,
    fee: Decimal,
    timestamp: datetime,
    reason: str,
) -> TradeRecord:
    total_fees = position.entry_fee + fee
    net_pnl = (fill_price - position.entry_price) * position.quantity - total_fees
    return TradeRecord(
        entry_timestamp=position.entry_timestamp,
        exit_timestamp=timestamp,
        quantity=position.quantity,
        entry_price=position.entry_price,
        exit_price=fill_price,
        fees=total_fees,
        net_pnl=net_pnl,
        exit_reason=reason,
    )


def run_backtest(
    candles: list[Candle],
    config: BacktestConfig,
    execution_start: int = 0,
    execution_end: int | None = None,
) -> BacktestResult:
    """Run causal signal logic with an optional flat execution window."""

    if not candles:
        raise ValueError("candles must not be empty")
    ordered = validate_dataset(candles, candles[0].symbol, config.interval)
    if execution_end is None:
        execution_end = len(ordered)
    if not 0 <= execution_start < execution_end <= len(ordered):
        raise ValueError("execution window must be inside the dataset")
    simulated = ordered[:execution_end]
    manifest = build_manifest(simulated, simulated[0].symbol, config.timeframe)
    signals = generate_signals(ordered, config.strategy)
    cash = config.initial_cash
    position: _OpenPosition | None = None
    pending_signal: StrategySignal | None = None
    trades: list[TradeRecord] = []
    equity_curve: list[Decimal] = []
    total_fees = Decimal("0")
    peak_equity = config.initial_cash

    for index, candle in enumerate(simulated):
        if index >= execution_start and pending_signal is not None:
            signal = pending_signal
            if signal.action is Action.ENTER_LONG and position is None:
                if signal.stop_price is None:
                    raise ValueError("entry signal is missing stop price")
                context = RiskContext(
                    equity=cash,
                    cash=cash,
                    gross_exposure=Decimal("0"),
                    peak_equity=peak_equity,
                    daily_pnl=Decimal("0"),
                    signal_timestamp=signal.timestamp,
                    now=candle.timestamp,
                )
                try:
                    decision = size_entry(candle.open, signal.stop_price, context, config.risk)
                except RiskRejected:
                    decision = None
                if decision is not None:
                    entry_order = Order(
                        order_id=f"entry-{index}",
                        symbol=candle.symbol,
                        side=OrderSide.BUY,
                        order_type=OrderType.MARKET,
                        quantity=decision.quantity,
                    )
                    fill = config.fill_model.fill(entry_order, candle)
                    if fill is not None:
                        notional = fill.price * fill.quantity
                        margin = notional / config.risk.leverage
                        borrowed = notional - margin
                        cash -= margin + fill.fee
                        position = _OpenPosition(
                            entry_timestamp=fill.timestamp,
                            entry_price=fill.price,
                            quantity=fill.quantity,
                            borrowed_notional=borrowed,
                            entry_fee=fill.fee,
                            stop_price=signal.stop_price,
                            take_profit_price=signal.take_profit_price,
                        )
                        total_fees += fill.fee
            elif signal.action is Action.EXIT_LONG and position is not None:
                exit_order = Order(
                    order_id=f"exit-{index}",
                    symbol=candle.symbol,
                    side=OrderSide.SELL,
                    order_type=OrderType.MARKET,
                    quantity=position.quantity,
                )
                fill = config.fill_model.fill(exit_order, candle)
                if fill is not None:
                    cash += fill.price * fill.quantity - fill.fee - position.borrowed_notional
                    trades.append(
                        _trade_from_exit(
                            position,
                            fill.price,
                            fill.fee,
                            fill.timestamp,
                            signal.reason,
                        )
                    )
                    total_fees += fill.fee
                    position = None
            pending_signal = None

        if position is not None:
            protective_reason: str | None = None
            reference_price: Decimal | None = None
            if candle.low <= position.stop_price:
                protective_reason = "protective stop"
                reference_price = min(position.stop_price, candle.open)
            elif (
                position.take_profit_price is not None
                and candle.high >= position.take_profit_price
            ):
                protective_reason = "take profit"
                reference_price = max(position.take_profit_price, candle.open)
            if protective_reason is not None and reference_price is not None:
                exit_order = Order(
                    order_id=f"protective-exit-{index}",
                    symbol=candle.symbol,
                    side=OrderSide.SELL,
                    order_type=OrderType.MARKET,
                    quantity=position.quantity,
                )
                fill = config.fill_model.fill(exit_order, candle, reference_price)
                if fill is not None:
                    cash += fill.price * fill.quantity - fill.fee - position.borrowed_notional
                    trades.append(
                        _trade_from_exit(
                            position,
                            fill.price,
                            fill.fee,
                            fill.timestamp,
                            protective_reason,
                        )
                    )
                    total_fees += fill.fee
                    position = None

        if index >= execution_start:
            current_signal = signals[index]
            if (
                current_signal.action is Action.ENTER_LONG
                and position is None
                or current_signal.action is Action.EXIT_LONG
                and position is not None
            ):
                pending_signal = current_signal

        equity = (
            cash
            if position is None
            else cash + position.quantity * candle.close - position.borrowed_notional
        )
        equity_curve.append(equity)
        peak_equity = max(peak_equity, equity)

    metrics = calculate_metrics(
        equity_curve,
        trades,
        config.initial_cash,
        ordered[0].close,
        simulated[-1].close,
        total_fees,
    )
    return BacktestResult(manifest, tuple(trades), tuple(equity_curve), metrics)
