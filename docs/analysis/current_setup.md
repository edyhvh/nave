# Current Setup — BTC and ETH

> **Generated:** 2026-04-09 (refreshed via `theory_v2` live analyzer)
> **Engine:** `trading.theory_v2.TheoryV2Engine` with iter 4 / iter 5 / iter 6
> refinement gates active
> **Data window:** 5 years weekly · 1 year daily · 90 days 4H · 30 days 1H
> **Last available local bar:** 2026-04-09 (gap-filled from Binance)
> **Run:** `python -m trading.theory_v2 --coins BTC ETH`

## BTC

```
ACTION    : STAND ASIDE
STAGE     : daily
REASON    : daily does not confirm weekly bias
```

- Weekly bias: **long**
- Daily confirmation: **not confirmed**
- 4H setup: not evaluated (gate not reached)
- 1H trigger: none

Interpretation:

- BTC still leans bullish at the weekly level, but the 20-day SMA on the daily
  is above current price, so the daily-confirmation gate fails.
- Because the daily gate fails, none of the downstream gates are evaluated:
  there is no climax check, no chase test, no 4H setup, no 1H trigger.
- The correct read is **patience**. A fresh entry requires the daily SMA to
  reflect renewed bullish momentum (price above the 20-day SMA + 0.5%).

## ETH

```
ACTION    : STAND ASIDE
STAGE     : daily
REASON    : daily does not confirm weekly bias
```

- Weekly bias: **long**
- Daily confirmation: **not confirmed**
- 4H setup: not evaluated
- 1H trigger: none

Interpretation:

- ETH mirrors BTC: weekly is long, but the daily layer has not yet confirmed
  the continuation off the recent pullback.
- Both coins are in the same posture today — the engine's correct call is to
  stand aside until the daily catches up.

## How to refresh this card

```
python -m trading.theory_v2 --coins BTC ETH
```

The analyzer loads weekly/daily/4H/1H data via the project's `data_loader`
(local Parquet files with Binance gap-fill), runs the refined engine for each
coin, and prints an action card. A `STAND ASIDE` card always names the gate
that stopped the evaluation, so you can see whether you are waiting for a
weekly bias flip, a daily confirmation, a climax cooldown to expire, a deeper
retrace, a 4H setup, or a 1H trigger.

## Engine reference

Each gate, in order:

1. **Weekly bias** — close vs 8-week SMA (±2% deadband). Wider deadband
   prevents false short flips during bull-market pullbacks.
2. **Daily confirmation** — close vs 10-day SMA must agree with weekly bias.
   Shorter window responds faster to trend resumptions.
3. **Climax cooldown (iter 4)** — no daily true range > 3 × 20-day ATR within
   the last 10 bars. If a recent climax candle is detected, all entries are
   suspended until the cooldown window expires.
4. **Chase prevention (iter 5)** — current price must be inside the 50–95 %
   retracement band of the most recent daily impulse leg. Shallow retracements
   (still extended near the impulse high/low) are rejected. If no clean leg
   is detectable in the last 60 daily bars, the gate is permissive.
5. **4H setup** — close vs 8-bar SMA on 4H must agree with bias.
6. **1H trigger** — entry at last 1H close, stop is the wider of:
   - the swing high/low of the last 24 1H bars (structural)
   - 1.5 × 14-day daily ATR (volatility floor — iter 6)
   Targets use ZC1/ZC2 dynamic exit: ZC1 (80% at nearest structural swing
   level, min 1R) and ZC2 (20% trailed to next swing or 2.5R).

The fired signal is routed through `trading.execution.build_execution_plan`,
which enforces the timeframe contract (weekly/daily bias, 4H setup, 1H
trigger, positive risk distance) before any order is sent.
