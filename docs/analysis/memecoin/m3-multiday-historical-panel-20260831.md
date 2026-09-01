MULTI-DAY PANEL PARTIALLY VALIDATED

# NAVE M3 multi-day historical research panel

This status refers to the historical-data acquisition gates only. It does not mean an edge or executable result was validated. NAVE remains read-only, research-only, and human-gated.

## EXECUTIVE RESULT

The paid Day-2 Dune event result was recovered locally rather than rerun. PumpApi Historical Replay then passed a bounded one-hour semantic agreement audit and a resumable one-day acquisition completed for the same 1,000-mint sample. Five decompression-integrity failures were isolated as missing hours rather than imputed.

The evidence supports `PUMPAPI_VALID_WITH_LIMITATIONS` for early-event acquisition. It does not yet support a three-day or fourteen-day panel: the minimum statistical quality gate requires eight usable days, 5,000 valid decision-time rows, and non-dominant provider coverage.

## DAY-2 SALVAGE

The prior report’s `event_panel_rows = 0` classification was corrected by forensic inspection of the already-paid local Dune response. The Day-2 denominator has 48,330 launches; the deterministic sample has 1,000 mints; the recovered first-hour response contains 82,804 rows and 6,641 rows in the audited 21:00 UTC overlap. No equivalent Dune query was rerun.

Classification: `DAY2_PARTIALLY_RECOVERED`. Denominator and first-hour selected events are available; the recovered Dune execution does not provide the complete multi-day continuation panel.

## DUNE USAGE

The current Dune usage check reports 2,024.104 credits consumed of 2,500 included, leaving 475.896 included credits. New Dune query credits used by this continuation are 0. The previous broad extraction overage remains historical sunk cost; this worktree made no new raw-event Dune request.

## PUMPAPI CURRENT STATUS

Official [Historical Replay documentation](https://pumpapi.io/historical-replay), [FAQ](https://pumpapi.io/FAQ), and [fees](https://pumpapi.io/fees) were checked for archive URL, free historical access, archive start date, JSONL/zstd format, `localTimestamp`, schema aliases, and supported venues. Trade API, wallet, signing, and execution functionality were not used. The external [replayer repository](https://github.com/Solana-Trading-Lab/replayer-rust) was inspected for methodology; it had no clear license in the inspected repository, so no source was copied or vendored.

## PUMPAPI BANDWIDTH MODEL

The representative 2026-08-28 21:00 UTC archive was 608,173,816 compressed bytes. Streaming produced 3,949,203,772 decompressed bytes and 3,042,273 events. The optimized parser used 19,584 kB peak RSS, took 97.54 seconds, and retained 12,032 selected-mint events (~14.2 MB JSONL). Raw decompressed data was not persisted. Linear planning estimates are documented in `pumpapi-acquisition-cost-model-20260831.md`; 14 days are approximately 188.8 GB compressed and 9.5 CPU hours before network variability.

## DUNE VS PUMPAPI AGREEMENT / ONE-HOUR PROOF

In the 6,641-row overlap, transaction signatures matched 6,641/6,641 and mints matched 6,641/6,641. Economic-wallet matches were 6,634/6,641 after using singular `breakdown[].trader`; seven multi-trader events remain explicitly ambiguous. Side semantics matched 6,637/6,641. The four discrepancies are a small but systematic side inversion for one mint and remain flagged for semantic review; they are not attributed to CREATE. Separately, 67 CREATE events are represented by Dune as initial buys, a known lifecycle representation difference. Quote amounts matched within tolerance on 6,631 rows; real quote reserves on 6,634; real token reserves on 6,637. The seven token-amount unknowns are CREATE events, not silently imputed.

Event-time differences had median 985 ms, p95 1,466 ms, and maximum 2,168 ms. `localTimestamp` remains separate from event time and is used as provider availability evidence. The agreement result is `PUMPAPI_VALID_WITH_LIMITATIONS`, not a claim that either source is infallible.

## ONE-DAY PROOF

The 2026-08-28 run uses the same deterministic 1,000-mint selection and streams each hourly archive through zstd into normalized compact event files. Each hour has a checkpoint and metrics file. Hours 01, 06, 11, 13, and 17 returned nonzero decompressor status after producing partial output; they remain `FAILED`, and the verified day is classified partial. No future event history is filled across the gaps. The 19 verified hours contain 211,350 selected events, 855 mints, 29,540 wallets, 807 CREATE events, 132,809 BUY events, 77,710 SELL events, and 24 MIGRATE events.

## THREE-DAY PILOT

Not started. A third day requires a deterministic denominator/sample manifest that is not locally present. A new broad Dune denominator query is not justified under the credit-protection rule. PumpApi-only CREATE discovery would require an additional full-day pass and is deferred until the one-day gate is complete.

## FOURTEEN-DAY PANEL

Not started. The target window remains 2026-08-15 through 2026-08-28 UTC, subject to archive availability, maturity, and protocol-regime review. The measured cost model makes a 14-day replay operationally possible only as resumable stream processing, but not yet justified before the one-day integrity and schema gate passes.

## DATA QUALITY BY DAY

| Date | Launch denominator | Sampled | Event coverage | Early participants | Migrated | Runner coverage | Quality |
|---|---:|---:|---|---:|---:|---|---|
| 2026-08-27 | 53,956 | 1,000 | Existing Dune first-hour artifact: 2,367 rows | Existing targeted machinery | 7 targeted | 4h/24h partial, 72h unavailable | COMPLETE RETAINED ARTIFACT |
| 2026-08-28 | 48,330 | 1,000 | 211,350 events / 19 of 24 hours verified / 855 mints | 28,093 wallet-mint first entries through 10m | 24 observed in selected sample | Not acquired | PARTIAL; hours 01, 06, 11, 13, 17 failed integrity |

The full per-hour checkpoint and metrics state is local and excluded from git. Missing launch time, wallet, side, amount, duplicates, and censoring remain explicit quality fields; the pipeline does not turn missingness into failure.

The compact dataset manifest, including hashes and known gaps, is `m3-multiday-data-manifest-20260831.json`.

## LAUNCH SAMPLE COVERAGE

The Day-1 and Day-2 sample manifests use the existing SHA-256 outcome-independent methodology. Day-2 selection is the prior deterministic 1,000-mint manifest, recovered locally. No survivor, winner, migration, or volume filter was introduced.

## PARTICIPANT COVERAGE / HISTORY MATURITY

Existing Day-1 targeted artifacts contain 1,786 wallet-token episodes and 1,666 wallets; the prior early-episode artifact contains 1,508 rows. Day-2 verified events produce 9,785 / 13,783 / 22,410 / 28,093 first wallet-mint entries by 30s / 60s / 5m / 10m. New Day-2 participant episodes are not promoted to mature reputation until point-in-time outcome joins are materialized; mature Day-2 reputation histories: 0. No wallet is called smart money. Beta-Binomial reputation remains the required shrinkage method, with matured cutoffs, intervals, sample size, and top-winner dependence.

## ALL-MIGRANT COVERAGE / RUNNER COVERAGE

The general 1,000/day sample and all-migrants Runner universe remain separate by design. The current acquisition does not yet provide complete post-migration continuation for Day 2. Runner outcomes at 24h and 72h are therefore `BLOCKED BY OUTCOME COVERAGE`; graduation is not treated as Runner success. Helius is not required now, though later account-level depth, failed exits, confirmed bundles, funding chains, or BOOST attribution could justify targeted validation.

## PROTOCOL REGIMES

Mayhem and cashback fields are preserved where PumpApi exposes them. BOOST remains UNKNOWN. No mechanical/protocol-generated flow is promoted to organic demand. A full 14-day regime segmentation is deferred until the daily panel exists.

## SOURCE CAPABILITY MATRIX

See `source-capability-matrix-20260831.md`. The current recommended architecture is hybrid: Dune for compact denominators, migration maps, and targeted PumpSwap continuation; PumpApi Historical Replay for streamed early events; local Parquet/DuckDB for interpretation.

## A/B/C/D READINESS AND STATISTICAL RESULTS

Not run. The quality gate is not met: fewer than eight usable calendar days and no frozen multi-day decision-time matrix. Models A–D must not be fit from this partial panel. The prior statistical sanity result remains `STATISTICAL SIGNAL SANITY INCONCLUSIVE` because its Day-2 acquisition failed; this iteration does not reinterpret that as a negative hypothesis result.

## TEMPORAL STABILITY / DAY-LEVEL EFFECTS

Not estimable. Two calendar-day artifacts are not a final holdout, and the new Day-2 event panel has an isolated provider gap. Chronological development/validation/holdout splits, horizon-aware purging, leave-day-out diagnostics, and top-day dependence remain pending the multi-day quality gate.

## PRFS STATUS

`BLOCKED BY HISTORICAL GATE LOGGING`. Repository search found reusable offline post-rejection primitives but no trustworthy historical PASS/REJECT gate journal with candidate state, reason, timestamp, and future observation. No historical false-negative rates were fabricated. The required passive future contract is documented in the prior research primitives and remains offline-only.

## PUMPAPI AUDIT STATUS

Useful with limitations for early events. The one-hour audit is reproducible from local compact output and shows high signature/mint agreement. The source is not yet validated for PumpSwap continuation, full historical participant warm-up, or failed transactions. One malformed/decompression-failed hour demonstrates why resumable quality flags are mandatory.

## HELIUS DECISION

`USEFUL_LATER_NOT_REQUIRED_NOW`. The present blocker is panel acquisition, not an absent Helius field. Helius should be considered only for a specific later validation gap: account-level PumpSwap depth/reserves, failed exit evidence, funding chains, confirmed bundle evidence, or BOOST attribution.

## FINAL QUESTIONS

1. Token-only state contains useful descriptive Day-1 information, but no multi-day statistical claim is supported.
2. Participant improvement over token-only state: not tested; insufficient temporal coverage.
3. Precursor improvement over token-only state: not tested; insufficient temporal coverage.
4. Participant identity after precursor features: not tested.
5. Naive participant self-flow signal: prior targeted audit found 1,107/2,367 trades (46.8%) attributable to selected participant wallets; classify `SELF-FLOW CONTAMINATED` until exogenous variants are tested.
6. Signal direction from Day 1 to Day 2: not estimable.
7. One-wallet/one-token dependence: prior return proxies are heavy-tailed; top-1/top-5 dependence remains visible, and no model result exists.
8. Participant reputation maturity: existing shrinkage machinery is mature; multi-day histories are not yet statistically mature for this panel.
9. Runner research: blocked by continuation coverage.
10. PumpApi: worth using as the next raw early-event audit/source, with limitations and checkpoints.
11. Helius: not needed now; useful later for specific validation gaps.
12. Highest-information next experiment: finish and verify one complete day, then run a bounded 3-day PumpApi panel with frozen denominators/sample manifests before any 14-day scale-up or A/B/C/D fitting.
