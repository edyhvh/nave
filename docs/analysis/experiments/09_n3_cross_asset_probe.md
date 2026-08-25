# Experiment N3 — Cross-asset confirmation probe (evidence-first)

**Branch:** `experiment/n2-regime-transition`
**Date:** 2026-08-25
**Protocol:** hypothesis → evidence probe (not yet a full A/B ship decision)
**Status:** ⚠️ PROBE — signals worth a refined experiment; not shippable as a hard filter
**One variable studied:** whether the OTHER coin's weekly momentum bias
(`momentum_bias`, 4-bar velocity > 1.2 ATR) at the same weekly mark predicts the
outcome of a fired baseline trade.

## Rationale / why not N1-N2 redux

N1 (parameter relaxations) and N2 (single-asset structural recovery detector)
both targeted the 63k→78k blind spot from within a *single* coin's own data and
both REJECTED. Q2 explicitly names **relative-strength / cross-asset** selection
as an open research line. This probe asks a cheap, reproducible question on the
BASELINE (control) trades: does cross-asset agreement separate winners from
losers? It does not touch production code and does not re-attempt to overfit one
historical move.

## Method

Standalone `scripts/_n3_cross_asset_probe.py` reuses the N2 A/B harness
semantics (same engine, same ZC1/ZC2 resolver, same 8 periods) but only walks
the CONTROL arm. For every fired trade it records the OTHER coin's weekly
`momentum_bias` at that week, then buckets the resolved outcome:
- **agree** — other coin's momentum bias == trade direction
- **disagree** — other coin's momentum bias is the opposite direction
- **neutral_other** — other coin's momentum bias is neutral

## Result (pooled, control arm == baseline trades)

| Bucket | Fired | Resolved | Correct | Incorrect | WR | Total R | Avg R |
|---|---|---|---|---|---|---|---|
| **all** | 30 | 21 | 18 | 3 | 85.7% | +26.69 | +1.271 |
| **agree** | 18 | 12 | 12 | 0 | **100%** | +20.00 | +1.666 |
| **disagree** | 0 | 0 | 0 | 0 | — | 0.00 | — |
| **neutral_other** | 12 | 9 | 6 | 3 | 66.7% | +6.70 | +0.744 |

**All 3 baseline losses occur when the other coin's weekly momentum is NEUTRAL:**
- 2017-18 ETH long (neutral) −1.00
- 2020-21 ETH long (neutral) −1.00
- 2024-25 BTC short (neutral) −1.00

The **agree** bucket has 12 resolved trades with **0 losses (WR 100%)**. The
neutral bucket carries all losses and a lower WR (66.7%).

## Interpretation (evidence, not yet an edge)

- Cross-asset agreement is a **genuine quality discriminator**: every resolved
  loss lives in the neutral-other bucket; agreeing trades never lost (12/12).
- But as a **hard filter** ("only trade when the other coin agrees"), N3 would
  drop total R from +26.69 → +20.00 (−6.69R) and cut trade count 30 → 18,
  because it also discards 6 correct neutral trades. That fails the baseline
  comparison rule (pooled R must rise, not fall). **Not shippable as a filter.**
- `disagree` never fires (BTC/ETH momentum rarely opposes at weekly scale) — so
  there is no "conflict" signal to exploit directly; only agreement vs. neutral.
- Sample is small (12 resolved in agree, 9 in neutral). The 100% WR is
  promising but not robust at n=12.

## ⚠️ CRITICAL INTEGRITY FINDING — stale baseline

The canonical baseline `00_baseline.md` (+44.14R pooled, BTC 22 / ETH 25 fired)
was captured **2026-04-26**. Re-running the SAME `scripts/theory_v2_backtest.py`
on current code now yields **+27.69R (BTC 15 / ETH 14 fired)**. This is NOT a
data bug — the divergence is concentrated in 2019, 2020, 2021 and 2024-25
periods (old fired 12+ trades in those; new fires ~0 there while firing more in
2024-25). The engine has changed materially since the baseline was frozen
(momentum refinements, COT overlay, regime analysis — many commits post-dating
the baseline). **The "Δ vs base" framing in `_log.md` is therefore misleading**
for any comparison to +44.14R.

The N2 A/B itself remains internally valid (control vs treatment on identical
code/data) — that verdict stands. But the absolute "vs base" deltas do not.

## Next steps (proposed)
1. **Re-capture the baseline** on current code (`theory_v2_backtest.py`) and
   update `00_baseline.md` + `_log.md` so future deltas are apples-to-apples.
2. Refine N3 as a *soft* cross-asset confirmation (e.g. only *require* agreement
   for neutral-weekly-bias trades, or use it as a sizing/confidence input)
   rather than a hard filter — testable once the baseline is re-frozen.

## Artifacts
- `scripts/_n3_cross_asset_probe.py` (probe harness)
- `docs/analysis/raw/n3_cross_asset_probe_20260825T204102Z.json` (raw results)
- `docs/analysis/raw/theory_v2_validation_20260825T204404Z.json` (fresh canonical re-run)
