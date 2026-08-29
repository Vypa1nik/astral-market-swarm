import json
from datetime import datetime
from decimal import Decimal
from threading import Thread
from urllib.error import HTTPError
from urllib.request import urlopen

from astral_market_swarm.events import Candle
from astral_market_swarm.orders import OrderStore
from astral_market_swarm.service import BotServiceConfig, StandalonePaperBot
from astral_market_swarm.web import create_http_server


class EmptySource:
    def fetch_klines(
        self,
        symbol: str,
        interval: str,
        limit: int,
        now: datetime,
    ) -> tuple[Candle, ...]:
        return ()


class DashboardSource:
    def fetch_klines(
        self,
        symbol: str,
        interval: str,
        limit: int,
        now: datetime,
    ) -> tuple[Candle, ...]:
        del symbol, interval, limit, now
        return (
            Candle(
                "BTC/USDT",
                datetime(2026, 1, 1, 0, 0, tzinfo=__import__("datetime").UTC),
                Decimal("100"),
                Decimal("102"),
                Decimal("99"),
                Decimal("101"),
                Decimal("20"),
            ),
            Candle(
                "BTC/USDT",
                datetime(2026, 1, 1, 0, 5, tzinfo=__import__("datetime").UTC),
                Decimal("101"),
                Decimal("104"),
                Decimal("100"),
                Decimal("103"),
                Decimal("25"),
            ),
        )


def test_read_only_health_and_state_endpoints(tmp_path: object) -> None:
    bot = StandalonePaperBot(
        EmptySource(),
        OrderStore(str(tmp_path / "orders.sqlite3")),
        BotServiceConfig(demo_cash=Decimal("5000")),
    )
    server = create_http_server(bot, "127.0.0.1", 0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"

    try:
        with urlopen(f"{base_url}/api/health", timeout=2) as response:
            health = json.load(response)
        with urlopen(f"{base_url}/api/state", timeout=2) as response:
            state = json.load(response)
        with urlopen(base_url, timeout=2) as response:
            html = response.read().decode()

        assert health == {"ok": True, "service": "astral-market-swarm", "mode": "paper"}
        assert state["demo_cash"] == "5000"
        assert state["display_currency"] == "USDT"
        assert state["paper_only"] == "true"
        assert "Astral Market Swarm" in html
        assert "paper only" in html

        try:
            urlopen(f"{base_url}/api/kill", timeout=2)
        except HTTPError as error:
            assert error.code == 404
        else:
            raise AssertionError("mutation endpoint unexpectedly exists")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_dashboard_endpoint_exposes_live_projection_and_refresh_contract(tmp_path: object) -> None:
    bot = StandalonePaperBot(
        DashboardSource(),
        OrderStore(str(tmp_path / "dashboard.sqlite3")),
        BotServiceConfig(demo_cash=Decimal("5000")),
    )
    bot.tick(datetime(2026, 1, 1, 0, 6, tzinfo=__import__("datetime").UTC))
    server = create_http_server(bot, "127.0.0.1", 0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"

    try:
        with urlopen(f"{base_url}/api/dashboard", timeout=2) as response:
            payload = json.load(response)

        assert payload["refresh_interval_ms"] == 10000
        assert payload["mode"] == "paper"
        assert payload["paper_only"] is True
        assert payload["demo_cash"] == "5000"
        assert payload["display_currency"] == "USDT"
        assert payload["strategy_profile"] == "conservative"
        assert payload["leverage"] == "1"
        assert payload["borrowed_notional"] == "0"
        assert payload["entry_mode"] == "recovery"
        assert payload["latest_candle"]["close"] == "103"
        assert len(payload["price_history"]) == 2
        assert payload["equity_history"]
        assert payload["activity"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_terminal_dashboard_shell_declares_live_refresh_and_chart_regions(tmp_path: object) -> None:
    bot = StandalonePaperBot(
        DashboardSource(),
        OrderStore(str(tmp_path / "terminal.sqlite3")),
        BotServiceConfig(demo_cash=Decimal("5000")),
    )
    bot.tick(datetime(2026, 1, 1, 0, 6, tzinfo=__import__("datetime").UTC))
    server = create_http_server(bot, "127.0.0.1", 0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"

    try:
        with urlopen(base_url, timeout=2) as response:
            html = response.read().decode()

        assert 'class="terminal-shell"' in html
        assert 'class="nav-item active"' in html
        assert 'data-view="overview"' in html
        assert 'data-view="market-pulse"' in html
        assert 'data-view="signal-engine"' in html
        assert 'data-view="paper-ledger"' in html
        assert "scrollIntoView" in html
        assert "aria-current" in html
        assert 'id="price-chart"' in html
        assert 'id="equity-chart"' in html
        assert "Astral Terminal" in html
        assert "setInterval(refreshDashboard, 10000)" in html
        assert "/api/dashboard" in html
        assert "location.reload" not in html
        assert "window.location" not in html
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
