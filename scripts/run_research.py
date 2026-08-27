"""Run a real Binance public-data research report."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from astral_market_swarm.backtest import BacktestConfig
from astral_market_swarm.binance_public import BinancePublicData
from astral_market_swarm.research import ResearchConfig, research_report_to_dict, run_research
from astral_market_swarm.risk import RiskConfig
from astral_market_swarm.strategy import StrategyConfig


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument(
        "--interval",
        default="1h",
        choices=("1m", "5m", "15m", "30m", "1h", "4h", "1d"),
    )
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ema-period", type=int, default=50)
    parser.add_argument("--rsi-period", type=int, default=14)
    parser.add_argument("--atr-period", type=int, default=14)
    parser.add_argument("--rsi-recovery", type=Decimal, default=Decimal("50"))
    parser.add_argument("--atr-stop-multiple", type=Decimal, default=Decimal("2"))
    parser.add_argument("--take-profit-multiple", type=Decimal, default=Decimal("2"))
    parser.add_argument("--max-signal-age-minutes", type=int, default=120)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    fetched_at = datetime.now(UTC)
    candles = BinancePublicData().fetch_klines(
        args.symbol,
        args.interval,
        limit=args.limit,
        now=fetched_at,
    )
    interval_minutes = {
        "1m": 1,
        "5m": 5,
        "15m": 15,
        "30m": 30,
        "1h": 60,
        "4h": 240,
        "1d": 1440,
    }[args.interval]
    strategy = StrategyConfig(
        ema_period=args.ema_period,
        rsi_period=args.rsi_period,
        atr_period=args.atr_period,
        rsi_recovery=args.rsi_recovery,
        atr_stop_multiple=args.atr_stop_multiple,
        take_profit_multiple=args.take_profit_multiple,
    )
    backtest_config = BacktestConfig(
        interval_minutes=interval_minutes,
        initial_cash=Decimal("5000"),
        strategy=strategy,
        risk=RiskConfig(max_signal_age=timedelta(minutes=args.max_signal_age_minutes)),
    )
    report = run_research(candles, backtest_config, ResearchConfig())
    payload = research_report_to_dict(report)
    payload["run_config"] = {
        "symbol": args.symbol,
        "interval": args.interval,
        "limit_requested": args.limit,
        "initial_cash": "5000",
        "display_currency": "USDT",
        "strategy": {
            "ema_period": args.ema_period,
            "rsi_period": args.rsi_period,
            "atr_period": args.atr_period,
            "rsi_recovery": str(args.rsi_recovery),
            "atr_stop_multiple": str(args.atr_stop_multiple),
            "take_profit_multiple": str(args.take_profit_multiple),
        },
        "risk": {"max_signal_age_minutes": args.max_signal_age_minutes},
        "research": {
            "split_fraction": "0.7",
            "warmup_bars": 200,
            "walk_forward_train_bars": 500,
            "walk_forward_test_bars": 100,
            "walk_forward_step_bars": 100,
        },
    }
    payload["data_source"] = {
        "provider": "Binance public spot klines",
        "endpoint": "https://api.binance.com/api/v3/klines",
        "fetched_at": fetched_at.isoformat(),
        "closed_bar_rule": "kline close time plus one millisecond is <= fetched_at",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "rows": report.dataset.row_count,
                "sha256": report.dataset.sha256,
                "in_sample_trade_count": report.in_sample.trade_count,
                "out_of_sample_trade_count": report.out_of_sample.trade_count,
                "out_of_sample_return": str(report.out_of_sample.total_return),
                "walk_forward_windows": len(report.walk_forward),
                "warnings": len(report.warnings),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
