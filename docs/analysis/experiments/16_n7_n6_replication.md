# N7 — N6 replication and OOS refresh

**Date:** 2026-08-30 18:32:57 UTC artifact (run completed locally; wall-clock 20:30 CEST)
**Lane:** crypto futures only; stock-options lane: not applicable.
**Status:** INCONCLUSIVE — validation refresh, no strategy change.

## Hypothesis

The accepted N6 daily-cadence squeeze path continues to capture gradual/post-crash
expansion, including the BTC 63k→79k move, without changing the verified weekly
baseline. This is a replication/OOS check, not permission to enable or trade it.

## Design and constraints

- Market/instruments: Binance spot OHLCV proxies for BTC and ETH; intended use is
  crypto-futures research, not an execution record.
- Timeframes: daily squeeze detection with existing 4H/1H downstream context;
  weekly control path retained.
- Data: local `data/binance_cache` plus Binance gap-fill where available; observed
  coverage 2017-08-17→2026-08-30 for 1D/4H/1H. Weekly history is partial. OpenBB
  was unavailable (`No module named 'openbb'`), so macro inputs were not refreshed.
- Costs: no explicit fee/slippage deduction in this harness; therefore results are
  optimistic and not production-ready.
- Risk: each resolved trade is expressed in R using the harness stop/target model;
  no leverage, liquidation, funding, or sizing simulation.
- Acceptance: pooled treatment must clear the existing N6 threshold (+27.69R),
  squeeze WR ≥70%, FP ≤20%, capture the OOS rally, and not degrade control.
  Canonical baseline remains +44.14R; strict baseline comparison also requires
  pooled R > +44.14R and WR not down >1pp.

## Work performed

Executed:

`python3 scripts/squeeze_daily_backtest.py --coins BTC ETH`

The script wrote `docs/analysis/raw/squeeze_daily_validation_20260830T183257Z.json`.
No production default was enabled; no financial action occurred.

## Results

| Metric | Control | Squeeze additive | Treatment |
|---|---:|---:|---:|
| BTC total R | +17.82 | +17.62 | +35.44 |
| ETH total R | +11.57 | +12.10 | +23.67 |
| Pooled total R | +29.39 | +29.72 | **+59.11** |
| Resolved WR (pooled) | 19/21 = 90.5% | 19/22 = 86.4% | 38/43 = 88.4% |
| FP rate (resolved losses) | 2/21 = 9.5% | 3/22 = 13.6% | 5/43 = 11.6% |

Treatment adds 26 squeeze trades over the control's 31 trades and improves total
R by **+29.72R**. The OOS slice generated BTC +1.57R on 2026-08-20 and ETH +1.70R
on 2026-05-27; the ETH 2026-08-20 squeeze remains unresolved. The BTC rally target
was captured by the 2026-08-20 daily signal (entry 69,420; stop 64,166; target 77,301).

For the resolved R sequence in the raw artifact, maximum peak-to-trough drawdown is
1.00R for control, squeeze, and treatment (calculated from resolved trade outcomes;
not an equity-curve or portfolio drawdown).

## Comparison and decision

- **N6 local gates:** ACCEPT on this refresh: +59.11R treatment > +27.69R,
  88.4% treatment WR >70%, 11.6% FP ≤20%, OOS rally captured, and treatment is
  additive to the control path.
- **Canonical baseline:** treatment +59.11R is above +44.14R by +14.97R, while
  pooled WR 88.4% is above the baseline pooled WR 78.4% (29/37 resolved from the
  baseline document). This supports reproducibility, but the baseline was captured
  on a different artifact/date and is not a synchronized apples-to-apples rerun.
- **Latency:** daily evaluation captured the 2026-08-20 BTC signal on the same
  dated daily bar; exact intraday latency is unknown because the harness has no
  event-time/fill simulation.
- **Sensitivity:** not measured in this bounded iteration; no parameter sweep was
  performed. One refreshed run is insufficient to establish robustness.

**Decision: INCONCLUSIVE.** The result is materially positive and replicates the
N6 acceptance gates, but missing explicit costs/slippage, partial weekly history,
unsynchronized baseline, unresolved trades, and lack of sensitivity/OOS separation
prevent promoting this to a new validated strategy or enabling it. Per policy, do
not alter strategy to explain one move.

## PR and next action

- **Draft PR:** no creado. The result is a validation refresh, not a reproducible
  strategy improvement eligible for a new PR; no merge was attempted.
- Next bounded iteration: independently rerun the accepted N6 path on a frozen,
  synchronized snapshot with explicit fee/slippage and a pre-registered OOS split;
  retain the weekly baseline unchanged. Stop after three consecutive experiments
  without improvement.

No orders, signatures, transfers, approvals, claims, or other financial execution
were performed.
