# Astral Market Swarm — Standalone Trading Engine

Standalone event-driven crypto spot trading engine built independently from all existing bots on the PC.

## Isolation boundary

This repository does **not** import, read, start, stop, or share runtime state with Freqtrade, Hummingbot, OctoBot, or any other existing local bot. It has its own virtual environment, configuration, state database, logs, ports, and API credentials.

## Safety status

- Spot only in v1; no leverage and no shorting.
- Paper account starts with 5,000 virtual USDT; no real funds are connected.
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

## Hostinger deployment boundary

The intended public hostname is `quantbot.sokezzz.com`. Deployment must be performed as a new Compose project and volume after a read-only inventory of the Hostinger host:

```text
docker ps -a
docker network ls
docker inspect <existing-service> --format '{{json .Config.Labels}}'
docker inspect <existing-service> --format '{{json .HostConfig.Binds}}'
```

Do not reuse an existing directory, volume, container, network namespace, `.env`, or process. Build on the Linux host, create the new DNS record only after the target IP is confirmed, and verify old container IDs/start times before and after deployment. The Compose file exposes only read-only health/state routes; it has no kill/resume API.

Cloudflare credentials are deliberately absent from Git. Use a narrowly scoped DNS-edit token from the deployment operator's secret store. Never paste it into source, logs, or a public report.

## Research references

- Freqtrade: https://github.com/freqtrade/freqtrade
- Freqtrade lookahead analysis: https://www.freqtrade.io/en/stable/lookahead-analysis/
- TradingView strategy testing notes: https://www.tradingview.com/pine-script-docs/concepts/strategies/
- Vibe-Trading research workspace: https://github.com/HKUDS/Vibe-Trading
