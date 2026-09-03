# NAVE three-day acquisition gate — 2026-09-01

## Status

Classification: **BLOCKED BY OUTCOME COVERAGE / INSUFFICIENT DATA**.
No edge was validated and no operational rule changed.

## Evidence before interpretation

- FACT: The canonical state before this iteration had one usable day (2026-08-28), with 24/24 restored archive-hour coverage, but no multi-day temporal sample.
- FACT: Three calendar days were predeclared before outcome inspection: 2026-08-29, 2026-08-30, and 2026-08-31 UTC.
- FACT: The selection contract was fixed in advance as the lexicographically first 1,000 mint addresses observed in create events for each date; this is outcome-independent, deterministic, and not survivor selection.
- FACT: The free official PumpApi Historical Replay path was invoked sequentially, one archive at a time, beginning with 2026-08-29 UTC.
- FACT: Six archives (00 through 05 UTC for 2026-08-29) were streamed for launch-mint discovery before the bounded runtime/resource gate was reached. No raw archive was retained and no canonical outcome Parquet was materialized.
- FACT: The remaining 66 archives were not acquired. Therefore, zero of the three new days is complete and no new token-level 15m/30m/60m masks can be produced without incomplete selection.
- FACT: No Dune query, purchase, credential use, wallet connection, signing, trading, alert, scanner, or strategy change occurred.

## Interpretation

INFERENCE: The PumpApi provider is reachable, but sequential full-day archive discovery is materially slower than the current bounded task runtime. Stopping rather than parallelizing preserves the explicit one-archive-at-a-time contract and avoids creating a partial, outcome-dependent sample.

UNKNOWN: Whether all three dates have complete remote archive availability; the six attempted archives were not retained as a durable manifest because the day-level selection was not completed.

## Coverage and missingness decision

No outcome analysis was run. No launches, rejected/dead/unexitably/unknown, right-censored, or protocol states were silently excluded. Because selection could not be completed, no favorable exclusion or imputation was possible. 24h/48h/72h Runner labels remain unobserved for these dates and must remain separate/right-censored at collection boundaries when acquisition resumes.

## Quality gate

- Three predeclared days acquired: **0/3 complete**.
- Token-level short-horizon masks: **not available for new days**.
- Five-day/preliminary temporal gate: **not met**.
- 5,000 paired Burst-row gate: **not met**.
- A/B/C/D fit: **not run**.

## Next step

Resume with the same predeclared dates and deterministic selection contract only if a bounded execution window can support sequential archive replay, or reduce archive scope through an already-validated retained launch manifest. Do not inspect outcomes to choose replacement dates. Preserve the current one-day evidence and remain in research-only mode.
