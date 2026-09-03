NAVE SURVIVAL / OBSERVABILITY PANEL — LOCAL EVIDENCE REPORT

STATUS

Classification: INSUFFICIENT DATA
Edge claim: false
Mode: read-only, research-only, human-gated
Observation date: 2026-09-01; evidence day: 2026-08-28 UTC

FACT — SOURCE AND SCOPE

- Reprocessed the retained canonical PumpApi Parquet at /home/david/nave/data/research/pumpapi/day/date=2026-08-28/pumpapi_events_recovered_full.parquet.
- Observed 254,522 normalized rows, 1,000 token clusters, and 30 migration events. The collection boundary is the last observed event in the recovered tape (2026-08-28T23:59:55.564Z).
- No Dune or PumpApi provider call was made in this iteration. No raw archive was retained or newly downloaded.
- The primary output is activity/survival, not a return or executable mark. Mark availability was deliberately not used to define the clusters.

METHOD — PREDECLARED DESCRIPTIVE PANEL

Each token is one cluster unit; repeated events are not treated as independent assets. Clusters are fixed from first-10-minute BUY/SELL count: ZERO=0, LOW_1_9=1–9, MEDIUM_10_99=10–99, HIGH_100_PLUS=100+. These bins are descriptive and are not a fitted threshold or a trading rule.

For each 15m/30m/60m horizon, the panel preserves:
- HAS_TRADE_THROUGH_HORIZON versus NO_ACTIVITY_THROUGH_HORIZON;
- future trade after the horizon as an observability/activity outcome;
- MIGRATED_BEFORE_HORIZON as a lifecycle state;
- RIGHT_CENSORED when the target exceeds the collection boundary;
- NO_FUTURE_TRADE when prior activity exists but no post-horizon trade is observed;
- TOKEN_INACTIVE when no activity is observed through the horizon.

PROVIDER_EVENT_GAP and TRUE_UNKNOWN remain valid missingness states in the contract. Neither was observed in this restored sample; that is not evidence they cannot occur elsewhere.

FACT — CLUSTER COMPOSITION

| Cluster | Tokens |
|---|---:|
| ZERO | 148 |
| LOW_1_9 | 320 |
| MEDIUM_10_99 | 355 |
| HIGH_100_PLUS | 177 |

FACT — HORIZON OUTCOMES

| Horizon | Migrated before horizon | No future trade | Observable future trade | Token inactive | Right censored |
|---|---:|---:|---:|---:|---:|
| 15m | 23 | 621 | 219 | 130 | 7 |
| 30m | 27 | 655 | 170 | 129 | 19 |
| 60m | 27 | 672 | 138 | 128 | 35 |

The activity view is separate from mark resolution. At 60m, 830 tokens had a trade through the horizon and 135 had no activity through it among the non-right-censored observations; 163 had a future trade at or after the target, including the migration-linked cases. This must not be read as a profitable or executable outcome.

INFERENCE — OBSERVABILITY SELECTION WARNING

The recovered tape supports a two-stage design: first model whether activity/survival is observed, then condition any future price-mark analysis on the frozen mark contract. A mark-only sample is activity-selected. The prior audit reported 60m resolved-mark medians of 138 first-10m trades versus 9 for unresolved tokens, and 24 versus 3 unique buyers. This panel confirms the need for clustering but does not estimate a survival model or predictive effect.

FACT — RUNNER CONTINUATION

Day-2 PumpApi contains 30 sampled migration events. Activity-only continuation (not quoted marks and not PumpSwap) is:

| Horizon | Activity observed | Eligible, not censored | Right censored |
|---|---:|---:|---:|
| 4h | 22 | 22 | 8 |
| 8h | 17 | 17 | 13 |
| 12h | 8 | 8 | 22 |
| 24h | 0 | 0 | 30 |
| 48h | 0 | 0 | 30 |
| 72h | 0 | 0 | 30 |

The apparent zeros at 24h/48h/72h are entirely right-censored and therefore are not Runner failure or success. The Day-1 compact Dune panel remains separate: seven targeted migrants had PumpSwap activity 7/7, 7/7, 7/7, 6/7, 1/7, 0/7 at 4h/8h/12h/24h/48h/72h, with quoted marks 7/7 at 4h, 2/7 at 24h, 1/7 at 48h, and 0/7 at 72h. It is descriptive only and not merged into this event-level panel.

UNKNOWN / LIMITATIONS

- Only one provider-complete event-level calendar day exists; the four bins and horizon counts are not temporal validation.
- Day-1 Dune has aggregate 60m evidence but no frozen point-in-time event features, so it cannot be combined into A-vs-C.
- The 30 Day-2 migrations are a sampled-day subset, not the all-day migrant universe; PumpSwap continuation for them is unavailable.
- No liquidity/depth, failed-exit, participant-history, causal, or fee/slippage evidence was added.
- No A/B/C/D model was fit; no scanner, watch, notification, or execution rule changed.

DECISION

Classification remains INSUFFICIENT DATA / BLOCKED BY OUTCOME COVERAGE. The local panel reduces semantic ambiguity and makes observability clustering reproducible, but it does not validate a signal. Do not fit A-vs-C until several event-level calendar days and frozen point-in-time features are available. The next bounded experiment is one predeclared additional event-level day using a compact launch manifest, subject to fresh resource preflight; no provider call is authorized by this report.

Artifact: docs/analysis/memecoin/nave-survival-observability-panel-20260901.json
