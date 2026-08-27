# Astral Market Swarm Standalone Design

**Date:** 2026-08-27
**Status:** Approved by user
**Target:** One crypto spot exchange, paper/testnet first
**Isolation:** New independent repository; existing local bots are out of scope

## Purpose

Build a standalone event-driven crypto spot engine that tests a concrete trading hypothesis using causal data, realistic costs, controlled risk, and a paper/testnet execution path before any live order surface is considered.

## Non-goals for v1

- No leverage, shorting, futures, funding, or liquidation logic.
- No market making or cross-exchange arbitrage.
- No Freqtrade, Hummingbot, OctoBot, or other bot-framework runtime dependency.
- No LLM or 29-agent swarm inside the order-decision loop.
- No automatic model retraining.
- No withdrawal permission or live trading by default.

## Components

1. **Market data adapter** — exchange-specific REST/WebSocket implementation behind a local interface; validates timestamps and source identity.
2. **Data QA and normalizer** — rejects duplicates, non-monotonic timestamps, invalid OHLCV, stale events, and malformed symbol/precision data.
3. **Event-driven backtester** — consumes the same normalized event types as paper runtime; models fees, spread, slippage, order latency, partial fills, and unavailable liquidity.
4. **Strategy** — deterministic long/flat baseline derived from the supplied EMA/RSI/ATR idea. Initial hypothesis: trend regime plus pullback/recovery, ATR-normalized exits, and an explicit volume/volatility filter. Parameters are configuration, not optimized on the final holdout.
5. **Risk engine** — calculates size from stop distance and equity, then applies max position, max gross exposure, daily loss, drawdown, stale-data, precision, and balance guards.
6. **Order state machine** — persists order intent before submission and models created, submitted, acknowledged, partially filled, filled, cancelled, rejected, and unknown states. Unknown state requires reconciliation before retry.
7. **Paper/testnet executor** — disabled by default until the chosen exchange and credentials are explicitly configured; live and paper endpoints are structurally separated.
8. **Reconciliation and audit** — compares local state with exchange state, records every decision and response without secrets, and activates a kill switch on contradiction.
9. **Reports** — actual metrics only: net/gross return, costs, trade count, expectancy, drawdown, Sharpe/Sortino where statistically meaningful, benchmark, turnover, exposure, and worst streak; include data/config fingerprints.

## Data flow

```text
raw exchange events
  -> validation and normalization
  -> event clock
  -> strategy signal
  -> risk gate
  -> order intent persisted
  -> simulator or paper executor
  -> fills and account state
  -> reconciliation/audit/report
```

## Validation gates

- Causal signal test: no future candle, future aggregate, or same-bar fill assumption leaks into a decision.
- Cost sensitivity: fees, spread, slippage, latency, and partial-fill assumptions are explicit and varied.
- Time split: development/validation/OOS holdout; final holdout is never used for tuning.
- Walk-forward: rolling train/validation windows for any parameter selection.
- Stability: parameter perturbation, market-regime slices, and bootstrap/Monte Carlo trade-order analysis.
- Parity: identical event fixtures produce identical signals and risk decisions in backtest and paper runtime.
- Operational failure tests: stale data, disconnect, timeout, rejection, duplicate response, partial fill, unknown order status, restart, and local/exchange state mismatch.

## Safety invariants

- Spot-only position model: long or flat.
- No order without a stop-derived maximum loss and valid symbol filters.
- No automatic retry after an unknown broker response.
- Kill switch blocks new entries but preserves reconciliation and safe exits.
- Secrets are read only from environment/secret storage and never committed or logged.
- Paper/testnet is the only enabled execution mode during v1.

## Acceptance criteria

- [ ] The project runs independently in its own environment and does not touch existing bot directories/processes/configs.
- [ ] Backtest metrics are computed from supplied historical data; no placeholder values.
- [ ] Strategy signals are causal and covered by regression tests.
- [ ] Fees, spread, slippage, latency, and fill assumptions appear in every report.
- [ ] OOS/walk-forward reports are reproducible from a pinned config and data fingerprint.
- [ ] Risk and order state transitions are unit/integration tested, including failure paths.
- [ ] Paper/testnet execution is disabled until one exchange is selected and verified.
- [ ] No live deployment is described as profitable without real forward evidence.

## References used

- Freqtrade repository and its live README: https://github.com/freqtrade/freqtrade
- Freqtrade lookahead-analysis documentation: https://www.freqtrade.io/en/stable/lookahead-analysis/
- TradingView Pine Script strategy documentation: https://www.tradingview.com/pine-script-docs/concepts/strategies/
- Vibe-Trading repository as research-workspace reference: https://github.com/HKUDS/Vibe-Trading
