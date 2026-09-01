STAGE-1 SURVIVAL MATERIAL PROGRESS

# NAVE Stage-1 survival, Day 4, and acquisition scale — 2026-09-01

## EXECUTIVE STATUS

FACT: 2026-08-30 is the third provider-complete event-level day for a frozen 1,000-launch sample. The sample was selected before replay by the declared SHA-256 rule from a 36,161-launch denominator. All 24 hourly archives completed after bounded resumable retries; no raw decompressed archive was retained.

FACT: Frozen post-horizon activity labels were computed at the 10-minute decision for 15m, 30m, and 60m. Provider gaps remain zero; migration unknown and right censoring remain explicit.

FACT: The unchanged Day-2-trained A_survival/C_survival comparison was evaluated on Day 4 without tuning. C was directionally better than A on this day, but its bootstrap interval includes zero. This is preliminary temporal evidence, not a validated signal or return claim.

INFERENCE: The additional day reduces calendar-day uncertainty and supports continuing one predeclared day at a time. It does not establish temporal stability or economic usefulness.

CLASSIFICATION: PROMISING EXPLORATORY SIGNAL for the frozen A/C temporal comparison only; INSUFFICIENT DATA / BLOCKED BY OUTCOME COVERAGE for any strategy or edge claim.

## EVIDENCE AND PREDECLARATION

- Date: 2026-08-30 UTC.
- Denominator: 36,161 unique launch mints.
- Sample: first 1,000 unique mints after ascending sha256('nave-2026-08-30-v1:' || mint) ordering.
- Selection was frozen before event replay and did not use survival, migration, volume, returns, or later outcomes.
- Dune execution recovered: 01M1F6WVV7889ZWQAWS9Z1PSCC. It returned exactly 1,000 rows and 23,000 datapoints; no rerun was made.
- Event replay filter union: 1,022 mints (1,000 general sample plus 22 verified Day-3 migrant mints).

## ACQUISITION AND INTEGRITY

The canonical root was /home/david/nave/data. The targeted stream used HTTP -> zstd -> projected JSONL -> normalized JSONL, with a maximum of three concurrent workers and resumable hourly checkpoints. Two transport-reset hours were retried individually and completed. The final materialization contains 294,446 normalized rows and 1,014 observed mints across 24/24 archive hours. The combined Parquet SHA-256 is 9767abcd975f608ad969c4eda5ea25d00fb1148c231825e979520b97f22ff5ee. Raw decompressed archives were not retained.

Acquisition manifest: docs/analysis/memecoin/nave-stage1-day4-acquisition-manifest-20260901.json.

## FROZEN SURVIVAL OUTCOMES

| UTC day | denominator | sample | normalized rows | archive hours | provider gaps |
|---|---:|---:|---:|---:|---:|
| 2026-08-28 | 48,330 | 1,000 | 254,522 | 24/24 | 0 |
| 2026-08-29 | 39,415 | 1,000 | 353,030 | 24/24 | 0 |
| 2026-08-30 | 36,161 | 1,000 | 294,446 | 24/24 | 0 |

Primary label: at least one valid BUY or SELL strictly in (launch_time + horizon, launch_time + horizon + 5m]. Negative requires a complete interval with no qualifying trade. A provider gap is not inactivity; migration without validated continuation is MIGRATION_UNKNOWN; intervals beyond collection end are RIGHT_CENSORED.

| Day | horizon | positive | negative | right-censored | migration unknown | provider gap | binary base rate |
|---|---|---:|---:|---:|---:|---:|---:|
| 2026-08-28 | 15m | 70 | 893 | 11 | 26 | 0 | 7.27% |
| 2026-08-28 | 30m | 35 | 918 | 19 | 28 | 0 | 3.67% |
| 2026-08-28 | 60m | 20 | 911 | 41 | 28 | 0 | 2.15% |
| 2026-08-29 | 15m | 96 | 878 | 7 | 19 | 0 | 9.86% |
| 2026-08-29 | 30m | 52 | 901 | 29 | 18 | 0 | 5.46% |
| 2026-08-29 | 60m | 29 | 892 | 60 | 19 | 0 | 3.15% |
| 2026-08-30 | 15m | 60 | 894 | 17 | 29 | 0 | 6.29% |
| 2026-08-30 | 30m | 42 | 896 | 32 | 30 | 0 | 4.48% |
| 2026-08-30 | 60m | 16 | 902 | 51 | 31 | 0 | 1.74% |

## OBSERVABILITY DIAGNOSTICS

FACT: At the 10-minute decision, Day-4 60m mark-observed tokens numbered 47 and non-observed tokens 953. Median early trades were 339 versus 9; median early buyers were 87 versus 3. As on prior days, exact-mark observability is strongly activity-selected.

INFERENCE: Mark-return analysis remains conditional on observable activity. The activity/survival layer is the defensible primary outcome for this iteration; no mark-return or executable-liquidity conclusion follows.

## A_SURVIVAL VS C_SURVIVAL — FROZEN TEMPORAL CHECK

The model was fit on Day 2 (2026-08-28), kept unchanged, and evaluated on Day 4 (2026-08-30) at the 60m label using one 10m row per token. Day 4 had 918 eligible rows and 16 positives.

| model | PR-AUC | top-20% precision lift | Brier | log loss |
|---|---:|---:|---:|---:|
| A_survival | 0.2423 | 2.8217x | 0.01629 | 0.07279 |
| C_survival | 0.2824 | 3.1352x | 0.01536 | 0.07085 |
| C minus A | +0.0400 | — | -0.00093 | -0.00194 |

The token-cluster bootstrap (1,000 iterations, same seed and one 10m row per token) estimated PR-AUC delta +0.0322 with 95% interval [-0.0212, +0.1078]. Brier delta was -0.000923 with 95% interval [-0.00226, +0.00010]. The interval crosses zero, so the result is exploratory and does not validate incremental information. It is not evidence of profitability, execution quality, or a live filter.

Prior Day-3 transfer had C minus A PR-AUC -0.0633; Day-4 direction differs. With only three comparable days, temporal stability remains UNKNOWN and may be REGIME_DEPENDENT.

## RUNNER AND PARTICIPANT STATUS

Participant B/D models remain deferred: point-in-time history is not mature and raw flow is SELF-FLOW CONTAMINATED. Day-4 migration continuation is not promoted to an all-migrant Runner result; any unavailable continuation remains MIGRATION_UNKNOWN or RIGHT_CENSORED rather than inactivity. Runner activity is descriptive only and never success, profit, or executable exit evidence.

## RESOURCE AND PROVIDER STATUS

FACT: Fresh Dune usage before the manifest query was 2,026.106 / 2,500 credits, leaving 473.894. The bounded launch query was completed and its 1,000-row result was recovered; no paid resource was purchased. The prior human checkpoint remains the governing limit. PumpApi replay used bounded free historical streams and retained only projected event rows. Disk availability was approximately 42.86 GiB before replay and remained above the guard threshold.

UNKNOWN: Exact incremental Dune credits for this execution are not available in the retained execution metadata; this is recorded as unknown rather than manufactured.

## SKEPTICAL INTERPRETATION

The strongest invalidation is calendar-day dependence: base rates changed across days and C improved on Day 4 after underperforming A on Day 3. The outcome is observable activity, not a return, and exact marks remain selected by activity. The 16-positive Day-4 60m sample makes uncertainty material. The Dune launch sample is compact and provider-derived; event outcomes depend on the PumpApi tape. No participant-excluded model, all-migrant Runner panel, or conditional economic outcome has been demonstrated.

Conclusion: PROMISING EXPLORATORY SIGNAL for a non-operational A/C research comparison; NO EDGE VALIDATED. Valid next state is NEXT_BOUNDED_EXPERIMENT, not WATCH, ENTER, BUY, or SELL.

## NEXT STEP

Acquire and validate exactly one additional predeclared event-level day, 2026-08-31, under the same frozen contract and bounded replay. Reassess only after 5–7 comparable days; do not tune thresholds or promote the result to an operational scanner, alert, watch, or trade.
