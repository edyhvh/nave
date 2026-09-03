# Experiment N3 — Cross-asset soft confirmation A/B

**Branch:** `experiment/n3-cross-asset-confirm`
**Date:** 2026-08-26
**Protocol:** P2 bounded experiment (A/B vs control, sensitivity sweep, OOS check)
**Status:** ❌ REJECT
**Stop-rule position:** experiment 2 of max 3 consecutive no-improvement experiments (N2 = first).

## Hypothesis (pre-registered)

N1 post-mortem showed the BTC 63k→78k rally was missed because weekly momentum
velocity oscillated near zero (below `min_velocity=1.2` ATR) throughout the
grind. The probe in `09_n3_cross_asset_probe.md` showed cross-asset agreement is
a real quality discriminator (agree bucket 100% WR) but not shippable as a hard
filter (−6.69R).

N3 therefore tested a **soft confirmation**: accept a sub-threshold but
directional weekly velocity (`|velocity| >= cross_confirm_min_velocity`) as bias
ONLY when the other coin's weekly momentum bias agrees in direction. Unlike N2,
this does not reuse the rejected recovery-detector approach and it can only ADD
trades (existing baseline trades untouched).

Pre-registered criteria vs re-captured baseline (+27.69R canonical /
+28.40R harness control on identical data):
- ACCEPT: pooled R > control AND pooled WR not lower by >1pp AND no period drops
  >2R unless another rises ≥4R AND OOS 2026 treatment ≥ control.
- INCONCLUSIVE: R improves but WR drops >1pp.
- REJECT: everything else.

## Implementation

- `trading/crypto/theory_v2.py`: optional `cross_asset_fn` +
  `cross_confirm_min_velocity` engine params (default off — production behavior
  unchanged when unset).
- `scripts/n3_cross_asset_confirm_ab.py`: A/B harness reusing the N2 semantics
  (same periods, ZC1/ZC2 resolver, COT provider).
- Data note: first run used remote-only data in the fresh worktree (control
  +45.84R ≠ baseline). Re-ran after copying `data/binance_cache`; control now
  matches the canonical backtest (+28.39R/+28.40R), confirming apples-to-apples.

## Result (pooled in-sample, correct cache)

| min_velocity | control R | treatment R | ΔR | WR | Verdict |
|---|---|---|---|---|---|
| 0.3 | +28.40 | +28.71 | +0.31 | 90.5% → 78.6% (−11.9pp) | REJECT |
| 0.5 | +28.39 | +28.70 | +0.31 | 86.4% → 75.9% (−10.5pp) | REJECT |
| 0.7 | +28.40 | +28.71 | +0.31 | 90.5% → 78.6% (−11.9pp) | REJECT |
| 0.9 | +28.40 | +30.71 | +2.31 | 90.5% → 84.6% (−5.9pp) | REJECT |
| 1.0 | +28.40 | +27.60 | −0.80 | 90.5% → 83.3% (−7.1pp) | REJECT |

Per-period detail (min_velocity=0.5): gains are scattered small (+1.52 ETH 2017,
+1.20 BTC 2023, +0.59 BTC 2022) while losses are concentrated single-trade
failures (−1.00 BTC 2017, −1.00 ETH 2023, −1.00 ETH 2024-25). The added
cross-asset-confirm trades resolve at ~50% WR overall — the probe's 100%-WR
agree-bucket did NOT transfer to newly added sub-threshold trades.

## OOS check (2026-01-01 → 2026-08-25)

Neither control nor treatment fired any trade in the N1 blind-spot window with
the canonical cached data. The mechanism never gets the chance to address the
missed rally: the sub-threshold weeks fail downstream gates (daily confirm /
chase gate / 4H), same terminal failure mode as N2's detector.

## Why it fails

1. Cross-asset agreement separates quality among *already-fired* baseline trades
   (probe finding) but has no predictive power for *additional* sub-threshold
   entries: those new trades are roughly coin-flips.
2. Any threshold loose enough to matter (≤0.9) destroys ≥5.9pp of pooled WR;
   tight enough to protect WR (~1.0) adds nothing or subtracts R.
3. OOS blind spot remains unreachable — downstream gates reject the slow grind
   regardless of weekly bias source.

## Verdict

❌ **REJECT.** No parameter passes the strict improvement rule. Production code
keeps the feature flag OFF (engine default unchanged); the experiment branch is
preserved with its raw JSON under `docs/analysis/raw/n3_cross_asset_confirm_ab_*.json`.

## Artifacts

- `scripts/n3_cross_asset_confirm_ab.py`
- `docs/analysis/raw/n3_cross_asset_confirm_ab_20260826T094953Z.json` (remote-data run — discarded, integrity note above)
- `docs/analysis/raw/n3_cross_asset_confirm_ab_20260826T095056Z.json` (canonical run, v=0.5)
- Sensitivity runs logged in console output of this session (v ∈ {0.3,0.7,0.9,1.0})

## Stop-rule consequence

Two consecutive no-improvement experiments (N2, N3). Per P2 bounds, exactly ONE
further attempt (N4) is permitted before experiments pause pending new evidence.
