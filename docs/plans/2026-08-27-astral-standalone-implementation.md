# Astral Market Swarm Standalone Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use godmode-task-runner to implement this plan task-by-task.

**Goal:** Build an independent, causal, event-driven crypto spot engine with real backtest metrics, hard risk gates, durable order state, and paper/testnet execution before any live capability.

**Architecture:** A standalone Python 3.11 package owns normalized market events, strategy signals, risk decisions, a fill simulator, durable order state, and reconciliation. Exchange-specific code is an adapter behind a narrow protocol and is added only after the user selects one exchange. Existing local bots are never imported, read, started, stopped, or shared.

**Tech Stack:** Python 3.11+, stdlib dataclasses/enum/decimal/asyncio/sqlite3, pytest, Ruff, mypy; optional exchange client only after venue selection. No bot framework dependency.

---

## Global constraints

- Work only in `D:/Users/kiko/Desktop/astral-market-swarm-standalone` on branch `feature/standalone-engine`.
- Never access existing bot directories, databases, configs, processes, ports, or credentials.
- Spot-only long/flat in v1; no leverage, shorting, futures, market making, RL, or LLM decisions.
- Every production module gets a failing test first.
- No hard-coded performance metrics; reports must be computed from supplied data.
- Live order surface remains disabled until OOS, walk-forward, and paper/testnet gates pass.

### Task 1: Package foundation and causal event model

**Files:**
- Create: `src/astral_market_swarm/__init__.py`
- Create: `src/astral_market_swarm/events.py`
- Test: `tests/unit/test_events.py`

**Step 1 — RED:** Write tests proving that a candle event requires an aware UTC timestamp, positive prices, non-negative volume, and monotonic event ordering; invalid values raise `ValueError`.

**Step 2 — Verify RED:** Run `uv run pytest tests/unit/test_events.py -q`. Expected: import/implementation failure because the event model does not exist.

**Step 3 — GREEN:** Implement frozen dataclasses for `Candle`, `Quote`, `MarketEvent`, and a strict UTC normalization helper. Do not add exchange-specific fields.

**Step 4 — Verify GREEN:** Run `uv run pytest tests/unit/test_events.py -q`, `uv run ruff check src tests`, and `uv run mypy src`.

**Step 5 — Commit:** `git add src tests && git commit -m "feat: add causal market event model"`.

### Task 2: Data QA and immutable dataset manifest

**Files:**
- Create: `src/astral_market_swarm/data_quality.py`
- Create: `src/astral_market_swarm/dataset.py`
- Test: `tests/unit/test_data_quality.py`

**Step 1 — RED:** Test duplicate timestamps, gaps, non-monotonic rows, OHLC invariant violations, NaN/inf values, wrong symbol, and stale final events. Test that a manifest records symbol, timeframe, UTC range, row count, and SHA-256 fingerprint.

**Step 2 — Verify RED:** Run `uv run pytest tests/unit/test_data_quality.py -q`. Expected: missing-module or missing-function failures.

**Step 3 — GREEN:** Implement deterministic validation that rejects invalid input instead of repairing silently. Store only validated normalized events in the backtest input.

**Step 4 — Verify GREEN:** Run the focused tests plus `uv run ruff check src tests` and `uv run mypy src`.

**Step 5 — Commit:** `git add src tests && git commit -m "feat: validate and fingerprint market data"`.

### Task 3: Strategy hypothesis and independent risk engine

**Files:**
- Create: `src/astral_market_swarm/strategy.py`
- Create: `src/astral_market_swarm/risk.py`
- Test: `tests/unit/test_strategy.py`
- Test: `tests/unit/test_risk.py`

**Step 1 — RED:** Test causal EMA/RSI/ATR calculations and long/flat signals from fixture candles. Test that a signal cannot use a candle after its decision timestamp. Test risk sizing from equity and stop distance, plus rejection for stale data, invalid stop, insufficient balance, max exposure, daily loss, and kill switch.

**Step 2 — Verify RED:** Run `uv run pytest tests/unit/test_strategy.py tests/unit/test_risk.py -q`. Expected: failures because modules do not exist.

**Step 3 — GREEN:** Implement one explicit baseline hypothesis derived from the supplied idea: EMA regime + RSI recovery/pullback + ATR-normalized stop and exit rules. Keep thresholds configurable and do not optimize them in code. Keep the risk engine separate from the strategy.

**Step 4 — Verify GREEN:** Run focused tests and static checks. Add a regression fixture that proves a future candle cannot alter an earlier signal.

**Step 5 — Commit:** `git add src tests && git commit -m "feat: add causal spot strategy and risk gates"`.

### Task 4: Event-driven fill simulator and metrics

**Files:**
- Create: `src/astral_market_swarm/fills.py`
- Create: `src/astral_market_swarm/backtest.py`
- Create: `src/astral_market_swarm/metrics.py`
- Test: `tests/unit/test_fills.py`
- Test: `tests/integration/test_backtest.py`

**Step 1 — RED:** Test market/limit order timing, fee calculation, spread, fixed/sliding slippage, insufficient liquidity, partial fills, rejected orders, and deterministic event ordering. Test a small fixture produces computed trades, net PnL, costs, max drawdown, trade count, exposure, and buy-and-hold benchmark.

**Step 2 — Verify RED:** Run `uv run pytest tests/unit/test_fills.py tests/integration/test_backtest.py -q`. Expected: failures because simulator and metrics do not exist.

**Step 3 — GREEN:** Implement the event loop using the same normalized events used by paper runtime. Every fill records intended price, actual price, quantity, fee, slippage, timestamp, and reason. Never claim profitability from a fixture.

**Step 4 — Verify GREEN:** Run focused tests, then `uv run pytest --cov=astral_market_swarm --cov-report=term-missing`.

**Step 5 — Commit:** `git add src tests && git commit -m "feat: add event-driven backtester and metrics"`.

### Task 5: Durable order state machine and reconciliation contract

**Files:**
- Create: `src/astral_market_swarm/orders.py`
- Create: `src/astral_market_swarm/reconciliation.py`
- Test: `tests/unit/test_orders.py`
- Test: `tests/unit/test_reconciliation.py`

**Step 1 — RED:** Test valid transitions through created/submitted/acknowledged/partial/filled/cancelled/rejected/unknown. Test invalid transitions are rejected, intents are persisted before submit, and an unknown response blocks retry until a broker lookup resolves it.

**Step 2 — Verify RED:** Run `uv run pytest tests/unit/test_orders.py tests/unit/test_reconciliation.py -q`. Expected: missing implementation failures.

**Step 3 — GREEN:** Implement an SQLite-backed audit store with idempotency keys, deterministic client order IDs, safe exit behavior under kill switch, and explicit reconciliation outcomes.

**Step 4 — Verify GREEN:** Simulate timeout, duplicate response, restart, partial fill, and local/exchange mismatch. Confirm no duplicate order is produced.

**Step 5 — Commit:** `git add src tests && git commit -m "feat: add durable order state and reconciliation"`.

### Task 6: Exchange-agnostic adapter and paper executor

**Files:**
- Create: `src/astral_market_swarm/exchange.py`
- Create: `src/astral_market_swarm/paper.py`
- Test: `tests/unit/test_exchange_contract.py`
- Test: `tests/integration/test_paper_runtime.py`

**Step 1 — RED:** Test the adapter protocol contract with a fake exchange: quote freshness, balances, symbol filters, order submission, lookup, cancellation, and graceful disconnect.

**Step 2 — Verify RED:** Run focused tests; expected missing protocol/runtime failures.

**Step 3 — GREEN:** Implement only the exchange-neutral protocol and deterministic fake/paper adapter. The adapter must not know about any existing local bot.

**Step 4 — Verify GREEN:** Run all tests, lint, format check, mypy, and dependency audit. Confirm execution mode defaults to `paper` and rejects `live`.

**Step 5 — Commit:** `git add src tests && git commit -m "feat: add exchange contract and paper runtime"`.

### Task 7: Concrete spot testnet adapter after venue selection

**Files:**
- Create: `src/astral_market_swarm/adapters/<selected_exchange>.py`
- Create: `tests/integration/test_<selected_exchange>_testnet.py`
- Modify: `README.md`
- Modify: `.env.example` (if required)

**Prerequisite:** User explicitly selects the exchange and its official paper/testnet endpoint.

**Steps:**
1. Verify the official API documentation, spot testnet availability, order types, symbol filters, rate limits, and sandbox/live separation.
2. Add a failing contract test for the selected venue.
3. Implement the narrow adapter with bounded timeouts, retry only for safe reads, idempotent client order IDs, and no withdrawal permission.
4. Run read-only connectivity, account, symbol metadata, and testnet order lifecycle checks.
5. Commit only after the adapter passes contract and integration tests.

### Task 8: Reproducible research report and CI gate

**Files:**
- Create: `src/astral_market_swarm/report.py`
- Create: `scripts/run_backtest.py`
- Create: `.github/workflows/quality.yml`
- Test: `tests/integration/test_report.py`
- Modify: `README.md`

**Steps:**
1. Add failing tests for report reproducibility, OOS/walk-forward sections, cost scenarios, benchmark, warnings, and data/config fingerprints.
2. Implement report generation without external claims or hard-coded results.
3. Add CI: Ruff lint, Ruff format check, mypy, pytest with coverage, and pip-audit/uv audit where available.
4. Run the complete local quality gate and record real output.
5. Commit `feat: add reproducible research reports and quality gates`.

### Final verification

- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run mypy src`
- `uv run pytest --cov=astral_market_swarm --cov-report=term-missing`
- verify no imports or file paths reference existing bot projects
- run a real historical-data backtest only after a data source is selected
- run paper/testnet lifecycle only after the concrete venue adapter is selected

## Explicitly excluded

- Profit guarantees or claims based on screenshots.
- 20x leverage, futures, shorting, market making, RL, automatic retraining, and LLM order decisions.
- Automatic live deployment.
- Reading or modifying any existing bot installation.
