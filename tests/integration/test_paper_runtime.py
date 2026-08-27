from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from astral_market_swarm.events import Candle
from astral_market_swarm.fills import Order, OrderSide, OrderType
from astral_market_swarm.orders import OrderState, OrderStore
from astral_market_swarm.paper import PaperExecutionError, PaperExecutor

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def bar(timestamp: datetime, price: str = "100") -> Candle:
    value = Decimal(price)
    return Candle(
        symbol="BTC/USDT",
        timestamp=timestamp,
        open=value,
        high=value + Decimal("2"),
        low=value - Decimal("2"),
        close=value + Decimal("1"),
        volume=Decimal("10"),
    )


def test_paper_executor_tracks_demo_cash_position_and_order_state(tmp_path: object) -> None:
    store = OrderStore(str(tmp_path / "orders.sqlite3"))
    executor = PaperExecutor(Decimal("5000"), store)
    buy = Order("buy-1", "BTC/USDT", OrderSide.BUY, OrderType.MARKET, Decimal("1"))

    fill = executor.submit(buy, bar(NOW))

    assert fill.quantity == Decimal("1")
    assert executor.account(bar(NOW)).positions["BTC/USDT"] == Decimal("1")
    assert executor.account(bar(NOW)).cash < Decimal("5000")
    assert store.get("buy-1").state is OrderState.FILLED

    sell = Order("sell-1", "BTC/USDT", OrderSide.SELL, OrderType.MARKET, Decimal("1"))
    executor.submit(sell, bar(NOW + timedelta(minutes=5), "101"))

    assert executor.account(bar(NOW)).positions.get("BTC/USDT", Decimal("0")) == Decimal("0")
    assert store.get("sell-1").state is OrderState.FILLED


def test_paper_executor_rejects_buy_without_cash(tmp_path: object) -> None:
    store = OrderStore(str(tmp_path / "orders.sqlite3"))
    executor = PaperExecutor(Decimal("10"), store)
    order = Order("buy-2", "BTC/USDT", OrderSide.BUY, OrderType.MARKET, Decimal("1"))

    with pytest.raises(PaperExecutionError, match="cash"):
        executor.submit(order, bar(NOW, "100"))

    assert store.get("buy-2").state is OrderState.REJECTED
