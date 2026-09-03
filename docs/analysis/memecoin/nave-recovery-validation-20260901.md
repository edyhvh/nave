# NAVE bounded recovery and validation gate

Date: 2026-09-01T02:57:31Z (UTC)
Scope: one local, read-only historical acquisition verification.
Mode: READ_ONLY_RESEARCH_ONLY_HUMAN_GATED.
Classification: BLOCKED BY OUTCOME COVERAGE / INSUFFICIENT DATA.

## Hypothesis

HYPOTHESIS: recovering the already-paid Day-2 result and verifying the existing replay-quality evidence can reduce uncertainty about whether a chronological multi-day panel is ready. This is not a hypothesis that any feature predicts returns.

## Evidence (FACT)

- The canonical state records `NO EDGE VALIDATED`, one usable day, incomplete Day-2 continuation, immature multi-day participant histories, and a blocker of incomplete multi-day outcome coverage.
- The referenced report paths in the canonical state are absent from this checkout, but the referenced acquisition commit `39e909809f85d998c7d6cbd06ff1bef93c18bc31` is present and its report, manifest, and compact panel JSON are recoverable with `git show`. This is repository evidence of a retained artifact, not a fresh provider call.
- The recovered compact panel reports Day 2 as `DAY2_PARTIALLY_RECOVERED`: 48,330 launches, a deterministic 1,000-mint sample, 82,804 recovered first-hour rows, and a 6,641-row Dune/PumpApi overlap. It states that the paid local Dune response was recovered and not rerun.
- In that overlap, signature and mint agreement were 6,641/6,641; economic-wallet agreement was 6,634/6,641; side semantics matched 6,637/6,641 with four rows flagged for semantic review. Timestamp differences were median 985 ms, p95 1,466 ms, maximum 2,168 ms. CREATE representation and unknown amount fields remain explicit.
- The recovered one-day replay retained 211,350 events across 19 verified hours, 855 mints, and 29,540 wallets. Five hours (`01`, `06`, `11`, `13`, `17` UTC) failed decompression integrity and remain missing; no gaps were filled.
- The recovered cost model measures one representative archive at 608,173,816 compressed bytes, 3,949,203,772 decompressed bytes, 3,042,273 input events, 97.54 seconds, and 19,584 kB peak RSS. Its 3-day estimate is 40.464 GB compressed and 1.95 CPU hours; this is planning evidence, not authorization to acquire data.
- Existing participant evidence marks self-flow as `SELF-FLOW CONTAMINATED`; Day-2 mature histories are zero. Runner outcomes remain `BLOCKED BY OUTCOME COVERAGE`; graduation is not Runner success.
- No Dune, PumpApi, Helius, web, wallet, signing, execution, alert, purchase, subscription, or credential action was performed in this iteration. Dune new-query credits: 0.

## Interpretation (INFERENCE)

Recovery confirms that the prior Day-2 result is not an empty panel and that the one-hour semantic agreement audit is reproducible from retained repository artifacts. It does not make the day complete: five replay hours, continuation outcomes, mature point-in-time participant histories, and a third-day denominator/sample manifest remain unavailable. Therefore the quality gate for a three-day panel and models A/B/C/D is still not met.

The highest-information reversible path remains a frozen-manifest three-day panel only after the one-day integrity gate is genuinely complete. Because this iteration recovered and re-checked existing evidence but did not reduce the decisive outcome-coverage blocker, no new child task is created; the three-consecutive-no-progress stop condition applies to the current continuation chain.

## Metrics and missingness

| Metric | Observed | Status |
|---|---:|---|
| Usable calendar days | 1 | INSUFFICIENT DATA |
| Day-2 replay hours | 19/24 | PARTIAL; five hours missing |
| Day-2 retained events | 211,350 | FACT; not complete-day coverage |
| Dune/PumpApi overlap | 6,641 rows | Agreement evidence with flagged discrepancies |
| Decision-time matrix | 0 validated multi-day rows | BLOCKED BY OUTCOME COVERAGE |
| Mature Day-2 participant histories | 0 | UNKNOWN history is not failure |
| Runner 24h/72h outcomes | unavailable | BLOCKED; no imputation |
| Self-flow status | 46.77% in prior targeted sample | SELF-FLOW CONTAMINATED |
| New Dune credits | 0 | FACT |

DEAD, UNEXITABLE, PROVIDER_UNAVAILABLE, and UNKNOWN remain distinct states. Missing hours are not favorable exclusions and are not converted into successful outcomes.

## Skeptical boundary (UNKNOWN)

It remains unknown whether participant, precursor, redundancy, breadth/flow, or sell-shock features have incremental value; whether a complete panel would pass the preregistered horizon coverage and holdout gates; and whether findings would persist across days, venues, protocol regimes, or concentration controls. No BUY, SELL, COPY TRADE, profitable, or validated-edge claim is made.

## Next-step decision

HOLD RESEARCH ONLY. Do not scale to fourteen days, fit A/B/C/D, change a scanner/watch/alert, or operationalize any result. A future run may attempt the smallest missing-hour/data-quality recovery or construct the required frozen third-day manifest, subject to fresh provider/resource preflight and the existing human gate.
