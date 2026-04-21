# Iter 15 — Convergence check (no improvement)

> **Date:** 2026-04-21
> **Scope:** Exploratory sweep — attempted two theory additions to improve
> on iter 14. Neither produced a measurable gain. Recording as the first
> no-improvement iteration per AGENTS.md convergence criteria.

---

## What was tried

### Attempt A — Daily-level momentum floor (ROC/daily-ATR threshold)

Added a secondary momentum check to `daily_confirms`: require daily
velocity = displacement over 10 daily bars divided by daily ATR-14 to
exceed a floor in the bias direction. Rationale: weekly momentum is
backward-looking; if daily has already cooled, the weekly signal is
stale.

| daily_v floor | pool totalR | vs iter 14 |
| ------------- | ----------- | ---------- |
| ≥ 0.3 ATRs    | +39.14      | −3.40      |
| ≥ 0.5 ATRs    | +36.24      | −6.30      |
| ≥ 0.8 ATRs    | +36.24      | −6.30      |
| ≥ 1.0 ATRs    | +36.24      | −6.30      |

Every floor reduced pooled R. 2024-2025-bull stayed at +1.70R
regardless, so the gate is stable where it matters. The SMA-10 check
already rejects the stale-daily case the floor was meant to catch.

### Attempt B — Narrower chase_gate for the momentum regime

Hypothesis: high-momentum moves retrace shallower than slow trends, so
the 50–95% retracement band is too wide. Tested tighter bands:

| chase band      | pool totalR | vs iter 14 |
| --------------- | ----------- | ---------- |
| 0.38–0.95       | +42.54      |  0.00      |
| 0.40–0.80       | +42.54      |  0.00      |
| 0.50–0.75       | +42.54      |  0.00      |
| 0.30–0.95       | +42.54      |  0.00      |

No change. The chase_gate rejects a non-trivial share of setups (43
rejects per coin in iter 14) but the specific band boundaries do not
move the fires that survive to outcome — suggesting the retracements
that reach the 50%+ threshold almost always stay inside 95%.

## Why nothing helped

The momentum gate at iter 14 is already doing the heavy lifting: 260
weekly rejections on BTC, 280 on ETH, out of ~360 evaluations per coin.
What passes has *already* satisfied the "fast and directional" criterion
by a margin. Subsequent gates (daily, 4H, chase, climax) filter small
amounts of noise but the real selectivity is at the weekly stage.

Adding more gates in the same conceptual direction (momentum / trend)
is redundant. Further improvement needs a different *kind* of filter —
most likely a regime detector (bull cycle / bear cycle / choppy range
on a >1-year horizon) or a macro overlay (rates direction, COT zero-line)
as flagged in iter 12.

## Decision

**No change.** iter 14 (`momentum_bias`, `min_velocity=1.2`,
`lookback=4`) stands as the converged configuration.

This is the first "no improvement" iteration; AGENTS.md convergence
criterion is 3 consecutive. Given the underlying cause (single dominant
filter, no free conceptual axis to add), further iterations are
unlikely without a scope widening (new data source, new timeframe
dimension). Recommend shipping and re-opening the loop only on new
evidence.

## Final pooled metrics (iter 14)

| Coin  | Fires | WR     | Avg R/trade | Total R |
| ----- | ----- | ------ | ----------- | ------- |
| BTC   | 21    | 76.5%  | +1.13       | +19.19  |
| ETH   | 25    | 78.9%  | +1.23       | +23.35  |
| Pool  | 46    | 77.8%  | +1.18       | +42.54  |

Key regime coverage:
- 2024-2025-bull: **+1.70R** (baseline iter 12: −3.30R)
- 2022-bear: +5.06R
- 2023-recovery: +9.22R
- 2017-2018 cycle: +9.90R
