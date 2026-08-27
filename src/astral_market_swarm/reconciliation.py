"""Broker-to-local order reconciliation."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .orders import OrderState, OrderStateError, OrderStore


class ReconciliationError(ValueError):
    """Raised when a broker response contradicts the local order intent."""


@dataclass(frozen=True, slots=True)
class BrokerOrderView:
    exchange_order_id: str
    client_order_id: str
    state: OrderState
    filled_quantity: Decimal


@dataclass(frozen=True, slots=True)
class ReconciliationOutcome:
    resolved: bool
    resubmitted: bool


def reconcile_order(
    store: OrderStore,
    order_id: str,
    broker_order: BrokerOrderView,
) -> ReconciliationOutcome:
    """Resolve an order from a broker lookup without ever submitting a retry."""

    local = store.get(order_id)
    if local.client_order_id != broker_order.client_order_id:
        raise ReconciliationError("client order ID mismatch")
    if broker_order.filled_quantity < 0 or broker_order.filled_quantity > local.quantity:
        raise ReconciliationError("broker filled quantity contradicts local quantity")
    try:
        store.transition(
            order_id,
            broker_order.state,
            exchange_order_id=broker_order.exchange_order_id,
            filled_quantity=broker_order.filled_quantity,
        )
    except OrderStateError as error:
        raise ReconciliationError(str(error)) from error
    return ReconciliationOutcome(resolved=True, resubmitted=False)
