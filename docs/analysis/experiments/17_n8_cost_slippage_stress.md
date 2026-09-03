# N8 — N6 cost/slippage stress

**Date:** 2026-08-31T18:33:11.766471+00:00
**Lane:** crypto futures only; stock-options lane: not applicable.
**Status:** INCONCLUSIVE — cost robustness check; no strategy change.

## Hypothesis

The N6 daily-cadence squeeze path remains positive after realistic round-trip fees, spread, and slippage, without weakening the verified weekly baseline. This tests execution robustness; it does not retune the strategy for the BTC 63k→79k move.

## Protocol

- Instrument proxies: BTC and ETH Binance OHLCV; research proxy only, no execution record.
- Timeframes: daily squeeze detection, existing 4H setup and 1H trigger; weekly control retained.
- Source: `/tmp/nave-n8-cost-stress/docs/analysis/raw/squeeze_daily_validation_20260830T183257Z.json`; SHA-256 `3199a1e3af417e9aa0f68b1cf8b302ce3dbfea11e676d05f55a468ab8a5a88d2`.
- Costs tested: 0.10%, 0.30% (base), 0.50%, 1.00% round-trip notional cost.
- R conversion: `cost_pct / stop_distance_pct`; costs applied to every fired trade in `fired_cost_net_r`. WR uses resolved outcomes only.
- Unresolved trades are not invented as wins/losses; `resolved_net_r` excludes their costs and is therefore optimistic for incomplete observations.
- Risk: no leverage, funding, liquidation, fill queue, or intraday impact model.
- Acceptance: base and stressed treatment fired-cost net R positive; additive squeeze path remains positive; no evidence of baseline degradation; OOS capture remains present.

## Quantitative result

| Scenario | Control fired-cost net R | Squeeze additive fired-cost net R | Treatment fired-cost net R | Treatment resolved WR |
|---|---:|---:|---:|---:|
| optimistic_0.10pct | +28.97 | +29.33 | +58.30 | 88.4% |
| base_0.30pct | +28.13 | +28.53 | +56.66 | 88.4% |
| stressed_0.50pct | +27.29 | +27.72 | +55.02 | 88.4% |
| severe_1.00pct | +25.20 | +25.72 | +50.92 | 88.4% |

At the base 0.30% assumption, treatment is **+56.66R** and the squeeze additions are **+28.53R**. At stressed 0.50%, treatment is **+55.02R** and squeeze additions **+27.72R**. The raw gross treatment remains +59.11R and resolved WR 88.4%; these are unchanged observations, not net performance claims.

## OOS and limitations

The source retains the BTC 2026-08-20 squeeze signal capturing the target move (entry 69,420; stop 64,166; target 77,301; +1.57R gross) and ETH 2026-05-27; exact intraday signal latency remains unknown. The canonical +44.14R baseline has no per-trade stop distances in its cited aggregate artifact, so an apples-to-apples net baseline stress test cannot be computed. Weekly coverage is partial, one snapshot is insufficient for robustness, and fees/slippage are modeled assumptions rather than observed fills.

## Decision

**INCONCLUSIVE.** Positive under all tested modeled cost scenarios, but this is not a validated production edge: baseline net comparison, synchronized data, funding/liquidation, and true event-time fills remain missing. Keep N6 disabled for live use and preserve the weekly baseline unchanged.

## PR / next action

- Draft PR: **no creado**; no strategy change or reproducible promotion occurred.
- Next bounded action: obtain a synchronized frozen BTC/ETH snapshot with per-trade stop distances for the baseline and model event-time fee/slippage/funding before any promotion decision.
- Stop rule: stop after three consecutive experiments without improvement; N8 is a robustness result, not a promotion.

No orders, signatures, transfers, approvals, claims, or other financial execution were performed.
