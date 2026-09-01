STAGE-1 SURVIVAL MATERIAL PROGRESS

# NAVE Stage-1 survival, Day 3, and acquisition scale — 2026-09-01

## EXECUTIVE STATUS

The main blocker was materially reduced. 2026-08-29 is now the second
provider-complete event-level day for a frozen 1,000-launch sample. The new
Stage-1 contract makes continued activity a post-horizon outcome and keeps
right censoring, provider gaps, and migration without continuation separate.
The first chronological A_survival versus C_survival sanity comparison was
run at one 10-minute decision row per token. C did not replicate its small
Day-2 development improvement on Day 3; this is preliminary and not an edge
claim.

## CURRENT BASELINE

- 2026-08-28: 1,000 sampled launches, 254,522 normalized PumpApi rows, 24/24
  archive hours, 30 sampled migrations.
- 2026-08-29: 1,000 sampled launches, 353,030 normalized rows, 24/24 archive
  hours, 22 sampled migrations. The 1,023 observed mints include the 30 Day-2
  migrant mints retained in the shared filter union; the general sample itself
  remains exactly 1,000.
- 2026-08-27 remains a compact Dune descriptive day and is not in the
  point-in-time A/C matrix.

## DAY-3 PREDECLARATION

2026-08-29 was fixed before inspecting Day-3 outcomes. The sample came from a
39,415-launch complete denominator using `sha256('nave-2026-08-29-v1:' || mint)`
ascending, first 1,000 unique mints. Selection did not use volume, survival,
migration, or returns. The predeclared continuation sequence remains
2026-08-30 then 2026-08-31.

## ACQUISITION PERFORMANCE PROFILE

The previous serial attempt processed only 6/72 archives in approximately
eight minutes and retained no promoted panel. The new path first recovered a
compact Dune launch/sample manifest, then used a single 1,030-mint filter union
(1,000 Day-3 sample plus 30 Day-2 migrants). The mint projection rejected
unrelated lines before full JSON normalization.

For Day 3, 58,187,058 input JSONL records were streamed, 353,030 were retained,
and 11,847,142,071 compressed bytes were downloaded. Hour wall time had a
median of 58.4 seconds and a maximum of 92.1 seconds; aggregate hour work was
1,301 seconds. A bounded three-worker phase completed 20 hours, while four
transport-reset hours were retried individually and completed. The full day
was therefore operationally repeatable within a bounded task window, with
retry/resume still required.

## OPTIMIZATION

The worker streams HTTP → zstd → projected JSONL → normalized JSONL. The
projection uses the mint field before `json.loads` for unrelated records; no
decompressed archive is retained. Checkpoints distinguish `COMPLETE`,
`COMPLETE_WITH_WARNINGS`, `FAILED`, and partial state. Valid output is not
discarded solely because a pipeline warning occurs. A 3-worker ceiling is
enforced; this is bounded parallelism, not a daemon or loop.

## DAY-3 COVERAGE

| Day | denominator | sample | event rows | observed mints | archive hours | provider gaps |
|---|---:|---:|---:|---:|---:|---:|
| 2026-08-28 | 48,330 | 1,000 | 254,522 | 1,000 | 24/24 | 0 |
| 2026-08-29 | 39,415 | 1,000 | 353,030 | 1,023 incl. migrant union | 24/24 | 0 |

For the frozen Stage-1 10-minute decision rows, the primary post-horizon
five-minute label counts are:

| Day | horizon | positive | negative | right-censored | migration unknown | provider gap | binary base rate |
|---|---|---:|---:|---:|---:|---:|---:|
| 2026-08-28 | 15m | 70 | 893 | 11 | 26 | 0 | 7.27% |
| 2026-08-28 | 30m | 35 | 918 | 19 | 28 | 0 | 3.67% |
| 2026-08-28 | 60m | 20 | 911 | 41 | 28 | 0 | 2.15% |
| 2026-08-29 | 15m | 96 | 878 | 7 | 19 | 0 | 9.86% |
| 2026-08-29 | 30m | 52 | 901 | 29 | 18 | 0 | 5.46% |
| 2026-08-29 | 60m | 29 | 892 | 60 | 19 | 0 | 3.15% |

## STAGE-1 OUTCOME CONTRACT

The frozen contract is `nave-stage1-survival-contract-20260901.json`. The
primary labels are `FUTURE_TRADE_AFTER_15M`, `_30M`, and `_60M`: at least one
valid BUY or SELL strictly after the horizon and through the next fixed five
minutes. The outcome interval begins strictly after every allowed decision
time. A complete interval with no trade is a negative activity outcome; a
provider gap is not inactivity; a migration without validated PumpSwap
continuation is `MIGRATION_UNKNOWN`; an interval beyond the collection end is
`RIGHT_CENSORED`. No price tolerance was changed.

## DAY-2 SURVIVAL BASE RATES

At the 10-minute decision, continuation-window base rates were 7.27% at 15m,
3.67% at 30m, and 2.15% at 60m. These are activity/survival rates, not return
rates. Day 2 is development/exploratory data.

## DAY-3 SURVIVAL BASE RATES

At the same decision point, Day 3 rates were 9.86%, 5.46%, and 3.15%. The
direction is compatible with Day 2, but two calendar days are not enough to
call the rate stable across regimes.

## OBSERVABILITY BIAS

The exact-mark selection problem remains real. In the new fixed diagnostic
window, Day-3 mark-observed tokens had a median of 422 early trades versus 14
for non-observed tokens and 77.5 versus 3 early buyers. The canonical Day-2
audit likewise found resolved 60m marks concentrated in active launches. Thus
mark-return analysis is conditional on market activity. The Stage-1 activity
label avoids converting the inactive majority into missing data or losses.

## A_SURVIVAL FEATURES

The baseline uses the frozen token-state family: age, pre-decision log return
when available, curve reserve state, raw buy/sell quote volume, raw trade
count, unique buyers, and migration state known by decision time. The replay
does not provide a mature point-in-time participant reputation table, so
participant-excluded flow is not claimed; raw and participant-contaminated
status remains explicit.

## C_SURVIVAL FEATURES

C adds only preregistered dynamic summaries available by the decision:
new-buyer acceleration, buy-volume acceleration, sell pressure, and trade-size
concentration. No event after the decision time was used. B/D participant
models were deferred.

## A_SURVIVAL VS C_SURVIVAL

A logistic baseline was fit on Day 2 and evaluated unchanged on Day 3 for the
60m continuation label. Day 2 had 931 eligible rows and Day 3 had 921; each is
one 10m row per token, avoiding fourfold pseudoreplication. A transferred to
Day 3 with PR-AUC 0.322, top-20% precision lift 3.45x, Brier 0.0256, and log
loss 0.1086. C transferred with PR-AUC 0.259, lift 2.93x, Brier 0.0270, and
log loss 0.1254. C minus A PR-AUC was -0.0633 and Brier change was +0.00136.

The 1,000-token bootstrap estimated PR-AUC delta -0.0569 with 95% interval
[-0.1219, 0.0034]. The result is `NO INCREMENTAL SURVIVAL INFORMATION` for
this preliminary temporal sanity check, subject to the limitations below;
the interval overlaps zero and no final conclusion is claimed.

## TEMPORAL REPLICATION

The Day-2 development improvement for C did not replicate on Day 3. This is a
two-day preliminary replication, not final temporal validation. More frozen
calendar days are needed before classifying the mechanism as temporally
unstable or regime-dependent.

## RUNNER ACTIVITY CONTINUATION

The sampled Day-2 migrant tape was carried into the Day-3 replay. In an exact
five-minute post-target activity diagnostic, Day-2 migrants were active for
7/30 at +4h, 6/30 at +8h, 1/30 at +12h, and 2/30 at +24h; +48h and +72h remain
right-censored. Day-3 sampled migrants were 6/20 at +4h, 3/12 at +8h, and
2/9 at +12h among eligible tokens; 24h+ are right-censored. These are
activity observations, not executable profit or liquidity evidence. The
current sampled migrant count tracked is 52 (30 Day 2 plus 22 Day 3); this is
not yet the all-migrant universe.

## RESOURCE USAGE

Free disk moved from 44 GB to 43 GB, remaining above the approximately 15 GB
guard. Available memory remained about 5.9 GB. Retained Day-3 Parquet is
approximately 49.5 MB; hourly normalized JSONL checkpoints total about 398 MB
and raw decompressed archives were not kept. The 11.85 GB compressed stream is
estimated at roughly 35.5 GB decompressed using a conservative 3x expansion
estimate; the estimate is not materialized storage.

## DUNE USAGE

Fresh usage is 2,026.106 / 2,500 included credits, leaving 473.894. New Dune
usage during this session is approximately 2.002 credits, from the bounded
Day-3 launch/sample manifest query; no event-history query or purchase was
made. The completed execution was recovered locally and will not be rerun.

## 5–7 DAY SCALE READINESS

`FAST_ENOUGH_FOR_AUTONOMOUS_SCALE`, with limitations: the targeted stream is
bounded and resumable, all 24 Day-3 hours are complete, and the sample is
frozen before event replay. Transport resets occurred under concurrency, so
the next quant continuation must retain retries, individual-hour checkpoint
validation, and the 3-worker ceiling. Scale should proceed one predeclared day
at a time, not as an unbounded batch.

## ABI/QUANT CONTINUATION

The canonical state and this report are being committed before one and only
one new quant continuation task is created. The task will extend the same
frozen Stage-1 panel through 2026-08-30 and 2026-08-31, validating each day
before materializing the next child. No scanner, alert, trading, wallet, or
capital behavior changes.

## SCIENTIFIC CONCLUSION

The first rigorous Stage-1 layer is now possible. Most short-horizon missing
marks are economically sparse activity rather than generic provider missingness,
and resolved-mark return research is strongly activity-selected. A strong
token-state baseline transfers better than the tested precursor extension on
the first chronological sanity day. This is preliminary survival evidence,
not an edge, return, or execution claim.

## NEXT EXPERIMENT

Acquire and validate the next predeclared event-level day, 2026-08-30, using
the targeted launch-manifest/filter-union replay. After the 5–7 day checkpoint,
reassess Stage-1 stability, conditional Stage-2 mark research, participant
history, and Runner all-migrant continuation.
