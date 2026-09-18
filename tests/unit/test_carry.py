from datetime import UTC, datetime
from decimal import Decimal

import pytest

from astral_market_swarm.carry import (
    CarryPosition,
    basis_rate,
    position_pnl,
)

NOW = datetime(2026, 9, 18, tzinfo=UTC)


def position() -> CarryPosition:
    return CarryPosition(
        symbol="BTC/USDT",
        spot_quantity=Decimal("1"),
        short_quantity=Decimal("1"),
        spot_entry=Decimal("100"),
        perp_entry=Decimal("101"),
        collateral=Decimal("50"),
        opened_at=NOW,
        accrued_funding=Decimal("2"),
        fees_paid=Decimal("1"),
        rebalance_cost=Decimal("0"),
    )


def test_equal_sized_spot_and_short_perp_is_delta_neutral_on_parallel_move() -> None:
    pnl = position_pnl(position(), spot_mark=Decimal("120"), perp_mark=Decimal("121"))

    assert pnl.spot_pnl == Decimal("20")
    assert pnl.perp_pnl == Decimal("-20")
    assert pnl.net_delta == Decimal("0")
    assert pnl.net_pnl == Decimal("1")


def test_basis_rate_rejects_non_positive_spot() -> None:
    with pytest.raises(ValueError, match="spot"):
        basis_rate(Decimal("100"), Decimal("0"))
