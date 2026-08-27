# Astral Market Swarm — Standalone Trading Engine

Standalone event-driven crypto spot trading engine built independently from all existing bots on the PC.

## Isolation boundary

This repository does **not** import, read, start, stop, or share runtime state with Freqtrade, Hummingbot, OctoBot, or any other existing local bot. It has its own virtual environment, configuration, state database, logs, ports, and API credentials.

## Safety status

- Spot only in v1; no leverage and no shorting.
- Paper/testnet first; live orders are not enabled by default.
- No hard-coded backtest metrics.
- Every order must pass the risk gate.
- Unknown order status is reconciled before any retry.

## Planned layers

`market data → data QA → event-driven backtest → strategy → risk gate → order state machine → paper/testnet adapter → reconciliation → audit/monitoring`

## Development

```text
Python 3.11+
uv sync --extra dev
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

The exchange adapter is intentionally selected after the core engine is tested; no exchange API key belongs in this repository.

## Research references

- Freqtrade: https://github.com/freqtrade/freqtrade
- Freqtrade lookahead analysis: https://www.freqtrade.io/en/stable/lookahead-analysis/
- TradingView strategy testing notes: https://www.tradingview.com/pine-script-docs/concepts/strategies/
- Vibe-Trading research workspace: https://github.com/HKUDS/Vibe-Trading
