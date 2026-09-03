# NAVE Dune credit model — 2026-08-31

## Decision

**DUNE PLAN RECOMMENDATION: STAY_FREE**

Projected normal NAVE usage is **900–2,400 credits/month**. No credit purchase
is recommended until a larger long-horizon sample is measured. Free overage is
economically preferable to Analyst for occasional excursions below roughly
4,000 credits/month; Plus is not supported by observed usage.

Pricing was checked against [Dune's credit guide](https://docs.dune.com/resources/credits-billing/how-credits-work) and [API billing](https://docs.dune.com/api-reference/overview/billing): Free is 2,500 credits/month, Analyst is $75 for 4,000, and Plus is $399 for 25,000. Free/Analyst/Plus export rates are 20/10/2 credits per MB, and storage limits are 100 MB/1 GB/15 GB. The trial account reports Free-tier economics.

## Observed accounting

The iteration began at 1,537.518 consumed credits and ended at 1,863.570:
**326.052 credits used**. The 319.000-credit increment was an attempted
bounded retrieval of the already-completed 701,428-row execution; it did not
rerun the 1,537-credit query. The remaining included balance is 636.430.

| Operation | Mints | Rows | Credits |
|---|---:|---:|---:|
| first-hour count benchmark | 100 | 1 | 0.584 |
| first-hour count benchmark | 1,000 | 1 | 0.472 |
| first-hour compact aggregate | 1,000 | 917 | 0.259 |
| token panel with 4h–72h Pump.fun marks | 1,000 | 1,000 | 0.147 |
| migration-first map | 1,000 | 7 | 0.215 |
| PumpSwap continuation | 7 | 6,227 | 3.601 |
| targeted first-hour participant slice | 7 | 2,367 | 1.653 |
| multi-chain count probe | — | 5 | 0.121 |

The benchmark is not perfectly linear: the 100-mint query cost more than the
1,000-mint count because Dune compute is resource-based. The reliable design
signal is architectural: compact one-row-per-mint output is cheap, while raw
event export and especially broad result retrieval dominate.

## Model by stage

| Stage | One-day estimate | Notes |
|---|---:|---|
| launch denominator | 2–10 | reuse the existing 53,956-row local denominator |
| Pump.fun first hour | 5–25 | one scan; no landmark cross join |
| completion/migration | 1–8 | build the small migrated set first |
| PumpSwap migrated tokens | 40–160 | largest uncertainty; only verified mints |
| early participants | 10–60 | targeted wallets/events, not all 72h wallets |
| participant PnL | 5–40 | local FIFO after event acquisition |
| result export | 10–80 | selected columns, pagination, compact aggregates |
| incremental daily update | 0.5–3/day | estimate; no saved-query write was made |

The **optimized 1,000-mint source panel cost was 0.147 credits**. A fuller
bounded package including the 7 migrated-token continuation and participant
slice cost **5.616 credits observed**. This is a proof of affordability for a
small panel, not evidence that a complete 53,956-token 72-hour event export is
cheap.

## Horizon estimates and gates

| Scope | Estimated credits |
|---|---:|
| one complete day | 60–180 |
| seven complete days | 420–1,260 |
| fourteen complete days | 840–2,520 |
| thirty complete days | 1,800–5,400 |
| one month of compact daily refreshes | 30–150 |

The estimates satisfy the compute-side 24-hour gate on the low/central case,
but full result retrieval is not yet proven affordable at cohort scale. The
complete 24-hour panel was therefore **not run**. The seven-day panel was also
not run because temporal value is not established from one calendar day and
retrieval uncertainty remains material.

## Monthly scenarios

| Scenario | Credits/month | Decision |
|---|---:|---|
| light | 150–350 | Free |
| normal | 900–2,400 | Free |
| heavy | 3,500–7,500 | Free overage initially; compare Analyst if sustained |

The model excludes live trading, notifications, and any paid-provider use. It
also does not treat missing PumpSwap depth, failed exits, priority fees, Jito
bundles, BOOST attribution, or wallet identity as available.
