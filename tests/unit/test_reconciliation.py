from datetime import UTC, datetime
from decimal import Decimal

import pytest

from astral_market_swarm.orders import OrderState, OrderStore
from astral_market_swarm.reconciliation import (
    BrokerOrderView,
    ReconciliationError,
    reconcile_order,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def seed_unknown(tmp_path: object) -> OrderStore:
    store = OrderStore(str(tmp_path / "orders.sqlite3"))
    store.create_intent("local-1", "ams-1", "BTC/USDT", "buy", Decimal("0.1"), NOW)
    store.transition("local-1", OrderState.SUBMITTED)
    store.transition("local-1", OrderState.UNKNOWN)
    return store


def test_reconciliation_rejects_mismatched_client_id(tmp_path: object) -> None:
    store = seed_unknown(tmp_path)

    with pytest.raises(ReconciliationError, match="client order"):
        reconcile_order(
            store,
            "local-1",
            BrokerOrderView("exchange-1", "other-client-id", OrderState.FILLED, Decimal("0.1")),
        )


def test_reconciliation_rejects_quantity_contradiction(tmp_path: object) -> None:
    store = seed_unknown(tmp_path)

    with pytest.raises(ReconciliationError, match="quantity"):
        reconcile_order(
            store,
            "local-1",
            BrokerOrderView("exchange-1", "ams-1", OrderState.FILLED, Decimal("0.2")),
        )
