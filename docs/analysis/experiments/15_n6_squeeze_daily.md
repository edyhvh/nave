# N6 — Daily-cadence squeeze entry (bypass weekly bias gates)

**Verdict: ACCEPT** (2026-08-26)

## Problem

NAVE evaluates bias on a weekly cadence, but a volatility squeeze → explosion
completes in 1–2 days. The N5 weekly-bias squeeze detector failed (0% WR,
−7.0R, 100% FP) because by the time the weekly evaluator ran, the squeeze had
already exploded and price was extended — and the downstream chase/climax
gates then rejected the (now-extended) entry.

## What works (from N5 discovery)

The squeeze *pattern* has 94.4% historical precision (34 TP / 2 FP across 36
BTC+ETH events 2017–2026). The problem is evaluation *timing*, not signal
quality.

## Solution — N6 daily-cadence path

An independent `evaluate_squeeze_daily()` path on `TheoryV2Engine`:

1. Each day, evaluate squeeze state (BB width < p25 of 120d OR < 3.5% absolute,
   sustained ≥ 7 days).
2. When squeeze was active AND a breakout bar appears (close beyond compression
   range ± 0.5× ATR-14), arm the bias immediately (do not wait for the weekly
   evaluation).
3. Apply existing daily/4H/1H gates normally, but **SKIP** both the chase gate
   and the climax cooldown — a squeeze breakout *is* the move and *is* the
   climax, so blocking it would prevent the exact entry this path targets.
4. Timeout: no breakout within 14 days of squeeze end → disarm.

The weekly path (`evaluate()`) is untouched. Production defaults are unchanged:
`evaluate_squeeze_daily()` is only invoked explicitly by the A/B harness — it is
**not** wired into live evaluation.

## Files

- `trading/crypto/analysis/squeeze_daily.py` — daily squeeze evaluator (self-contained)
- `trading/crypto/theory_v2.py` — `evaluate_squeeze_daily()` method (additive, off by default)
- `scripts/squeeze_daily_backtest.py` — N6 A/B harness (control vs treatment)
- `docs/analysis/raw/squeeze_daily_validation_*.json` — raw per-trade evidence
- `tests/test_n6_squeeze_daily_isolated.py` — isolation/regression tests
- `tests/test_n6_squeeze_daily_logic.py` — behavioral breakout tests

## ACCEPT evidence (pre-registered criteria)

| Criterion | Threshold | Result | Pass |
|---|---|---|---|
| Pooled R (treatment) | ≥ 27.69 | +35.41 (BTC+ETH) | ✅ |
| WR squeeze trades | ≥ 70% | 84.6% (11/13) | ✅ |
| FP rate squeeze trades | ≤ 20% | 15.4% | ✅ |
| Rally 63k→78k captured (OOS 2026) | YES | 1 squeeze trade in OOS | ✅ |
| No degradation of existing trades | YES | control +17.82 → treatment +35.41 | ✅ |

Per-coin:

- BTC: squeeze adds +17.59R (84.6% WR); control 16 fired/+17.82R → treatment 31 fired/+35.41R
- ETH: squeeze adds +12.10R (88.9% WR); control 15 fired/+11.57R → treatment 26 fired/+23.67R

## Merge path (still required before enabling)

1. Add a `squeeze_daily_config` flag to `TheoryV2Engine` (default OFF).
2. In live evaluation, call `evaluate_squeeze_daily()` on each daily bar only
   when that flag is set.
3. `SqueezeDailyState` must be persisted across daily bars (not recreated per
   evaluation).

This PR is a **Draft** and does not enable the path. Merge and enabling remain
human-gated.
