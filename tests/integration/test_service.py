from datetime import UTC, datetime
from decimal import Decimal

import pytest

from astral_market_swarm.events import Candle
from astral_market_swarm.orders import OrderStore
from astral_market_swarm.service import BotServiceConfig, StandalonePaperBot, profile_config
from astral_market_swarm.strategy import StrategyConfig

START = datetime(2026, 1, 1, tzinfo=UTC)


def candles(closes: list[str]) -> list[Candle]:
    result: list[Candle] = []
    for index, close in enumerate(closes):
        value = Decimal(close)
        result.append(
            Candle(
                symbol="BTC/USDT",
                timestamp=START.replace(minute=index * 5),
                open=value,
                high=value + Decimal("1"),
                low=value - Decimal("1"),
                close=value,
                volume=Decimal("100"),
            )
        )
    return result


class FakeSource:
    def __init__(self, responses: list[list[Candle]]) -> None:
        self.responses = responses
        self.calls = 0

    def fetch_klines(
        self,
        symbol: str,
        interval: str,
        limit: int,
        now: datetime,
    ) -> tuple[Candle, ...]:
        response = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        return tuple(response)


def test_paper_bot_processes_bars_with_5000_demo_account(tmp_path: object) -> None:
    data = candles(["100", "102", "100", "98", "99", "102", "99"])
    source = FakeSource([data[:5], data[:6], data[:7]])
    store = OrderStore(str(tmp_path / "orders.sqlite3"))
    bot = StandalonePaperBot(
        source,
        store,
        BotServiceConfig(
            demo_cash=Decimal("5000"),
            display_currency="USDT",
            strategy=StrategyConfig(
                ema_period=2,
                rsi_period=2,
                atr_period=2,
                rsi_recovery=Decimal("30"),
                atr_stop_multiple=Decimal("1"),
                take_profit_multiple=Decimal("1"),
            ),
        ),
    )

    bot.tick(data[4].timestamp)
    bot.tick(data[5].timestamp)
    bot.tick(data[6].timestamp)
    state = bot.snapshot()

    assert state.mode == "paper"
    assert state.demo_cash == Decimal("5000")
    assert state.processed_bars == 3
    assert state.last_candle_timestamp == data[6].timestamp
    assert state.equity > 0
    assert state.position_quantity == Decimal("0")


def test_paper_blast_profile_is_explicitly_leveraged_and_capped() -> None:
    config = profile_config("paper-blast")

    assert config.strategy.ema_period == 20
    assert config.strategy.rsi_recovery == Decimal("50")
    assert config.strategy.max_hold_bars == 12
    assert config.risk.leverage == Decimal("3")
    assert config.risk.max_position_fraction == Decimal("1.5")
    assert config.risk.max_gross_exposure_fraction == Decimal("1.5")


def test_unknown_profile_fails_closed() -> None:
    with pytest.raises(ValueError, match="unknown strategy profile"):
        profile_config("live-blast")
