# Experiment N4 (planned, NEXT) — Cross-asset agreement as soft confirmation / sizing input

**Status:** 🔜 NEXT — protocol recorded; NOT implemented in this task.
**Baseline to beat:** +27.69R pooled (BTC +16.12 / ETH +11.57), re-captured 2026-08-25 on current code (`00_baseline.md`).
**Branch:** `experiment/n2-regime-transition`
**Date recorded:** 2026-08-26

## Origin

N3 probe (`09_n3_cross_asset_probe.md`) showed cross-asset weekly momentum agreement is a
genuine **quality discriminator** but fails as a hard filter:
- **agree** bucket: 12 resolved trades, 12 correct, **WR 100%**, +20.00R
- **neutral_other** bucket: 9 resolved, 6 correct, WR 66.7%, +6.70R — **all 3 baseline losses live here**
- `disagree` never fires at weekly scale, so there is no exploitable conflict signal.

Hard-filtering ("only trade when the other coin agrees") would drop pooled R +26.69 → +20.00
(−6.69R) and cut trade count 30 → 18 because it also discards 6 correct neutral trades.
That fails the strict-improvement rule. **Do NOT ship as a filter.**

## Hypothesis (N4)

Using cross-asset agreement as a **soft confirmation / sizing input** — not a rejection gate —
improves risk-adjusted return without sacrificing correct trades:
- The discriminator's signal is *quality* (agreement ⇒ fewer losers), not *direction*.
  Preserve all fired trades, but modulate **size / confidence** (and optionally tighten the
  exit trail) by the other coin's agreement state.

## Protocol

One variable: **size multiplier (or confidence weight) applied per agreement bucket.**
The `agree` bucket gets a **boost**; the `neutral_other` bucket gets a **discount** (e.g. 1.0×
base on agree, 0.5× on neutral) — never 0× (that is the rejected hard filter).

Evaluation on the **control arm == baseline trades** (same engine, same ZC1/ZC2 resolver,
same 8 periods as `scripts/theory_v2_backtest.py`):
- Reuse the N2/N3 A/B harness semantics (`scripts/_n3_cross_asset_probe.py` as the base).
- Strict-improvement gate vs **new** baseline +27.69R:
  1. Pooled R **>** +27.69R, **AND**
  2. Pooled WR not lower by more than 1pp, **AND**
  3. Per-period regressions limited (no period drops > 2R unless another rises by 4R+).
- Report trade count and avg R/trade (a pure sizing split should not change WR, only R).

## Invalidation

- If agreement adds < ~0.5R pooled after sizing split, it is noise — REJECT.
- If WR drops below baseline on the *same* resolved trade set, REJECT.
- If the effect only shows on the same small n (12 agree) and does not survive a
  sensitivity sweep of the multiplier (0.25/0.5/0.75), treat as INCONCLUSIVE.

## Scope guard

N4 is a **bounded sizing/confirmation experiment** on the theory engine's optional inputs
(cross_asset_fn + a per-bucket weight), default OFF so production output is unchanged —
exactly the pattern N3 used for the soft confirmation hook. Do not build a new architecture.

## Decision ownership

This protocol is recorded here for the next experiment card. It is a research step, not a
shipping decision; any shipped change requires its own verdict + log row.
