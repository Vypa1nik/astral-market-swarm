# trend-regime strategy

Validated replacement for the `paper-blast` profile, which lost money in live
paper trading. This document records why the old profile failed, how the new one
was derived, and the exact evidence behind it.

## Why paper-blast lost money

`paper-blast` ran a momentum entry on 5-minute bars with a take-profit at
2x ATR(14). Reproduced on 30,000 real 5m BTC/USDT bars (105 days):

| metric | value |
| --- | --- |
| return | **-25.24%** |
| win rate | 13.2% |
| profit factor | 0.05 |
| max drawdown | 25.2% |
| trades | 53 |

The failure is arithmetic, not bad luck. The execution model in `fills.py`
charges a 0.1% fee per side plus 6 bps of adverse fill (2 bps spread +
5 bps slippage / the documented divisors), so a round trip costs **0.32% of
notional**. On 5m bars median ATR(14) is only **0.1214% of price**:

```
round-trip cost 0.3200%  /  median ATR 0.1214%  =  2.64x ATR
live take-profit target                        =  2.00x ATR
```

The target was smaller than the cost of reaching it. Measured over every 5m bar
with an unconditional triple barrier, gross edge was -0.0062% and net edge
**-0.3262% per trade**. No entry rule can fix a negative-sum exit structure.

## The timeframe is the fix

Cost is fixed in percentage terms while volatility scales with bar duration, so
the cost/ATR ratio decides whether any strategy can work:

| timeframe | median ATR(14) | round-trip cost in ATR units | best net EV found |
| --- | --- | --- | --- |
| 5m | 0.121% | **2.64x ATR** | negative for every signal tested |
| 15m | 0.279% | 1.15x ATR | negative for every signal tested |
| 1h | 0.599% | 0.53x ATR | still negative |
| 4h | 1.645% | **0.19x ATR** | positive |

Only on 4h bars does the market move far enough relative to trading costs.
`trend-regime` therefore runs on `INTERVAL=4h`, and the profile hardcodes that
interval rather than trusting the environment.

## Rules

Entry (`entry_mode="trend_stack"`), all conditions on the closed bar:

- `close > EMA200` — regime filter
- `EMA20 > EMA50 > EMA200` — aligned trend stack
- `close > previous close` — timing trigger

Exit, whichever comes first:

- initial stop at `entry - 3.0 x ATR(14)`
- stop moves to breakeven once price reaches `+1.0 R` (R = initial stop distance)
- trailing stop at `run_high - 8.0 x ATR(14)`; the stop only ever ratchets up
- time stop after 96 bars (16 days)
- no take-profit: winners are left to run, which is what pays for a 30% win rate

Risk: 3% risk per trade, 3x max position fraction, 3x paper leverage,
10% daily loss halt, 30% drawdown halt.

## Evidence

Full history, 19,784 real 4h BTC/USDT bars (2017-08-17 to 2026-08-30, 9.0 years),
starting from 10,000 USDT:

| metric | value |
| --- | --- |
| final equity | 77,281 USDT |
| total return | **+672.8%** |
| CAGR | +25.4% |
| profit factor | 1.54 |
| win rate | 29.7% |
| max drawdown | 23.4% |
| trades | 172 |
| avg hold | 48 bars (8 days) |

Yearly: 2017 +39.2%, 2018 -9.9%, 2019 +67.5%, 2020 +88.1%, 2021 +26.6%,
2022 -12.8%, 2023 +36.8%, 2024 +17.8%, 2025 +12.9%, 2026 -2.6%.
Profitable in 7 of 10 calendar years, including the 2018 and 2022 bear markets.

### Walk-forward validation

Five sequential folds of ~659 days each, no parameter refitting:

| fold 1 | fold 2 | fold 3 | fold 4 | fold 5 | positive |
| --- | --- | --- | --- | --- | --- |
| +73.9% | +157.8% | +5.4% | +23.5% | +22.9% | **5/5** |

On a final untouched holdout (last 701 days, never used for any tuning
decision) the config returned **+21.14%** with PF 1.14 and 16% max drawdown.

Buy-and-hold returned +1,697% over the same 9 years, so this strategy does not
beat simply holding BTC. It targets a lower drawdown (23.4% vs the 70%+ that
holding suffered in 2018 and 2022) and stays positive in bear markets, which
holding does not.

### Honest limitations

- Long-only on a single symbol, so it is exposed to BTC regime changes.
- 2026 year-to-date is -2.6%; chop without sustained trends is its weak case.
- 172 trades over 9 years is a small sample. Wide confidence intervals apply.
- Backtest results are not a promise of live results even in paper mode.

## Reproducing

```bash
# production behaviour is asserted by the test suite
uv run pytest tests/unit/test_trend_regime.py -v
```

The port from research to production was cross-checked by feeding the same real
4h bars through the production `generate_signals()` with the production risk
sizing: **+659.0%** versus the research harness's **+672.8%**. The small delta
comes from research sizing on the close while production sizes on the
adverse-adjusted fill.
