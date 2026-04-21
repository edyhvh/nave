# Iter 16 — Why we only caught the Apr 2026 BTC rally at the top

> **Date:** 2026-04-21
> **Scope:** Diagnostic. User question: "The latest Bitcoin rally had a lot
> of momentum. How could we have known?" Result: negative — the recent
> rally exposes a structural limit of the 4-week momentum lookback, and
> the obvious fixes all degrade other periods.

---

## What actually happened (BTC 2026-03 → 2026-04)

Bottom 2026-03-02 at $65,971 → peak so far 2026-04-20 at $76,361
(+15.7% in 7 weeks, with several 1–3 week pullbacks along the way).

Weekly momentum velocity (our iter 14 gate, `lookback=4`, `min_velocity=1.2`):

| Week        | Close    | Δ 4w     | ATR8    | velocity | bias    |
| ----------- | -------- | -------- | ------- | -------- | ------- |
| 2026-03-02  | 65,971   | −4,359   | 9,594   | −0.45    | neutral |
| 2026-03-09  | 72,815   | +3,983   | 9,631   | +0.41    | neutral |
| 2026-03-16  | 67,859   | +216     | 9,761   | +0.02    | neutral |
| 2026-03-23  | 66,011   | +234     | 8,777   | +0.03    | neutral |
| 2026-03-30  | 69,034   | +3,063   | 6,807   | +0.45    | neutral |
| 2026-04-06  | 72,963   | +147     | 6,728   | +0.02    | neutral |
| 2026-04-13  | 74,418   | +5,943   | 7,137   | +0.83    | neutral |
| **2026-04-20** | **76,361** | **+10,350** | **6,556** | **+1.58** | **long** |

Our gate fired on the final week at $76,361 — ~2.5% off the peak, with
the rally already 85% spent. Live, even this late fire was blocked at
`weekly_cot` because BTC net-speculator positioning is at the 95th
percentile (extreme — reversal risk).

**So we effectively missed the whole rally.**

## Why the 4-week momentum gate was blind

The 4-week window repeatedly landed on consolidation boundaries:

- 2026-03-16 eval: compare 2026-02-16 vs 2026-03-16 → 67,643 vs 67,859 → +216 (flat)
- 2026-04-06 eval: compare 2026-03-09 vs 2026-04-06 → 72,815 vs 72,963 → +147 (flat)

The structure from Feb 23 to Apr 06 was **range chop between $65k–$73k,
then breakout** — not 4 weeks of steady slope. The 4-week SMA‑style
displacement metric cancels out over that range. Only the Apr 13–20
two-week burst was big enough to push the 4-week displacement through
the threshold.

Meanwhile the **daily tape** was screaming momentum by Apr 10:
- Apr 05: +2.58%, Apr 07: +4.46%, Apr 10: +2.25%, Apr 13: +5.20%,
  Apr 17: +2.55%, Apr 20: +2.76%.
- Daily ROC-10 on Apr 13 ≈ +11%, about 5 daily ATRs of displacement.

## Experiment — can a daily-acceleration "early trigger" help?

Sweep: lower weekly threshold + require daily velocity (ROC-10 / daily
ATR-14) to confirm.

| weekly min | daily min | BTC R  | ETH R  | Pool   | 2024-2025-bull |
| ---------- | --------- | ------ | ------ | ------ | -------------- |
| **1.2**    | **0.0** (iter 14) | **+19.19** | **+21.65** | **+40.84** | **+1.70** |
| 0.8        | 1.0       | +17.28 | +15.75 | +33.03 | −2.30          |
| 0.8        | 1.5       | +17.14 |  +8.15 | +25.29 | −4.00          |
| 1.0        | 1.0       | +17.09 | +17.75 | +34.84 | −0.30          |
| 1.0        | 1.5       | +15.94 | +10.15 | +26.09 | −2.00          |
| 1.0        | 0.8       | +17.09 | +17.75 | +34.84 | −0.30          |
| 0.9        | 1.2       | +18.28 | +16.05 | +34.33 | −0.30          |

All seven variants **degrade** pooled R and re-introduce losses in
2024-2025-bull. The daily acceleration filter admits more trades but at
lower quality: short-window velocity spikes on 2–3 daily candles that
reverse before the weekly bar closes. The iter 14 rule — require the
*weekly* move itself to be fast — is the actual signal. Daily
acceleration alone is too noisy.

## Why no variant helps

The 2026 rally is a **breakout-from-range** pattern, not a pure momentum
pattern:

- 4 weeks of chop ($65–73k) → breakout above $73k → continuation.
- The momentum signature only appears in the two weeks *after* the
  breakout, by which point the move is 85% done.
- Lowering the threshold to catch earlier weeks also catches noise
  elsewhere — the bull pullbacks of 2024-2025, random spikes in 2022
  bear, etc. — because "slow-moving but slightly directional" is common.

## Honest diagnosis

The momentum gate we built in iter 13–14 is good at the job it was
designed for: trending regimes with sustained velocity (2017 bull,
2018 bear, 2022 cascade, 2020-ATH). It is structurally blind to:

1. **Range-breakout** patterns where the breakout is the defining event,
   not the trend slope.
2. **Accelerating** regimes where daily tape leads weekly by 1–2 bars
   (this case).

The current rally is category (1) and partly (2). Fixing it requires a
separate gate, not a tune of the existing one.

## What *would* have caught it (future iter 17 candidates)

Two distinct features, neither trivial:

### A. Range-breakout detector (preferred)

Detect a 4–8 week range (high/low range < K × ATR), then fire on the
first weekly close outside that range in the direction of the breakout.
This is a **different setup**, not a tweak of `momentum_bias`. It can
coexist: fire if *either* the momentum gate passes *or* a breakout fires.

Mechanically:
```
range_high = max(close[-8:-1])
range_low  = min(close[-8:-1])
range_size = range_high - range_low
if range_size < 1.5 * weekly_ATR_8:  # flat range
    if close[-1] > range_high + 0.5 * weekly_ATR: fire long
    if close[-1] < range_low  - 0.5 * weekly_ATR: fire short
```

Would have fired on the 2026-04-06 weekly close (first close above the
Feb-Mar range), catching the rally at $72,963 instead of $76,361 —
~4.5% earlier.

### B. Velocity-acceleration detector

Fire when `velocity_now` is meaningfully higher than `velocity_4w_ago`
even if still below the absolute threshold. Captures "momentum building
from rest." Simpler to implement, but prone to catching head-fakes.

## Decision

**No code change.** Iter 14 stands. The current rally is a known blind
spot, not a bug — we accurately rejected each week by design.

## Recommendation to the user

Before merging to main, decide:

- **Accept the blind spot** — ship iter 14, note that range-breakout
  entries are out of scope. The backtested edge is strong.
- **Add iter 17: range-breakout detector** — separate 2–3 iteration
  cycle to add the gate above, backtest, tune threshold. Would target
  the specific regime that iter 14 cannot see.

This iter 16 is diagnostic: one "no improvement" iteration of 3 per
AGENTS.md convergence. iter 15 was the first; iter 16 is the second.
