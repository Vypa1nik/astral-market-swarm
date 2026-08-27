# Hybrid Terminal Dashboard Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use godmode-task-runner to implement this plan task-by-task.

**Goal:** Replace the sparse paper status page at `quantbot.sokezzz.com` with an original dense dark trading terminal that refreshes data every 10 seconds without a full-page reload.

**Architecture:** Keep the existing paper-only engine, Binance public-data adapter, SQLite ledger, and read-only boundary. Add a dashboard projection that exposes validated market/history/activity data through `/api/dashboard`; render an original responsive HTML/CSS/SVG terminal shell that polls this endpoint with `fetch()` every 10,000 ms and updates DOM nodes in place.

**Tech Stack:** Python 3.11 standard library HTTP server, HTML5, CSS custom-property tokens, vanilla JavaScript, inline SVG, pytest, Ruff, mypy, Docker Compose, Traefik.

---

## Safety and scope

- Modify only the standalone repository and its `quantbot-standalone` deployment.
- Do not read, write, restart, or reuse `trading.sokezzz.com` application files or state.
- Keep paper-only mode and virtual balance at 5,000 USDT.
- Keep all mutation routes absent; `/api/kill`, `/api/resume`, `/api/orders` must remain 404.
- Do not copy logos, labels, exact layout, text, or data from `trading.sokezzz.com`; use only general dashboard UX inspiration.

## Task 1: Dashboard data projection

**Files:**
- Modify: `src/astral_market_swarm/service.py`
- Modify: `src/astral_market_swarm/web.py`
- Test: `tests/integration/test_http_app.py`

1. Add a serializable dashboard snapshot containing current paper account identity, latest candle, bounded recent candle history, equity points, activity/status fields, update timestamp, and `refresh_interval_ms=10000`.
2. Derive all values from the current bot and journal; never generate fake profit or trade values.
3. Add `GET /api/dashboard` with `Cache-Control: no-store` and JSON content type.
4. Keep existing `/api/health`, `/api/state`, and 404 mutation behavior.
5. Test the endpoint using a deterministic fake source and assert the refresh marker, paper-only mode, USDT balance, candle history shape, and no mutation endpoint.
6. Run `uv run pytest tests/integration/test_http_app.py -q`, then full quality checks.
7. Commit: `feat: expose dashboard data projection`.

## Task 2: Original terminal frontend shell

**Files:**
- Modify: `src/astral_market_swarm/web.py`
- Test: `tests/integration/test_http_app.py`

1. Replace the sparse root HTML with semantic dashboard markup: header, sidebar navigation, KPI cards, main chart panel, signal/market pulse panels, activity table, and mobile-friendly layout.
2. Define all visual tokens in one `:root` block: navy backgrounds, cyan accent, green positive, red negative, amber warning, neutral scale, spacing, radii, typography, and shadows.
3. Use only original names/content such as Astral Terminal, Engine status, Market pulse, Signal engine, Paper ledger, and Activity feed.
4. Include initial loading/empty/error/degraded states in markup and accessible live regions.
5. Add responsive breakpoints and `prefers-reduced-motion` behavior.
6. Test HTML for required semantic landmarks, token names, paper-only text, and no secret marker.
7. Run focused and full tests.
8. Commit: `feat: add hybrid dark terminal dashboard`.

## Task 3: SVG chart and 10-second live refresh

**Files:**
- Modify: `src/astral_market_swarm/web.py`
- Test: `tests/integration/test_http_app.py`

1. Add inline SVG chart containers for price action, equity curve, signal markers, gridlines, and legend.
2. Implement vanilla JavaScript functions that safely map validated JSON values to SVG coordinates and text nodes.
3. Poll `/api/dashboard` with `setInterval(refreshDashboard, 10000)` and an immediate first fetch; update DOM in place without `location.reload`, `window.location.reload`, or navigation.
4. Show last update time, next refresh countdown, request latency, and a `LIVE`/`DEGRADED` state. On fetch failure retain last good data and expose the error without throwing away the screen.
5. Prevent concurrent refreshes with an in-flight guard; abort stale requests with `AbortController` if needed.
6. Escape all server-provided text through `textContent` or safe JSON serialization; do not inject untrusted values into `innerHTML`.
7. Test for the 10,000 ms interval marker, dashboard endpoint URL, no full-page reload API, SVG elements, and degraded-state copy.
8. Run full tests and static checks.
9. Commit: `feat: add live svg charts and ten second refresh`.

## Task 4: Local browser verification

**Files:** no source changes unless defects are found.

1. Run `uv run pytest --cov=astral_market_swarm --cov-report=term-missing -q`.
2. Run Ruff lint/format and mypy.
3. Start the app on a temporary local port with an isolated temporary state DB.
4. Verify `/api/health`, `/api/state`, `/api/dashboard`, root HTML, mutation 404s, and two `/api/dashboard` reads at least 10 seconds apart.
5. Open the local page in a browser and inspect screenshot/layout at desktop and narrow viewport; check browser console for JS errors.
6. Confirm no secret/private-key markers occur in public HTML or JSON.

## Task 5: VPS deploy and acceptance

1. Record current legacy container IDs/start times/status/restart counts before write.
2. Build a commit archive without `.env`; upload to `/tmp`; replace only `/docker/quantbot` with the new standalone tree; preserve `.env` mode 600.
3. Run target-host `docker compose build --pull` and `docker compose up -d` only for `astral-market-swarm`.
4. Verify container health, paper identity, 5,000 USDT, processed bars, public market timestamp, and no API errors.
5. Verify `https://quantbot.sokezzz.com/`, `/api/health`, `/api/state`, `/api/dashboard`, and mutation 404s.
6. Use CamoFox/browser screenshot and console inspection for visual and runtime verification. Verify a second dashboard poll changes `last_update`/data or at least reports the current fresh timestamp without page navigation.
7. Re-check legacy fingerprints and Traefik health; abort/report if any changed unexpectedly.
8. Remove temporary upload artifacts only from `/tmp`.
9. Commit any final source fix and update deployment archive.

## Final acceptance checklist

- [ ] Original dark hybrid terminal is visible publicly.
- [ ] Responsive layout works on desktop and narrow viewport.
- [ ] `/api/dashboard` returns live validated data.
- [ ] Browser polls every 10 seconds without full-page reload.
- [ ] Price/equity chart renders from real data or an honest empty state.
- [ ] Paper-only and 5,000 USDT identity remain visible.
- [ ] Mutation endpoints remain 404.
- [ ] 49+ tests plus new UI/API tests pass.
- [ ] Ruff, format, mypy pass.
- [ ] Public HTTPS route passes.
- [ ] Existing bot and Traefik container fingerprints are unchanged.
- [ ] No secrets occur in source, JSON, HTML, screenshots, or logs.

## References

- `https://trading.sokezzz.com` — read-only visual reference for information hierarchy only.
- `https://www.tradingview.com/pine-script-docs/concepts/strategies/` — strategy report, equity, drawdown, benchmark, cost concepts.
- `https://htmlstream.com/preview/front-dashboard-v2.0/dashboard-default-dark.html` — dark dashboard shell/sidebar pattern.
- `https://www.creative-tim.com/product/material-dashboard-dark` — dark dashboard token/card pattern.
- `https://coreui.io/product/free-bootstrap-dashboard-with-charts/` — responsive analytics/chart pattern.
