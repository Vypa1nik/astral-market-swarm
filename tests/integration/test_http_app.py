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
