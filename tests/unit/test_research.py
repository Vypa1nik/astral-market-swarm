from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from astral_market_swarm.backtest import BacktestConfig
from astral_market_swarm.events import Candle
from astral_market_swarm.research import (
    CostScenario,
    ResearchConfig,
    research_report_to_dict,
    run_research,
)
from astral_market_swarm.strategy import StrategyConfig

START = datetime(2026, 1, 1, tzinfo=UTC)


def make_candles(count: int = 40) -> list[Candle]:
    candles: list[Candle] = []
    value = Decimal("100")
    for index in range(count):
        if index % 7 in (0, 1):
            value += Decimal("2")
        elif index % 7 in (3, 4):
            value -= Decimal("3")
        candles.append(
            Candle(
                symbol="BTC/USDT",
                timestamp=START + timedelta(minutes=index * 5),
                open=value,
                high=value + Decimal("2"),
                low=value - Decimal("2"),
                close=value,
                volume=Decimal("1000"),
            )
        )
    return candles


def test_research_report_contains_oos_walk_forward_and_cost_scenarios() -> None:
    backtest_config = BacktestConfig(
        interval_minutes=5,
        initial_cash=Decimal("5000"),
        strategy=StrategyConfig(ema_period=3, rsi_period=2, atr_period=2),
    )
    config = ResearchConfig(
        split_fraction=Decimal("0.6"),
        warmup_bars=5,
        walk_forward_train_bars=10,
        walk_forward_test_bars=5,
        walk_forward_step_bars=5,
        cost_scenarios=(
            CostScenario("free", Decimal("0"), 0, 0),
            CostScenario("baseline", Decimal("0.001"), 5, 5),
        ),
    )

    report = run_research(make_candles(), backtest_config, config)

    assert report.dataset.row_count == 40
    assert report.in_sample.trade_count >= 0
    assert report.out_of_sample.warmup_bars == 5
    assert report.out_of_sample.start_equity > 0
    assert report.walk_forward
    assert {item.name for item in report.cost_scenarios} == {"free", "baseline"}

    payload = research_report_to_dict(report)
    assert payload["dataset"]["sha256"] == report.dataset.sha256
    assert payload["out_of_sample"]["ending_equity"] == str(report.out_of_sample.ending_equity)
    assert payload["warnings"]


def test_research_rejects_invalid_walk_forward_configuration() -> None:
    with pytest.raises(ValueError, match="walk_forward_test_bars"):
        ResearchConfig(walk_forward_test_bars=0)
