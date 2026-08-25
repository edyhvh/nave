# Baseline (current code, re-captured 2026-08-25)

**IMPORTANT (2026-08-25):** The original iter-18 baseline (+44.14R pooled,
BTC +20.79 / ETH +23.35, captured 2026-04-26 on `feat/stocks`) is **stale**.
Re-running the identical `scripts/theory_v2_backtest.py --coins BTC ETH` on
current code returns materially different results, concentrated in 2019 / 2020 /
2021 and 2024-25 (many post-baseline engine commits: momentum refinements, COT
overlay, regime analysis). See `09_n3_cross_asset_probe.md` for the integrity
finding. All future "Δ vs base" comparisons must use THIS re-captured baseline.

Captured **2026-08-25** by re-running `scripts/theory_v2_backtest.py --coins BTC ETH`.
Raw: `docs/analysis/raw/theory_v2_validation_20260825T204715Z.json`.

| Metric | BTC | ETH |
|---|---|---|
| Fired | 15 | 14 |
| Win | 10 | 8 |
| Loss | 1 | 1 |
| Unresolved | 4 | 5 |
| Total R | +16.12 | +11.57 |
| WR (resolved) | 90.9% | 88.9% |
| Avg R/trade | +1.465 | +1.286 |

**Pooled total R = +27.69R** — the number every experiment must beat on current
code.

Stage rejections (BTC): weekly=328, chase_gate=21, 4H=25, daily=25,
climax_cooldown=17.
Stage rejections (ETH): weekly=338, chase_gate=24, 4H=16, daily=25,
climax_cooldown=14.

## Comparison rules (unchanged)

An experiment is a *strict improvement* iff:
- Pooled total R **>** +27.69R (current-code baseline), **AND**
- Pooled WR is **not lower** by more than 1pp, **AND**
- Per-period regressions are limited (no period drops > 2R unless another rises
  by 4R+).

If only pooled R improves but WR collapses, treat as inconclusive — document, do
not ship.

> Note: the historical shipped experiments (01 SOL, 07 LINK) and N1/N2 used the
> OLD +44.14R baseline. Their internal A/B verdicts stand, but their "Δ vs base"
> columns reference the stale number.
