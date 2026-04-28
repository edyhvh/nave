# Baseline (iter 18, feat/stocks)

Captured **2026-04-26** by re-running `scripts/theory_v2_backtest.py --coins BTC ETH`.

| Metric | BTC | ETH |
|---|---|---|
| Fired | 22 | 25 |
| Win | 14 | 15 |
| Loss | 4 | 4 |
| Unresolved | 4 | 6 |
| Total R | +20.79 | +23.35 |
| WR (resolved) | 77.8% | 78.9% |
| Avg R/trade | +1.155 | +1.229 |

**Pooled total R = +44.14R** — the number every experiment must beat.

Stage rejections (BTC): chase_gate=44, weekly=257, 4H=33, climax_cooldown=33, daily=33, weekly_cot=9.
Stage rejections (ETH): weekly=274, climax_cooldown=21, chase_gate=44, daily=35, 4H=23, weekly_cot=9.

Raw: `docs/analysis/raw/theory_v2_validation_20260427T004337Z.json`.

## Comparison rules
An experiment is a *strict improvement* iff:
- Pooled total R **>** +44.14R, **AND**
- Pooled WR is **not lower** by more than 1pp, **AND**
- Per-period regressions are limited (no period drops > 2R unless another rises by 4R+).

If only pooled R improves but WR collapses, treat as inconclusive — document, do not ship.
