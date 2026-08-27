"""Exchange-neutral runtime contracts for the standalone engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Protocol

from .fills import Fill, Order
from .reconciliation import BrokerOrderView


class ExecutionMode(Enum):
    PAPER = "paper"
    TESTNET = "testnet"
    LIVE = "live"


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    mode: ExecutionMode = ExecutionMode.PAPER
    account_id: str = "astral-demo-5000"
    demo_cash: Decimal = Decimal("5000")
    display_currency: str = "EUR"

    def __post_init__(self) -> None:
        if not self.account_id.strip():
            raise ValueError("account_id must not be empty")
        if self.demo_cash <= 0:
            raise ValueError("demo_cash must be positive")
        if self.mode is ExecutionMode.LIVE:
            raise ValueError("live execution is disabled in v1")


@dataclass(frozen=True, slots=True)
class Quote:
    symbol: str
    bid: Decimal
    ask: Decimal
    timestamp: datetime

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol must not be empty")
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        if self.bid <= 0 or self.ask <= 0:
            raise ValueError("quote prices must be positive")
        if self.ask < self.bid:
            raise ValueError("ask must not be below bid")
        if self.timestamp.tzinfo != UTC:
            object.__setattr__(self, "timestamp", self.timestamp.astimezone(UTC))


class ExchangeAdapter(Protocol):
    """Minimal contract a concrete spot venue adapter must satisfy."""

    @property
    def mode(self) -> ExecutionMode: ...

    def quote(self, symbol: str) -> Quote: ...

    def submit(self, order: Order) -> Fill: ...

    def lookup(self, client_order_id: str) -> BrokerOrderView | None: ...

    def cancel(self, client_order_id: str) -> BrokerOrderView: ...
