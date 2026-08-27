"""Stateful paper bot loop built on the standalone strategy and executor."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

from .events import Candle
from .fills import Fill, Order, OrderSide, OrderType
from .orders import OrderStore
from .paper import PaperExecutor
from .risk import RiskConfig, RiskContext, RiskRejected, size_entry
from .strategy import Action, StrategyConfig, StrategySignal, generate_signals


class CandleSource(Protocol):
    def fetch_klines(
        self,
        symbol: str,
        interval: str,
        limit: int,
        now: datetime,
    ) -> tuple[Candle, ...]: ...


@dataclass(frozen=True, slots=True)
class BotServiceConfig:
    symbol: str = "BTC/USDT"
    interval: str = "5m"
    lookback: int = 250
    demo_cash: Decimal = Decimal("5000")
    display_currency: str = "USDT"
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)

    def __post_init__(self) -> None:
        if not self.symbol.strip() or not self.interval.strip():
            raise ValueError("symbol and interval must not be empty")
        if not 2 <= self.lookback <= 1000:
            raise ValueError("lookback must be between 2 and 1000")
        if self.demo_cash <= 0:
            raise ValueError("demo_cash must be positive")
        if not self.display_currency.strip():
            raise ValueError("display_currency must not be empty")


@dataclass(frozen=True, slots=True)
class BotState:
    account_id: str
    mode: str
    demo_cash: Decimal
    display_currency: str
    symbol: str
    interval: str
    processed_bars: int
    last_candle_timestamp: datetime | None
    last_signal: str
    last_error: str | None
    cash: Decimal
    equity: Decimal
    position_quantity: Decimal

    def public_dict(self) -> dict[str, str | int | None]:
        return {
            "account_id": self.account_id,
            "mode": self.mode,
            "paper_only": "true",
            "demo_cash": str(self.demo_cash),
            "display_currency": self.display_currency,
            "symbol": self.symbol,
            "interval": self.interval,
            "processed_bars": self.processed_bars,
            "last_candle_timestamp": (
                self.last_candle_timestamp.isoformat() if self.last_candle_timestamp else None
            ),
            "last_signal": self.last_signal,
            "last_error": self.last_error,
            "cash": str(self.cash),
            "equity": str(self.equity),
            "position_quantity": str(self.position_quantity),
        }


class StandalonePaperBot:
    """Processes closed bars and keeps a single isolated paper account."""

    def __init__(
        self,
        candle_source: CandleSource,
        order_store: OrderStore,
        config: BotServiceConfig,
    ) -> None:
        self._source = candle_source
        self._config = config
        self._executor = PaperExecutor(config.demo_cash, order_store)
        self._last_candle_timestamp: datetime | None = None
        self._last_candle: Candle | None = None
        self._recent_candles: tuple[Candle, ...] = ()
        self._pending_signal: StrategySignal | None = None
        self._processed_bars = 0
        self._last_signal = "not started"
        self._last_error: str | None = None
        self._equity_history: list[dict[str, str]] = []
        self._activity: list[dict[str, str]] = []

    def tick(self, now: datetime | None = None) -> BotState:
        """Process exactly one new closed candle, if the source has one."""

        current_time = now or datetime.now(UTC)
        if current_time.tzinfo is None or current_time.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        candles = self._source.fetch_klines(
            self._config.symbol,
            self._config.interval,
            self._config.lookback,
            current_time,
        )
        if len(candles) < 2:
            raise ValueError("at least two closed candles are required")
        latest = candles[-1]
        self._recent_candles = tuple(candles[-180:])
        if (
            self._last_candle_timestamp is not None
            and latest.timestamp <= self._last_candle_timestamp
        ):
            return self.snapshot()

        if self._pending_signal is not None:
            self._execute_pending(self._pending_signal, latest)
            self._pending_signal = None

        signals = generate_signals(candles, self._config.strategy)
        current_signal = signals[-1]
        account = self._executor.account(latest)
        position_quantity = account.positions.get(self._config.symbol, Decimal("0"))
        if (
            current_signal.action is Action.ENTER_LONG
            and position_quantity == 0
            or current_signal.action is Action.EXIT_LONG
            and position_quantity > 0
        ):
            self._pending_signal = current_signal
        else:
            self._last_signal = current_signal.reason

        self._last_candle_timestamp = latest.timestamp
        self._last_candle = latest
        self._processed_bars += 1
        self._last_error = None
        state = self.snapshot()
        self._equity_history.append(
            {
                "timestamp": latest.timestamp.isoformat(),
                "equity": str(state.equity),
                "cash": str(state.cash),
                "position_quantity": str(state.position_quantity),
            }
        )
        self._equity_history = self._equity_history[-180:]
        self._activity.append(
            {
                "timestamp": latest.timestamp.isoformat(),
                "kind": "bar",
                "message": f"processed closed {self._config.interval} bar",
                "detail": self._last_signal,
            }
        )
        self._activity = self._activity[-40:]
        return state

    def _execute_pending(self, signal: StrategySignal, candle: Candle) -> Fill | None:
        account = self._executor.account(candle)
        position_quantity = account.positions.get(self._config.symbol, Decimal("0"))
        if signal.action is Action.ENTER_LONG:
            if signal.stop_price is None:
                raise ValueError("entry signal is missing stop price")
            context = RiskContext(
                equity=account.equity,
                cash=account.cash,
                gross_exposure=Decimal("0"),
                peak_equity=max(self._config.demo_cash, account.equity),
                daily_pnl=account.equity - self._config.demo_cash,
                signal_timestamp=signal.timestamp,
                now=candle.timestamp,
            )
            try:
                decision = size_entry(candle.open, signal.stop_price, context, self._config.risk)
            except RiskRejected as error:
                self._last_signal = f"risk rejected: {error}"
                return None
            order = Order(
                order_id=f"entry-{candle.timestamp.isoformat()}",
                symbol=self._config.symbol,
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=decision.quantity,
            )
            fill = self._executor.submit(order, candle)
            self._last_signal = f"entry filled: {fill.quantity} @ {fill.price}"
            return fill

        if signal.action is Action.EXIT_LONG and position_quantity > 0:
            order = Order(
                order_id=f"exit-{candle.timestamp.isoformat()}",
                symbol=self._config.symbol,
                side=OrderSide.SELL,
                order_type=OrderType.MARKET,
                quantity=position_quantity,
            )
            fill = self._executor.submit(order, candle)
            self._last_signal = f"exit filled: {fill.quantity} @ {fill.price}"
            return fill
        self._last_signal = "pending signal skipped"
        return None

    def snapshot(self) -> BotState:
        if self._last_candle is None:
            cash = self._config.demo_cash
            equity = cash
            position_quantity = Decimal("0")
        else:
            account = self._executor.account(self._last_candle)
            cash = account.cash
            equity = account.equity
            position_quantity = account.positions.get(self._config.symbol, Decimal("0"))
        return BotState(
            account_id="astral-demo-5000-usdt",
            mode="paper",
            demo_cash=self._config.demo_cash,
            display_currency=self._config.display_currency,
            symbol=self._config.symbol,
            interval=self._config.interval,
            processed_bars=self._processed_bars,
            last_candle_timestamp=self._last_candle_timestamp,
            last_signal=self._last_signal,
            last_error=self._last_error,
            cash=cash,
            equity=equity,
            position_quantity=position_quantity,
        )

    def dashboard_dict(self, now: datetime | None = None) -> dict[str, object]:
        """Return the read-only projection consumed by the terminal dashboard."""

        current_time = now or datetime.now(UTC)
        state = self.snapshot()
        latest = self._last_candle
        latest_payload: dict[str, str] | None = None
        if latest is not None:
            latest_payload = self._candle_dict(latest)
        price_history = [self._candle_dict(candle) for candle in self._recent_candles]
        marked_price = latest.close if latest is not None else Decimal("0")
        position_notional = state.position_quantity * marked_price
        activity = list(self._activity)
        if not activity and latest is None:
            activity = [
                {
                    "timestamp": current_time.astimezone(UTC).isoformat(),
                    "kind": "engine",
                    "message": "waiting for first closed bar",
                    "detail": "paper loop is online",
                }
            ]
        return {
            "schema_version": 1,
            "refresh_interval_ms": 10000,
            "server_time": current_time.astimezone(UTC).isoformat(),
            "last_updated": state.last_candle_timestamp.isoformat()
            if state.last_candle_timestamp
            else None,
            "account_id": state.account_id,
            "mode": state.mode,
            "paper_only": True,
            "demo_cash": str(state.demo_cash),
            "display_currency": state.display_currency,
            "symbol": state.symbol,
            "interval": state.interval,
            "processed_bars": state.processed_bars,
            "last_signal": state.last_signal,
            "last_error": state.last_error,
            "cash": str(state.cash),
            "equity": str(state.equity),
            "position": {
                "quantity": str(state.position_quantity),
                "notional": str(position_notional),
            },
            "latest_candle": latest_payload,
            "price_history": price_history,
            "equity_history": list(self._equity_history),
            "activity": activity,
        }

    @staticmethod
    def _candle_dict(candle: Candle) -> dict[str, str]:
        return {
            "timestamp": candle.timestamp.isoformat(),
            "open": str(candle.open),
            "high": str(candle.high),
            "low": str(candle.low),
            "close": str(candle.close),
            "volume": str(candle.volume),
        }

    def record_error(self, error: Exception) -> None:
        """Expose a bounded diagnostic in the read-only status endpoint."""

        self._last_error = f"{type(error).__name__}: {error}"
