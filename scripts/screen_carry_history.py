"""Screen historical BTC spot/perpetual carry opportunities after full round-trip costs."""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

COST = Decimal("0.0068")  # Four legs: fees, spreads, slippage, and conservative reserve.
MIN_FUNDING = Decimal("0.0001")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--funding", type=Path, required=True)
    parser.add_argument("--spot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    funding = json.loads(args.funding.read_text(encoding="utf-8"))["records"]
    spot = json.loads(args.spot.read_text(encoding="utf-8"))
    spot_by_hour = {
        datetime.fromtimestamp(int(row[0]) / 1000).replace(minute=0, second=0, microsecond=0):
        Decimal(str(row[4]))
        for row in spot
    }
    rows: list[dict[str, str]] = []
    for item in funding:
        timestamp = datetime.fromisoformat(item["timestamp"])
        settlement_hour = timestamp.replace(
            tzinfo=None, minute=0, second=0, microsecond=0
        )
        spot_price = spot_by_hour.get(settlement_hour)
        if spot_price is None:
            continue
        perp_price = Decimal(item["mark_price"])
        rate = Decimal(item["rate"])
        basis = perp_price / spot_price - Decimal("1")
        eligible = basis + rate >= COST and rate >= MIN_FUNDING
        if eligible:
            rows.append(
                {
                    "timestamp": item["timestamp"],
                    "spot": str(spot_price),
                    "perp": str(perp_price),
                    "basis": str(basis),
                    "funding": str(rate),
                    "gross_edge": str(basis + rate),
                    "net_edge_after_entry_exit_cost": str(basis + rate - COST),
                }
            )
    report = {
        "assumptions": {
            "round_trip_four_leg_cost_rate": str(COST),
            "minimum_funding_rate": str(MIN_FUNDING),
            "entry_rule": "basis + one funding settlement >= total round-trip cost",
        },
        "funding_records": len(funding),
        "aligned_records": len(spot_by_hour),
        "eligible_entries": len(rows),
        "entries": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        {
            "funding_records": len(funding),
            "eligible_entries": len(rows),
            "output": str(args.output),
        }
    )


if __name__ == "__main__":
    main()
