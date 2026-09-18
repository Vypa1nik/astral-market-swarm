from datetime import UTC, datetime
from decimal import Decimal

from astral_market_swarm.binance_futures_public import FundingSettlement, PerpetualSnapshot
from astral_market_swarm.carry_strategy import CarryAction, CarryConfig, CarryContext, decide

NOW = datetime(2026, 9, 18, tzinfo=UTC)


def context(**overrides: object) -> CarryContext:
    base: dict[str, object] = {
        "symbol": "BTC/USDT",
        "spot_mark": Decimal("100"),
        "snapshot": PerpetualSnapshot(
            "BTC/USDT",
            NOW,
            Decimal("101"),
            Decimal("100"),
            Decimal("0.0002"),
            NOW,
        ),
        "funding_history": tuple(
            FundingSettlement("BTC/USDT", NOW, Decimal("0.0002"), Decimal("101"))
            for _ in range(7)
        ),
        "now": NOW,
        "has_open_position": False,
        "adl_risk": "low",
    }
    base.update(overrides)
    return CarryContext(**base)


def test_opens_only_when_basis_and_funding_cover_cost_hurdle() -> None:
    decision = decide(
        context(),
        CarryConfig(round_trip_cost_rate=Decimal("0.006"), safety_hurdle_rate=Decimal("0.001")),
    )

    assert decision.action is CarryAction.OPEN_PAIR
    assert decision.reason == "cost_covered_carry_edge"
    assert decision.expected_net_edge > 0


def test_reports_explicit_reason_when_basis_is_below_cost_hurdle() -> None:
    decision = decide(
        context(
            snapshot=PerpetualSnapshot(
                "BTC/USDT", NOW, Decimal("100.10"), Decimal("100"), Decimal("0.0002"), NOW
            )
        ),
        CarryConfig(round_trip_cost_rate=Decimal("0.006"), safety_hurdle_rate=Decimal("0.001")),
    )

    assert decision.action is CarryAction.HOLD_CASH
    assert decision.reason == "edge_below_cost_hurdle"


def test_blocks_pair_when_funding_is_not_persistent() -> None:
    history = tuple(
        FundingSettlement("BTC/USDT", NOW, Decimal("-0.0001"), Decimal("101"))
        for _ in range(7)
    )

    decision = decide(context(funding_history=history), CarryConfig())

    assert decision.action is CarryAction.HOLD_CASH
    assert decision.reason == "funding_not_persistent"
