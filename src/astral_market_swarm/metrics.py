"""Backtest trade records and auditable performance metrics."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class TradeRecord:
    entry_timestamp: datetime
    exit_timestamp: datetime
    quantity: Decimal
    entry_price: Decimal
    exit_price: Decimal
    fees: Decimal
    net_pnl: Decimal
    exit_reason: str


@dataclass(frozen=True, slots=True)
class BacktestMetrics:
    ending_equity: Decimal
    net_pnl: Decimal
    total_return: Decimal
    gross_profit: Decimal
    gross_loss: Decimal
    trade_count: int
    win_rate: Decimal
    profit_factor: Decimal | None
    max_drawdown: Decimal
    total_fees: Decimal
    turnover: Decimal
    benchmark_return: Decimal


def calculate_metrics(
    equity_curve: Sequence[Decimal],
    trades: Sequence[TradeRecord],
    initial_cash: Decimal,
    first_close: Decimal,
    last_close: Decimal,
    total_fees: Decimal,
) -> BacktestMetrics:
    """Calculate metrics from actual equity and trade records."""

    if not equity_curve or initial_cash <= 0 or first_close <= 0:
        raise ValueError("equity curve and prices must be positive")
    ending_equity = equity_curve[-1]
    net_pnl = ending_equity - initial_cash
    gross_profit = sum((max(trade.net_pnl, Decimal("0")) for trade in trades), Decimal("0"))
    gross_loss = sum((max(-trade.net_pnl, Decimal("0")) for trade in trades), Decimal("0"))
    wins = sum(1 for trade in trades if trade.net_pnl > 0)
    trade_count = len(trades)
    win_rate = Decimal(wins) / trade_count if trade_count else Decimal("0")
    profit_factor = gross_profit / gross_loss if gross_loss else None

    peak = equity_curve[0]
    max_drawdown = Decimal("0")
    for equity in equity_curve:
        peak = max(peak, equity)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - equity) / peak)

    turnover = sum(
        (trade.quantity * (trade.entry_price + trade.exit_price) for trade in trades),
        Decimal("0"),
    )
    benchmark_return = last_close / first_close - Decimal("1")
    return BacktestMetrics(
        ending_equity=ending_equity,
        net_pnl=net_pnl,
        total_return=net_pnl / initial_cash,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        trade_count=trade_count,
        win_rate=win_rate,
        profit_factor=profit_factor,
        max_drawdown=max_drawdown,
        total_fees=total_fees,
        turnover=turnover,
        benchmark_return=benchmark_return,
    )
