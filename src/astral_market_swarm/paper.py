"""Isolated paper/testnet-style executor with no external side effects."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

from .events import Candle
from .fills import Fill, FillModel, Order, OrderSide
from .orders import OrderState, OrderStore, deterministic_client_order_id


class PaperExecutionError(ValueError):
    """Raised when a paper order cannot be accepted or filled."""


@dataclass(frozen=True, slots=True)
class PaperAccount:
    cash: Decimal
    positions: Mapping[str, Decimal]
    borrowed: Mapping[str, Decimal]
    equity: Decimal

    @property
    def borrowed_notional(self) -> Decimal:
        return sum(self.borrowed.values(), Decimal("0"))


class PaperExecutor:
    """One isolated paper account backed by its own order journal."""

    def __init__(
        self,
        initial_cash: Decimal,
        order_store: OrderStore,
        fill_model: FillModel | None = None,
        leverage: Decimal = Decimal("1"),
    ) -> None:
        if initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        if leverage < 1 or leverage > 3:
            raise ValueError("paper leverage must be between 1 and 3")
        self._order_store = order_store
        self._fill_model = fill_model or FillModel()
        self._leverage = leverage
        self._cash, self._positions, self._borrowed = order_store.load_paper_account_state(
            initial_cash
        )

    def submit(self, order: Order, candle: Candle) -> Fill:
        """Persist intent, simulate a fill, then update paper account state."""

        client_order_id = deterministic_client_order_id(
            order.symbol, order.side.value, candle.timestamp
        )
        try:
            self._order_store.create_intent(
                order.order_id,
                client_order_id,
                order.symbol,
                order.side.value,
                order.quantity,
                candle.timestamp,
            )
            self._order_store.transition(order.order_id, OrderState.SUBMITTED)
        except ValueError as error:
            raise PaperExecutionError(str(error)) from error

        fill = self._fill_model.fill(order, candle)
        if fill is None:
            self._order_store.transition(order.order_id, OrderState.REJECTED)
            raise PaperExecutionError("order was not fillable")

        if order.side is OrderSide.BUY:
            notional = fill.price * fill.quantity
            margin = notional / self._leverage
            borrowed = notional - margin
            required_cash = margin + fill.fee
            if required_cash > self._cash:
                self._order_store.transition(order.order_id, OrderState.REJECTED)
                raise PaperExecutionError("cash is insufficient")
            self._cash -= required_cash
            self._positions[order.symbol] = (
                self._positions.get(order.symbol, Decimal("0")) + fill.quantity
            )
            self._borrowed[order.symbol] = self._borrowed.get(order.symbol, Decimal("0")) + borrowed
        else:
            current_quantity = self._positions.get(order.symbol, Decimal("0"))
            if fill.quantity > current_quantity:
                self._order_store.transition(order.order_id, OrderState.REJECTED)
                raise PaperExecutionError("asset quantity is insufficient")
            current_borrowed = self._borrowed.get(order.symbol, Decimal("0"))
            borrowed_repayment = current_borrowed * fill.quantity / current_quantity
            self._cash += fill.price * fill.quantity - fill.fee - borrowed_repayment
            remaining = current_quantity - fill.quantity
            if remaining:
                self._positions[order.symbol] = remaining
                self._borrowed[order.symbol] = current_borrowed - borrowed_repayment
            else:
                self._positions.pop(order.symbol, None)
                self._borrowed.pop(order.symbol, None)
        self._order_store.save_paper_account(self._cash, self._positions, self._borrowed)

        self._order_store.transition(order.order_id, OrderState.ACKNOWLEDGED)
        final_state = (
            OrderState.FILLED if fill.quantity == order.quantity else OrderState.PARTIALLY_FILLED
        )
        self._order_store.transition(
            order.order_id,
            final_state,
            filled_quantity=fill.quantity,
        )
        return fill

    def account(self, candle: Candle) -> PaperAccount:
        """Mark this isolated paper account at the provided candle close."""

        marked_value = self._positions.get(candle.symbol, Decimal("0")) * candle.close
        borrowed = dict(self._borrowed)
        return PaperAccount(
            self._cash,
            dict(self._positions),
            borrowed,
            self._cash + marked_value - sum(borrowed.values(), Decimal("0")),
        )
