"""Durable order intent and state transitions."""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from threading import RLock
from typing import Concatenate, ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")


class OrderState(Enum):
    CREATED = "created"
    SUBMITTED = "submitted"
    ACKNOWLEDGED = "acknowledged"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


class OrderStateError(ValueError):
    """Raised for missing orders or invalid order state transitions."""


_TRANSITIONS: dict[OrderState, frozenset[OrderState]] = {
    OrderState.CREATED: frozenset({OrderState.SUBMITTED, OrderState.CANCELLED, OrderState.UNKNOWN}),
    OrderState.SUBMITTED: frozenset(
        {
            OrderState.ACKNOWLEDGED,
            OrderState.PARTIALLY_FILLED,
            OrderState.FILLED,
            OrderState.CANCELLED,
            OrderState.REJECTED,
            OrderState.UNKNOWN,
        }
    ),
    OrderState.ACKNOWLEDGED: frozenset(
        {
            OrderState.PARTIALLY_FILLED,
            OrderState.FILLED,
            OrderState.CANCELLED,
            OrderState.REJECTED,
            OrderState.UNKNOWN,
        }
    ),
    OrderState.PARTIALLY_FILLED: frozenset(
        {
            OrderState.PARTIALLY_FILLED,
            OrderState.FILLED,
            OrderState.CANCELLED,
            OrderState.UNKNOWN,
        }
    ),
    OrderState.UNKNOWN: frozenset(
        {
            OrderState.ACKNOWLEDGED,
            OrderState.PARTIALLY_FILLED,
            OrderState.FILLED,
            OrderState.CANCELLED,
            OrderState.REJECTED,
        }
    ),
    OrderState.FILLED: frozenset(),
    OrderState.CANCELLED: frozenset(),
    OrderState.REJECTED: frozenset(),
}


def _locked(
    method: Callable[Concatenate[OrderStore, P], R],
) -> Callable[Concatenate[OrderStore, P], R]:
    def wrapper(self: OrderStore, /, *args: P.args, **kwargs: P.kwargs) -> R:
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper


@dataclass(frozen=True, slots=True)
class OrderRecord:
    order_id: str
    client_order_id: str
    symbol: str
    side: str
    quantity: Decimal
    state: OrderState
    created_at: datetime
    updated_at: datetime
    exchange_order_id: str | None
    filled_quantity: Decimal


class OrderStore:
    """Small SQLite-backed order journal for one isolated bot namespace."""

    def __init__(self, path: str) -> None:
        self._lock = RLock()
        self._connection = sqlite3.connect(path, check_same_thread=False, timeout=30)
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                client_order_id TEXT NOT NULL UNIQUE,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                quantity TEXT NOT NULL,
                state TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                exchange_order_id TEXT,
                filled_quantity TEXT NOT NULL
            )
            """
        )
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS paper_account_state (
                state_key TEXT PRIMARY KEY,
                state_value TEXT NOT NULL
            )
            """
        )
        self._connection.commit()

    @_locked
    def create_intent(
        self,
        order_id: str,
        client_order_id: str,
        symbol: str,
        side: str,
        quantity: Decimal,
        created_at: datetime,
    ) -> None:
        if quantity <= 0 or created_at.tzinfo is None or created_at.utcoffset() is None:
            raise ValueError("quantity must be positive and created_at must be timezone-aware")
        timestamp = created_at.isoformat()
        try:
            self._connection.execute(
                """
                INSERT INTO orders (
                    order_id, client_order_id, symbol, side, quantity, state,
                    created_at, updated_at, exchange_order_id, filled_quantity
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
                """,
                (
                    order_id,
                    client_order_id,
                    symbol,
                    side,
                    str(quantity),
                    OrderState.CREATED.value,
                    timestamp,
                    timestamp,
                    "0",
                ),
            )
            self._connection.commit()
        except sqlite3.IntegrityError as error:
            self._connection.rollback()
            raise OrderStateError("order intent already exists") from error

    @_locked
    def get(self, order_id: str) -> OrderRecord:
        row = self._connection.execute(
            "SELECT order_id, client_order_id, symbol, side, quantity, state, created_at, "
            "updated_at, exchange_order_id, filled_quantity FROM orders WHERE order_id = ?",
            (order_id,),
        ).fetchone()
        if row is None:
            raise OrderStateError(f"order not found: {order_id}")
        return OrderRecord(
            order_id=row[0],
            client_order_id=row[1],
            symbol=row[2],
            side=row[3],
            quantity=Decimal(row[4]),
            state=OrderState(row[5]),
            created_at=datetime.fromisoformat(row[6]),
            updated_at=datetime.fromisoformat(row[7]),
            exchange_order_id=row[8],
            filled_quantity=Decimal(row[9]),
        )

    @_locked
    def transition(
        self,
        order_id: str,
        new_state: OrderState,
        exchange_order_id: str | None = None,
        filled_quantity: Decimal | None = None,
    ) -> OrderRecord:
        current = self.get(order_id)
        if new_state not in _TRANSITIONS[current.state]:
            raise OrderStateError(f"invalid transition: {current.state.value} -> {new_state.value}")
        filled = current.filled_quantity if filled_quantity is None else filled_quantity
        if filled < current.filled_quantity or filled > current.quantity:
            raise OrderStateError("filled quantity is outside order bounds")
        if new_state is OrderState.FILLED and filled != current.quantity:
            raise OrderStateError("filled state requires the full quantity")
        updated_at = datetime.now(current.updated_at.tzinfo)
        self._connection.execute(
            "UPDATE orders SET state = ?, updated_at = ?, "
            "exchange_order_id = COALESCE(?, exchange_order_id), "
            "filled_quantity = ? WHERE order_id = ?",
            (new_state.value, updated_at.isoformat(), exchange_order_id, str(filled), order_id),
        )
        self._connection.commit()
        return self.get(order_id)

    @_locked
    def retry_allowed(self, order_id: str) -> bool:
        return self.get(order_id).state is OrderState.CREATED

    @_locked
    def load_paper_account(
        self,
        initial_cash: Decimal,
    ) -> tuple[Decimal, dict[str, Decimal]]:
        cash, positions, _borrowed = self.load_paper_account_state(initial_cash)
        return cash, positions

    @_locked
    def load_paper_account_state(
        self,
        initial_cash: Decimal,
    ) -> tuple[Decimal, dict[str, Decimal], dict[str, Decimal]]:
        cash_row = self._connection.execute(
            "SELECT state_value FROM paper_account_state WHERE state_key = 'cash'"
        ).fetchone()
        cash = initial_cash if cash_row is None else Decimal(cash_row[0])
        rows = self._connection.execute(
            "SELECT state_key, state_value FROM paper_account_state "
            "WHERE state_key LIKE 'position:%'"
        ).fetchall()
        positions = {
            row[0].removeprefix("position:"): Decimal(row[1])
            for row in rows
            if Decimal(row[1]) != 0
        }
        borrowed_rows = self._connection.execute(
            "SELECT state_key, state_value FROM paper_account_state "
            "WHERE state_key LIKE 'borrowed:%'"
        ).fetchall()
        borrowed = {
            row[0].removeprefix("borrowed:"): Decimal(row[1])
            for row in borrowed_rows
            if Decimal(row[1]) != 0
        }
        return cash, positions, borrowed

    @_locked
    def save_paper_account(
        self,
        cash: Decimal,
        positions: dict[str, Decimal],
        borrowed: dict[str, Decimal] | None = None,
    ) -> None:
        self._connection.execute(
            "INSERT INTO paper_account_state(state_key, state_value) VALUES('cash', ?) "
            "ON CONFLICT(state_key) DO UPDATE SET state_value = excluded.state_value",
            (str(cash),),
        )
        self._connection.execute(
            "DELETE FROM paper_account_state WHERE state_key LIKE 'position:%'"
        )
        self._connection.executemany(
            "INSERT INTO paper_account_state(state_key, state_value) VALUES(?, ?)",
            [(f"position:{symbol}", str(quantity)) for symbol, quantity in positions.items()],
        )
        if borrowed is not None:
            self._connection.execute(
                "DELETE FROM paper_account_state WHERE state_key LIKE 'borrowed:%'"
            )
            self._connection.executemany(
                "INSERT INTO paper_account_state(state_key, state_value) VALUES(?, ?)",
                [(f"borrowed:{symbol}", str(value)) for symbol, value in borrowed.items()],
            )
        self._connection.commit()

    @_locked
    def close(self) -> None:
        self._connection.close()


def deterministic_client_order_id(symbol: str, side: str, timestamp: datetime) -> str:
    """Build a stable, bounded ID for idempotent broker submission."""

    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    payload = f"{symbol}|{side}|{timestamp.isoformat()}".encode()
    return f"ams-{hashlib.sha256(payload).hexdigest()[:28]}"
