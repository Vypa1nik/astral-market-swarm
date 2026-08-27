"""Deterministic order fill model for simulation and paper execution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from .events import Candle


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"


@dataclass(frozen=True, slots=True)
class Order:
    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: Decimal
    limit_price: Decimal | None = None

    def __post_init__(self) -> None:
        if not self.order_id.strip() or not self.symbol.strip():
            raise ValueError("order_id and symbol must not be empty")
        if self.quantity <= 0:
            raise ValueError("order quantity must be positive")
        if self.order_type is OrderType.LIMIT and (
            self.limit_price is None or self.limit_price <= 0
        ):
            raise ValueError("limit orders require a positive limit_price")


@dataclass(frozen=True, slots=True)
class Fill:
    order_id: str
    symbol: str
    side: OrderSide
    timestamp: datetime
    quantity: Decimal
    price: Decimal
    fee: Decimal


@dataclass(frozen=True, slots=True)
class FillModel:
    fee_rate: Decimal = Decimal("0.001")
    spread_bps: int = 5
    slippage_bps: int = 5
    max_volume_fraction: Decimal = Decimal("1")

    def __post_init__(self) -> None:
        if self.fee_rate < 0 or self.spread_bps < 0 or self.slippage_bps < 0:
            raise ValueError("execution costs must be non-negative")
        if not 0 < self.max_volume_fraction <= 1:
            raise ValueError("max_volume_fraction must be in the interval (0, 1]")

    def fill(
        self,
        order: Order,
        candle: Candle,
        reference_price: Decimal | None = None,
    ) -> Fill | None:
        """Fill an order against one candle, returning None when not fillable."""

        if order.symbol != candle.symbol:
            raise ValueError("order symbol does not match candle symbol")
        if order.order_type is OrderType.LIMIT:
            assert order.limit_price is not None
            if order.side is OrderSide.BUY and candle.low > order.limit_price:
                return None
            if order.side is OrderSide.SELL and candle.high < order.limit_price:
                return None
            price = order.limit_price
        else:
            price = reference_price if reference_price is not None else candle.open
            if price <= 0:
                raise ValueError("reference price must be positive")
            spread = Decimal(self.spread_bps) / Decimal("20000")
            slippage = Decimal(self.slippage_bps) / Decimal("10000")
            adverse_cost = spread + slippage
            if order.side is OrderSide.BUY:
                price *= Decimal("1") + adverse_cost
            else:
                price *= Decimal("1") - adverse_cost

        available_quantity = candle.volume * self.max_volume_fraction
        quantity = min(order.quantity, available_quantity)
        if quantity <= 0:
            return None
        fee = price * quantity * self.fee_rate
        return Fill(
            order.order_id,
            order.symbol,
            order.side,
            candle.timestamp,
            quantity,
            price,
            fee,
        )
