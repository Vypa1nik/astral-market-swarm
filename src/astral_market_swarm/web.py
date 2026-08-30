"""Read-only HTTP surface and original dark terminal dashboard."""

from __future__ import annotations

import json
from collections.abc import Mapping
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from .service import StandalonePaperBot


class _Handler(BaseHTTPRequestHandler):
    bot: StandalonePaperBot

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/api/health":
            self._send_json({"ok": True, "service": "astral-market-swarm", "mode": "paper"})
            return
        if path == "/api/state":
            self._send_json(self.bot.snapshot().public_dict())
            return
        if path == "/api/dashboard":
            self._send_json(self.bot.dashboard_dict())
            return
        if path == "/":
            self._send_html(render_dashboard(self.bot.dashboard_dict()))
            return
        self.send_error(404)

    def _send_json(self, payload: Mapping[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, body_text: str) -> None:
        body = body_text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'",
        )
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return None


def create_http_server(
    bot: StandalonePaperBot,
    host: str = "127.0.0.1",
    port: int = 8080,
) -> ThreadingHTTPServer:
    """Create a read-only server bound to the supplied bot instance."""

    class BoundHandler(_Handler):
        pass

    BoundHandler.bot = bot
    server = ThreadingHTTPServer((host, port), BoundHandler)
    server.daemon_threads = True
    server.allow_reuse_address = True
    return server


def _json_seed(payload: Mapping[str, object]) -> str:
    """Embed trusted JSON without allowing a value to terminate the script tag."""

    return (
        json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def render_dashboard(payload: Mapping[str, object]) -> str:
    """Render the complete dashboard shell with a live, in-place refresh loop."""

    seed = _json_seed(payload)
    template = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#07111d">
<title>Astral Terminal · BTC/USDT paper engine</title>
<style>
:root {
  --bg-0: #050b13;
  --bg-1: #081421;
  --bg-2: #0c1b2a;
  --panel: #0d1d2c;
  --panel-raised: #112638;
  --line: #1b3b50;
  --line-bright: #24556b;
  --text: #d9eef3;
  --muted: #7693a0;
  --dim: #4f6a78;
  --cyan: #4de3e8;
  --cyan-soft: #2aadb9;
  --green: #53e39a;
  --red: #ff6d7d;
  --amber: #f3c969;
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;
  --space-8: 32px;
  --radius-sm: 6px;
  --radius-md: 10px;
  --shadow-panel: 0 18px 50px rgba(0, 0, 0, .25);
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
* { box-sizing: border-box; }
html { min-width: 320px; background: var(--bg-0); }
body {
  margin: 0;
  min-height: 100vh;
  color: var(--text);
  background: radial-gradient(circle at 70% -20%, #123149 0, transparent 43%), var(--bg-0);
  font-size: 13px;
  letter-spacing: .01em;
}
button { font: inherit; color: inherit; }
button:focus-visible, a:focus-visible { outline: 2px solid var(--cyan); outline-offset: 3px; }
.terminal-shell {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 224px minmax(0, 1fr);
  grid-template-rows: 66px minmax(0, 1fr);
}
.sidebar {
  grid-row: 1 / -1;
  padding: var(--space-6) var(--space-4);
  border-right: 1px solid var(--line);
  background: linear-gradient(180deg, rgba(13, 31, 45, .98), rgba(5, 12, 20, .98));
}
.brand { display: flex; align-items: center; gap: var(--space-3); padding: 0 var(--space-2) var(--space-8); }
.brand-mark {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  border: 1px solid var(--cyan);
  border-radius: 9px;
  color: var(--cyan);
  background: rgba(77, 227, 232, .1);
  box-shadow: 0 0 24px rgba(77, 227, 232, .12);
  font-weight: 800;
}
.brand strong { display: block; font-size: 14px; letter-spacing: .08em; text-transform: uppercase; }
.brand small { color: var(--muted); font-size: 10px; }
.nav-label { padding: var(--space-2); color: var(--dim); font-size: 10px; font-weight: 700; letter-spacing: .14em; text-transform: uppercase; }
.nav-list { display: grid; gap: var(--space-1); margin: 0; padding: 0; list-style: none; }
.nav-item {
  width: 100%;
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: 11px var(--space-3);
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  text-align: left;
}
.nav-item:hover { color: var(--text); background: rgba(77, 227, 232, .05); }
.nav-item.active { border-color: rgba(77, 227, 232, .22); color: var(--cyan); background: rgba(77, 227, 232, .08); }
.nav-icon { width: 20px; text-align: center; color: var(--cyan-soft); font-size: 15px; }
.sidebar-foot { margin-top: auto; padding: var(--space-6) var(--space-2) 0; color: var(--dim); font-size: 10px; line-height: 1.7; }
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  padding: 0 var(--space-8);
  border-bottom: 1px solid var(--line);
  background: rgba(5, 13, 22, .82);
  backdrop-filter: blur(16px);
}
.crumbs { display: flex; align-items: center; gap: var(--space-3); min-width: 0; }
.crumbs strong { color: var(--text); font-size: 15px; }
.crumbs span { color: var(--muted); }
.live-strip { display: flex; align-items: center; gap: var(--space-4); color: var(--muted); font-size: 11px; }
.live-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--green); box-shadow: 0 0 14px var(--green); }
.live-dot.degraded { background: var(--red); box-shadow: 0 0 14px var(--red); }
.status-pill {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: 6px 10px;
  border: 1px solid rgba(83, 227, 154, .35);
  border-radius: 999px;
  color: var(--green);
  background: rgba(83, 227, 154, .08);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: .11em;
}
.workspace { min-width: 0; padding: var(--space-6) var(--space-8) 40px; }
.kicker { color: var(--cyan); font-size: 10px; font-weight: 800; letter-spacing: .16em; text-transform: uppercase; }
.hero-row { display: flex; align-items: end; justify-content: space-between; gap: var(--space-4); margin-bottom: var(--space-6); }
h1 { margin: 5px 0 0; font-size: clamp(24px, 3vw, 38px); letter-spacing: -.04em; line-height: 1; }
.hero-note { max-width: 420px; color: var(--muted); text-align: right; line-height: 1.6; }
.kpi-grid { display: grid; grid-template-columns: repeat(5, minmax(130px, 1fr)); gap: var(--space-3); margin-bottom: var(--space-4); }
.panel {
  min-width: 0;
  border: 1px solid var(--line);
  border-radius: var(--radius-md);
  background: linear-gradient(145deg, rgba(17, 38, 56, .92), rgba(9, 23, 36, .92));
  box-shadow: var(--shadow-panel);
}
.kpi { position: relative; overflow: hidden; padding: var(--space-4); }
.kpi::after {
  content: "";
  position: absolute;
  width: 90px;
  height: 90px;
  top: -45px;
  right: -24px;
  border: 1px solid rgba(77, 227, 232, .15);
  border-radius: 50%;
}
.kpi-label { color: var(--muted); font-size: 10px; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; }
.kpi-value { margin: 10px 0 4px; color: var(--text); font-size: clamp(17px, 2vw, 23px); font-weight: 750; letter-spacing: -.04em; white-space: nowrap; }
.kpi-sub { color: var(--dim); font-size: 10px; }
.kpi-sub.good { color: var(--green); }
.content-grid { display: grid; grid-template-columns: minmax(0, 1.65fr) minmax(260px, .75fr); gap: var(--space-4); }
.panel-head { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); padding: var(--space-4) var(--space-5); border-bottom: 1px solid var(--line); }
.panel-title { display: flex; align-items: center; gap: var(--space-2); font-size: 12px; font-weight: 750; letter-spacing: .04em; }
.panel-title::before { content: ""; width: 3px; height: 16px; border-radius: 99px; background: var(--cyan); box-shadow: 0 0 10px rgba(77, 227, 232, .65); }
.panel-meta { color: var(--muted); font-size: 10px; }
.chart-panel { overflow: hidden; }
.chart-wrap { position: relative; padding: var(--space-3) var(--space-4) var(--space-4); }
.chart-svg { display: block; width: 100%; height: 310px; overflow: visible; }
.chart-svg.small { height: 118px; }
.chart-grid { stroke: rgba(95, 145, 160, .18); stroke-width: 1; }
.chart-axis { fill: var(--dim); font-size: 10px; }
.price-area { fill: url(#priceFill); opacity: .5; }
.price-line { fill: none; stroke: var(--cyan); stroke-width: 2.4; vector-effect: non-scaling-stroke; filter: drop-shadow(0 0 5px rgba(77, 227, 232, .45)); }
.equity-line { fill: none; stroke: var(--green); stroke-width: 2.2; vector-effect: non-scaling-stroke; }
.price-dot { fill: var(--cyan); stroke: var(--bg-1); stroke-width: 3; }
.chart-legend { display: flex; flex-wrap: wrap; gap: var(--space-4); padding: 0 var(--space-5) var(--space-4); color: var(--muted); font-size: 10px; }
.legend-key { display: inline-flex; align-items: center; gap: 6px; }
.legend-key i { width: 10px; height: 3px; display: inline-block; border-radius: 99px; background: var(--cyan); }
.legend-key i.green { background: var(--green); }
.legend-key i.amber { background: var(--amber); }
.side-stack { display: grid; gap: var(--space-4); align-content: start; }
.signal-panel { min-height: 184px; }
.signal-body { padding: var(--space-5); }
.signal-badge {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: 8px 11px;
  border: 1px solid rgba(243, 201, 105, .3);
  border-radius: 999px;
  color: var(--amber);
  background: rgba(243, 201, 105, .08);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: .12em;
  text-transform: uppercase;
}
.signal-main { margin: 18px 0 4px; font-size: 21px; font-weight: 750; letter-spacing: -.04em; }
.signal-detail { color: var(--muted); line-height: 1.6; }
.pulse-grid { display: grid; gap: var(--space-4); padding: var(--space-5); }
.pulse-row { display: grid; grid-template-columns: 85px 1fr 45px; align-items: center; gap: var(--space-3); color: var(--muted); font-size: 10px; }
.pulse-track { height: 5px; overflow: hidden; border-radius: 99px; background: #152d3e; }
.pulse-track span { display: block; height: 100%; border-radius: inherit; background: linear-gradient(90deg, var(--cyan-soft), var(--cyan)); }
.pulse-track span.green { background: linear-gradient(90deg, #248c69, var(--green)); }
.pulse-track span.amber { background: linear-gradient(90deg, #9d7936, var(--amber)); }
.pulse-value { color: var(--text); text-align: right; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.lower-grid { display: grid; grid-template-columns: minmax(0, 1.1fr) minmax(0, .9fr); gap: var(--space-4); margin-top: var(--space-4); }
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; min-width: 540px; }
th, td { padding: 12px var(--space-5); border-bottom: 1px solid rgba(27, 59, 80, .72); text-align: left; white-space: nowrap; }
th { color: var(--dim); font-size: 9px; font-weight: 800; letter-spacing: .12em; text-transform: uppercase; }
td { color: var(--muted); font-size: 11px; }
td:first-child { color: var(--text); }
.activity-kind { color: var(--cyan); font-size: 10px; font-weight: 800; text-transform: uppercase; }
.empty-row { padding: 30px var(--space-5); color: var(--dim); text-align: center; }
.footer-bar { display: flex; justify-content: space-between; gap: var(--space-4); padding: var(--space-5) 2px 0; color: var(--dim); font-size: 10px; }
#refresh-announcer { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
@media (max-width: 1120px) {
  .terminal-shell { grid-template-columns: 76px minmax(0, 1fr); }
  .sidebar { padding-inline: 10px; }
  .brand { justify-content: center; padding-inline: 0; }
  .brand-copy, .nav-label, .nav-item span:not(.nav-icon), .sidebar-foot { display: none; }
  .nav-item { justify-content: center; padding-inline: 8px; }
  .topbar { padding-inline: var(--space-6); }
  .workspace { padding-inline: var(--space-6); }
  .kpi-grid { grid-template-columns: repeat(3, 1fr); }
}
@media (max-width: 760px) {
  .terminal-shell { display: block; }
  .sidebar { display: none; }
  .topbar { min-height: 58px; padding-inline: var(--space-4); }
  .live-strip span:not(.live-dot), .hero-note { display: none; }
  .workspace { padding: var(--space-5) var(--space-4) 32px; }
  .hero-row { align-items: start; }
  .kpi-grid { grid-template-columns: repeat(2, 1fr); }
  .content-grid, .lower-grid { grid-template-columns: 1fr; }
  .chart-svg { height: 260px; }
  .footer-bar { display: block; line-height: 1.8; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    scroll-behavior: auto !important;
    transition-duration: .01ms !important;
    animation-duration: .01ms !important;
  }
}
</style>
</head>
<body>
<div class="terminal-shell">
  <aside class="sidebar" aria-label="Primary navigation">
    <div class="brand"><div class="brand-mark" aria-hidden="true">A</div><div class="brand-copy"><strong>Astral</strong><small>market terminal</small></div></div>
    <div class="nav-label">Workspace</div>
    <nav><ul class="nav-list">
      <li><button type="button" class="nav-item active" data-view="overview" data-target="view-overview" aria-current="page"><span class="nav-icon" aria-hidden="true">◈</span><span>Overview</span></button></li>
      <li><button type="button" class="nav-item" data-view="market-pulse" data-target="view-market-pulse"><span class="nav-icon" aria-hidden="true">⌁</span><span>Market pulse</span></button></li>
      <li><button type="button" class="nav-item" data-view="signal-engine" data-target="view-signal-engine"><span class="nav-icon" aria-hidden="true">⌘</span><span>Signal engine</span></button></li>
      <li><button type="button" class="nav-item" data-view="paper-ledger" data-target="view-paper-ledger"><span class="nav-icon" aria-hidden="true">▤</span><span>Paper ledger</span></button></li>
    </ul></nav>
    <div class="nav-label" style="margin-top:32px">System</div>
    <ul class="nav-list">
      <li><button type="button" class="nav-item" data-view="data-stream" data-target="view-data-stream"><span class="nav-icon" aria-hidden="true">◌</span><span>Data stream</span></button></li>
      <li><button type="button" class="nav-item" data-view="risk-guard" data-target="view-signal-engine"><span class="nav-icon" aria-hidden="true">✓</span><span>Risk guard</span></button></li>
    </ul>
    <div class="sidebar-foot">Read-only terminal<br>Paper execution boundary<br>Public market data</div>
  </aside>
  <header class="topbar">
    <div class="crumbs"><strong id="current-view">Overview</strong><span>/</span><span id="top-symbol">BTC/USDT</span></div>
    <div class="live-strip"><span id="top-updated">sync pending</span><span class="live-dot" id="live-dot"></span><span class="status-pill" id="engine-status">LIVE · PAPER</span></div>
  </header>
  <main class="workspace">
    <div class="hero-row" id="view-overview" tabindex="-1"><div><div class="kicker">Astral Market Swarm · Control room</div><h1>Astral Terminal</h1></div><div class="hero-note">paper only · 10000 USDT demo cash · Causal paper engine monitoring public market data. No live orders. Paper leverage is simulated only.</div></div>
    <section class="kpi-grid" aria-label="Account and market summary">
      <article class="panel kpi"><div class="kpi-label">Paper equity</div><div class="kpi-value" id="kpi-equity">—</div><div class="kpi-sub good" id="kpi-equity-sub">USDT account value</div></article>
      <article class="panel kpi"><div class="kpi-label">Available cash</div><div class="kpi-value" id="kpi-cash">—</div><div class="kpi-sub">settled paper balance</div></article>
      <article class="panel kpi"><div class="kpi-label">Live mark</div><div class="kpi-value" id="kpi-price">—</div><div class="kpi-sub" id="kpi-price-sub">latest closed bar</div></article>
      <article class="panel kpi"><div class="kpi-label">Position</div><div class="kpi-value" id="kpi-position">—</div><div class="kpi-sub" id="kpi-position-sub">flat exposure</div></article>
      <article class="panel kpi"><div class="kpi-label">Bars processed</div><div class="kpi-value" id="kpi-bars">—</div><div class="kpi-sub" id="kpi-bars-sub">engine heartbeat</div></article>
    </section>
    <div class="content-grid">
      <section class="panel chart-panel" id="view-data-stream" tabindex="-1" aria-labelledby="price-heading">
        <div class="panel-head"><div class="panel-title" id="price-heading">Price action · closed bars</div><div class="panel-meta" id="price-range">waiting for feed</div></div>
        <div class="chart-wrap"><svg class="chart-svg" id="price-chart" viewBox="0 0 900 310" role="img" aria-label="BTC USDT price action chart"><defs><linearGradient id="priceFill" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#4de3e8" stop-opacity=".35"/><stop offset="1" stop-color="#4de3e8" stop-opacity="0"/></linearGradient></defs><g id="price-grid"></g><path class="price-area" id="price-area" d=""></path><path class="price-line" id="price-line" d=""></path><circle class="price-dot" id="price-dot" cx="0" cy="0" r="5"></circle><text class="chart-axis" id="price-label" x="14" y="24">—</text></svg></div>
        <div class="chart-legend"><span class="legend-key"><i></i>BTC/USDT mark</span><span class="legend-key"><i class="amber"></i>closed candle stream</span><span class="legend-key"><i class="green"></i>paper equity below</span></div>
        <div class="chart-wrap" style="padding-top:0"><svg class="chart-svg small" id="equity-chart" viewBox="0 0 900 118" role="img" aria-label="Paper equity curve"><g id="equity-grid"></g><path class="equity-line" id="equity-line" d=""></path><text class="chart-axis" id="equity-label" x="14" y="20">equity · — USDT</text></svg></div>
      </section>
      <div class="side-stack">
        <section class="panel signal-panel" id="view-signal-engine" tabindex="-1" aria-labelledby="signal-heading"><div class="panel-head"><div class="panel-title" id="signal-heading">Signal engine</div><div class="panel-meta">causal</div></div><div class="signal-body"><div class="signal-badge" id="signal-badge">● monitoring</div><div class="signal-main" id="signal-main">No setup</div><div class="signal-detail" id="signal-detail">Waiting for a qualified EMA / RSI / ATR setup.</div></div></section>
        <section class="panel" id="view-market-pulse" tabindex="-1" aria-labelledby="pulse-heading"><div class="panel-head"><div class="panel-title" id="pulse-heading">Market pulse</div><div class="panel-meta" id="pulse-meta">BTC/USDT</div></div><div class="pulse-grid"><div class="pulse-row"><span>Trend regime</span><div class="pulse-track"><span id="pulse-trend" style="width:38%"></span></div><span class="pulse-value" id="pulse-trend-value">—</span></div><div class="pulse-row"><span>Volatility</span><div class="pulse-track"><span class="amber" id="pulse-volatility" style="width:22%"></span></div><span class="pulse-value" id="pulse-volatility-value">—</span></div><div class="pulse-row"><span>Data health</span><div class="pulse-track"><span class="green" id="pulse-health" style="width:100%"></span></div><span class="pulse-value" id="pulse-health-value">OK</span></div></div></section>
      </div>
    </div>
    <div class="lower-grid">
      <section class="panel" aria-labelledby="activity-heading"><div class="panel-head"><div class="panel-title" id="activity-heading">Activity feed</div><div class="panel-meta" id="activity-meta">paper journal</div></div><div class="table-wrap"><table><thead><tr><th>Time</th><th>Type</th><th>Event</th><th>Detail</th></tr></thead><tbody id="activity-rows"><tr><td colspan="4" class="empty-row">Loading engine activity…</td></tr></tbody></table></div></section>
      <section class="panel" id="view-paper-ledger" tabindex="-1" aria-labelledby="ledger-heading"><div class="panel-head"><div class="panel-title" id="ledger-heading">Paper ledger</div><div class="panel-meta">isolated paper account</div></div><div class="chart-wrap"><div class="pulse-grid" style="padding:0"><div class="pulse-row"><span>Account</span><span class="pulse-value" id="ledger-account">—</span><span></span></div><div class="pulse-row"><span>Execution</span><span class="pulse-value" id="ledger-mode">PAPER ONLY</span><span></span></div><div class="pulse-row"><span>Profile</span><span class="pulse-value" id="ledger-profile">—</span><span></span></div><div class="pulse-row"><span>Paper leverage</span><span class="pulse-value" id="ledger-leverage">1x</span><span></span></div><div class="pulse-row"><span>Borrowed notional</span><span class="pulse-value" id="ledger-borrowed">0 USDT</span><span></span></div><div class="pulse-row"><span>Interval</span><span class="pulse-value" id="ledger-interval">—</span><span></span></div><div class="pulse-row"><span>Refresh</span><span class="pulse-value">10 sec</span><span></span></div><div class="pulse-row"><span>Last bar</span><span class="pulse-value" id="ledger-last-bar">—</span><span></span></div></div></div></section>
    </div>
    <div class="footer-bar"><span>ASTRAL / READ-ONLY PAPER TERMINAL / PUBLIC DATA</span><span id="footer-refresh">Next sync in 10.0s</span></div>
    <div id="refresh-announcer" aria-live="polite">Dashboard is loading.</div>
  </main>
</div>
<script id="dashboard-seed" type="application/json">__DASHBOARD_SEED__</script>
<script>
(() => {
  "use strict";
  const initial = JSON.parse(document.getElementById("dashboard-seed").textContent || "{}");
  let dashboard = initial;
  let inFlight = false;
  let nextRefresh = 10;
  const byId = (id) => document.getElementById(id);
  const text = (id, value) => {
    const node = byId(id);
    if (node) node.textContent = value ?? "—";
  };
  const number = (value, digits = 2) => {
    const parsed = Number(value);
    return Number.isFinite(parsed)
      ? parsed.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: digits })
      : "—";
  };
  const shortTime = (value) => value
    ? new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })
    : "—";
  const rangeText = (history) => history.length
    ? `${shortTime(history[0].timestamp)} — ${shortTime(history[history.length - 1].timestamp)}`
    : "waiting for feed";
  const setStatus = (ok, message) => {
    const dot = byId("live-dot");
    const status = byId("engine-status");
    if (dot) dot.classList.toggle("degraded", !ok);
    if (status) {
      status.textContent = ok ? "LIVE · PAPER" : "DEGRADED";
      status.style.color = ok ? "var(--green)" : "var(--red)";
    }
    if (message) text("refresh-announcer", message);
  };
  const makePath = (values, width, height, padding = 14) => {
    if (!values.length) return { line: "", area: "", last: [0, 0] };
    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = max - min || Math.max(Math.abs(max) * .001, 1);
    const points = values.map((value, index) => [
      padding + index * (width - padding * 2) / Math.max(values.length - 1, 1),
      height - padding - (value - min) / span * (height - padding * 2),
    ]);
    const line = points.map((point, index) => `${index ? "L" : "M"} ${point[0].toFixed(2)} ${point[1].toFixed(2)}`).join(" ");
    const area = `${line} L ${points[points.length - 1][0].toFixed(2)} ${height - padding} L ${points[0][0].toFixed(2)} ${height - padding} Z`;
    return { line, area, last: points[points.length - 1], min, max };
  };
  const drawGrid = (id, width, height, rows = 5, cols = 8) => {
    const node = byId(id);
    if (!node) return;
    node.replaceChildren();
    for (let row = 1; row < rows; row += 1) {
      const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
      line.setAttribute("x1", "14");
      line.setAttribute("x2", String(width - 14));
      line.setAttribute("y1", String(row * height / rows));
      line.setAttribute("y2", String(row * height / rows));
      line.setAttribute("class", "chart-grid");
      node.appendChild(line);
    }
    for (let col = 1; col < cols; col += 1) {
      const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
      line.setAttribute("x1", String(col * width / cols));
      line.setAttribute("x2", String(col * width / cols));
      line.setAttribute("y1", "0");
      line.setAttribute("y2", String(height));
      line.setAttribute("class", "chart-grid");
      node.appendChild(line);
    }
  };
  const renderCharts = (data) => {
    const prices = (data.price_history || []).map((item) => Number(item.close)).filter(Number.isFinite);
    const price = makePath(prices, 900, 310);
    drawGrid("price-grid", 900, 310);
    byId("price-line").setAttribute("d", price.line);
    byId("price-area").setAttribute("d", price.area);
    byId("price-dot").setAttribute("cx", String(price.last[0]));
    byId("price-dot").setAttribute("cy", String(price.last[1]));
    text("price-label", prices.length ? `${number(prices[prices.length - 1], 2)} USDT` : "—");
    const equities = (data.equity_history || []).map((item) => Number(item.equity)).filter(Number.isFinite);
    const equityValues = equities.length === 1 ? [equities[0], equities[0]] : equities;
    const equity = makePath(equityValues, 900, 118);
    drawGrid("equity-grid", 900, 118, 3, 8);
    byId("equity-line").setAttribute("d", equity.line);
    text("equity-label", equities.length ? `equity · ${number(equities[equities.length - 1], 2)} USDT` : "equity · — USDT");
  };
  const renderActivity = (items) => {
    const rows = byId("activity-rows");
    if (!rows) return;
    rows.replaceChildren();
    const entries = [...(items || [])].reverse().slice(0, 8);
    if (!entries.length) {
      const row = document.createElement("tr");
      const cell = document.createElement("td");
      cell.colSpan = 4;
      cell.className = "empty-row";
      cell.textContent = "No activity recorded yet.";
      row.appendChild(cell);
      rows.appendChild(row);
      return;
    }
    entries.forEach((item) => {
      const row = document.createElement("tr");
      [shortTime(item.timestamp), item.kind || "engine", item.message || "—", item.detail || "—"].forEach((value, index) => {
        const cell = document.createElement("td");
        cell.textContent = value;
        if (index === 1) cell.className = "activity-kind";
        row.appendChild(cell);
      });
      rows.appendChild(row);
    });
  };
  const render = (data) => {
    dashboard = data;
    const latest = data.latest_candle || {};
    const position = data.position || {};
    const history = data.price_history || [];
    const error = data.last_error;
    text("top-symbol", data.symbol);
    text("top-updated", data.server_time ? `sync ${shortTime(data.server_time)}` : "sync pending");
    text("kpi-equity", `${number(data.equity, 2)} ${data.display_currency || "USDT"}`);
    text("kpi-cash", `${number(data.cash, 2)} ${data.display_currency || "USDT"}`);
    text("kpi-price", `${number(latest.close, 2)}`);
    text("kpi-price-sub", latest.timestamp ? `closed ${shortTime(latest.timestamp)}` : "latest closed bar");
    text("kpi-position", number(position.quantity, 6));
    text("kpi-position-sub", `${number(position.notional, 2)} USDT notional`);
    text("kpi-bars", String(data.processed_bars ?? 0));
    text("kpi-bars-sub", error ? "feed error recorded" : "engine heartbeat");
    text("price-range", rangeText(history));
    text("pulse-meta", data.symbol || "BTC/USDT");
    text("signal-main", data.last_signal || "No setup");
    text("signal-badge", `${(data.strategy_profile || "conservative").replace("paper-", "")} · ${data.leverage || "1"}x simulated`);
    text("signal-detail", error || `${data.entry_mode || "recovery"} entry mode is monitoring closed bars. Paper leverage only; no live orders.`);
    text("ledger-account", data.account_id);
    text("ledger-mode", data.paper_only ? "PAPER ONLY" : "UNKNOWN");
    text("ledger-profile", data.strategy_profile || "conservative");
    text("ledger-leverage", `${data.leverage || "1"}x simulated`);
    text("ledger-borrowed", `${number(data.borrowed_notional, 2)} USDT`);
    text("ledger-interval", data.interval);
    text("ledger-last-bar", data.last_updated ? shortTime(data.last_updated) : "—");
    const trend = history.length > 1 ? Number(history[history.length - 1].close) - Number(history[0].close) : 0;
    const trendPct = history.length > 1 ? Math.min(100, Math.max(0, 50 + trend / Math.max(Number(history[0].close), 1) * 500)) : 38;
    byId("pulse-trend").style.width = `${trendPct}%`;
    text("pulse-trend-value", trend > 0 ? "up" : trend < 0 ? "down" : "flat");
    const volatility = history.length > 1 ? Math.abs(Number(history[history.length - 1].close) - Number(history[history.length - 2].close)) / Math.max(Number(history[history.length - 2].close), 1) * 10000 : 0;
    byId("pulse-volatility").style.width = `${Math.min(100, Math.max(4, volatility * 4))}%`;
    text("pulse-volatility-value", `${number(volatility, 1)} bps`);
    renderCharts(data);
    renderActivity(data.activity);
    setStatus(!error, error ? `Degraded: ${error}` : `Updated ${shortTime(data.server_time)}`);
  };
  const refreshDashboard = async () => {
    if (inFlight) return;
    inFlight = true;
    const started = performance.now();
    try {
      const response = await fetch("/api/dashboard", {
        cache: "no-store",
        headers: { Accept: "application/json" },
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      render(data);
      text("activity-meta", `synced in ${Math.round(performance.now() - started)}ms`);
    } catch (error) {
      setStatus(false, `Dashboard refresh failed: ${error.message}`);
    } finally {
      inFlight = false;
      nextRefresh = 10;
    }
  };
  const wireNavigation = () => {
    const viewNames = {
      overview: "Overview",
      "market-pulse": "Market pulse",
      "signal-engine": "Signal engine",
      "paper-ledger": "Paper ledger",
      "data-stream": "Data stream",
      "risk-guard": "Risk guard",
    };
    document.querySelectorAll("[data-view][data-target]").forEach((button) => {
      button.addEventListener("click", () => {
        document.querySelectorAll("[data-view]").forEach((item) => {
          item.classList.toggle("active", item === button);
          if (item === button) item.setAttribute("aria-current", "page");
          else item.removeAttribute("aria-current");
        });
        text("current-view", viewNames[button.dataset.view] || "Overview");
        const target = byId(button.dataset.target);
        if (target) {
          target.scrollIntoView({ behavior: "smooth", block: "start" });
          target.focus({ preventScroll: true });
        }
      });
    });
  };
  wireNavigation();
  render(dashboard);
  refreshDashboard();
  setInterval(refreshDashboard, 10000);
  setInterval(() => {
    nextRefresh = Math.max(0, nextRefresh - 0.1);
    text("footer-refresh", `Next sync in ${nextRefresh.toFixed(1)}s`);
  }, 100);
  window.refreshDashboard = refreshDashboard;
})();
</script>
</body>
</html>"""
    return template.replace("__DASHBOARD_SEED__", seed)
