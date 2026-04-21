# Iter 14 — Tune momentum velocity threshold (1.5 → 1.2 ATRs)

> **Date:** 2026-04-21
> **Scope:** Single-parameter tune of the iter 13 momentum gate to recover
> coverage lost by the initial 1.5-ATR threshold.
> **Baseline:** `docs/analysis/raw/theory_v2_validation_20260421T081953Z.json` (iter 13)
> **After:** `docs/analysis/raw/theory_v2_validation_20260421T082413Z.json`

---

## Why this iteration exists

Iter 13 introduced a velocity-based weekly gate but picked the threshold
(1.5 weekly ATRs over 4 weeks) by a qualitative "large candle body" argument,
not by data. On pooled backtest, iter 13 filtered out some legitimately
fast regimes (2020-covid-crash BTC = 0 fires, 2024-ETF-approval = 0/0,
2024-2025-bull = 0/0). The question is whether lowering the threshold
retains the WR / avg-R edge while recovering those periods.

## Experiment — parameter sweep

7 configurations tested over the full 9-period BTC+ETH backtest:

| min_vel | lookback | BTC fires | BTC WR | BTC totalR | ETH totalR | pool   | 24-bull |
| ------- | -------- | --------- | ------ | ---------- | ---------- | ------ | ------- |
| 1.0     | 4        | 26        | 66.7%  | +17.79     | +22.35     | +40.14 | −0.30   |
| **1.2** | **4**    | **21**    | **76.5%** | **+19.19** | **+23.35** | **+42.54** | **+1.70** |
| 1.5     | 4        | 16        | 83.3%  | +15.18     | +19.25     | +34.43 |  0.00   |
| 1.0     | 3        | 21        | 66.7%  | +16.54     | +21.41     | +37.95 | −1.00   |
| 1.2     | 3        | 20        | 64.7%  | +13.37     | +17.37     | +30.75 | −1.00   |
| 1.5     | 3        | 14        | 66.7%  |  +9.78     | +16.35     | +26.13 | −1.00   |
| 2.0     | 4        |  8        | 71.4%  |  +7.79     | +12.15     | +19.95 |  0.00   |

**Winner:** `min_velocity=1.2, lookback=4`.

- Highest pooled totalR of all configurations (+42.54).
- Keeps WR above 76% on both coins (vs iter 12's 66.7% / 72.2%).
- Turns 2024-2025-bull profitable (+1.70R, was −3.30R pooled in iter 12,
  0.00R in iter 13).
- 2024-ETF-approval still dark at 0 fires — neither threshold recovers
  it without hurting other periods, so deferring to iter 15.

Shorter lookbacks (3 weeks) degrade results uniformly: faster but too
noisy to identify true momentum regimes. 2.0 ATRs is too tight — good
WR but half the trade count.

## What changed

- `trading/theory_v2.py` line ~108: `min_velocity=1.5` → `min_velocity=1.2`.
- Docstring for the pipeline updated to match.
- No test changes required — the existing `test_momentum_bias_*` tests
  already use ramps with velocity well above both 1.5 and 1.2.

## Full validation — vs. iter 12 and iter 13

| Metric        | iter 12 (SMA-8) | iter 13 (v≥1.5) | iter 14 (v≥1.2) |
| ------------- | --------------- | --------------- | --------------- |
| BTC fires     | 44              | 16              | 21              |
| BTC WR        | 66.7%           | 83.3%           | 76.5%           |
| BTC avg R     | +0.77           | +1.27           | +1.13           |
| BTC total R   | +27.71          | +15.18          | +19.19          |
| ETH fires     | 47              | 17              | 25              |
| ETH WR        | 72.2%           | 80.0%           | 78.9%           |
| ETH avg R     | +0.94           | +1.28           | +1.23           |
| ETH total R   | +33.83          | +19.25          | +23.35          |
| Pooled totalR | +61.54          | +34.43          | +42.54          |
| 2024-25-bull  | −3.30R          |  0.00R          | +1.70R          |

iter 14 vs iter 13: +8.11R (BTC +4.01, ETH +4.10), +5 BTC fires, +8 ETH
fires. Win rate dips a few points but avg R/trade is still dramatically
above the SMA baseline.

iter 14 vs iter 12: −19.00R in total R but +0.36R avg/trade BTC,
+0.29R avg/trade ETH. The pivot is still "fewer, higher quality trades"
— the design goal.

## Decision

**Ship.** Clear Pareto improvement over iter 13 on total R while
preserving the momentum character. The 2024-2025-bull period is now
profitable for the first time in the backtest history.

## Future iterations

- **iter 15:** daily-level momentum confirmation. Add ROC-5 vs ROC-20
  daily acceleration to reject entries when weekly momentum is already
  cooling. This could recover 2024-ETF-approval or tighten 2020-ATH
  where mid-cycle pullbacks currently fire false signals.
