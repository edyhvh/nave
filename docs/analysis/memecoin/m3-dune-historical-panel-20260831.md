DUNE PANEL PARTIALLY VALIDATED

# M3 Dune Historical Panel

Date: 2026-08-31 UTC  
Scope: NAVE/Hermes only; read-only research; human-gated; no wallet access,
signing, swaps, notifications, OpenClaw changes, or capital.

## EXECUTIVE RESULT

Dune removes the previous M3 data blocker at the source/schema level, but this
iteration does not validate a complete 24-hour event-feature panel within the
declared 500-credit hard stop.

The evidence is split:

- Dune directly exposes a complete 2026-08-27 Pump.fun launch denominator of
  53,956 mints with launch time, creator, quote asset, supply, protocol state,
  and Token-2022 program fields.
- A one-token proof follows one mint through CREATE, Pump.fun trades, COMPLETE,
  MIGRATE, and PumpSwap trades. The local proof has 323 normalized rows and a
  real PumpSwap pool identity.
- The existing `m3_dual_horizon.build_trajectory` layer accepts the adapted
  proof and produces historical 60m/24h/72h descriptive trajectories. The
  15m mark remains missing in this token and is not imputed.
- The full cohort window query was submitted with bounded dates and protocol
  filters, but its completed result became unreadable after the account
  exceeded its configured read-credit limit. It consumed approximately
  1,537.518 credits, exceeding the 500-credit iteration hard stop.

Therefore the correct status is partial validation, not a strategy result.
Fast Burst and Runner trajectories are proven on one token and are not ready
for cohort research. Early participant episode reconstruction is proven on the
same token only. Historical execution remains partial. No edge is claimed.

## EXISTING NAVE STATE

The prior dual-horizon iteration was preserved before Dune work. Its completed
commit is `ac1cacf7ba4360930f0a930c1119191afffb009b` on branch
`experiment/m3-dual-horizon-trajectory-research`. The Dune branch/worktree was
created from that commit:

`research/dune-historical-panel` at `nave/.worktrees/dune-historical-panel/`.

The prior report was `BLOCKED BY DATA` because the active journal had no valid
launch/event timestamps or primary 5m–4h outcomes, and the historical replay
archives were not downloaded. That work remains intact; this branch adds the
Dune research layer rather than replacing it.

## DUNE ACCOUNT / CREDIT CONSTRAINT

Initial usage was 0 / 2,500 trial credits. The small schema and row probes were
cheap. The exact observed checkpoints were 0.125 credits after the first
schema probes, 5.371 after row/price probes, and 83.559 after the bounded
cohort candidate, completeness, and launch export queries. The full window
query then drove observed usage to approximately 1,338.518 credits. The final
usage command is recorded separately in `data/research/dune/credit_usage.json`.

The 500-credit safety limit is therefore exceeded. No further Dune query was
run after the overrun. The query was not intentionally designed to be
unbounded: it used 2026-08-27 through 2026-08-31 UTC, Pump.fun/PumpSwap
filters, selected columns, server-side aggregation, and a 72-hour horizon.
However, the cross-join of 53,956 launches, 13 window landmarks, and event
joins was still too expensive for this account configuration. This is a
demonstrated cost-feasibility failure, not evidence that raw Dune tables are
absent.

## DUNE TABLES USED

| Table | Use | Partition | Key evidence |
|---|---|---|---|
| `pumpdotfun_solana.pump_evt_createevent` | launch and protocol metadata | `evt_block_time` | mint, creator, supply, initial reserves, Mayhem, cashback, quote mint, token program |
| `pumpdotfun_solana.pump_evt_tradeevent` | Pump.fun bonding-curve trades | `evt_block_time` | user, side, token/SOL amounts, virtual/real reserves, fees, slot, transaction and instruction order |
| `pumpdotfun_solana.pump_evt_completeevent` | completion/graduation | `evt_block_time` | mint, bonding curve, transaction and time |
| `pumpdotfun_solana.pump_call_migrate` | migration and PumpSwap pool | `call_block_time` | mint, pool, Pump AMM, vault accounts, signer, logs, instruction order |
| `dex_solana.trades` | PumpSwap continuation | `block_time` | project, mint pair, trader, amounts, USD amount, vaults, fees, slot/transaction order |
| `prices.usd` | historical SOL/USD conversion | `minute` | historical SOL minute marks, 4,320 rows for the 72-hour proof period |

The Dune docs-search CLI itself failed with `Tool SearchDuneDocs not found`.
Dataset catalog discovery and authenticated SQL execution worked, so this did
not block the data proof.

## SCHEMA AUDIT

The launch table is materially better than the prior NAVE journal: all 53,956
rows had non-null mint, creator, launch timestamp, launch slot, launch
transaction, quote mint, token supply, and token program in the exported
denominator. Pump.fun trade rows expose the required side, user, amounts,
reserve snapshots, and several fee fields directly. Pump.fun prices in USD are
derivable from observed SOL/token quantities plus the historical SOL mark.

Completion and migration are directly represented. The migration call exposes
the PumpSwap pool and token-vault accounts. PumpSwap trades directly expose
trader, token/quote amounts, USD amount, vaults, and partial fee fields. The
selected DEX table does not expose historical PumpSwap reserve snapshots or a
complete failure/exitability state; those remain partial or missing.

| Capability | Classification | Limitation |
|---|---|---|
| launch timestamp, slot, transaction | DIRECT | complete for exported denominator |
| creator, quote asset, supply | DIRECT | supply is observed, not blindly assumed 1B |
| Pump.fun buy/sell and amounts | DIRECT | raw amounts are integer units and require decimals |
| Pump.fun virtual/real reserves | DIRECT | present on trade events |
| Pump.fun historical USD price | DERIVABLE | quote amount and historical SOL/USD mark |
| Pump.fun fees | DIRECT | populated fee, creator, buyback fields where present |
| completion and migration | DIRECT | migration calls need log/duplicate QA |
| PumpSwap pool | DIRECT at migration; DERIVABLE in DEX rows | DEX trade rows need lifecycle join |
| PumpSwap historical reserves/depth | NOT AVAILABLE in selected table | execution impact cannot be fully reconstructed |
| wallet episodes/inventory | DERIVABLE | exact multi-event panel was not materialized for the full cohort |
| wallet funding/sybil relationships | NOT AVAILABLE | no independent actor claim |
| failed transactions/exits, priority fees, Jito | NOT AVAILABLE in selected tables | execution validation gap |

## ONE-TOKEN END-TO-END PROOF

Proof mint: `7Ki5LtQqQ5Qj9bXPaSPxd5ixfNGS4XNCBV1PgQXgpump`.

The proof artifact is `data/research/dune/proof_token_lifecycle.parquet` and
its compact summary is `data/research/dune/proof_token_lifecycle_summary.json`.
It contains 323 rows: 1 CREATE, 156 Pump.fun BUY, 141 Pump.fun SELL, 1
COMPLETE, 1 MIGRATE, 13 PumpSwap BUY, and 10 PumpSwap SELL. The migration
links to PumpSwap pool `8xsNCD82yZMe9E79zuMGscyRk9R8zSFzZPzS59kmiC2b`. The
PumpSwap continuation starts in the migration boundary and is linked by the
same mint and pool context; no symbol-based join is used.

Representative rows only:

| UTC time | type | venue | slot | amount / quote | pool |
|---|---|---|---:|---:|---|
| 2026-08-27 11:33:18 | CREATE | pumpfun | 442094104 | — | — |
| 2026-08-27 11:33:18 | BUY | pumpfun | 442094104 | 2,115,327.70 / 0.059259 SOL | — |
| 2026-08-27 11:39:48 | COMPLETE | pumpfun | 442095183 | — | bonding curve |
| 2026-08-27 11:39:49 | MIGRATE | pumpfun | 442095185 | — | verified PumpSwap pool |
| 2026-08-27 11:39:49 | PUMPSWAP_BUY | pumpswap | 442095187 | 46,572.16 / 0.00001 SOL | same pool |
| 2026-08-27 11:39:49 | PUMPSWAP_SELL | pumpswap | 442095186 | 123,835,213.20 / 0.041438 SOL | same pool |

The proof has historical amount-derived prices and a complete 72-hour event
look-ahead. It is a source/wiring proof, not a representative performance
sample.

## 24-HOUR COHORT AND COMPLETENESS

Selected period: launches from `2026-08-27 00:00:00 UTC` inclusive through
`2026-08-28 00:00:00 UTC` exclusive. The date is historical, has a full
72-hour look-ahead through 2026-08-30, and is recent enough to exercise the
current Mayhem/cashback/Token-2022 schema.

| Metric | Count | Percentage |
|---|---:|---:|
| launch_count | 53,956 | 100.00% |
| tokens_with_valid_launch_time | 53,956 | 100.00% |
| tokens_with_creator | 53,956 | 100.00% |
| tokens_with_quote_asset | 53,956 | 100.00% |
| tokens_with_supply | 53,956 | 100.00% |
| tokens_with_token_program | 53,956 | 100.00% |
| tokens_with_pumpfun_trades | 48,986 | 90.79% |
| tokens_graduated | 1,357 | 2.51% |
| tokens_with_migration | 261 | 0.48% |
| graduated_tokens_followed_into_PumpSwap | 261 | 0.48% of launches; 100% of migrated graduated subset |
| tokens_with_pumpswap_trades | 1,358 | 2.52% |

The exact total raw trade count, full-cohort 5m/15m/60m/4h/24h/48h/72h
outcome counts, and full-cohort participant episode count are deliberately
not reported: the large window result could not be fetched after the credit
limit. The denominator itself is not survivor-filtered.

## PUMP.FUN, MIGRATION, AND PUMPSWAP RECONSTRUCTION

The Pump.fun event tables resolve the prior missing launch and event-time
blockers. Trade direction is read from `is_buy`; `user` is used as the trader,
not `evt_tx_signer`. Slot, transaction index, and outer/inner instruction
indexes are retained. Reserve and fee fields exist on the Pump.fun trade
event.

The complete event and migrate call are independently queryable by mint. A
bounded candidate scan found 261 cohort mints with completion, migration, and
PumpSwap follow-through. The proof token demonstrates the exact cross-stage
join. An anomaly remains: PumpSwap trade activity can be timestamped in the
migration boundary or immediately around the migration call. Ordering must
use slot and instruction indexes; timestamp-only joins are insufficient.

## TRAJECTORY OUTCOMES AND M3 INTEGRATION

The Dune proof was adapted to the existing M3 provider-agnostic event schema
and passed through `build_trajectory`. The integration artifact is
`data/research/dune/integration_proof.json`.

The proof reports 1 eligible token, 1 complete 60m trajectory, 1 complete 24h
trajectory, and 1 complete 72h trajectory. The 5m mark is resolved; the 15m
mark is missing; later marks are resolved according to the M3 trajectory
coverage logic. This demonstrates the adapter, event ordering, historical
mark construction, and fail-closed missingness. It does not demonstrate
cohort coverage or an edge.

`M3 DUAL-HORIZON DATA BLOCKER: PARTIALLY RESOLVED`.

Fast Burst data: one-token proof ready; cohort data not ready.  
Runner data: one-token 4h–72h trajectory proof; cohort data not ready.  
False Runner, survival, and transition research: not run.  
No Burst/Runner thresholds were tuned or promoted.

## EARLY PARTICIPANTS, PNL, AND POINT-IN-TIME HISTORY

The proof produces 31 wallet-token episodes in
`data/research/dune/participant_episodes.parquet`, preserving wallet, mint,
first entry, seconds since launch, first buy, total buy/sell quantities,
first sell, counts, and remaining inventory. The first-30-second,
first-60-second, and first-5-minute landmarks are computed from the observed
trade time. Full cohort episodes were not run after the hard stop.

The local FIFO proof separates realized SOL PnL before fees from remaining
inventory for a ten-wallet subset of the one-token proof. It is classified as
partial, not fully validated, because the proof query did not carry all fee
fields into the local episode output and the sample is one token. No wallet is
called profitable from subsequent price appreciation or open inventory.

Point-in-time history logic is implemented and tested locally: only events and
matured outcomes strictly before a cutoff are eligible. A 72-hour outcome for
a token launched less than 72 hours before the cutoff is censored, not known.
The full multi-token reputation calculation was not run.

Participant convergence is supported at the raw wallet/timestamp/slot level
in the proof. Dune alone does not prove that multiple wallets are independent
economic actors: funding chains, sybil relationships, bundle identity, and
coordinated exits are missing.

Creator history is source-feasible because creator and launch time are direct,
but no all-cohort creator-history join was run. It remains a next experiment.

## PROTOCOL STATES AND BOOST

Mayhem mode, cashback, quote mint, Token-2022 program, launch supply, and
Pump.fun fee fields are available directly in the selected tables. Mayhem
supply is read from the observed token total supply; the panel does not assume
one billion tokens.

BOOST and protocol-generated post-migration flow are not reliably identified
by the selected tables. No field proved which PumpSwap buys were mechanical
BOOST buy-and-burn flow versus organic demand. This remains a material gap for
the post-BOOST residual-demand hypothesis and for organic buyer/volume
features. It is not imputed or inferred.

## SELL-SHOCK ABSORPTION

The one-token panel has enough event timestamps, side, quote amount, wallet,
and post-event trades to run a small sell-shock calculation. The M3 detector
uses only prior valid sell history. However, the broad event/window query
result was unavailable, so no cohort absorption statistic is reported. Dune
can test the hypothesis on a bounded event panel; liquidity/reserve recovery
after PumpSwap sells remains incomplete because historical PumpSwap reserves
are not in the selected trade table.

## EXECUTION / EXITABILITY

Bonding-curve execution is derivable from Pump.fun reserve snapshots and
observed trade quantities. PumpSwap mark prices, amounts, pool accounts, and
some fees are available, but historical reserve/depth snapshots and complete
route state are not. Therefore fixed-notional price impact is only derivable
when reserve state is separately available; otherwise it is UNKNOWN.

| Capability | Dune-only result |
|---|---|
| bonding-curve pricing | DERIVABLE |
| PumpSwap AMM pricing | APPROXIMABLE from trades; reserve state missing |
| historical fees | DIRECT/PARTIAL |
| creator fees | DIRECT on Pump.fun; incomplete post-route proof |
| slippage and fixed-notional impact | PARTIAL; requires historical depth |
| failed transactions and failed exits | NOT AVAILABLE in selected tables |
| priority fees | NOT AVAILABLE |
| same-block ordering | DIRECT where indexes are populated |
| Jito/bundle effects | NOT AVAILABLE |

Dune alone is suitable for historical mark/flow discovery but not for final
realistic-execution validation.

## INTERNAL CONSISTENCY AND DATA QUALITY

Implemented offline checks cover timestamp parsing, trade side interpretation,
amount-derived price, event ordering, migration pool propagation, PumpSwap
linking, duplicate event identity, null/fail-closed behavior, wallet entry
landmarks, FIFO realized versus unrealized inventory, and point-in-time future
exclusion. The proof has one mint identity and one linked migration pool.

Observed limitations/anomalies:

- the DEX table can show PumpSwap activity at the migration boundary;
- PumpSwap pool identity must be joined from migration or stable vault context;
- PumpSwap reserve/depth and complete failure state are absent;
- Pump.fun trade price USD depends on historical SOL minute marks;
- the broad window query shape was too expensive and its result was blocked by
  the account credit limit;
- BOOST/generated-flow attribution and economic-wallet independence are
  unproven.

## PREVIOUS BLOCKERS VS DUNE

| Previous blocker | Dune result | Status | Evidence |
|---|---|---|---|
| missing launch timestamps | direct event timestamp | RESOLVED | 53,956 / 53,956 valid launch times |
| missing event-level outcomes | event tables and historical marks exist | PARTIAL | one-token proof; full result unavailable after cost overrun |
| missing wallet episodes | user/trader and ordered events exist | PARTIAL | 31 proof episodes; full cohort not materialized |
| missing migration linkage | complete + migrate + pool accounts | RESOLVED for bounded cohort | 261 followed mints; one-token pool proof |
| historical liquidity | Pump.fun reserves direct | PARTIAL | PumpSwap reserve/depth missing |
| historical execution | curve math and marks possible | PARTIAL / STILL BLOCKED for realistic execution | failed exits, depth, priority fees, Jito missing |
| protocol-generated flow | no reliable BOOST discriminator | STILL BLOCKED | mechanical vs organic PumpSwap flow unresolved |
| right-censored horizons | explicit 72h bounds and missing marks | PARTIAL | local fail-closed logic; full cohort unavailable |

## DUNE CREDIT COST, STORAGE, AND CONTEXT PROTECTION

Local Dune data is approximately 94 MB, including ignored raw CLI JSON,
13.9 MB launch Parquet, 80 KB proof Parquet, 14 KB participant Parquet, and
small summaries. `*.parquet` and `data/` are gitignored; no raw export is
committed. SQL is tracked under `research/dune/` with SHA-256 entries in the
local manifest.

The full window query was the largest operation. No large result was pasted
into Codex context. Raw results were written to disk and inspected using row
counts, schemas, null rates, compact samples, and aggregates only. No API key
was printed, copied into a repository file, or placed in a report.

## HELIUS DECISION

HELIUS DECISION: USEFUL FOR INDEPENDENT VALIDATION, NOT REQUIRED YET

Dune is missing historical PumpSwap depth/reserves, complete failed-transaction
and failed-exit states, priority fees, Jito/bundle effects, funding-chain
relationships, and a reliable BOOST/generated-flow discriminator. These gaps
matter for execution realism, independent-participant status, and post-BOOST
organic-demand research. A future minimum Helius task would audit a small
sample of migration-boundary transactions, PumpSwap reserve/account states,
and suspected BOOST transactions; it is not needed for Dune-based discovery
and was not configured or called in this iteration. The current Dune credit
overrun is a query-plan/account-budget issue, not a reason to buy another
provider.

## RESEARCH NOW UNBLOCKED

The missing launch/event source is no longer hypothetical. NAVE can now build
a Dune-backed historical panel, and the existing M3 adapter has a working
proof path. The full research program is not yet unlocked because the complete
cohort windows and participant outputs were not fetched within the budget,
and realistic execution remains partial.

## NEXT HIGHEST-VALUE ITERATION

1. Do not rerun the over-budget query. First redesign it as chronological,
   server-side daily partitions with no launch×window cross-join explosion.
2. Run a tiny 100–1,000-mint pipeline proof from the already fetched launch
   denominator, including participant episodes and 5m–72h outcomes, with a
   pre-run cost cap or a small query cost experiment.
3. Add PumpSwap depth/reserve and BOOST classification only if Dune exposes a
   bounded affordable source; otherwise preserve NULL and plan a targeted
   independent audit later.
4. Complete a ten-wallet, multi-token realized-PnL and cutoff-history proof
   before any participant research.
5. Only after these pass, materialize a full daily cohort panel and return to
   Burst, Runner, false-runner, sell absorption, and convergence hypotheses.

No strategy thresholds were optimized, no trading edge was tested, and no
notification or execution path was changed.
