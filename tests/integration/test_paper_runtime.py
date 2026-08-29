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


def test_paper_account_persists_across_executor_restart(tmp_path: object) -> None:
    database = str(tmp_path / "orders.sqlite3")
    first_store = OrderStore(database)
    first_executor = PaperExecutor(Decimal("5000"), first_store)
    order = Order("buy-3", "BTC/USDT", OrderSide.BUY, OrderType.MARKET, Decimal("1"))
    first_executor.submit(order, bar(NOW))
    first_store.close()

    second_store = OrderStore(database)
    second_executor = PaperExecutor(Decimal("5000"), second_store)

    account = second_executor.account(bar(NOW))
    assert account.positions["BTC/USDT"] == Decimal("1")
    assert account.cash < Decimal("5000")


def test_flat_paper_account_stays_flat_after_restart(tmp_path: object) -> None:
    database = str(tmp_path / "flat-after-exit.sqlite3")
    store = OrderStore(database)
    executor = PaperExecutor(Decimal("5000"), store, leverage=Decimal("3"))
    executor.submit(
        Order("buy-flat", "BTC/USDT", OrderSide.BUY, OrderType.MARKET, Decimal("1")),
        bar(NOW),
    )
    executor.submit(
        Order("sell-flat", "BTC/USDT", OrderSide.SELL, OrderType.MARKET, Decimal("1")),
        bar(NOW + timedelta(minutes=5), "101"),
    )
    store.close()

    restarted_store = OrderStore(database)
    restarted = PaperExecutor(Decimal("5000"), restarted_store, leverage=Decimal("3"))
    account = restarted.account(bar(NOW + timedelta(minutes=5), "101"))

    assert account.positions.get("BTC/USDT", Decimal("0")) == Decimal("0")
    assert account.borrowed_notional == Decimal("0")


def test_paper_executor_supports_bounded_leveraged_margin_and_repayment(
    tmp_path: object,
) -> None:
    database = str(tmp_path / "leveraged.sqlite3")
    store = OrderStore(database)
    executor = PaperExecutor(Decimal("5000"), store, leverage=Decimal("3"))
    entry_bar = bar(NOW, "100")
    entry = Order("leveraged-buy", "BTC/USDT", OrderSide.BUY, OrderType.MARKET, Decimal("5"))

    executor.submit(entry, entry_bar)
    leveraged = executor.account(entry_bar)

    assert leveraged.borrowed_notional > 0
    assert leveraged.cash > Decimal("4500")
    assert leveraged.equity > Decimal("5000")
    assert leveraged.equity < Decimal("5050")

    exit_bar = bar(NOW + timedelta(minutes=5), "102")
    exit_order = Order("leveraged-sell", "BTC/USDT", OrderSide.SELL, OrderType.MARKET, Decimal("5"))
    executor.submit(exit_order, exit_bar)
    flat = executor.account(exit_bar)

    assert flat.positions.get("BTC/USDT", Decimal("0")) == Decimal("0")
    assert flat.borrowed_notional == Decimal("0")
