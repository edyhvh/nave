# Frozen September 1 cohort: recovered tape, not a validated strategy

Verdict: **DESCRIPTIVE_FROZEN_INTRADAY_COHORT; NO EDGE VALIDATED**.
This supersedes the old Day-6 *archive availability* blocker, not its comparable-day acceptance gate.

## Evidence recovered without new acquisition

The local checkpoint records recovery completed on September 2 at 08:01:25 UTC: 24/24 hours, curl/zstd/consumer exit codes zero. This verification checks hourly retained counts and file sizes against saved metrics, rejects malformed selected records, and records SHA-256 hashes. The 420,140 normalized events cover 1,021 mints in the frozen 1,025-mint filter union (1,000 launch sample plus prior migrants). The existing projected tape was materialized locally; no new Dune query, paid transcript, archive download, sample reselection or parameter search was performed. Three free HTTP HEAD checks also returned 200; no new archives were downloaded.

Crucially, the launch manifest was acquired at **2026-09-01 21:02:37 UTC**, before the sampled UTC day ended. Its latest sampled launch is 20:56:49. The stated denominator 29,434 is a denominator at acquisition, not a verified full-day population. Restoring outcome hours 21–23 does not restore launch inclusion for those hours. The frozen sample is useful for descriptive replay but **must not become a fifth comparable full-calendar-day sample**. Four earlier complete daily samples remain the comparable panel.

## Frozen descriptive result

No features, training day, decision clock, horizons, regularization or bootstrap settings were tuned. The existing implementation trains on August 28 and evaluates the September 1 frozen sample at launch +10 minutes, using the existing future-trade activity labels. Its historical features use event time, not a replay of receiver latency; real-time availability is another unproven gate.

| Horizon | Positive | Negative | Migration unknown | Activity rate among resolved labels |
|---|---:|---:|---:|---:|
| 15 minutes | 86 | 881 | 33 | 8.89% |
| 30 minutes | 43 | 924 | 33 | 4.45% |
| 60 minutes | 18 | 949 | 33 | 1.86% |

Right-censored labels are zero for this intraday sample; that is **not** improved full-day coverage. Late-day launches were absent from its sampling frame.

At 60 minutes (967 binary labels, only 18 positives), baseline A has average precision 0.1337 versus C's 0.1231. C adds buyer acceleration, buy-volume acceleration, sell pressure and trade-size concentration. C−A average precision is −0.0106; the 95% token-bootstrap interval is [−0.0602, +0.0548]. C−A Brier is −0.00020, interval [−0.00127, +0.00097]. Both intervals cross zero: **no stable incremental benefit is demonstrated**. This descriptive comparison is not a new holdout strategy-validation result.

Only 49/1,000 tokens have a price mark in the existing approximately one-hour mark window. Mark-resolved tokens have median 306 early trades and 84 buyers; unresolved tokens have 14 trades and 4 buyers. Conditioning a return analysis on those 49 tokens would select unusually active tokens. Do not call missing marks losses, exits or zero returns.

## Strategy direction

Continue an identity-verified, liquidity- and observability-first **research screener**, with three separate populations: launch cohorts, timestamped social discoveries, and established platform tokens. Keep the simple A baseline; C remains an unproven candidate rather than a deployed filter. PONS belongs to the established-platform case study and has no demonstrated identity/economic linkage to this Solana cohort.

Do not promote to trade alerts or a PONS position. First freeze an explicitly closed-UTC-day launch population, reuse its complete event tape where available, and evaluate untouched dates without tuning. Participant-excluded history, same-pool executable outcomes, liquidity-aware costs and stressed holdout expectancy remain required before a paper-strategy decision. Recoverable data and an interesting story are not sufficient.

NEXT STATE: **NEXT_BOUNDED_EXPERIMENT**, gated by existing resource limits and operational-notification readiness. No recurring job, watch, wallet, order or service is activated by this research.

## Reproduction and skeptical checks

Run `PYTHONPATH=. .venv/bin/python scripts/verify_stage1_cached_day.py --day-dir data/research/pumpapi/day/date=2026-09-01 --train-events data/research/pumpapi/day/date=2026-08-28/pumpapi_events_recovered_full.parquet --output REPORT.json` from a checkout with the cached data paths available. Full aggregate metrics, per-hour hashes, frozen sample hash and limitations are in [the JSON audit](stage1-frozen-cohort-verification-20260906.json). Raw event/Parquet data stays local.

Checks: archive completion PASS; frozen sample identity/count PASS; full-day sample FAIL; C incremental stability FAIL; executable-return coverage FAIL; PONS linkage NOT ESTABLISHED; edge validation NO. This script does not perform independent blockchain reconciliation or reconstruct the missing launch denominator.
