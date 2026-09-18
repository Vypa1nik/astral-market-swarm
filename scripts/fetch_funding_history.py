"""Fetch reproducible public Binance perpetual funding history snapshots."""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from astral_market_swarm.binance_futures_public import BinanceFuturesPublicData


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not 1 <= args.days <= 3650:
        raise ValueError("days must be between 1 and 3650")
    now = datetime.now(UTC)
    start = now - timedelta(days=args.days)
    adapter = BinanceFuturesPublicData()
    settlements = []
    cursor = start
    while cursor <= now:
        page = adapter.fetch_funding_history(
            args.symbol,
            limit=1000,
            start_time=cursor,
            end_time=now,
            now=now,
        )
        if not page:
            break
        settlements.extend(page)
        next_cursor = page[-1].timestamp + timedelta(milliseconds=1)
        if next_cursor <= cursor:
            raise RuntimeError("funding history pagination did not advance")
        cursor = next_cursor
        if len(page) < 1000:
            break
    settlements = list({item.timestamp: item for item in settlements}.values())
    settlements.sort(key=lambda item: item.timestamp)
    payload = {
        "symbol": args.symbol,
        "fetched_at": now.isoformat(),
        "requested_start": start.isoformat(),
        "records": [
            {
                "timestamp": item.timestamp.isoformat(),
                "rate": str(item.rate),
                "mark_price": str(item.mark_price),
            }
            for item in settlements
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    total_rate = sum((item.rate for item in settlements), Decimal("0"))
    print(
        {
            "output": str(args.output),
            "records": len(settlements),
            "first": settlements[0].timestamp.isoformat() if settlements else None,
            "last": settlements[-1].timestamp.isoformat() if settlements else None,
            "total_rate": str(total_rate),
        }
    )


if __name__ == "__main__":
    main()
