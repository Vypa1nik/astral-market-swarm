from datetime import UTC, datetime
from decimal import Decimal

from astral_market_swarm.orders import OrderStore

NOW = datetime(2026, 9, 18, tzinfo=UTC)


def test_carry_funding_event_is_idempotent_and_persisted(tmp_path: object) -> None:
    store = OrderStore(str(tmp_path / "orders.sqlite3"))

    first = store.record_carry_funding(
        "BTC/USDT", NOW, Decimal("0.0001"), Decimal("100"), Decimal("1")
    )
    duplicate = store.record_carry_funding(
        "BTC/USDT", NOW, Decimal("0.0001"), Decimal("100"), Decimal("1")
    )

    assert first is True
    assert duplicate is False
    assert store.carry_funding_total("BTC/USDT") == Decimal("0.01")
