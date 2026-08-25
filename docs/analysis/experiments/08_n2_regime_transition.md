# Experiment N2 — Regime-transition detector (post-crash recovery)

**Branch:** `experiment/n2-regime-transition`
**Date:** 2026-08-25
**Protocol:** problem → hypothesis → experiment → evidence → adversarial check → **REJECT** → persist learning
**One variable changed:** optional third weekly bias source (`recovery_transition`), off by default in production.

## Problem (from N1 post-mortem)

The NAVE engine missed the BTC 63k→78k rally (Mar–Apr 2026), a 7-week gradual
recovery from a liquidation crash. The two weekly bias gates both failed on it:
- `momentum_bias` requires velocity > 1.2 weekly ATRs/4w; the move oscillated near zero.
- `range_breakout_bias` requires a flat prior range ≤ 1.5 weekly ATRs; the range was 3+ ATRs wide.

The gate fired only at the peak ($78,658). N1 tested 5 parameter relaxations —
all rejected. Root cause identified as needing a *new regime-transition
detector*, not a parameter tune.

## Hypothesis

A structural **post-crash recovery classifier** — independent of velocity and
range-width — can detect the crash→recovery transition on daily structure and
arm an earlier long bias without degrading the historical baseline. It should
**only** fire when momentum and range-breakout both return neutral (i.e. it can
only create trades the baseline would have stood aside on), and the full
downstream gate chain (daily confirm, climax cooldown, chase gate, 4H, 1H)
still applies before any entry fires.

## Detector

`trading/crypto/analysis/recovery_detector.py`, `detect_recovery_transition()`.
Confirms a long only when ALL hold:
1. A qualifying crash inside the lookback: close drew down ≥ 15% from a prior
   swing high within `crash_lookback` (60) daily bars → find `crash_low`.
2. Recovery magnitude: close ≥ 8% above `crash_low` (`min_recovery_off_low`).
3. Structure: close above EMA-20 **and** EMA-20 rising over 3 bars.
4. Higher low: min low over last 10 bars > `crash_low` (not re-testing).

## Experiment (in-sample, A/B on identical data)

`scripts/n2_regime_transition_ab.py` — control (detector OFF) vs treatment
(detector ON) over the same 8 historical periods, same resolver, same COT feed.

| Arm | Fired | Resolved | WR | Total R | Avg R |
|---|---|---|---|---|---|
| **Control** | 31 | 22 | **86.4%** | **+28.39** | +1.291 |
| **Treatment** | 40 | 31 | 67.7% | +24.11 | +0.778 |
| Δ | +9 | +9 | **−18.7pp** | **−4.28R** | −0.513 |

`recovery_transition` contributed 9 trades, net **−4.28R, 22% WR** (2 correct,
7 incorrect) — exactly the pooled delta. All degradation comes from the
detector's new trades; existing momentum/range trades are unchanged.

### Per-period treatment deltas (R)
- 2017–18: ETH +1.52 (1 win)
- 2022-bear: BTC −1.00 (1 false long)
- 2023-recovery: BTC +0.20, ETH −2.00 (2 false longs)
- 2024-25-bull: BTC −2.00, ETH −1.00 (3 false longs)

## Out-of-sample (2026, the N1 blind-spot window)

Ran the detector over 2026-01-01 → 2026-08-25 (the 63k→78k move), not used in
design. **Detector armed 0 of 26 weekly scans on BTC and fired 0 trades.** The
crash precondition fails on BTC because the 60-day crash window scrolls out and
recovery_pct stayed < 8% while the crash low was still in window (only 1–4% at
the early-recovery weekly marks), so it never triggered during the actual move.
ETH armed 6 weeks but all were blocked downstream (weekly/COt/daily stages).
**The detector does not catch the very move it was designed for.**

## Adversarial check — robustness gate (all 8 metrics)

| Metric | Result |
|---|---|
| Sample size | 22→31 resolved trades; adequate |
| Out-of-sample | **FAIL** — 0/26 BTC arming in the 2026 target window |
| Expectancy | 1.291 → 0.778 R/trade (**worse**) |
| Max drawdown | Detector adds 7 losing −1R trades → worse |
| Fees/slippage | More fired trades at lower WR → worse after costs |
| Regime robustness | Fires false longs in 2022-bear and 2024-25-bull |
| False-positive rate | 7/9 recovery-transition trades = **78% FP** |
| Parameter sensitivity | No setting improves over control (below) |

### Parameter sensitivity (one param moved at a time)
| Config | Fired | WR | Total R | OOS armed BTC |
|---|---|---|---|---|
| Control (no detector) | 31 | 86.4% | +27.28 | — |
| base | 40 | 67.7% | +22.99 | 0 |
| crash_dd 0.10 | 37 | 71.4% | +23.48 | 6 |
| crash_dd 0.20 | 33 | 79.2% | +25.28 | 2 |
| min_recovery 0.05 | 40 | 67.7% | +22.99 | 0 |
| min_recovery 0.12 | 38 | 72.4% | +24.99 | 0 |
| crash_lookback 30 | 34 | 80.0% | +26.79 | 0 |
| crash_lookback 120 | 36 | 74.1% | +24.48 | 0 |
| higher_low 20 | 35 | 76.9% | +25.48 | 0 |
| ema_slope 5 | 40 | 67.7% | +22.99 | 0 |

Every configuration lands **below** the control pooled R and none arms BTC in
the 2026 target window (except looser crash thresholds, which still underperform
in-sample). The rejection is robust to parameter choice.

## Verdict

**REJECT.** The regime-transition detector does not reproduce an edge:
- In-sample it strictly *degrades* the baseline (−4.28R, WR −18.7pp).
- Out-of-sample it misses the exact 63k→78k move it was designed to catch.
- No parameter setting rescues it (false-positive rate 78%, underperforms in
  both bear and bull regimes).

NO EDGE is a valid conclusion. Consistent with N1: the gradual post-crash
recovery remains a **documented, unresolved blind spot**. A naive structural
"crash→recovery" classifier on daily EMA/higher-low geometry is insufficient.
Production default (detector OFF) is unchanged; the detector module is retained
as an experimental artifact for future reference.

## Learning persisted
- Added to `docs/analysis/experiments/_log.md` as row N2 (❌).
- Blind-spot note in `docs/agent_onboarding.md` §8 and `strategy_context()`
  updated to record that the structural detector also fails, keeping the blind
  spot explicitly open.

## Artifacts
- `trading/crypto/analysis/recovery_detector.py` (detector, unused in prod)
- `scripts/n2_regime_transition_ab.py` (A/B harness)
- `docs/analysis/raw/n2_regime_transition_ab_20260825T201127Z.json` (raw results)
- Diagnostics in task workspace `diagnostics/` (`_n2_sensitivity.py`, `_n2_diag_*.py`)
