NAVE bounded PumpApi-vs-Dune missing-hour quality proof

Date: 2026-09-01T12:10:45Z (UTC)
Scope: one bounded local, read-only, research-only quality iteration.
Mode: READ_ONLY_RESEARCH_ONLY_HUMAN_GATED.
Classification: BLOCKED BY OUTCOME COVERAGE / INSUFFICIENT DATA.

Hypothesis

HYPOTHESIS: retained artifacts may establish whether the five failed PumpApi hours can be recovered locally and whether the existing Dune/PumpApi overlap is reproducible without a paid provider call. This is a data-quality hypothesis, not a return or trading-signal hypothesis.

Evidence (FACT)

- The canonical state and preceding recovery report identify failed replay hours 01, 06, 11, 13, and 17 UTC on 2026-08-28. They remain missing and were not imputed or favorably excluded.
- The retained acquisition commit 39e909809f85d998c7d6cbd06ff1bef93c18bc31 contains the compact manifest, historical-panel JSON, panel report, and the PumpApi replay/agreement code. The manifest records 211,350 retained PumpApi rows across 19 verified hours, 855 mints, and 29,540 wallets, with the five failed hours explicitly listed.
- Local filesystem inspection found no PumpApi day directory or recovered hourly Parquet under the current worktree or `/home/david/nave/data/research/pumpapi/day/date=2026-08-28`. Therefore the failed-hour decompressed/raw or canonical hourly payloads are not locally recoverable from the available workspace.
- The retained Dune first-hour Parquet is available in the existing sibling worktree at `/home/david/nave/.worktrees/dune-efficient-panel/data/research/dune/pumpfun_first_hour_events.parquet`. Its SHA-256 is `9a9a6027abc3e1c508d990f10d4d756bdbfa77c6d51b3abeaa4d0c0227cb678c`, matching the retained manifest.
- The retained panel JSON records a 6,641-row overlap: signature matches 6,641/6,641, mint matches 6,641/6,641, economic-wallet matches 6,634/6,641, and side semantics match 6,637/6,641. Four side discrepancies and seven multi-trader wallet ambiguities remain flagged. Timestamp deltas are median 985 ms, p95 1,466 ms, maximum 2,168 ms.
- The preceding report records 0 new Dune credits and a fail-closed preflight with estimate=0 allowed. This iteration made no Dune or PumpApi call, used no credentials, and purchased nothing.
- The local resource guard was re-run with credits-used=2024.104, included=2500, checkpoint-used=2024.104, estimate=0, and free-disk-gb=49. It returned `allowed=true`, `level=OK`, and remaining included credits 475.896. This authorizes only zero-cost local inspection, not a provider call.

Interpretation (INFERENCE)

The missing hours cannot be recovered from the currently available local filesystem. The tracked commit preserves the manifest and quality accounting, but not the excluded raw/decompressed PumpApi payloads. The Dune artifact and prior overlap figures are recoverable evidence, but they cannot reconstruct absent PumpApi hours or supply missing continuation outcomes.

The overlap therefore remains a bounded source-semantic proof with limitations, not predictive validation. It does not establish complete 24-hour coverage, 24h/72h Runner outcomes, mature point-in-time participant histories, temporal stability, cost-adjusted returns, or absence of self-flow contamination.

Skeptical checks

- Treating 19/24 verified hours as a complete day: REJECTED; five integrity failures remain explicit missingness.
- Reconstructing failed hours from aggregate counts or the Dune overlap: REJECTED; no event-level PumpApi payload exists locally for those hours, and Dune covers only the retained first-hour overlap.
- Treating the 6,641-row agreement as an outcome test: REJECTED; it tests source identity/semantics only and contains known ambiguity/discrepancy rows.
- Excluding failed hours, DEAD, UNEXITABLE, PROVIDER_UNAVAILABLE, or UNKNOWN histories: REJECTED; missingness is preserved.
- Fitting A/B/C/D or scaling to 14 days: REJECTED; the quality gate is unmet and validated multiday outcome rows remain zero.

Metrics and missingness

- Verified replay hours: 19/24 — PARTIAL.
- Failed hours: 01, 06, 11, 13, 17 UTC — FAILED and preserved.
- Local PumpApi failed-hour recovery: unavailable — UNKNOWN/PROVIDER_UNAVAILABLE locally, not a favorable exclusion.
- Dune/PumpApi overlap rows: 6,641 — descriptive source agreement only.
- Validated multiday outcome rows: 0 — BLOCKED BY OUTCOME COVERAGE.
- Participant history: not mature for multiday modeling; existing self-flow status remains `SELF-FLOW CONTAMINATED`.
- New provider credits: 0.

Decision

NEXT STATE: HUMAN_DECISION.

No additional provider call is justified or authorized by this bounded experiment. Keep NAVE paused at the native human gate unless a human-approved, zero-cost retained artifact becomes available or Joni explicitly decides that a new bounded data acquisition is worth its resource and outcome-coverage cost. No scanner, watch, alert, strategy, or execution rule changes are made.
