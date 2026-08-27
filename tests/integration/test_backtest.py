from datetime import UTC, datetime
from decimal import Decimal

from astral_market_swarm.backtest import BacktestConfig, run_backtest
from astral_market_swarm.events import Candle
from astral_market_swarm.strategy import StrategyConfig

START = datetime(2026, 1, 1, tzinfo=UTC)


def make_candles(closes: list[str]) -> list[Candle]:
    result: list[Candle] = []
    for index, close in enumerate(closes):
        value = Decimal(close)
        result.append(
            Candle(
                symbol="BTC/USDT",
                timestamp=START.replace(minute=index * 5),
                open=value,
                high=value + Decimal("1"),
                low=value - Decimal("1"),
                close=value,
                volume=Decimal("100"),
            )
        )
    return result


def test_backtest_computes_trades_costs_drawdown_and_benchmark() -> None:
    result = run_backtest(
        make_candles(["100", "102", "100", "98", "99", "102", "99", "95"]),
        BacktestConfig(
            interval_minutes=5,
            initial_cash=Decimal("5000"),
            strategy=StrategyConfig(
                ema_period=2,
                rsi_period=2,
                atr_period=2,
                rsi_recovery=Decimal("30"),
                atr_stop_multiple=Decimal("1"),
                take_profit_multiple=Decimal("1"),
            ),
        ),
    )

    assert result.metrics.trade_count >= 1
    assert result.metrics.total_fees > 0
    assert result.metrics.max_drawdown >= 0
    assert result.metrics.benchmark_return < 0
    assert len(result.manifest.sha256) == 64
    assert result.metrics.ending_equity > 0


def test_backtest_oos_execution_starts_flat_at_boundary() -> None:
    data = make_candles(["100", "102", "100", "98", "99", "102", "99", "95"])
    result = run_backtest(
        data,
        BacktestConfig(
            interval_minutes=5,
            initial_cash=Decimal("5000"),
            strategy=StrategyConfig(ema_period=2, rsi_period=2, atr_period=2),
        ),
        execution_start=4,
    )

    assert all(value == Decimal("5000") for value in result.equity_curve[:4])
    assert all(trade.entry_timestamp >= data[4].timestamp for trade in result.trades)
