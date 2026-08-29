from datetime import UTC, datetime
from decimal import Decimal
from threading import Thread

import pytest

from astral_market_swarm.orders import (
    OrderState,
    OrderStateError,
    OrderStore,
    deterministic_client_order_id,
)
from astral_market_swarm.reconciliation import BrokerOrderView, reconcile_order

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def test_order_store_persists_intent_before_submit_and_valid_transitions(tmp_path: object) -> None:
    store = OrderStore(str(tmp_path / "orders.sqlite3"))
    store.create_intent(
        order_id="local-1",
        client_order_id="ams-1",
        symbol="BTC/USDT",
        side="buy",
        quantity=Decimal("0.1"),
        created_at=NOW,
    )

    assert store.get("local-1").state is OrderState.CREATED
    store.transition("local-1", OrderState.SUBMITTED)
    store.transition("local-1", OrderState.UNKNOWN)

    assert store.get("local-1").state is OrderState.UNKNOWN
    assert store.retry_allowed("local-1") is False


def test_order_store_rejects_invalid_transition(tmp_path: object) -> None:
    store = OrderStore(str(tmp_path / "orders.sqlite3"))
    store.create_intent("local-2", "ams-2", "BTC/USDT", "buy", Decimal("0.1"), NOW)

    with pytest.raises(OrderStateError, match="transition"):
        store.transition("local-2", OrderState.FILLED)


def test_order_store_can_be_read_from_http_worker_thread(tmp_path: object) -> None:
    store = OrderStore(str(tmp_path / "threaded-orders.sqlite3"))
    store.create_intent("threaded-1", "ams-threaded-1", "BTC/USDT", "buy", Decimal("0.1"), NOW)
    errors: list[Exception] = []

    def read_from_worker() -> None:
        try:
            assert store.get("threaded-1").state is OrderState.CREATED
        except Exception as error:  # noqa: BLE001 - capture cross-thread regression
            errors.append(error)

    thread = Thread(target=read_from_worker)
    thread.start()
    thread.join(timeout=2)

    assert errors == []


def test_reconciliation_resolves_unknown_without_resubmitting(tmp_path: object) -> None:
    store = OrderStore(str(tmp_path / "orders.sqlite3"))
    store.create_intent("local-3", "ams-3", "BTC/USDT", "buy", Decimal("0.1"), NOW)
    store.transition("local-3", OrderState.SUBMITTED)
    store.transition("local-3", OrderState.UNKNOWN)

    outcome = reconcile_order(
        store,
        "local-3",
        BrokerOrderView("exchange-3", "ams-3", OrderState.FILLED, Decimal("0.1")),
    )

    assert outcome.resolved is True
    assert outcome.resubmitted is False
    assert store.get("local-3").state is OrderState.FILLED
    assert store.retry_allowed("local-3") is False


def test_client_order_id_is_deterministic_and_bounded() -> None:
    first = deterministic_client_order_id("BTC/USDT", "buy", NOW)
    second = deterministic_client_order_id("BTC/USDT", "buy", NOW)

    assert first == second
    assert first.startswith("ams-")
    assert len(first) <= 32
