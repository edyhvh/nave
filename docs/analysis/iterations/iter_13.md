# Iter 13 — Replace slow weekly SMA with momentum-velocity bias

> **Date:** 2026-04-21
> **Scope:** Pivot the weekly bias gate from "slow SMA trend" to
> "high-momentum velocity". Only rapid up/down moves qualify as a tradable
> regime.
> **Baseline:** `docs/analysis/raw/theory_v2_validation_20260417T001435Z.json` (iter 12)
> **After:** `docs/analysis/raw/theory_v2_validation_20260421T081953Z.json`

---

## Why this iteration exists

Iter 12's residual pain point was 2024-2025-bull at −3.00R BTC, −0.30R ETH —
shorts firing into a bull market because the SMA-8 deadband flipped on
drawdowns. More broadly, the user intent for the strategy is to capture
**fast** directional moves, not slow grinds. SMA-8 with 4% deadband is a
direction classifier, not a momentum classifier: it says nothing about
*how fast* price is moving relative to its own volatility.

## What changed

New function `momentum_bias(weekly, lookback=4, min_velocity=1.5)` in
`trading/theory_v2.py`:

```
velocity = (close_now − close_{4 bars ago}) / weekly_ATR_8
```

- `velocity > +1.5` → long (high-momentum up-move)
- `velocity < −1.5` → short (high-momentum down-move)
- otherwise → neutral

`TheoryV2Engine.evaluate` now calls `momentum_bias` instead of `weekly_bias`
for its first gate. The velocity score is stored in signal metadata
(`weekly_velocity_atr`) and surfaced in the live action card.

Why ATR-normalization instead of percentage displacement?
- Percentage ignores volatility regime — 5% in a quiet tape is huge, 5%
  mid-2022 crash is nothing.
- ATR-normalized velocity reads the same in both regimes: "the move is
  X standard volatility units per 4 weeks."
- 1.5 ATRs in 4 weeks = candle bodies dominate wicks in the prevailing
  direction, which matches the transcripts' definition of momentum
  (`technical.yaml` → `candle_shape_to_phase`).

## Experiment — pooled results

| Metric        | iter 12 (SMA-8) | iter 13 (momentum) | Δ        |
| ------------- | --------------- | ------------------ | -------- |
| BTC fires     | 44              | 16                 | −28 (−64%) |
| BTC WR        | 66.7%           | 83.3%              | +16.6pp  |
| BTC avg R     | +0.77           | +1.27              | +0.50    |
| BTC total R   | +27.71          | +15.18             | −12.53   |
| ETH fires     | 47              | 17                 | −30 (−64%) |
| ETH WR        | 72.2%           | 80.0%              | +7.8pp   |
| ETH avg R     | +0.94           | +1.28              | +0.34    |
| ETH total R   | +33.83          | +19.25             | −14.58   |

Fewer trades, much higher quality — which is the momentum signature. The
strategy now refuses to participate in regimes that are directional but
slow, which is the user's explicit design goal.

## Per-period behaviour

| Period                     | BTC iter 12 | BTC iter 13 | ETH iter 12 | ETH iter 13 |
| -------------------------- | ----------- | ----------- | ----------- | ----------- |
| 2017-bull+2018-bear        | +9.14 (10)  | +5.80 (6)   | +5.62 (7)   | +4.10 (4)   |
| 2019-recovery              | −1.30 (5)   | +1.70 (1)   | +3.20 (3)   | +4.20 (1)   |
| 2020-covid-crash           | +2.17 (2)   |  0.00 (0)   | +3.16 (4)   | +1.70 (2)   |
| 2020-recovery+2021-ATH     | +4.19 (8)   | +1.40 (6)   | +13.34 (14) | +3.10 (5)   |
| 2022-bear                  | +3.94 (4)   | +1.46 (1)   | +7.01 (9)   | +4.60 (4)   |
| 2023-recovery              | +9.17 (7)   | +4.82 (2)   | +2.80 (5)   | +1.55 (1)   |
| 2024-ETF-approval          | +3.40 (3)   |  0.00 (0)   | −1.00 (2)   |  0.00 (0)   |
| **2024-2025-bull**         | **−3.00 (5)** | **0.00 (0)** | **−0.30 (3)** | **0.00 (0)** |

The problem period is resolved by exclusion, not by improved selection.
That is acceptable — the theory now correctly identifies 2024-2025-bull
as "not a high-momentum regime for a shorter" and refuses to fire in
either direction. It also loses coverage in 2024-ETF-approval and
2020-covid-crash (0 fires each) which may be addressable in a future
iteration by tuning `min_velocity` down or shortening the lookback.

## Decision

**Ship.** The refactor trades quantity for quality in a way that aligns
with the theory's documented `momentum` philosophy and eliminates the
single worst-performing period.

## Future iterations

- **iter 14:** try `min_velocity=1.2` or `lookback=3` to recover some
  signals in 2024-ETF-approval and 2020-covid-crash without losing the
  2024-2025-bull filter.
- **iter 15:** add a daily-level momentum confirmation
  (ROC-5 > ROC-20 acceleration) so we don't enter when weekly momentum
  is cooling.
