"""Read-only Binance public market-data adapter."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .events import Candle


class PublicDataError(ValueError):
    """Raised when public market data cannot be trusted or fetched."""


_ALLOWED_INTERVALS = frozenset({"1m", "5m", "15m", "30m", "1h", "4h", "1d"})


class BinancePublicData:
    """Small read-only client for the public spot klines endpoint."""

    def __init__(self, base_url: str = "https://api.binance.com/api/v3") -> None:
        if not base_url.startswith("https://"):
            raise ValueError("Binance base URL must use HTTPS")
        self._base_url = base_url.rstrip("/")

    def fetch_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 250,
        now: datetime | None = None,
    ) -> tuple[Candle, ...]:
        api_symbol = self._validate_parameters(symbol, interval, limit)
        current_time = now or datetime.now(UTC)
        if current_time.tzinfo is None or current_time.utcoffset() is None:
            raise PublicDataError("now must be timezone-aware")
        query = urlencode({"symbol": api_symbol, "interval": interval, "limit": limit})
        request_url = f"{self._base_url}/klines?{query}"
        request = Request(request_url, headers={"Accept": "application/json"})
        try:
            with urlopen(request, timeout=15) as response:
                payload = json.loads(response.read())
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            raise PublicDataError("Binance public data request failed") from error
        if not isinstance(payload, list):
            raise PublicDataError("Binance response is not a kline list")

        candles: list[Candle] = []
        for row in payload:
            if not isinstance(row, list) or len(row) < 7:
                raise PublicDataError("Binance response contains a malformed row")
            try:
                opened_at = datetime.fromtimestamp(int(row[0]) / 1000, UTC)
                closed_at = datetime.fromtimestamp((int(row[6]) + 1) / 1000, UTC)
                candle = Candle(
                    symbol=self._display_symbol(api_symbol),
                    timestamp=opened_at,
                    open=Decimal(str(row[1])),
                    high=Decimal(str(row[2])),
                    low=Decimal(str(row[3])),
                    close=Decimal(str(row[4])),
                    volume=Decimal(str(row[5])),
                )
            except (ArithmeticError, TypeError, ValueError, OverflowError) as error:
                raise PublicDataError("Binance response contains an invalid row") from error
            if closed_at <= current_time:
                candles.append(candle)
        return tuple(candles)

    @staticmethod
    def _validate_parameters(symbol: str, interval: str, limit: int) -> str:
        normalized = symbol.replace("/", "").upper()
        if not normalized.isalnum() or not 6 <= len(normalized) <= 20:
            raise PublicDataError("symbol is invalid")
        if interval not in _ALLOWED_INTERVALS:
            raise PublicDataError("interval is not allowed")
        if not 1 <= limit <= 1000:
            raise PublicDataError("limit must be between 1 and 1000")
        return normalized

    @staticmethod
    def _display_symbol(symbol: str) -> str:
        if symbol.endswith("USDT"):
            return f"{symbol[:-4]}/USDT"
        return symbol
