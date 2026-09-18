from datetime import UTC, datetime
from decimal import Decimal

from astral_market_swarm.carry import CarryPosition
from astral_market_swarm.carry_backtest import CarryBacktestConfig, run_carry_backtest

NOW = datetime(2026, 9, 18, tzinfo=UTC)


def test_backtest_accounts_for_funding_and_four_leg_costs() -> None:
    position = CarryPosition(
        symbol="BTC/USDT",
        spot_quantity=Decimal("1"),
        short_quantity=Decimal("1"),
        spot_entry=Decimal("100"),
        perp_entry=Decimal("101"),
        collateral=Decimal("50"),
        opened_at=NOW,
        accrued_funding=Decimal("0"),
        fees_paid=Decimal("0"),
        rebalance_cost=Decimal("0"),
    )

    result = run_carry_backtest(
        position,
        exit_spot=Decimal("110"),
        exit_perp=Decimal("110"),
        funding_rates=(Decimal("0.001"), Decimal("0.001")),
        config=CarryBacktestConfig(total_execution_cost_rate=Decimal("0.004")),
    )

    assert result.spot_pnl == Decimal("10")
    assert result.perp_pnl == Decimal("-9")
    assert result.funding_pnl == Decimal("0.22")
    assert result.execution_cost == Decimal("1.684")
    assert result.net_pnl == Decimal("-0.464")
