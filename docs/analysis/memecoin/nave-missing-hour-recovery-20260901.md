NAVE bounded missing-hour recovery and overlap decision

Date: 2026-09-01T12:05:18Z (UTC)
Scope: one local, read-only recovery/quality iteration after the native human unblock.
Mode: READ_ONLY_RESEARCH_ONLY_HUMAN_GATED.
Classification: INSUFFICIENT DATA / BLOCKED BY OUTCOME COVERAGE.

Hypothesis

HYPOTHESIS: the highest-information reversible step is to recover already-paid artifacts and verify whether the smallest available local evidence can close the missing-hour and outcome-coverage gate. If not, a bounded provider-overlap proof is preferable to multi-day scale-up. This is not a hypothesis that any feature predicts returns.

Evidence (FACT)

- The canonical NAVE state before this iteration recorded one usable day, Day-2 as 19/24 verified hours, five failed replay hours, zero validated multiday decision rows, zero mature Day-2 participant histories, and SELF-FLOW CONTAMINATED. The decisive blocker was incomplete multiday outcome coverage.
- The retained acquisition commit 39e909809f85d998c7d6cbd06ff1bef93c18bc31 was inspected with git show. Its compact manifest, panel JSON, and report are recoverable repository artifacts; no provider endpoint was called and no query was rerun.
- The recovered panel reports a Day-2 denominator of 48,330 launches, a deterministic 1,000-mint sample, 82,804 recovered first-hour rows, and a 6,641-row Dune/PumpApi overlap. Signature and mint agreement are 6,641/6,641; economic-wallet agreement is 6,634/6,641; side semantics match 6,637/6,641 with four rows flagged for semantic review. Timestamp deltas are median 985 ms, p95 1,466 ms, and maximum 2,168 ms.
- The one-day PumpApi replay retained 211,350 events across 19 verified hours, 855 mints, and 29,540 wallets. Hours 01, 06, 11, 13, and 17 UTC failed decompression integrity. They remain missing; no imputation or favorable exclusion was applied.
- The acquisition commit reports 0 new Dune credits and no purchase/upgrade. A local fail-closed resource preflight with credits-used 2024.104, included 2500, checkpoint 2024.104, estimate 0, and free disk 49 GB returned allowed=true and level=OK. This preflight authorized only zero-cost local inspection, not a provider call.
- The manifest and panel artifact hashes were recomputed from the retained commit as dc1232762e633c03e05d3dece11187f9003bfdf967923ca865988281b8e2a6ee and 85014582bf92fac1be40c1b48f153cde4e98808d4207cdfae43d9797b557792a. The historical panel report contains 113 lines.

Interpretation (INFERENCE)

Local recovery confirms that the prior paid result is retained and that a bounded one-hour semantic overlap proof exists. It does not recover the five failed hours, continuation outcomes, a third-day denominator/sample manifest, or mature point-in-time participant histories. Therefore it does not reduce the decisive outcome-coverage blocker enough to permit a three-day statistical panel, fourteen-day scale-up, or A/B/C/D fitting.

The overlap is source-semantic evidence only. It cannot validate predictive performance, cost-adjusted returns, temporal stability, or absence of self-flow contamination. The correct operational research state remains paused pending the smallest next data-quality experiment.

Metrics and missingness

- Usable calendar days: 1 — INSUFFICIENT DATA.
- Verified replay hours: 19/24 — PARTIAL; five FAILED hours preserved.
- Validated multiday outcome rows: 0 — BLOCKED BY OUTCOME COVERAGE.
- Mature Day-2 participant histories: 0 — UNKNOWN history is not failure.
- Self-flow: SELF-FLOW CONTAMINATED; no exogenous participant claim.
- Runner 24h/72h outcomes: unavailable — BLOCKED; no imputation.
- New provider credits: 0 FACT.
- Missing states DEAD, UNEXITABLE, PROVIDER_UNAVAILABLE, and UNKNOWN remain distinct.

Next-step decision

NEXT STATE: NEXT_BOUNDED_EXPERIMENT.

Create exactly one follow-up for a bounded PumpApi-vs-Dune overlap/quality proof restricted to already-paid or locally retained evidence and explicitly checking whether any missing-hour recovery is possible without a new paid call. The child must remain read-only, research-only, human-gated, and must stop before multi-day scale-up if outcome coverage is still incomplete. No scanner, watch, alert, strategy, or execution rule changes are authorized.
