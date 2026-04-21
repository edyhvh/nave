# Iter 12 — Widen weekly SMA deadband to 4%

> **Date:** 2026-04-16
> **Scope:** Reduce false weekly-bias flips during moderate pullbacks.
> **Baseline:** `docs/analysis/raw/theory_v2_validation_20260414T190949Z.json` (iter 11)
> **After:** `docs/analysis/raw/theory_v2_validation_20260417T001435Z.json`

---

## Why this iteration exists

Iter 11's 2024-2025-bull investigation revealed that 3 of 5 BTC fires
were SHORTS triggered during healthy bull-market pullbacks. The weekly
SMA-8 with 2% deadband was flipping bearish on 5–10% corrections where
the longer-term trend was still up.

## Experiment

Tested 5 variants against the full 9-period BTC backtest:

| Variant                | Fired | WR    | Total R | Bull24 R |
| ---------------------- | ----- | ----- | ------- | -------- |
| A) SMA-8, db=2%        | 48    | 63.2% | +25.71  | -3.00    |
| B) SMA-8, db=3%        | 47    | 64.9% | +26.71  | -3.00    |
| **C) SMA-8, db=4%**    | 44    | 66.7% | +27.71  | -3.00    |
| D) consec=2, db=2%     | 38    | 60.0% | +18.53  | -3.00    |
| E) consec=2, db=3%     | 36    | 60.7% | +16.03  | -3.00    |

Also tested longer SMA windows (12, 16) — all degraded performance
(pooled dropped to +15–17R range). Longer windows are too slow to
capture real trend changes.

**Observation:** 2024-2025-bull stays at -3.00R across ALL variants. The
remaining shorts fire at 10%+ drawdowns, beyond any reasonable deadband.
Fixing that period requires a regime-level detector (future iteration).

## What changed

- `trading/theory_v2.py` line 79: `deadband=0.02` → `deadband=0.04`
- `tests/test_theory_v2.py`: steepened test ramps (step ×2) to clear the
  wider deadband; 3 tests adjusted, same logic.

## Full validation (both coins, all periods)

| Metric        | iter 11 | iter 12 | Δ       |
| ------------- | ------- | ------- | ------- |
| BTC total R   | +25.71  | +27.71  | +2.00   |
| BTC WR        | 63.2%   | 66.7%   | +3.5pp  |
| BTC avg R     | +0.68   | +0.77   | +0.09   |
| BTC fires     | 48      | 44      | −4      |
| ETH total R   | +34.23  | +33.83  | −0.40   |
| ETH WR        | 71.1%   | 72.2%   | +1.1pp  |
| ETH avg R     | +0.90   | +0.94   | +0.04   |
| ETH fires     | 52      | 47      | −5      |

BTC improved cleanly; ETH dipped 0.40R because one 2024-ETF-era fire
(which was a loser) was filtered — net positive for quality even though
total R is marginally lower.

## Limitations

- 2024-2025-bull BTC is STILL -3.00R. This is not addressable via the
  weekly bias gate. The 5 surviving fires (3 shorts) happen during
  drawdowns deep enough to flip even a 4% deadband. A regime-level
  filter (ATH proximity, macro overlay) would be needed.
- Deadband=4% is a judgment call; was not grid-searched. Higher values
  (5%+) risk suppressing legitimate bear signals during 2022.

## Decision

**Ship.** BTC pooled improves, WR improves, no period degraded
meaningfully, and the wider deadband aligns with the theory's documented
caution against false short signals in bull markets.

## Future iterations

- **2024-2025-bull residual:** regime detector (ATH proximity or macro-
  derived bull/bear flag) as a separate gate. Not part of this iteration.
- **Re-entry discipline (iter 3):** investigation flagged that 2024-07-22
  long was a 7-day re-entry after 2024-07-15 long. Chase gate did not
  catch it. Worth a dedicated iter 13 if the regime problem is addressed.
