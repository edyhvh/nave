# Experiment G1 — Glassnode on-chain overlay on BTC momentum entries

**Status:** ✅ REJECT (with reason — data gate not satisfiable at zero cost)
**Branch:** `experiment/g1-glassnode-overlay`
**Date recorded:** 2026-08-26
**Baseline to beat:** current-code BTC +16.12R (15 fired, 90.9% WR) / pooled +27.69R — `00_baseline.md`.
**Harness:** `scripts/_g1_glassnode_overlay.py` (promoted from `scripts/glassnode_position_spike.py`).

## Origin

The Glassnode evaluation existed only as a dormant spike (`scripts/glassnode_position_spike.py`),
recorded as "Glassnode remains a dormant spike script, not an active experiment" in the
P2-nave-hardening objective. This card materializes it as a pre-registered, bounded experiment
that must end in exactly one verdict: **ADOPT / PARTIAL / REJECT**.

Hypothesis (pre-registered, unchanged from the spike): a counterfactual overlay that blocks
BTC **longs** when SOPR > 1.02 or exchange netflow > 0 (profit-taking / inflow), and blocks BTC
**shorts** when SOPR < 0.98 or netflow < 0 (capitulation / outflow), improves the R-multiple
outcome of the nave BTC momentum entries versus the current-code baseline.

## Method

- **Trade set:** regenerated on current code by walking `TheoryV2Engine` over the same 8
  in-sample periods and same ZC1/ZC2 resolver as the N3 harness (`scripts/_n3_cross_asset_probe.py`).
  This reproduces the current baseline exactly: **BTC fired=15, resolved=11, WR=90.9%,
  sumR=+16.12R** — matching `00_baseline.md`. (The stale June unified backtest, which the old
  spike defaulted to, is NOT used.)
- **Overlay data:** Glassnode SOPR + exchange netflow, **cache-first** from `var/glassnode_cache`;
  live fetch only attempted if a provisioned key + `gn` CLI exist.
- **Decision rule (pre-registered):** see harness `_decide()`. ADOPT only if kept.sumR >
  baseline.sumR, WR not lower by >1pp, false positives low, per-period regressions limited;
  PARTIAL if sumR improves but WR collapses or false-positive blocking is material; REJECT if
  the overlay blocks nothing, removes net-positive edge, or **data is unavailable** (no cache,
  no key) — in which case the metric is not actionable and the verdict is REJECT with the gap
  flagged, not a stall.

## Evidence (run 2026-08-26T17:25:50Z)

Raw: `docs/analysis/raw/g1_glassnode_overlay_20260826T172550Z.json`.

Baseline regenerated: BTC fired=15, correct=10, incorrect=1, unresolved=4, **sumR=+16.12**.

Glassnode data availability: **FALSE** — `var/glassnode_cache` does not exist, and live fetch
returns **HTTP 401** for every metric (`sopr`, `exchange_netflow`, `price`). No `GLASSNODE_API_KEY`
is provisioned in any credential store; no `gn` CLI is installed and it is not installable via
`pip` (`glassnode-cli`) or `npm` (`glassnode-cli`) — both return "No matching distribution / 404".

## Verdict criteria (the 5 mandated reports)

1. **Incremental signal value over baseline (+27.69R pooled / +16.12R BTC):** **NOT EVALUABLE.**
   With zero on-chain snapshots (all 15 trades have `missing_snapshots`), no kept-vs-blocked
   comparison exists; `kept == baseline == +16.12R`, `blocked = 0`. There is no evidence the
   overlay adds or removes R.

2. **Historical usefulness:** sample = 15 BTC trades across the 8 periods (2017–2025), 11
   resolved, WR 90.9%, avgR +1.075. But **no period has any on-chain snapshot**, so the overlay
   applies to 0/15 trades. No kept-vs-baseline win-rate/avgR contrast is computable.

3. **False positives:** **NOT EVALUABLE.** `false_positives_blocked_winners = 0` only because
   nothing was blocked (0 snapshots), not because blocking is precise. Precision/recall of the
   overlay is undefined without data.

4. **Redundancy:** **UNRESOLVED, qualitatively weak.** SOPR (profit-taking) and exchange netflow
   (inflow/outflow) plausibly re-encode what the nave theory already captures via momentum
   velocity, climax-cooldown, and COT/regime bias — i.e. they may be a proxy for the same
   "extended vs cool" regime state. But this is a hypothesis, not a measurement. It cannot be
   confirmed without aligned on-chain series.

5. **Paid-access justification:** **GAP DISCLOSED.** The free/Standard tier *would* be sufficient
   for these three 24h metrics, **but no account/key is provisioned in this environment**, so even
   the free tier is unreachable (401). Making the metric actionable therefore requires either
   (a) a human to provision a free Glassnode key, or (b) a paid tier. **Per the card's restriction,
   nothing was purchased.** The only path to a grounded ADOPT/PARTIAL verdict is a provisioned key
   (free or paid) — a human decision. No purchase was made.

## Verdict: REJECT

**Reason:** the Glassnode on-chain overlay cannot be evaluated as actionable in this environment.
No API key is provisioned, no `gn` CLI is installed, and `var/glassnode_cache` is empty; every
metric fetch returns 401. The overlay is therefore not adoptable — there is zero evidence it adds
R after costs/filtering, and the free-tier gap (no provisioned key) is a human decision. This is
the DATA_UNAVAILABLE branch of the stop conditions: documented, cache-only path attempted and
empty, concluded REJECT-with-reason rather than stalling.

> **Scope note:** This is NOT a finding that SOPR/netflow "doesn't work." It is a finding that the
> overlay is **unactionable** without provisioned Glassnode access. If Joni provisions a key
> (free Standard tier is sufficient for these 24h metrics), re-running
> `scripts/_g1_glassnode_overlay.py` will populate the kept/blocked/FP analysis and yield a
> grounded ADOPT/PARTIAL verdict. No purchase is required for that path.

## Invalidation / falsification

- The thesis is falsified if, with a provisioned key, `kept.sumR <= baseline.sumR`, or WR drops
  >1pp, or false-positive blocking ≥30% of blocked.
- The thesis is confirmed only if kept.sumR > +16.12R (BTC) with WR not lower by >1pp and low FPs.

## Reproducibility

```
python scripts/_g1_glassnode_overlay.py            # cache-first; emits verdict + raw JSON
python scripts/_g1_glassnode_overlay.py --json
```
Output written to `docs/analysis/raw/g1_glassnode_overlay_{ts}.json`, reproducible from
`var/glassnode_cache` once populated.
