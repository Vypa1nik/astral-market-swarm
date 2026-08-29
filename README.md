# Astral Market Swarm — Standalone Trading Engine

Standalone event-driven crypto spot trading engine built independently from all existing bots on the PC.

## Isolation boundary

This repository does **not** import, read, start, stop, or share runtime state with Freqtrade, Hummingbot, OctoBot, or any other existing local bot. It has its own virtual environment, configuration, state database, logs, ports, and API credentials.

## Safety status

- Spot long-only in v1; no shorting. The default `conservative` profile uses 1x.
- Optional `paper-blast` is a clearly labeled, isolated 3x margin simulation only; it cannot submit live orders.
- Paper account starts with 5,000 virtual USDT; no real funds are connected.
- Paper/testnet first; live orders are not enabled by default.
- No hard-coded backtest metrics.
- Every order must pass the risk gate.
- Unknown order status is reconciled before any retry.

## Planned layers

`market data → data QA → event-driven backtest → strategy → risk gate → order state machine → paper/testnet adapter → reconciliation → audit/monitoring`

## Quick Start

### Local Development

```bash
# Install dependencies
uv sync --extra dev

# Run tests
uv run pytest -q

# Run linting and type checking
uv run ruff check .
uv run ruff format --check .
uv run mypy src

# Start paper trading
uv run python -m astral_market_swarm.app
```

### Docker Deployment

```bash
# Build and start the container
docker-compose up -d

# Check logs
docker-compose logs -f

# Check health
curl http://localhost:8080/health

# Stop
docker-compose down
```

### Configuration

Create a `.env` file (optional, defaults provided):

```env
SYMBOL=BTC/USDT
INTERVAL=5m
DEMO_CASH=5000
LOOKBACK=250
POLL_SECONDS=300
```

See [PIPELINE_SCHEMA.md](./PIPELINE_SCHEMA.md) for full architecture details.

The exchange adapter is intentionally selected after the core engine is tested; no exchange API key belongs in this repository.

## Historical research

The research runner fetches closed public Binance spot klines and writes an auditable JSON report. It includes the dataset SHA-256, in-sample metrics, a flat-start out-of-sample window, rolling walk-forward windows, and optimistic/baseline/stress execution-cost scenarios.

```bash
uv run python scripts/run_research.py \
  --symbol BTCUSDT \
  --interval 1d \
  --limit 1000 \
  --ema-period 50 \
  --rsi-recovery 50 \
  --max-signal-age-minutes 2880 \
  --output reports/candidate-1d.json
```

The report is research-only. A positive return with a small trade count is not a promotion criterion, and this command never changes the paper or live runtime configuration.

## Paper profiles

The runtime defaults to the conservative EMA/RSI recovery profile. For controlled paper experimentation only, set `STRATEGY_PROFILE=paper-blast`. This profile uses an EMA20 momentum entry, 1.5x gross/position caps, 1% risk per trade, a 3x simulated leverage ceiling, an 8% daily-loss guard, a 25% drawdown guard, and a 12-bar time stop. It is intentionally not a profitability claim: it can lose the virtual account quickly and must remain paper-only.

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
