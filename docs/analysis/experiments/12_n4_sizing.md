# Experiment N4 — Cross-asset agreement as soft sizing input

**Status:** REJECT — mechanical leverage, not alpha
**Branch:** `experiment/n4-sizing-split`
**Date:** 2026-08-26
**Baseline:** +27.69R pooled (BTC +16.12 / ETH +11.57), re-captured 2026-08-25

## Hypothesis

Using cross-asset agreement (BTC↔ETH weekly momentum) as a **sizing multiplier** —
boosting agree trades, discounting neutral_other — would improve pooled R without
sacrificing correct trades.

## Method

Harness `scripts/_n4_sizing_split.py` reuses the N3 probe's engine, resolver, and
8 in-sample periods. For each fired trade, the R is multiplied by:
- `agree_mult` when the other coin's weekly bias agrees with the trade direction
- `neutral_mult` when the other coin is neutral
- 1.0× for disagree (never fires at weekly scale)

Sweep: agree_mult ∈ {1.1, 1.25, 1.5}, neutral_mult ∈ {0.25, 0.5, 0.75} = 9 configs.

## Results

| agree | neutral | sized_R | Δ vs base | WR%   | resolved | gate |
|-------|---------|---------|-----------|-------|----------|------|
| 1.10  | 0.25    | +24.10  | −3.59     | 86.4% | 22       | FAIL |
| 1.10  | 0.50    | +26.20  | −1.49     | 90.5% | 21       | FAIL |
| 1.10  | 0.75    | +28.30  | +0.61     | 90.5% | 21       | PASS |
| 1.25  | 0.25    | +27.10  | −0.59     | 90.5% | 21       | FAIL |
| 1.25  | 0.50    | +29.20  | +1.51     | 90.5% | 21       | PASS |
| 1.25  | 0.75    | +31.30  | +3.61     | 90.5% | 21       | PASS |
| 1.50  | 0.25    | +32.10  | +4.41     | 90.5% | 21       | PASS |
| 1.50  | 0.50    | +34.20  | +6.51     | 90.5% | 21       | PASS |
| 1.50  | 0.75    | +36.30  | +8.61     | 90.5% | 21       | PASS |

Best: agree=1.5× neutral=0.75× → +36.30R (Δ +8.61R), WR 90.5%, no period regressions.

## Why this is REJECT despite passing all gates

### 1. The improvement is purely mechanical, not alpha

The agree bucket has **0 losses** (12/12 correct in N3 probe). Boosting it from 1.0× to
1.5× amplifies existing wins by 50% — it does not predict any new information. This is
**leverage on a quality signal**, not edge discovery.

Any agree_mult > 1.0× will produce a monotonic R increase. There is no sweet spot — the
"best" config (1.5×) is simply the most aggressive point in the sweep. This is the
signature of a mechanical artifact, not a genuine parameter sensitivity.

### 2. The WR gate is structurally meaningless for sizing experiments

A pure sizing multiplier does not change which trades win or lose — it only scales R.
Therefore WR is identical across all 9 configs (90.5%). The gate "WR not lower by >1pp"
will always pass for any sizing-only experiment. The gate was designed for experiments
that change the trade set (filters, detectors), not for rescaling.

### 3. Data integrity note

The harness shows 19/21 resolved correct (90.5% WR) while the N3 probe showed 18/21
(85.7%). One trade resolved differently between runs — likely the 2021-11-08 ETH long
that N3 counted as incorrect (−1.0R) but the harness may have left unresolved. This
does not affect the REJECT verdict (the structural argument holds regardless), but
should be investigated if N4 were to be revisited.

### 4. The protocol's invalidation rule confirms REJECT

The protocol states: "If agreement adds < ~0.5R pooled after sizing split, it is noise
— REJECT." The *agreement signal itself* adds no R — the R increase comes entirely from
the mechanical boost multiplier applied to the agree bucket. The signal's contribution
to R improvement, net of the multiplier effect, is zero.

## What N3+N4 together tell us

| Finding | Evidence |
|---------|----------|
| Cross-asset agreement is a genuine quality discriminator | N3: agree=100% WR vs neutral=66.7% WR |
| It fails as a hard filter | N3: −6.69R, trade count 30→18 |
| It fails as a soft sizing input | N4: improvement is mechanical leverage, not alpha |
| The signal is real but not exploitable | Both experiments confirm: the discriminator exists but cannot be converted to edge within the current strategy framework |

## Conclusion

Cross-asset weekly momentum agreement is a **legitimate quality signal** — agree trades
are genuinely better than neutral trades. But within the NAVE strategy's existing
structure (fixed R-multiple risk, ZC1/ZC2 exit), this signal cannot be converted into
additional alpha. The improvement from sizing is pure leverage on an already-positive
bucket, which is not the same as improving the strategy.

**Verdict: REJECT.** N4 is experiment 3 of 3 without improvement → P2 experiments pause
per stop rule. Resume only with new evidence or a fundamentally different approach to
exploiting the quality signal (e.g., exit optimization, not sizing).

## Files

- Harness: `scripts/_n4_sizing_split.py`
- Raw results: `docs/analysis/raw/n4_sizing_split_20260826T182955Z.json`
- Protocol: `docs/analysis/experiments/10_n4_protocol.md`
