# NAVE one-day outcome-coverage gate verification

Date: 2026-09-01T02:55:35Z (UTC)
Scope: bounded local-only verification of the existing one-day historical acquisition.
Mode: READ_ONLY_RESEARCH_ONLY_HUMAN_GATED.

## Classification

BLOCKED BY OUTCOME COVERAGE.

The one-day acquisition is not a complete usable day. This verification makes no strategy, profitability, BUY, SELL, WATCH, or operational claim.

## Evidence (FACT)

- The canonical local panel record identifies 2026-08-28 as `PARTIAL`, with 19 verified hours out of 24 and failed hours `01`, `06`, `11`, `13`, and `17`.
- The retained 2026-08-28 dataset contains 211,350 selected events, 855 mints, and 29,540 wallets. These are retained observations, not a complete-day denominator.
- The deterministic daily sample target is 1,000 mints and was not selected using survivor, winner, migration, or volume outcomes.
- The local panel contract requires at least 8 usable days and 5,000 valid decision-time rows before model fitting; the existing record reports 1 usable day and 0 decision rows for that gate.
- Missing hours are explicitly recorded as integrity failures. No events were imputed across gaps and no failed hours were converted into favorable exclusions.
- The existing manifest labels the hourly replay `PARTIAL` and records the five failed hours. Its retained Parquet hash is `caee8e6993b5c63755f8a64536349d3c57f81a151a9376a9e1b901cd1dad739d`.
- The local state records `READ_ONLY_RESEARCH_ONLY_HUMAN_GATED`, `primary_horizon_coverage: INSUFFICIENT`, and no current validated strategy path.
- No Dune, PumpApi, Helius, web-search, wallet, execution, signing, transfer, alert, credential, or paid-provider action was performed for this verification.

## Gate result (INFERENCE)

The one-day data-quality gate FAILS closed. Five failed replay hours prevent treating 2026-08-28 as a complete usable day for outcome coverage or chronological model evaluation. The retained rows may support descriptive inspection only; they cannot establish 5m/15m/30m/60m/4h outcomes for the missing intervals or repair the denominator.

Therefore the multi-day panel remains `BLOCKED BY OUTCOME COVERAGE`, with `INSUFFICIENT DATA` as the evidence-quality classification. A bounded three-day panel is not released by this task.

## Missingness and invalidation boundary

- `FAILED` replay hours remain failed and are not treated as zero activity.
- Missing pools/exits remain `DEAD` or `UNEXITABLE` where those states are present; provider failure remains distinct from those states.
- Unknown launch time, side, amount, censoring, and continuation outcomes remain unknown.
- Graduation is not Runner success; Runner 24h/72h outcomes remain blocked until same-pool continuation is verified.

## Operator hold

Per the operator note, the continuation is held for inspection. No child task is created. The next experiment remains only a state-level candidate: after an explicit release and a fresh preflight, acquire/verify a bounded three-day panel with frozen daily manifests. This report does not authorize that work.

## What would change the result

A future iteration would need a reproducible, frozen daily manifest and complete, same-pool outcomes for the required horizons, with integrity coverage documented for every attempted interval and sufficient usable-day/decision-row counts. Until then, valid conclusions remain `BLOCKED BY OUTCOME COVERAGE` and `INSUFFICIENT DATA`.
