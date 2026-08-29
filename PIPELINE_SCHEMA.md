# Pipeline Schema — Astral Market Swarm

**Type**: Event-driven spot trading engine  
**Version**: 1.0.0-standalone  
**Safety**: Paper/testnet-first, no live orders by default

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    MARKET DATA INGESTION                         │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │ Binance API  │───>│ Data Quality │───>│ Event Stream │      │
│  │  (klines)    │    │    Gate      │    │   (Candle)   │      │
│  └──────────────┘    └──────────────┘    └──────────────┘      │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    STRATEGY & SIGNAL GENERATION                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ EMA + RSI Recovery Strategy                              │   │
│  │ • Trend: 50-period EMA slope                             │   │
│  │ • Momentum: RSI recovery from oversold                   │   │
│  │ • Signal expiry: configurable max age                    │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                         RISK GATE                                │
│  • Position sizing (default: 1x Kelly)                          │
│  • Exposure limits (default: 80% max)                           │
│  • Cooldown enforcement                                          │
│  • Balance validation                                            │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    ORDER STATE MACHINE                           │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ States: PENDING → SUBMITTED → FILLED → SETTLED           │   │
│  │ Error handling: REJECTED, PARTIAL, UNKNOWN               │   │
│  │ Storage: SQLite with thread-safe locking                 │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    EXCHANGE ADAPTER                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │ Paper Trader │    │   Testnet    │    │ Live (gated) │      │
│  │ (default)    │    │  (optional)  │    │  (disabled)  │      │
│  └──────────────┘    └──────────────┘    └──────────────┘      │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    RECONCILIATION & AUDIT                        │
│  • Fill verification                                             │
│  • Balance reconciliation                                        │
│  • Order status sync                                             │
│  • Metrics export (ROI, Sharpe, drawdown, win rate)             │
└─────────────────────────────────────────────────────────────────┘
```

---

## Component Details

### 1. Market Data Ingestion

**Purpose**: Fetch and validate live or historical market data.

**Input**: 
- Binance public API (spot klines)
- Symbol (e.g., `BTC/USDT`)
- Interval (e.g., `5m`, `1h`, `1d`)

**Data Quality Gate**:
- ✓ Timestamp monotonicity
- ✓ No duplicate candles
- ✓ OHLCV sanity (high ≥ low, volume ≥ 0)
- ✓ Gap detection with logging

**Output**: 
- `Candle` events with validated OHLCV + timestamp

**Failure Mode**: 
- Stale data → warning logged, no signal generated
- Invalid candle → rejected, runtime continues

---

### 2. Strategy & Signal Generation

**Strategy**: EMA + RSI Recovery (trend + momentum hybrid)

**Parameters**:
| Parameter | Default | Description |
|-----------|---------|-------------|
| `ema_period` | 50 | Exponential moving average lookback |
| `rsi_period` | 14 | Relative strength index lookback |
| `rsi_recovery` | 50 | RSI threshold for buy signal (recovery from oversold) |
| `max_signal_age_minutes` | 60 | Signal expiry (prevents stale signals) |

**Logic**:
1. Calculate 50-period EMA and 14-period RSI
2. **Buy signal** if:
   - EMA slope > 0 (uptrend)
   - RSI crosses above `rsi_recovery` threshold
   - Signal age < `max_signal_age_minutes`
3. **Sell signal** if:
   - Opposite conditions OR manual exit

**Output**: `Signal(action=BUY|SELL, confidence=0.0-1.0, timestamp)`

---

### 3. Risk Gate

**Purpose**: Prevent over-leverage and catastrophic loss.

**Checks**:
1. **Position Sizing**:
   - Default: 1x Kelly criterion (conservative)
   - `paper-blast` profile: 3x Kelly (simulation only)
   
2. **Exposure Limit**:
   - Max 80% of available balance per position
   - Min order size: $10 USDT equivalent

3. **Cooldown**:
   - Min 1 candle between signals (prevents overtrading)

4. **Balance Validation**:
   - Reject if balance < min order size
   - Reject if order would exceed exposure limit

**Output**: `PASS` (order proceeds) or `REJECT` (logged, no order)

---

### 4. Order State Machine

**States**:
```
PENDING → SUBMITTED → FILLED → SETTLED
            ↓            ↓
        REJECTED     PARTIAL
            ↓
         UNKNOWN (reconcile)
```

**Storage**: SQLite (`orders.sqlite3`)
- Thread-safe with `RLock`
- Atomic state transitions
- Audit trail (all state changes logged)

**Reconciliation**:
- `UNKNOWN` status triggers exchange query
- Retry with exponential backoff
- Never submit duplicate order for same intent

---

### 5. Exchange Adapter

**Paper Trader** (default):
- Simulated fills at next candle open
- Virtual balance (default: 5,000 USDT)
- No real API keys required
- Slippage model: 0.1% (configurable)

**Testnet** (optional):
- Binance Spot Testnet
- Real API protocol, fake funds
- Requires testnet API keys

**Live** (gated):
- Disabled by default
- Requires explicit config flag `LIVE_TRADING_ENABLED=true`
- Rate limits enforced
- Order confirmation UI required (future)

---

### 6. Reconciliation & Audit

**Fill Verification**:
- Compare exchange fill price vs expected
- Log slippage > 0.5%

**Balance Reconciliation**:
- Periodic balance check (every 10 minutes)
- Alert if exchange balance ≠ local state

**Metrics**:
- ROI (return on investment)
- Sharpe ratio
- Max drawdown
- Win rate
- Average profit per trade

**Export**: JSON reports to `reports/` directory

---

## Profiles

### `conservative` (default)
- Kelly multiplier: 1x
- Max exposure: 80%
- Slippage: 0.1%
- Commission: 0.1% (Binance spot)

### `paper-blast` (simulation only)
- Kelly multiplier: 3x (high risk)
- Max exposure: 95%
- Slippage: 0.2%
- Virtual funds: 5,000 USDT
- **Cannot submit live orders** (enforced in code)

---

## Deployment

### Local Development
```bash
uv sync --extra dev
uv run pytest -q
uv run python -m astral_market_swarm.app
```

### Docker
```bash
docker build -t astral-market-swarm .
docker run -p 8080:8080 \
  -e SYMBOL=BTC/USDT \
  -e INTERVAL=5m \
  -v $(pwd)/state:/app/state \
  astral-market-swarm
```

### Production (not recommended for v1)
- Use testnet first
- Enable live trading only after 30+ days of stable testnet operation
- Monitor metrics dashboard
- Set up alerting (balance drops, repeated rejections)

---

## Data Flow Example

**Scenario**: BTC/USDT 5m paper trading

1. **Market data**: Binance API returns latest 5m candle
2. **Data QA**: Validates timestamp, OHLCV ranges → `Candle` event
3. **Strategy**: Calculates EMA(50)=45000, RSI(14)=52 → `BUY` signal
4. **Risk gate**: Balance=4800 USDT, exposure=0% → size=960 USDT (20% position)
5. **Order state**: Creates `PENDING` order, saves to SQLite
6. **Exchange adapter**: Paper trader simulates fill at next candle open (45100)
7. **Order state**: Transitions `PENDING → SUBMITTED → FILLED`
8. **Reconciliation**: Verifies fill price, updates balance (4800 - 960 = 3840 USDT + 0.0213 BTC)
9. **Metrics**: Updates ROI, Sharpe, drawdown

---

## Safety Features

1. **No live trading by default** (requires explicit config change)
2. **Paper/testnet first** (simulated fills, no real funds)
3. **Risk gate** (prevents over-leverage, enforces cooldown)
4. **Reconciliation** (unknown order status triggers exchange query)
5. **Audit trail** (all state transitions logged to SQLite)
6. **Read-only research mode** (backtest without state mutations)

---

## Future Enhancements

- [ ] Web dashboard (real-time metrics, order history)
- [ ] Multi-symbol support (portfolio allocation)
- [ ] Additional strategies (MACD, Bollinger Bands)
- [ ] Live order confirmation UI (safety gate for real trading)
- [ ] Telegram/Discord alerts
- [ ] Advanced risk models (VaR, CVaR)

---

## License

MIT License - see LICENSE file

---

## Disclaimer

**This software is for educational and research purposes only.**

Cryptocurrency trading carries substantial risk of loss. The authors and contributors are not responsible for any financial losses incurred through use of this software. Always test thoroughly on paper/testnet before considering live trading.

**Never trade with funds you cannot afford to lose.**
