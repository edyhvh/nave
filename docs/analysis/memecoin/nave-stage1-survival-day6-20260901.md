STAGE-1 SURVIVAL MATERIAL PROGRESS

# NAVE Stage-1 survival, Day 6 acquisition gate — 2026-09-01

## EXECUTIVE STATUS

FACT: The predeclared 2026-09-01 launch sample was frozen before replay using sha256(nave-2026-09-01-v1:mint) ascending. The Dune result contained exactly 1,000 rows from a denominator of 29,434.

FACT: The bounded mint-first PumpApi replay used three workers and resumed from hourly checkpoints. At the final observation (2026-09-01T21:15Z), 21/24 hours completed; hours 21, 22, and 23 returned HTTP 404. Hour 16 was recovered after a transport reset; hours 08 and 13 were also recovered after transport resets.

FACT: Partial normalized output and per-hour integrity details are preserved in the acquisition manifest; no day-level Parquet was materialized.

CLASSIFICATION: PROVIDER_UNAVAILABLE / BLOCKED BY OUTCOME COVERAGE. This day is not admitted as a comparable Stage-1 day and no outcome, A/C comparison, or strategy conclusion is computed from partial coverage. EDGE_VALIDATED remains false.

## EVIDENCE

- Date: 2026-09-01 UTC; observation timestamp: 2026-09-01T21:15Z.
- Frozen launch sample: 1,000 mints; denominator 29,434; selection seed nave-2026-09-01-v1; selection frozen before event replay.
- Filter union: 1,025 mints (1,000 general sample plus 25 prior-day migrant mints available from the Day-5 tape).
- Replay: HTTP -> zstd -> projected JSONL -> normalized JSONL; maximum three workers; raw decompressed archives not retained.
- Completed archive hours: 21/24. Failed/unavailable hours at final checkpoint: 21, 22, 23 (HTTP 404); the earlier 16 failure was recovered.
- Partial retained rows and observed mints are recorded in the acquisition manifest; no Parquet was materialized because the canonical materializer fail-closes on incomplete hours.

## MISSINGNESS AND VALIDATION

The missing hours are preserved as provider-unavailable, not inactivity or negative outcomes. RIGHT_CENSORED, MIGRATION_UNKNOWN, and PROVIDER_GAP semantics were not collapsed; however, the day-level provider gap is unresolved and therefore no per-day survival base rates are valid. Participant B/D and Runner remain deferred/descriptive.

## RESOURCE / SAFETY

FACT: Dune usage before this bounded launch query was 2,027.345/2,500; the local guard passed a five-credit estimate. The query completed and the launch manifest was recovered. Exact incremental credits are UNKNOWN. No purchase, wallet, signing, transfer, trade, scanner, alert, or deployment action occurred.

## SKEPTICAL REVIEW

The decisive invalidation is incomplete provider coverage: three archive URLs were unavailable at observation time and the partial day cannot distinguish no event from missing tape. Replaying only available hours would create outcome-dependent missingness and bias the sample. The day is consequently excluded from the comparable panel; no A_survival-vs-C_survival temporal comparison is reported.

## NEXT STEP

Retry only the same predeclared 2026-09-01 hours after the provider makes them available, then materialize the day and reassess the 5–7-day checkpoint without tuning. If the provider remains unavailable, retain this gate and do not substitute a different date or treat the partial tape as a completed day.
