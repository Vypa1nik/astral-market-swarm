from decimal import Decimal

from astral_market_swarm.carry_risk import CarryRiskConfig, CarryRiskContext, approve_pair


def test_rejects_pair_that_breaks_cash_reserve_after_collateral() -> None:
    decision = approve_pair(
        CarryRiskContext(
            equity=Decimal("10000"),
            cash=Decimal("4500"),
            existing_collateral=Decimal("0"),
            target_notional=Decimal("2000"),
            proposed_collateral=Decimal("1000"),
            maintenance_margin=Decimal("100"),
        ),
        CarryRiskConfig(),
    )

    assert decision.approved is False
    assert decision.reason == "minimum_cash_reserve"


def test_approves_pair_with_margin_buffer_and_reserved_cash() -> None:
    decision = approve_pair(
        CarryRiskContext(
            equity=Decimal("10000"),
            cash=Decimal("10000"),
            existing_collateral=Decimal("0"),
            target_notional=Decimal("2000"),
            proposed_collateral=Decimal("1000"),
            maintenance_margin=Decimal("100"),
        ),
        CarryRiskConfig(),
    )

    assert decision.approved is True
    assert decision.reason == "approved"
