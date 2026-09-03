MULTI-DAY RESEARCH MATERIAL PROGRESS

## EXECUTIVE STATUS

The main progress this iteration is semantic rather than a new bulk download.
The 2026-08-28 PumpApi event tape was audited at token and horizon level, and
the opaque `UNRESOLVED` bucket was decomposed. At 60 minutes, 672 unresolved
tokens had prior trades but no trade at or after the target, 128 had no trade
through the target, two migrated before the target, and zero were attributed to
a provider gap or invalid price input. This is economically different from
missing data and supports survival/activity outcomes.

An existing paid 2026-08-27 Dune compact panel was also recovered locally as a
second partial day: 1,000 deterministic launch rows, 917 60-minute trade/mark
rows, and seven targeted migrated continuations. It cannot supply frozen
1m/3m/5m/10m event-level features, so it is not silently merged into the
point-in-time A-vs-C matrix.

No edge was validated. No trading, wallet, signing, alert, scanner, provider
purchase, upgrade, or live action occurred.

## BASELINE STATE

- Day 2, 2026-08-28: one provider-complete PumpApi day for the frozen 1,000-mint sample, 254,522 filtered rows, 1,000 observed mints.
- Day 1, 2026-08-27: existing compact Dune panel, 53,956-launch denominator, 1,000 deterministic sample rows, 917 60-minute aggregate marks.
- Fully comparable event-level days: 1.
- Observed panel days including the explicitly partial Dune day: 2.
- Current Dune usage: 2,024.104 of 2,500 included credits; 475.896 remaining.

## THREE-DAY PREDECLARATION

The existing quant continuation predeclared 2026-08-29, 2026-08-30, and
2026-08-31 UTC before inspecting outcomes. It streamed only 2026-08-29 hours
00–05 of 72 archives before its bounded runtime gate and promoted no partial
sample. Those dates therefore remain pending and were not replaced based on
outcomes.

The failed assumption was that a sequential full-day PumpApi discovery pass
was the highest-information next step inside the bounded task window. The
reversible pivot here is to resolve Day 2 observability semantics and reuse
already-paid compact evidence before another bulk replay.

## ACQUISITION

No new calendar day was downloaded in this iteration. Existing local evidence
was inspected from the stable data root `/home/david/nave/data` and prior
worktree artifacts. A small canonical hour manifest records the recovered Day
2 archive URLs, integrity status, parser status, row counts, and combined
Parquet checksum:

`docs/analysis/memecoin/nave-pumpapi-hour-manifest-20260901.json`

The new code resolves linked-worktree data through the Git common repository
root or an explicit `NAVE_DATA_ROOT`; it does not search sibling worktrees or
infer scientific validity from the current working directory.

## DAILY COVERAGE

| UTC day | Source | Sample | Decision snapshots | 15m full/resolved | 30m full/resolved | 60m full/resolved | Migrants |
|---|---|---:|---:|---:|---:|---:|---:|
| 2026-08-27 | existing Dune compact panel | 1,000 | 0 point-in-time | not exposed | not exposed | 917/917 aggregate marks | 7 targeted |
| 2026-08-28 | recovered PumpApi event tape | 1,000 | 4,000 | 993/242 | 981/196 | 965/163 | 30 |

The Day 1 60-minute Dune mark is retained as a descriptive cross-provider
observation, not treated as equivalent to the Day 2 event-derived resolver.

## UNRESOLVED TAXONOMY

The new deterministic resolver returns `RESOLVED`, `RIGHT_CENSORED`, or
`UNRESOLVED` plus a reason. It checks provider completeness before economic
inactivity, treats migration separately, and never labels a short no-trade
interval as permanent death.

| Horizon | Resolved | No future trade after target | Inactive through target | Migrated before horizon | Right censored | Provider gap | Price/reserve failure | True unknown |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 15m | 242 | 621 | 130 | 0 | 7 | 0 | 0 | 0 |
| 30m | 196 | 655 | 129 | 1 | 19 | 0 | 0 | 0 |
| 60m | 163 | 672 | 128 | 2 | 35 | 0 | 0 | 0 |

`TOKEN_INACTIVE` means no trade through that horizon in the observed tape; it
does not mean permanently dead. `NO_FUTURE_TRADE` means prior activity exists,
but no trade at or after the target was observed through the collection end.

## NO-FUTURE-TRADE VS MISSING-DATA

The five restored Day 2 hours are complete enough for the selected short
horizon mask, with zero internal gaps. All 253,492 BUY/SELL rows have a finite
positive provider price. Therefore the dominant unresolved class is not
provider absence, malformed price, or parser failure. It is sparse/non-
continuous trading relative to an exact target-time mark.

This distinction makes `NO_ACTIVITY_THROUGH_15M/30M/60M` valid descriptive
survival outcomes. It does not justify converting the rows to losses or
calling them dead. A later collection boundary remains right censoring.

## PRICE MARK AUDIT

The primary mark remains the first valid trade at or after the horizon. It
resolves 242, 196, and 163 tokens at 15m, 30m, and 60m. The low rate is caused
mostly by no trade at or after the target, not invalid price fields. A fixed
five-minute nearest-trade sensitivity resolves 154, 87, and 44 additional
coverage candidates at those horizons, respectively, but this sensitivity was
computed after coverage inspection and is exploratory. It is not promoted to
the primary outcome and must be frozen before any future return comparison.

The correct next resolver version should expose, without blending:

- `FIRST_MARK_AT_OR_AFTER_HORIZON`;
- `NEAREST_MARK_WITHIN_FIXED_TOLERANCE`;
- `NO_MARK`;
- activity/survival outcomes independent of mark availability.

## OBSERVABILITY BIAS

Among the 965 non-right-censored 60-minute tokens, resolved-mark tokens were
much more active before the decision horizon than unresolved tokens:

| Pre-decision measure | Resolved-mark median | Unresolved median |
|---|---:|---:|
| trades in first 10m | 138 | 9 |
| unique buyers in first 10m | 24 | 3 |
| BUY quote volume in first 10m (SOL) | 11.03 | 0.63 |
| trades through 60m | 159 | 9 |

This is strong selection-bias evidence against fitting mark returns only on
resolved rows without a first-stage observability/survival analysis. No
observability model was fit because the event-level temporal sample is still
one day.

## SURVIVAL/ACTIVITY OUTCOMES

The resolver now supports horizon-specific activity states rather than a
single unresolved bucket. For Day 2 at 60m, 830 of 965 non-right-censored
tokens had a trade through the target and 135 did not; five of those 135 later
received a valid mark after the target, so activity and mark outcomes are not
identical. The primary market-activity labels for future work are:

- `HAS_TRADE_THROUGH_HORIZON`;
- `NO_ACTIVITY_THROUGH_HORIZON`;
- `FUTURE_TRADE_AFTER_HORIZON`;
- `TIME_TO_LAST_TRADE` and future buyer breadth where observed.

These labels preserve the distinction between economic inactivity and provider
missingness.

## MULTI-DAY BURST COVERAGE

Day 2 contributes 1,000 valid decision rows at each 1m/3m/5m/10m point and
4,000 token-time snapshots, but only one independent calendar day. The Day 1
compact Dune result has no event history ending at each frozen decision time,
so it cannot contribute valid A or C features without look-ahead. The combined
multi-day point-in-time A-vs-C matrix is therefore not ready.

The maximum conservative Day 2 paired mark rows is 968/784/652 at 15m/30m/60m
(four decision times per resolved token). These are clustered within token and
are not 968/784/652 independent assets.

## RUNNER ALL-MIGRANT UNIVERSE

The available Day 2 PumpApi sample contains 30 verified migrations, but the
complete daily all-launch migration universe was not acquired. The existing
Day 1 Dune compact panel contains seven sample migrations and targeted
PumpSwap continuation. This is a targeted sample, not an all-migrant panel;
it must not be represented as full-day Runner coverage.

## RUNNER 4H/8H/12H/24H/48H/72H

For the seven existing Day 1 targeted migrants, PumpSwap activity exists for
7/7 at 4h, 7/7 at 8h, 7/7 at 12h, 6/7 at 24h, 1/7 at 48h, and 0/7 at 72h.
The Dune token panel supplies quoted marks for 7/7 at 4h, 2/7 at 24h, 1/7 at
48h, and 0/7 at 72h. Activity is not a quoted executable exit.

Day 2's 30 sampled migrants remain right-censored at 24h/48h/72h because the
PumpApi tape ends at the Day 2 boundary. Migration is retained as a lifecycle
event and is never treated as Runner success or token death.

## A VS C READINESS

Not ready. A has one event-level day; C requires ordered precursor history at
each frozen decision time. Day 1's aggregate 60-minute Dune fields cannot be
used at 1m/3m/5m/10m. The conservative 5,000 paired-row gate and several-day
temporal gate are not met. Participant models B/D remain deferred.

## A VS C RESULTS IF RUN

Not run. No model, threshold, feature search, random cross-validation, or
operational change was performed.

## TEMPORAL STABILITY

Not estimable. There is one provider-complete event day and one compact
cross-provider descriptive day. The 2026-08-29/30/31 predeclared acquisition
attempt remains incomplete. Any apparent return difference would be dominated
by day and provider definition rather than temporal validation.

## PROVIDER COST

No new provider call was made. The existing paid Dune artifacts were read from
local storage; no Dune execution was rerun. New Dune usage is 0 credits.

## DUNE USAGE

The verified current reading is 2,024.104 consumed of 2,500 included credits,
leaving 475.896. The 25-credit target, 50-credit soft limit, and 75-credit hard
stop remain unchanged. No new query is justified by this iteration.

## DATA ARCHITECTURE

Implemented and tested:

- explicit `OutcomeEvidence` and `classify_outcome` taxonomy;
- provider-gap precedence over inactivity;
- migration-before-horizon distinct from death;
- right censoring distinct from unresolved;
- stable shared data-root resolution for linked worktrees;
- canonical Day 2 hour manifest with `COMPLETE` versus `COMPLETE_WITH_WARNINGS`;
- local audit script producing token-level classifications without provider calls.

The five recovered-hour warnings are retained as `COMPLETE_WITH_WARNINGS`,
not silently dropped as failed. No decompressed raw archive was committed.

## 10–14 DAY SCALE DECISION

**READY_WITH_LIMITATIONS.** The taxonomy, data-root resolution, and compact
manifest approach are ready for staged expansion. Full PumpApi multi-day replay
is not operationally ready under the current short bounded runtime: six of 72
archives consumed about eight minutes in the prior continuation. Scale should
use a predeclared launch manifest or longer bounded windows, reuse overlapping
future-day streams for Runner, and keep unresolved activity outcomes separate
from mark outcomes.

## SCIENTIFIC CONCLUSION

The dominant Day 2 unresolved bucket is a market-observability problem caused
by sparse continuation at the exact horizon, not an established provider-data
gap. A two-stage design—activity/survival first, price mark conditional on
observability—is more defensible than discarding unresolved rows or assigning
losses. The result remains preliminary and does not establish predictive edge.

## NEXT HIGHEST-INFORMATION EXPERIMENT

Use existing Day 1 compact Dune evidence plus Day 2 PumpApi events to build a
clustered, outcome-independent survival/observability panel and migration-aware
Runner activity table. Then acquire one additional predeclared event-level day
through a compact launch-manifest/targeted stream plan, rather than repeating
the three-day sequential full-discovery attempt. Do not fit A-vs-C until there
are several event-level days and a frozen outcome contract.
