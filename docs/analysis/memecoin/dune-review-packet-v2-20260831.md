# NAVE Dune review packet v2 — 2026-08-31

## EXECUTIVE STATUS

**DUNE PIPELINE VALIDATED WITH LIMITATIONS**

The prior failure was an engineering/economics failure: a monolithic query
multiplied 53,956 launches by 13 landmarks and large event joins, then its
701,428-row result was pulled without a sufficiently narrow export. V2 proves
that compact source slices are inexpensive and reusable locally. It does not
validate a trading edge, realistic execution, or temporal stability.

## WHAT CHANGED SINCE V1

- The completed expensive execution was recovered by metadata, uniform sample,
  and server-side filtered result calls. It was not rerun.
- A new staged architecture separates launch denominator, first-hour Pump.fun
  events, completion/migration, migrated PumpSwap events, participant episodes,
  and local trajectory/outcome construction.
- Deterministic SHA-256 mint sampling and a JSONL cost ledger were added.
- A compact 1,000-launch panel and targeted 7-mint continuation were acquired.
- Multi-token FIFO realized-PnL and point-in-time cutoff machinery was validated
  on real Dune event rows.
- BNB/Four.meme, Base/Clanker, TON, BOOST, and PumpSwap-depth feasibility was
  investigated only within bounded catalog/count probes.

## EXPENSIVE RESULT RECOVERY

Execution `01M1CP4YZMQAYD2JAWQZK49SHC`, query id 0, completed at
2026-08-31T19:54:25Z and expires 2026-11-29. Metadata reports 701,428 rows,
33 columns, and 253,462,228 bytes. A uniform sample and a deterministic
one-mint filter were recovered. The full result was not exported. The first
CLI retrieval attempt incurred 319 credits because the configured CLI path did
not honor the intended bounded fetch; subsequent API calls used columns,
filters, limits, and sampling. The 1,537-credit computation was never rerun.

## QUERY ARCHITECTURE V1 VS V2

| V1 | V2 |
|---|---|
| 72h all-launch event query | local canonical denominator reused |
| launch × 13 landmark rows | first-hour events scanned once |
| all long-horizon joins together | migration map before PumpSwap |
| participant calculation in giant SQL | bounded participant events, local episodes |
| Dune computes every threshold | Dune answers on-chain facts; local code computes research features |

FAST_BURST is isolated to 0–60 minutes. RUNNER uses 4h–72h continuation only
for the small verified migrated set. Raw wallet events are not exported for
all launches.

## CREDIT BENCHMARK AND SCALING

The iteration began at 1,537.518 and ended at 1,863.570 consumed credits:
326.052 credits used, 636.430 included credits remaining. The new-work ceiling
at the start was 481.241 credits; it was respected. No operation was allowed
above 50 credits.

| Experiment | Mints | Rows/events | Credits |
|---|---:|---:|---:|
| first-hour count | 100 | 6,676 events | 0.584 |
| first-hour count | 1,000 | 62,875 events | 0.472 |
| compact token panel | 1,000 | 1,000 rows | 0.147 |
| migration map | 1,000 | 7 rows | 0.215 |
| PumpSwap continuation | 7 migrated | 6,227 events | 3.601 |
| targeted early events | 7 migrated | 2,367 events | 1.653 |

The 100/1,000 count pair is not linear; Dune charges for actual compute and
network resources. The robust result is that one-row-per-mint aggregates are
sub-credit at 1,000 mints, while raw continuation event exports scale with
event volume and result size. The optimized 1,000-mint source panel was 0.147
credits; the fuller bounded package including 7 migrated continuations was
5.616 credits.

## 24H, 7D, AND 30D STATUS

The compact 1,000-launch panel is materialized locally. It has 917/1,000
first-hour trade coverage. Pump.fun-only marks near 4h/24h/48h/72h resolve for
7/2/1/0 rows because tokens leave the curve; this is why post-migration joins
are required. A complete 24h cohort panel was not run: compact compute is
estimated at 60–180 credits, but cohort-scale result retrieval has not been
proven affordable under the per-operation cap. The 7-day panel was not run;
the estimate is 420–1,260 credits. Thirty-day historical coverage is estimated
at 1,800–5,400 credits and is not authorized by this iteration.

## MATERIALIZED VIEWS AND INCREMENTAL QUERIES

`dune matview list` returned no existing views. Official Dune documentation
states the Free materialized-view limit is 1 MB, so raw Solana/Pump.fun history
is not an appropriate materialization candidate. Local immutable Parquet is
the better current store. A compact daily launch aggregate is the only
reasonable future Dune materialization candidate.

`research/dune/04_daily_incremental.sql` prototypes the documented
`TABLE(previous.query.result(...))` pattern with a one-day lookback. It was not
executed because it requires a saved-query context and no Dune write/schedule
was authorized. The estimated recurring cost is 0.5–3 credits/day.

## EARLY PARTICIPANTS AND MULTI-TOKEN PNL

The targeted slice contains 2,367 Pump.fun first-hour rows and 6,227 PumpSwap
rows across 7 migrated mints. Local reconstruction produced 1,786 wallet-token
episodes, 1,508 within five minutes, and 1,666 wallets. The machinery passes
FIFO realized-PnL, separate fees, separate remaining inventory, and
point-in-time cutoff checks across multiple tokens and at least ten wallets.
This is a historical targeted proof, not a full-cohort reputation dataset.
Funding chains, sybil/economic-actor identity, bundles, failed exits, and
protocol-generated flow remain unavailable.

## BURST/RUNNER DATA AND LOCAL DESCRIPTIVES

The 1,000-launch panel supports descriptive first-hour mark proxies for 887
rows. High/open mark-return proxy counts are +100%: 110, +200%: 53, and +500%:
19. Median is 1.99%, mean is 47.46%; these are mark proxies, not executable
returns and have no fee/depth adjustment. No family model was fit. A single
calendar day and seven migrated long-horizon examples cannot establish
FAST_BURST, FALSE_RUNNER, SUSTAINED_RUNNER, or DEAD/SLOW_BLEED stability.
Substantive local statistical research is therefore gated.

## BOOST, DEPTH, AND HELIUS

Catalog search surfaced community candidates for Pump buy-back data and pool
balances, but no verified bounded BOOST discriminator. BOOST remains UNKNOWN.
The selected `dex_solana.trades` table has trade amounts and wallet identity,
not historical PumpSwap reserves/depth snapshots. Depth is classified
HELIUS_LIKELY_NEEDED for independent validation, but Helius is not required
for current discovery. No Helius account, key, or query was used.

## MULTI-CHAIN FEASIBILITY

The one bounded Dune count probe returned 7 Base Clanker v4 TokenCreated rows,
1,501,010 Base DEX rows, and zero rows for the selected BNB proxy transfer and
TON/TONCO day. Counts are not comparable graduations.

- BNB/Four.meme: partial catalog candidates, but no verified launch,
  bonding-curve, or migration source; insufficient for a panel.
- Base/Clanker: partial and promising. Clanker v4 TokenCreated exposes token,
  pool, paired-token, sender, metadata, and event time; a future bounded proof
  can join Base DEX trades.
- TON: insufficient. TONCO pool lifecycle tables exist, but no launchpad or
  jetton creation source and no confirmed DEX trade coverage were found.

The chain-neutral schema remains Launch, TradeEvent, ParticipantEpisode,
LiquidityState, LifecycleTransition, VenueMigration, TrajectoryMark, Outcome,
and ProtocolState. Adapter implementations beyond PumpFun are deferred.

## MONTHLY PLAN AND CREDIT PURCHASE

| Scenario | Credits/month |
|---|---:|
| Research-light | 150–350 |
| Research-normal | 900–2,400 |
| Research-heavy | 3,500–7,500 |

**DUNE PLAN RECOMMENDATION: STAY_FREE.** Normal work fits the 2,500-credit
allowance. Occasional Free overage is cheaper than Analyst until usage is
sustained near 4,000 credits/month; Plus is not justified. **CREDIT PURCHASE
RECOMMENDATION: DO NOT PURCHASE UNTIL MORE COST DATA EXISTS.**

## NEXT RESEARCH ITERATION

Use the acquired Parquet locally. If a human later approves bounded Dune spend,
acquire another calendar day using the same compact/migration-first stages,
then test chronological descriptive stability. Only after multiple dates,
complete outcomes, and execution-quality fields are available should NAVE test
participant incremental value or any candidate hypothesis. No trading,
notification, or OpenClaw change is authorized.
