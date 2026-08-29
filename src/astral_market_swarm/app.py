"""Docker entrypoint for the isolated paper service."""

from __future__ import annotations

import os
import signal
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from threading import Event, Thread

from .binance_public import BinancePublicData
from .orders import OrderStore
from .service import BotServiceConfig, StandalonePaperBot, profile_config
from .web import create_http_server


def _env_decimal(name: str, default: str) -> Decimal:
    try:
        value = Decimal(os.getenv(name, default))
    except InvalidOperation as error:
        raise ValueError(f"{name} must be a decimal") from error
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def build_bot() -> StandalonePaperBot:
    symbol = os.getenv("SYMBOL", "BTC/USDT")
    interval = os.getenv("INTERVAL", "5m")
    lookback = int(os.getenv("LOOKBACK", "250"))
    state_db = os.getenv("STATE_DB", "/app/state/orders.sqlite3")
    profile = profile_config(os.getenv("STRATEGY_PROFILE", "conservative"))
    source = BinancePublicData(
        os.getenv("BINANCE_PUBLIC_BASE_URL", "https://api.binance.com/api/v3")
    )
    store = OrderStore(state_db)
    return StandalonePaperBot(
        source,
        store,
        BotServiceConfig(
            symbol=symbol,
            interval=interval,
            lookback=lookback,
            demo_cash=_env_decimal("DEMO_CASH", "5000"),
            display_currency=os.getenv("DISPLAY_CURRENCY", "USDT"),
            strategy_profile=profile.strategy_profile,
            strategy=profile.strategy,
            risk=profile.risk,
        ),
    )


def run() -> None:
    bot = build_bot()
    server = create_http_server(bot, "0.0.0.0", int(os.getenv("PORT", "8080")))
    stop = Event()

    def poll() -> None:
        interval_seconds = max(30, int(os.getenv("POLL_SECONDS", "300")))
        while not stop.is_set():
            try:
                bot.tick(datetime.now(UTC))
            except Exception as error:  # noqa: BLE001 - service must remain observable
                bot.record_error(error)
            stop.wait(interval_seconds)

    def shutdown(signum: int, frame: object) -> None:
        del signum, frame
        stop.set()
        server.shutdown()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    Thread(target=poll, name="paper-poll", daemon=True).start()
    server.serve_forever()


if __name__ == "__main__":
    run()
