"""Read-only Binance USDⓈ-M perpetual public market-data adapter."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class FuturesPublicDataError(ValueError):
    """Raised when public perpetual data cannot be trusted or fetched."""


@dataclass(frozen=True, slots=True)
class PerpetualSnapshot:
    """A public mark/index/funding snapshot for one USDⓈ-M perpetual."""

    symbol: str
    timestamp: datetime
    mark_price: Decimal
    index_price: Decimal
    last_funding_rate: Decimal
    next_funding_time: datetime

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol must not be empty")
        for name in ("timestamp", "next_funding_time"):
            value = getattr(self, name)
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware")
            if value.tzinfo != UTC:
                object.__setattr__(self, name, value.astimezone(UTC))
        for name in ("mark_price", "index_price", "last_funding_rate"):
            try:
                value = Decimal(str(getattr(self, name)))
            except (ArithmeticError, ValueError) as error:
                raise ValueError(f"{name} must be a decimal number") from error
            if not value.is_finite():
                raise ValueError(f"{name} must be finite")
            object.__setattr__(self, name, value)
        if self.mark_price <= 0 or self.index_price <= 0:
            raise ValueError("mark and index prices must be positive")


@dataclass(frozen=True, slots=True)
class FundingSettlement:
    """One realized public perpetual funding event."""

    symbol: str
    timestamp: datetime
    rate: Decimal
    mark_price: Decimal

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol must not be empty")
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        if self.timestamp.tzinfo != UTC:
            object.__setattr__(self, "timestamp", self.timestamp.astimezone(UTC))
        for name in ("rate", "mark_price"):
            try:
                value = Decimal(str(getattr(self, name)))
            except (ArithmeticError, ValueError) as error:
                raise ValueError(f"{name} must be a decimal number") from error
            if not value.is_finite():
                raise ValueError(f"{name} must be finite")
            object.__setattr__(self, name, value)
        if self.mark_price <= 0:
            raise ValueError("mark_price must be positive")


class BinanceFuturesPublicData:
    """Small HTTPS-only client for public USDⓈ-M perpetual endpoints."""

    def __init__(self, base_url: str = "https://fapi.binance.com/fapi/v1") -> None:
        if not base_url.startswith("https://"):
            raise ValueError("Binance Futures base URL must use HTTPS")
        self._base_url = base_url.rstrip("/")

    def fetch_perpetual_snapshot(
        self, symbol: str, now: datetime | None = None
    ) -> PerpetualSnapshot:
        api_symbol = self._validate_symbol(symbol)
        current_time = self._validate_now(now)
        payload = self._fetch_json("premiumIndex", {"symbol": api_symbol})
        if not isinstance(payload, dict):
            raise FuturesPublicDataError("Binance Futures snapshot is malformed")
        try:
            response_symbol = str(payload["symbol"])
            timestamp = datetime.fromtimestamp(int(payload["time"]) / 1000, UTC)
            next_funding = datetime.fromtimestamp(int(payload["nextFundingTime"]) / 1000, UTC)
            snapshot = PerpetualSnapshot(
                self._display_symbol(response_symbol),
                timestamp,
                Decimal(str(payload["markPrice"])),
                Decimal(str(payload["indexPrice"])),
                Decimal(str(payload["lastFundingRate"])),
                next_funding,
            )
        except (ArithmeticError, KeyError, TypeError, ValueError, OverflowError) as error:
            raise FuturesPublicDataError("Binance Futures snapshot is malformed") from error
        if response_symbol != api_symbol:
            raise FuturesPublicDataError("Binance Futures snapshot symbol does not match request")
        if snapshot.timestamp > current_time:
            raise FuturesPublicDataError("Binance Futures snapshot is from the future")
        return snapshot

    def fetch_funding_history(
        self, symbol: str, limit: int = 100, now: datetime | None = None
    ) -> tuple[FundingSettlement, ...]:
        api_symbol = self._validate_symbol(symbol)
        if not 1 <= limit <= 1000:
            raise FuturesPublicDataError("limit must be between 1 and 1000")
        current_time = self._validate_now(now)
        payload = self._fetch_json("fundingRate", {"symbol": api_symbol, "limit": limit})
        if not isinstance(payload, list):
            raise FuturesPublicDataError("Binance Futures funding history is malformed")
        deduplicated: dict[datetime, FundingSettlement] = {}
        for row in payload:
            if not isinstance(row, dict):
                raise FuturesPublicDataError("Binance Futures funding row is malformed")
            try:
                response_symbol = str(row["symbol"])
                timestamp = datetime.fromtimestamp(int(row["fundingTime"]) / 1000, UTC)
                settlement = FundingSettlement(
                    self._display_symbol(response_symbol),
                    timestamp,
                    Decimal(str(row["fundingRate"])),
                    Decimal(str(row["markPrice"])),
                )
            except (ArithmeticError, KeyError, TypeError, ValueError, OverflowError) as error:
                raise FuturesPublicDataError("Binance Futures funding row is malformed") from error
            if response_symbol != api_symbol:
                raise FuturesPublicDataError(
                    "Binance Futures funding symbol does not match request"
                )
            if settlement.timestamp <= current_time:
                deduplicated.setdefault(settlement.timestamp, settlement)
        return tuple(deduplicated[key] for key in sorted(deduplicated))

    def _fetch_json(self, path: str, parameters: dict[str, str | int]) -> object:
        request = Request(
            f"{self._base_url}/{path}?{urlencode(parameters)}",
            headers={"Accept": "application/json"},
        )
        try:
            with urlopen(request, timeout=15) as response:
                return json.loads(response.read())
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
            raise FuturesPublicDataError("Binance Futures public data request failed") from error

    @staticmethod
    def _validate_symbol(symbol: str) -> str:
        normalized = symbol.replace("/", "").upper()
        if not normalized.isalnum() or not 6 <= len(normalized) <= 20:
            raise FuturesPublicDataError("symbol is invalid")
        return normalized

    @staticmethod
    def _validate_now(now: datetime | None) -> datetime:
        current_time = now or datetime.now(UTC)
        if current_time.tzinfo is None or current_time.utcoffset() is None:
            raise FuturesPublicDataError("now must be timezone-aware")
        return current_time.astimezone(UTC)

    @staticmethod
    def _display_symbol(symbol: str) -> str:
        if symbol.endswith("USDT"):
            return f"{symbol[:-4]}/USDT"
        return symbol
