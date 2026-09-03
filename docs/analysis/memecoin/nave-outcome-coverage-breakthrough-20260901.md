# NAVE outcome-coverage breakthrough — 2026-09-01

## EXECUTIVE STATUS

**MATERIAL PROGRESS.** The five apparently missing PumpApi hours were not absent
archives. They were orphaned/failed local replay outputs plus a stale checkpoint
interpretation. A fresh streamed recovery from the official archives restored
24/24 UTC archive-hour coverage for the frozen 1,000-mint Day-2 sample.

This does not validate an edge. The recovered day is still one calendar day,
24h/48h/72h outcomes are right-censored at the collection boundary, and only
163 conservative 60m outcome rows are currently paired with valid decision
snapshots.

## PREVIOUS BLOCKER

The canonical blocker was `BLOCKED BY OUTCOME COVERAGE`: the repository state
treated 19/24 verified hours as a failed Day-2 panel and consequently exposed
zero validated multiday outcome rows.

## WHY THREE ITERATIONS FAILED

The repeated assumption was: `checkpoint.status=FAILED` plus no data under the
current checkout means the hour is unavailable and the whole day is unusable.
The prior checks did not search the sibling M3 worktree where all five retained
outputs existed, and the acquisition contract had no `COMPLETE_WITH_WARNINGS`
state for a streamed archive that returned a non-zero pipeline status. This
conflated archive-level acquisition status with token-level scientific coverage.

The fresh test falsified remote absence and archive corruption: all five official
URLs returned HTTP 200 and `curl | zstd -t` exited 0. Re-streaming through the
existing normalizer produced zero malformed lines and complete hour boundaries.

## CURRENT DATA INVENTORY

| Artifact | Scope | Rows / mints | Status |
|---|---|---:|---|
| `data/research/pumpapi/day/date=2026-08-28/pumpapi_events_recovered_full.parquet` | PumpApi filtered replay, all 24 hours | 254,522 / 1,000 | Complete for the frozen sample and calendar day |
| retained prior Parquet | PumpApi replay, old checkpoint selection | 238,027 / 957 | Superseded; excluded failed-hour outputs |
| Dune `first_hour_1000` | Already-paid Day-2 first-hour response | 82,804 / 916 unique mints | Recovered local evidence; no new query |
| Dune launch result | Day-2 launch denominator | 48,330 launches | Already-paid local result |
| Day-1 Dune panel | 2026-08-27 | 1,000-token panel | One prior usable calendar day |

The selection is deterministic and outcome-independent (`sha256(seed || mint)`),
with 1,000 Day-2 mints resolved against the 48,330-launch denominator. No raw
multi-gigabyte decompressed archive was retained.

## 19/24 COVERAGE AUDIT

The old manifest reported 19/24 because hours 01, 06, 11, 13, and 17 had a
`FAILED` checkpoint. Their old filtered files were non-empty, but the state
machine discarded them. The fresh recovery produced the following retained
counts: 01=5,714; 06=3,235; 11=3,224; 13=16,393; 17=14,606. All 24 recovered
hour files end within their declared UTC hour; all five new parser runs had
zero malformed lines.

The final all-day Parquet has 254,522 rows versus 238,027 before recovery,
restores the sample from 957 to 1,000 observed mints, and restores the five
hour-level gaps without imputation.

## MISSING-HOUR ROOT CAUSES

| UTC hour | Prior local status | Remote status | Fresh replay | Root cause conclusion |
|---|---|---|---|---|
| 01 | FAILED; 3,138 retained rows | HTTP 200; zstd OK | 5,714 rows; 0 malformed | transient/previous pipeline failure; recoverable |
| 06 | FAILED; 2,894 retained rows | HTTP 200; zstd OK | 3,235 rows; 0 malformed | transient/previous pipeline failure; recoverable |
| 11 | FAILED; 994 retained rows | HTTP 200; zstd OK | 3,224 rows; 0 malformed | transient/previous pipeline failure; recoverable |
| 13 | FAILED; 8,389 retained rows | HTTP 200; zstd OK | 16,393 rows; 0 malformed | transient/previous pipeline failure; recoverable |
| 17 | FAILED; 11,262 retained rows | HTTP 200; zstd OK | 14,606 rows; 0 malformed | transient/previous pipeline failure; recoverable |

The official replay page documents hourly archives at
`https://replay.pumpapi.io/YYYY/MM/DD/HH.jsonl.zst`, and the five current
archive probes matched that contract. The archived data path is free and did
not require a credential, wallet, or Trade API call.

## TOKEN-LEVEL CENSORING AUDIT

The new pure contract in `research/nave/outcome_coverage.py` evaluates the
interval from each launch to each horizon. A missing/failed hour becomes
`INTERNAL_GAP` only for tokens whose required interval crosses it. A collection
boundary becomes `RIGHT_CENSORED`; a complete interval with no usable mark is
`UNRESOLVED`. No interpolation or favorable exclusion is performed.

With all 24 archive hours restored, `INTERNAL_GAP=0` for every tested short
horizon. Before recovery, the old calendar/day mask would have discarded
246/293/389 tokens for 15m/30m/60m respectively even though the interval mask
could preserve unaffected trajectories. This demonstrates that the old day
level completeness rule was scientifically too strict.

## BURST COVERAGE NOW

All 1,000 sampled launches have an event-backed point-in-time snapshot at each
of 1m, 3m, 5m, and 10m in the recovered filtered stream. The resulting maximum
decision snapshot count is 4,000, below the requested 5,000-row gate.

| Horizon | FULL interval | conservative resolved mark | unresolved | right-censored | internal gap |
|---|---:|---:|---:|---:|---:|
| 15m | 993 | 242 | 751 | 7 | 0 |
| 30m | 981 | 196 | 785 | 19 | 0 |
| 60m | 965 | 163 | 802 | 35 | 0 |

The paired 60m dataset is therefore 163 tokens × 4 decision times = 652
decision/label rows at most. This is not enough for the preregistered Burst
model gate and is not a multiday result.

## RUNNER COVERAGE NOW

The recovered Day-2 sample contains 30 verified migration events. This is a
sampled-day count, not the all-mint Runner universe. Conservative outcome
coverage is 19/30 at 4h, 13/30 at 8h, and 7/30 at 12h; 24h, 48h, and 72h are
right-censored because the archive ends on 2026-08-28. PumpSwap continuation
and migration-linked all-mint history remain incomplete.

## ALREADY-PAID DUNE RECOVERY

Local retained Dune execution metadata was inspected before any new query. The
principal results are the 701,428-row Day-1 window execution
`01M1CP4YZMQAYD2JAWQZK49SHC` (result retrieval had previously hit the configured
credit limit), Day-2 launch execution `01M1D4NBZ9ME2E2MB3N5J5WCVG` with 48,330
rows, and Day-2 first-hour execution `01M1D4RMF5ED93D1CQCVPTA73D` with 82,804
rows. Existing Day-1 migration and PumpSwap executions were also retained.
No server-side result was rerun and no new Dune execution was needed.

## NEW DUNE USAGE

`dune usage -o json` reported 2,024.104 credits consumed out of 2,500, leaving
475.896 included credits. New Dune credits used in this session: **0**. The
local resource guard remains unchanged; no purchase or upgrade occurred.

## PUMPAPI REMOTE STATUS

All five archive probes returned HTTP 200. End-to-end zstd tests exited 0 and
reported decompressed byte counts of approximately 3.53 GB (01), 3.30 GB (06),
3.12 GB (11), 3.61 GB (13), and 4.10 GB (17). Recovery streamed HTTP → zstd →
JSONL normalization/filtering and retained only compact selected-mint rows.
The 36 MB filtered Parquet hash is
`8dbed19dda1c9d190178e176c2e3483c9f4de1029fb4a6906413ecea91092b7`.

## ACQUISITION STRATEGY A/B/C

| Strategy | Rows unlocked | Calendar diversity | Provider cost | Engineering | Scientific validity |
|---|---:|---|---|---|---|
| A. Repair five hours | +16,495 retained rows; +43 mints; 242/196/163 short-horizon marks | None | 0 Dune credits; bounded free replay bandwidth | Low after fixing path/state interpretation | Valid for the recovered day, still one-day preliminary |
| B. Token-level censoring | Preserves unaffected trajectories; avoids 246/293/389 old-mask discards | None | 0 | Low; pure deterministic contract added | Valid if gaps remain explicit and selection is audited |
| C. Acquire cleaner new days | Not measured today | Highest; required for temporal validation | Future bounded replay bandwidth | Moderate | Best next step for generalization |

## SELECTED STRATEGY

Select **A + B** for today: repair the recoverable archives, then use explicit
token/horizon masks instead of day-level invalidation. Select **C** as the next
experiment because one repaired day cannot meet temporal stability or the
multi-day outcome gate.

## NEW DATA ACQUIRED

Five free official PumpApi archive replays were streamed and filtered. The
durable local product is the ignored 36 MB canonical Parquet above; raw
compressed/decompressed archives were not stored. No trading, wallet, signing,
purchase, subscription, or live-action change occurred.

## VALID DECISION-TIME ROWS

Event-backed decision snapshots: 1m=1,000; 3m=1,000; 5m=1,000; 10m=1,000.
These are eligibility counts, not independent observations. The maximum
paired 60m Burst set is 652 rows before any feature-quality or duplicate-
transaction exclusions.

## STATISTICAL RESEARCH RUN

Only a deterministic coverage and descriptive-return sanity pass was run. Among
resolved marks, uncosted launch-to-mark medians were -8.07% (15m), -11.92%
(30m), and -11.96% (60m); means were dominated by extreme outliers. This is a
coverage diagnostic, not a strategy test, and does not support an edge claim.

## A/B/C/D STATUS

| Model | Status |
|---|---|
| A — token state | NOT RUN; no frozen multi-day feature matrix and below 5,000 paired rows |
| B — token + participant | NOT RUN; point-in-time participant history is immature and self-flow remains contaminated |
| C — token + precursor | NOT RUN; no valid multi-day feature matrix; the recovered day is preliminary |
| D — token + participant + precursor | NOT RUN; both participant and sample-quality gates unmet |

## TEMPORAL COVERAGE

Usable calendar days: **1**. The recovered 2026-08-28 panel is complete for
the selected archive-hour interval, but it does not create a second independent
day. Chronological development/validation segmentation remains unavailable.

## SCIENTIFIC CONCLUSION

The previous premise that all 24 hours had to be complete before any short-
horizon research was usable is falsified. The actual root cause was a
recoverable provider replay/checkpoint failure compounded by a worktree-local
artifact discovery gap, plus an all-or-nothing day-level completeness contract.

The outcome-coverage blocker is materially reduced for Burst on this day, but
not eliminated for Runner or multiday inference. Classification: **PRELIMINARY
DATA COVERAGE RECOVERY / INSUFFICIENT DATA FOR EDGE VALIDATION**.

## REMAINING BLOCKER

At least several independent days with complete short-horizon marks, at least
5,000 valid paired decision-time rows if available, and verified PumpSwap
continuations for Runner are still missing. Participant reputation also remains
immature and raw participant-related flow must remain participant-excluded for
exogenous-demand analyses.

## NEXT HIGHEST-INFORMATION EXPERIMENT

Acquire the next three clean historical days with the repaired streaming
checkpoint/manifest and the same outcome-independent 1,000-mint daily sample.
Build token-level 15m/30m/60m masks first; run A vs C only when the resulting
chronological dataset clears the five-day/preliminary and paired-row quality
gates. This is exactly one bounded `quant` continuation task; no Dune query is
needed unless the replay path fails again.
