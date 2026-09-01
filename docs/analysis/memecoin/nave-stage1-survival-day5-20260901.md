STAGE-1 SURVIVAL MATERIAL PROGRESS

# NAVE Stage-1 survival, Day 5 — 2026-09-01

## EXECUTIVE STATUS

FACT: 2026-08-31 is the fourth provider-complete event-level day for a frozen 1,000-launch sample. The sample was selected before replay by ascending SHA-256 ordering from a 37,540-launch denominator. All 24 PumpApi hourly archives completed with bounded three-worker streaming; no raw decompressed archive was retained.

FACT: The frozen post-horizon activity labels were computed at the 10-minute decision for 15m, 30m, and 60m. Provider gaps remain zero; migration-unknown and right-censored statuses remain explicit.

FACT: The unchanged Day-2-trained A_survival/C_survival comparison was evaluated on Day 5 without tuning. C underperformed A on PR-AUC and Brier on this day; the token-cluster bootstrap interval crosses zero.

CLASSIFICATION: WEAK / UNSTABLE SIGNAL for the frozen A/C research comparison on this day; INSUFFICIENT DATA / BLOCKED BY OUTCOME COVERAGE for any strategy or edge claim. EDGE_VALIDATED remains false.

## EVIDENCE AND PREDECLARATION

- Date: 2026-08-31 UTC.
- Denominator: 37,540 unique launch mints.
- Sample: first 1,000 unique mints after ascending sha256('nave-2026-08-31-v1:' || mint) ordering.
- Selection was frozen before event replay and did not use survival, migration, volume, returns, or later outcomes.
- Dune inline launch/sample execution completed with 1,000 rows and 24,000 datapoints; no rerun or purchase occurred.
- Replay filter union: 1,034 mints (1,000 general sample plus 34 prior-day migrant mints).

## ACQUISITION AND INTEGRITY

The canonical root was /home/david/nave/data. The targeted stream used HTTP -> zstd -> projected JSONL -> normalized JSONL, with a maximum of three concurrent workers and resumable hourly checkpoints. The final materialization contains 555,201 normalized rows and 1,027 observed mints across 24/24 archive hours. Combined Parquet SHA-256:  e7233b7ead392ed90bf51d9e3ed471d2d70b0377b5cc33b755d310935a6c6847. Raw decompressed archives were not retained.

Acquisition manifest: docs/analysis/memecoin/nave-stage1-day5-acquisition-manifest-20260901.json.

## FROZEN SURVIVAL OUTCOMES

| UTC day | denominator | sample | normalized rows | archive hours | provider gaps |
|---|---:|---:|---:|---:|---:|
| 2026-08-28 | 48,330 | 1,000 | 254,522 | 24/24 | 0 |
| 2026-08-29 | 39,415 | 1,000 | 353,030 | 24/24 | 0 |
| 2026-08-30 | 36,161 | 1,000 | 294,446 | 24/24 | 0 |
| 2026-08-31 | 37,540 | 1,000 | 555,201 | 24/24 | 0 |

Primary label is at least one valid BUY or SELL strictly in (launch_time + horizon, launch_time + horizon + 5m]. Negative requires a complete interval with no qualifying trade. Provider gaps are not inactivity; migration without validated continuation is MIGRATION_UNKNOWN; intervals beyond collection end are RIGHT_CENSORED.

| Day | horizon | positive | negative | right-censored | migration unknown | provider gap | binary base rate |
|---|---|---:|---:|---:|---:|---:|---:|
| 2026-08-31 | 15m | 86 | 872 | 21 | 21 | 0 | 8.98% |
| 2026-08-31 | 30m | 51 | 897 | 31 | 21 | 0 | 5.38% |
| 2026-08-31 | 60m | 22 | 894 | 63 | 21 | 0 | 2.40% |

## OBSERVABILITY DIAGNOSTICS

FACT: At the 10-minute decision, Day-5 60m mark-observed tokens numbered 49 and non-observed tokens 951. Median early trades were 229 versus 9; median early buyers were 62 versus 3.

INFERENCE: Exact-mark observability remains strongly activity-selected. The activity/survival layer remains the defensible primary outcome; no mark-return or executable-liquidity conclusion follows.

## FROZEN A_SURVIVAL VS C_SURVIVAL

The model was fit on Day 2 (2026-08-28), kept unchanged, and evaluated on Day 5 (2026-08-31) at the 60m label using one 10m row per token. Day 5 had 916 eligible rows and 22 positives.

| model | PR-AUC | top-20% precision lift | Brier | log loss |
|---|---:|---:|---:|---:|
| A_survival | 0.2464 | 2.9578x | 0.02051 | 0.09172 |
| C_survival | 0.2220 | 2.7303x | 0.02136 | 0.11623 |
| C minus A | -0.0244 | — | +0.00085 | +0.02451 |

The 1,000-iteration token-cluster bootstrap estimated PR-AUC delta -0.0337 with 95% interval [-0.1282, +0.0511]. Brier delta was +0.00088 with 95% interval [-0.00054, +0.00279]. Both intervals cross zero. This is not evidence of profitability, execution quality, or a live filter.

Prior frozen transfers were C minus A PR-AUC -0.0633 on Day 3 and +0.0400 on Day 4. Across four comparable days, temporal stability is UNKNOWN and the direction is consistent with TEMPORALLY UNSTABLE / REGIME-DEPENDENT behavior rather than validated incremental information.

## RUNNER AND PARTICIPANT STATUS

Participant B/D models remain deferred: point-in-time history is not mature and raw flow remains SELF-FLOW CONTAMINATED. Runner continuation is descriptive only and does not establish success, profit, or executable exit evidence. Any unavailable continuation remains MIGRATION_UNKNOWN or RIGHT_CENSORED rather than inactivity.

## RESOURCE AND PROVIDER STATUS

Fresh Dune usage before the launch query was 2,027.345 / 2,500 included credits, leaving 472.655. The bounded launch query completed under the 5-credit preflight estimate; exact incremental credits are UNKNOWN in retained execution metadata. PumpApi used bounded historical replay and retained only projected event rows. Disk remained above the configured guard. No purchase, subscription, wallet, signing, trade, scanner, alert, or deployment action occurred.

## SKEPTICAL INTERPRETATION

The strongest invalidation is temporal instability: C direction changed across the three unchanged temporal transfers, and Day 5 again favored A. The target is observable activity rather than return. Exact marks remain selected by activity, Day-5 has only 22 positive 60m labels and 63 right-censored rows, raw participant flow is not exogenous, and all-migrant Runner coverage remains incomplete.

Conclusion: WEAK / UNSTABLE SIGNAL for this non-operational A/C comparison; NO EDGE VALIDATED. Valid next state is NEXT_BOUNDED_EXPERIMENT, not WATCH, ENTER, BUY, or SELL.

## NEXT STEP

One additional predeclared event-level day remains information-positive before the 5–7-day checkpoint: 2026-09-01 UTC, subject to fresh resource preflight and the same frozen contract. Do not tune C after this result. Reassess only after at least five comparable days with per-day clustered uncertainty and outcome coverage review.
