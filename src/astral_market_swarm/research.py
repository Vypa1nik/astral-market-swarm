"""Reproducible OOS, walk-forward, and cost-sensitivity research."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from typing import Any

from .backtest import BacktestConfig, BacktestResult, run_backtest
from .data_quality import validate_dataset
from .dataset import DatasetManifest, build_manifest
from .events import Candle
from .metrics import calculate_metrics


@dataclass(frozen=True, slots=True)
class CostScenario:
    """Execution-cost assumptions for one research run."""

    name: str
    fee_rate: Decimal
    spread_bps: int
    slippage_bps: int

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("cost scenario name must not be empty")
        if self.fee_rate < 0 or self.spread_bps < 0 or self.slippage_bps < 0:
            raise ValueError("cost assumptions must be non-negative")


_DEFAULT_COST_SCENARIOS = (
    CostScenario("baseline", Decimal("0.001"), 5, 5),
    CostScenario("optimistic", Decimal("0"), 0, 0),
    CostScenario("stress", Decimal("0.0015"), 10, 15),
)


@dataclass(frozen=True, slots=True)
class ResearchConfig:
    """Split, walk-forward, and cost assumptions for an auditable report."""

    split_fraction: Decimal = Decimal("0.7")
    warmup_bars: int = 200
    walk_forward_train_bars: int = 500
    walk_forward_test_bars: int = 100
    walk_forward_step_bars: int = 100
    cost_scenarios: tuple[CostScenario, ...] = _DEFAULT_COST_SCENARIOS

    def __post_init__(self) -> None:
        if not 0 < self.split_fraction < 1:
            raise ValueError("split_fraction must be between 0 and 1")
        if self.warmup_bars < 0:
            raise ValueError("warmup_bars must be non-negative")
        if self.walk_forward_train_bars <= 0:
            raise ValueError("walk_forward_train_bars must be positive")
        if self.walk_forward_test_bars <= 0:
            raise ValueError("walk_forward_test_bars must be positive")
        if self.walk_forward_step_bars <= 0:
            raise ValueError("walk_forward_step_bars must be positive")
        if not self.cost_scenarios:
            raise ValueError("at least one cost scenario is required")
        names = [scenario.name for scenario in self.cost_scenarios]
        if len(names) != len(set(names)):
            raise ValueError("cost scenario names must be unique")


@dataclass(frozen=True, slots=True)
class ResearchMetrics:
    """Metrics for one explicitly bounded research window."""

    start: datetime
    end: datetime
    warmup_bars: int
    start_equity: Decimal
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

    @classmethod
    def from_result(
        cls,
        result: BacktestResult,
        candles: tuple[Candle, ...],
        config: BacktestConfig,
        start_index: int,
        end_index: int,
        warmup_bars: int,
    ) -> ResearchMetrics:
        equity_curve = result.equity_curve[start_index:end_index]
        if not equity_curve:
            raise ValueError("research window must contain at least one candle")
        start_timestamp = candles[start_index].timestamp
        end_timestamp = candles[end_index - 1].timestamp
        trades = tuple(
            trade
            for trade in result.trades
            if start_timestamp <= trade.entry_timestamp <= end_timestamp
        )
        metrics = calculate_metrics(
            equity_curve,
            trades,
            config.initial_cash,
            candles[start_index].close,
            candles[end_index - 1].close,
            result.metrics.total_fees,
        )
        return cls(
            start=start_timestamp,
            end=end_timestamp,
            warmup_bars=warmup_bars,
            start_equity=equity_curve[0],
            ending_equity=metrics.ending_equity,
            net_pnl=metrics.net_pnl,
            total_return=metrics.total_return,
            gross_profit=metrics.gross_profit,
            gross_loss=metrics.gross_loss,
            trade_count=metrics.trade_count,
            win_rate=metrics.win_rate,
            profit_factor=metrics.profit_factor,
            max_drawdown=metrics.max_drawdown,
            total_fees=metrics.total_fees,
            turnover=metrics.turnover,
            benchmark_return=metrics.benchmark_return,
        )


@dataclass(frozen=True, slots=True)
class WalkForwardWindow:
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    train: ResearchMetrics
    test: ResearchMetrics


@dataclass(frozen=True, slots=True)
class CostScenarioResult:
    name: str
    in_sample: ResearchMetrics
    out_of_sample: ResearchMetrics


@dataclass(frozen=True, slots=True)
class ResearchReport:
    dataset: DatasetManifest
    in_sample: ResearchMetrics
    out_of_sample: ResearchMetrics
    walk_forward: tuple[WalkForwardWindow, ...]
    cost_scenarios: tuple[CostScenarioResult, ...]
    warnings: tuple[str, ...]


def _config_for_costs(config: BacktestConfig, scenario: CostScenario) -> BacktestConfig:
    fill_model = replace(
        config.fill_model,
        fee_rate=scenario.fee_rate,
        spread_bps=scenario.spread_bps,
        slippage_bps=scenario.slippage_bps,
    )
    return replace(config, fill_model=fill_model)


def _run_window(
    candles: tuple[Candle, ...],
    config: BacktestConfig,
    start_index: int,
    end_index: int,
    warmup_bars: int,
) -> ResearchMetrics:
    if not 0 <= start_index < end_index <= len(candles):
        raise ValueError("research window must be inside the dataset")
    result = run_backtest(
        list(candles[:end_index]),
        config,
        execution_start=start_index,
        execution_end=end_index,
    )
    return ResearchMetrics.from_result(
        result,
        candles,
        config,
        start_index,
        end_index,
        min(warmup_bars, start_index),
    )


def _warning_messages(
    candles: tuple[Candle, ...],
    in_sample: ResearchMetrics,
    out_of_sample: ResearchMetrics,
    walk_forward: tuple[WalkForwardWindow, ...],
) -> tuple[str, ...]:
    warnings = [
        "Historical simulation is not evidence of future profitability.",
        "No parameter optimization is performed by this report; review selection bias separately.",
    ]
    if len(candles) < 500:
        warnings.append(f"Dataset has only {len(candles)} bars; statistical confidence is limited.")
    if in_sample.trade_count < 30:
        warnings.append(f"In-sample trade count is low: {in_sample.trade_count}.")
    if out_of_sample.trade_count < 30:
        warnings.append(f"Out-of-sample trade count is low: {out_of_sample.trade_count}.")
    if not walk_forward:
        warnings.append("No complete walk-forward window fits the supplied dataset.")
    return tuple(warnings)


def run_research(
    candles: list[Candle],
    backtest_config: BacktestConfig,
    config: ResearchConfig | None = None,
) -> ResearchReport:
    """Run baseline IS/OOS, rolling walk-forward, and cost sensitivity."""

    research_config = config or ResearchConfig()
    if not candles:
        raise ValueError("candles must not be empty")
    ordered = validate_dataset(candles, candles[0].symbol, backtest_config.interval)
    manifest = build_manifest(ordered, ordered[0].symbol, backtest_config.timeframe)
    split_index = int(len(ordered) * research_config.split_fraction)
    if split_index <= 0 or split_index >= len(ordered):
        raise ValueError("split produces an empty in-sample or out-of-sample range")

    baseline = _config_for_costs(backtest_config, research_config.cost_scenarios[0])
    in_sample = _run_window(ordered, baseline, 0, split_index, 0)
    out_of_sample = _run_window(
        ordered,
        baseline,
        split_index,
        len(ordered),
        research_config.warmup_bars,
    )

    walk_forward_items: list[WalkForwardWindow] = []
    test_start = research_config.walk_forward_train_bars
    while test_start + research_config.walk_forward_test_bars <= len(ordered):
        train_start = max(0, test_start - research_config.walk_forward_train_bars)
        test_end = test_start + research_config.walk_forward_test_bars
        train = _run_window(ordered, baseline, train_start, test_start, 0)
        test = _run_window(
            ordered,
            baseline,
            test_start,
            test_end,
            research_config.warmup_bars,
        )
        walk_forward_items.append(
            WalkForwardWindow(
                train_start=train.start,
                train_end=train.end,
                test_start=test.start,
                test_end=test.end,
                train=train,
                test=test,
            )
        )
        test_start += research_config.walk_forward_step_bars

    cost_results: list[CostScenarioResult] = []
    for scenario in research_config.cost_scenarios:
        scenario_config = _config_for_costs(backtest_config, scenario)
        cost_results.append(
            CostScenarioResult(
                scenario.name,
                _run_window(ordered, scenario_config, 0, split_index, 0),
                _run_window(
                    ordered,
                    scenario_config,
                    split_index,
                    len(ordered),
                    research_config.warmup_bars,
                ),
            )
        )

    walk_forward = tuple(walk_forward_items)
    return ResearchReport(
        dataset=manifest,
        in_sample=in_sample,
        out_of_sample=out_of_sample,
        walk_forward=walk_forward,
        cost_scenarios=tuple(cost_results),
        warnings=_warning_messages(ordered, in_sample, out_of_sample, walk_forward),
    )


def _metrics_to_dict(metrics: ResearchMetrics) -> dict[str, Any]:
    return {
        "start": metrics.start.isoformat(),
        "end": metrics.end.isoformat(),
        "warmup_bars": metrics.warmup_bars,
        "start_equity": str(metrics.start_equity),
        "ending_equity": str(metrics.ending_equity),
        "net_pnl": str(metrics.net_pnl),
        "total_return": str(metrics.total_return),
        "gross_profit": str(metrics.gross_profit),
        "gross_loss": str(metrics.gross_loss),
        "trade_count": metrics.trade_count,
        "win_rate": str(metrics.win_rate),
        "profit_factor": None if metrics.profit_factor is None else str(metrics.profit_factor),
        "max_drawdown": str(metrics.max_drawdown),
        "total_fees": str(metrics.total_fees),
        "turnover": str(metrics.turnover),
        "benchmark_return": str(metrics.benchmark_return),
    }


def research_report_to_dict(report: ResearchReport) -> dict[str, Any]:
    """Serialize every report value without losing Decimal precision."""

    return {
        "dataset": {
            "symbol": report.dataset.symbol,
            "timeframe": report.dataset.timeframe,
            "start": report.dataset.start.isoformat(),
            "end": report.dataset.end.isoformat(),
            "row_count": report.dataset.row_count,
            "sha256": report.dataset.sha256,
        },
        "in_sample": _metrics_to_dict(report.in_sample),
        "out_of_sample": _metrics_to_dict(report.out_of_sample),
        "walk_forward": [
            {
                "train_start": item.train_start.isoformat(),
                "train_end": item.train_end.isoformat(),
                "test_start": item.test_start.isoformat(),
                "test_end": item.test_end.isoformat(),
                "train": _metrics_to_dict(item.train),
                "test": _metrics_to_dict(item.test),
            }
            for item in report.walk_forward
        ],
        "cost_scenarios": [
            {
                "name": item.name,
                "in_sample": _metrics_to_dict(item.in_sample),
                "out_of_sample": _metrics_to_dict(item.out_of_sample),
            }
            for item in report.cost_scenarios
        ],
        "warnings": list(report.warnings),
    }
