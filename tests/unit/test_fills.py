from datetime import UTC, datetime
from decimal import Decimal

from astral_market_swarm.events import Candle
from astral_market_swarm.fills import FillModel, Order, OrderSide, OrderType

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def bar(**overrides: object) -> Candle:
    values: dict[str, object] = {
        "symbol": "BTC/USDT",
        "timestamp": NOW,
        "open": Decimal("100"),
        "high": Decimal("110"),
        "low": Decimal("90"),
        "close": Decimal("105"),
        "volume": Decimal("10"),
    }
    values.update(overrides)
    return Candle(**values)


def order(**overrides: object) -> Order:
    values: dict[str, object] = {
        "order_id": "order-1",
        "symbol": "BTC/USDT",
        "side": OrderSide.BUY,
        "order_type": OrderType.MARKET,
        "quantity": Decimal("1"),
    }
    values.update(overrides)
    return Order(**values)


def test_market_fill_models_spread_slippage_and_fee() -> None:
    fill = FillModel(fee_rate=Decimal("0.01"), spread_bps=100, slippage_bps=0).fill(order(), bar())

    assert fill is not None
    assert fill.price == Decimal("100.5")
    assert fill.quantity == Decimal("1")
    assert fill.fee == Decimal("1.005")


def test_sell_fill_applies_costs_in_adverse_direction() -> None:
    fill = FillModel(spread_bps=100, slippage_bps=100).fill(order(side=OrderSide.SELL), bar())

    assert fill is not None
    assert fill.price == Decimal("98.5")


def test_limit_order_can_remain_unfilled_and_can_be_partial() -> None:
    model = FillModel(max_volume_fraction=Decimal("0.5"))
    unfilled = model.fill(
        order(order_type=OrderType.LIMIT, limit_price=Decimal("89")),
        bar(),
    )
    partial = model.fill(
        order(order_type=OrderType.LIMIT, limit_price=Decimal("95"), quantity=Decimal("10")),
        bar(volume=Decimal("2")),
    )

    assert unfilled is None
    assert partial is not None
    assert partial.quantity == Decimal("1")
    assert partial.price == Decimal("95")
