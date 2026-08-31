BLOCKED BY DATA

# M3 Dual-Horizon Trajectory Research

Date: 2026-08-31  
Scope: Hermes/NAVE only. Read-only research. No OpenClaw changes, wallet access,
signing, orders, notifications, or capital.

## EXECUTIVE RESULT

No Fast Burst edge, Sustained Runner edge, survival filter, participant signal,
or Burst-to-Runner transition is validated. This is a data-blocked result, not
a negative claim about the market.

The required historical event panel was not available in the workspace. The
existing NAVE journal is an active-survivor scan journal with no launch/event
timestamps and no 5m–4h outcomes. It cannot be converted into a launch panel
without introducing selection and survivorship bias. The public corpus was
identified and its `KNOWN_ISSUES.md` was read, but its 6.7GB Parquet files were
not downloaded or queried.

The only completed work in this iteration is the isolated, read-only research
layer and its invariant tests. The module is intentionally provider-agnostic;
it does not create a scanner trigger or an execution path.

Therefore:

- the Burst-versus-Runner distinction remains an untested hypothesis;
- no trajectory-family count or regime fraction is reported;
- no participant or wallet can be called informative;
- no holdout was unlocked;
- no research notification should be activated.

## DATA ACTUALLY OBTAINED

### Local NAVE artifacts

| Artifact | Observed | What it can support |
|---|---:|---|
| `var/memecoin_m3/signal_journal.json` | 1,885 entries | Forward-journal integrity context only |
| Passed entries | 482 | Prior scanner selection count, not a historical cohort |
| Rejected entries | 1,403 | Rejected scan context; not complete launch population |
| 5m/15m/30m/60m/4h outcomes | 0 each | No short-horizon evaluation |
| Numeric 24h/48h outcomes | 1,130 / 775 | Existing current-provider context, not same-pool historical outcomes |
| 7d outcomes | 0 | Existing M3 gate remains unmet |
| Launch timestamps missing | 1,885 | Cannot establish lifecycle age |
| Entry pair missing | 572 | Cannot establish same-pool execution identity |
| Current memecoin cache | 5,315 JSON files, about 25M | Current/provider cache; not historical replay |
| Historical `.jsonl.zst` archives | 0 | No PumpApi event panel |
| Public corpus Parquet files | 0 | No corpus query |

The prior M3 metrics report’s 24h/48h figures are retained as history. They are
not used as Runner results because resolution came from current market data and
does not prove the entry pool or historical executability.

### External discovery source

The public [PumpFun Launch-to-Graduation Corpus](https://huggingface.co/datasets/Slinky21/Pumpfun_Memecoin_Corpus)
reports 798,430 launches, 33.58 million trades, pre- and post-graduation
snapshots, and outcome labels. It is a hypothesis-discovery/falsification
source only. No query was run in this iteration.

The corpus [KNOWN_ISSUES.md](https://huggingface.co/datasets/Slinky21/Pumpfun_Memecoin_Corpus/blob/main/KNOWN_ISSUES.md)
was read before any planned query. Its quantified issues are recorded in the
manifest and include corrected Mayhem supply columns, irrecoverable
`top10_pct_suspect` rows, corrupted and missing SOL price fields, System
Program contamination, curve-depletion regime shift, stale `wallet_stats`,
synthetic migration addresses, the July 3 outage, holder-count and Mayhem
regime breaks, silence-rate change, outcome-label gotchas, graduation-proxy
leakage, and right censoring.

## DATA QUALITY / EXCLUSIONS

The public corpus would be filtered and retained as follows when acquired:

- Use corrected supply/concentration fields for Mayhem tokens. Mayhem supply
  is not assumed to be 1B; protocol-consistent supply is required for quoted
  market-cap reconstruction.
- Exclude `top10_pct_suspect` rows from concentration analyses. They are not
  imputed.
- Exclude corrupted `sol_amount` rows from SOL volume and P&L, while retaining
  their quality flags. Missing SOL/price rows remain missing.
- Exclude the documented System Program address from wallet and cohort
  features; recompute activity directly from valid trades.
- Do not use `wallet_stats` activity or volume totals. Recompute wallet
  roll-forwards from trades.
- Exclude synthetic migration sentinels when a real pool identity is required.
- Treat the July 3 outage as provider unavailability and preserve adjacent
  regime boundaries; it is not token death.
- Model the holder-count break, Mayhem rollout, concentration-bug interval,
  silence-rate break, and post-outage curve-depletion shift as market/data
  regimes.
- Exclude graduation-prediction leakage fields such as
  `entry_price_20s_usd`, `entry_price_30s_usd`, and `entry_price_1m_usd`.
- A target beyond collection end is `UNKNOWN` with a right-censor reason, not
  `DEAD`, `NON_RUNNER`, or a zero return.

No rows were silently discarded in the implemented research primitives. The
module returns explicit quality flags and preserves unresolved states.

## TRAJECTORY DISCOVERY

Not run: there is no complete launch-to-72h event panel. The planned discovery
procedure is frozen as feature-based, interpretable clustering over normalized
trajectory vectors. Candidate `k` values are 2, 3, 4, 5, and 6; the
implementation reports cluster sizes and within-cluster distance and does not
select a strategy from the best score.

The vector includes log-normalized price, real volume, participant count, and
liquidity at 5m, 30m, 4h, 24h, and 48h. It is deliberately not a peak-market-cap
label. Chronological block stability, normalization sensitivity, and economic
interpretability must be checked before any labels are defined.

The planned descriptive labels are `NO_START`, `FAST_BURST`, `FALSE_RUNNER`,
`SUSTAINED_RUNNER`, `MINOR_PUMP`, `SLOW_BLEED`, and `UNKNOWN`. They are not
assigned in this report.

## BURST REGIME

Not evaluated. The Fast Burst head remains the comparable short-horizon track:
$100 paper notional, maximum 0.25% of available liquidity, +20% target, -15%
stop, and 60-minute time stop. Same-event ambiguity is stop-first.

Required outcomes are executable 5m, 15m, 30m, and 60m returns, target/stop
status, MAE/MFE, dead/unexitability status, and net results under frozen
optimistic/base/stressed cost scenarios. No result is available.

## RUNNER REGIME

Not evaluated. Runner outcomes are separate raw conditional return distributions
at 4h, 8h, 12h, 24h, 48h, and 72h. A fixed +20% target is not the primary
Runner outcome.

The predeclared exit families are fixed-time exits at 4h/8h/24h/48h, trailing
drawdowns of 20%/30%/40%, and market-quality deterioration exits. Exit research
must not start until an entry/state classifier demonstrates out-of-sample
information. No Runner classifier or exit result exists.

## FALSE-RUNNER ANALYSIS

Not evaluated. Peak quoted market cap alone cannot qualify a Runner. The panel
must measure liquidity-to-market-cap, real-volume-to-market-cap,
independent-volume-to-market-cap, fixed-notional exit value/impact, time near
highs, liquidity retention, buyer breadth, and sell-shock survival.

The explicit null hypothesis is that apparent million-dollar or ten-million-
dollar peaks do not distinguish durable executable markets after these controls.
No evidence is available to accept or reject it.

## PROTOCOL-STATE ANALYSIS

The implementation creates an explicit `protocol_state` object with fields for
Mayhem, agent state, cashback, tokenized-agent/buyback status, BOOST, generated
flow, quote asset, launch variant, Token-2022 extensions, venue, pool identity,
migration state, and fee fields. Unknown remains unknown.

Protocol-generated trades are excluded from organic buyer, organic volume, and
real-flow features. They are retained in separate protocol-flow measures.

Current Pump public documentation describes PumpSwap as a constant-product AMM
and documents pool/buy/sell state; the [PumpSwap documentation](https://github.com/pump-fun/pump-public-docs/blob/main/docs/PUMP_SWAP_README.md)
also documents pool state and quoting mechanics. This iteration did not verify
the historical rollout date, activation rule, or complete instruction-level
classification needed for BOOST. Consequently no BOOST-adjusted result is
claimed.

## POST-BOOST ANALYSIS

Blocked by absent historical transaction/instruction data and incomplete
historical rollout verification. The intended test is a matched comparison at
approximately five minutes after a verified mechanical BOOST window:

- protocol-generated buy volume/share;
- organic buy volume and independent buyers;
- price and liquidity retention after BOOST ends;
- sell-shock absorption after BOOST;
- 4h–72h executable continuation.

BOOST flow must not inflate momentum, buyer counts, buy/sell ratios, or market
quality. No post-BOOST trigger or notification is enabled.

## ORGANIC SELL-ABSORPTION TEST

Blocked by absent event panel. The implemented detector uses only earlier valid
sell history and a predeclared relative shock multiplier of 3.0 after at least
three prior valid sells. The post-shock study is intended to measure 30s/60s/
120s recovery, new independent buyers, cohort turnover, largest cluster share,
flow entropy, liquidity recovery, creator-linked flow, protocol flow, and
15m–60m executable outcomes.

Controls must match token age, curve progress, prior return/volume, liquidity,
launch hour, market regime, and protocol state. A rolling absorption score is
deferred until the individual event result is validated.

## BUYER TURNOVER TEST

Blocked by absent participant-level event data. The panel design separates new
buyers from returning buyers and separates same-wallet recycling from new
external capital. Cluster-adjusted counts, entropy, largest-cluster share,
trade-size composition, and seller-to-new-buyer replacement are explanatory
features only until matched controls and chronological validation exist.

## MARKET-QUALITY TEST

Blocked by absent pool reserves/depth and fixed-notional historical execution
data. The implementation explicitly refuses to qualify a Runner from peak
market cap alone. Missing depth or route information is `UNKNOWN` or
`UNEXITABLE`, not a favorable resolved outcome.

Required fixed research notionals are $100, $500, and $1,000 where depth is
observable. These are paper probes only and do not authorize larger positions.

## CREATOR HISTORY TEST

Blocked by absent point-in-time launch and outcome panel. Creator history would
be built strictly from launches completed before each observation time and
tested by matched launch-quality comparisons. Planned fields include prior
launches/graduations, prior Burst/Runner/False-Runner/Dead outcomes, drawdown,
lifetime, liquidity survival, time since prior launch, and launch-frequency
bursts. Creator history is a risk feature, not a causal or bullish assumption.

## EARLY PARTICIPANT / ENTRY TRIGGER RESEARCH

### Reconstruction methodology

No participant result is available. On acquisition, trades will be normalized
with timestamp, mint/pool epoch, side, wallet, SOL/token amounts, protocol
state, creator linkage, and bundle/cluster evidence. The unit of signal will be
an economic participant or independent cluster, not an unexamined wallet
address.

### Wallet vs economic-actor clustering

Funding relationships, recurring co-buying, creator relationships, bundle
timing, disposable-wallet patterns, and coordinated exits will be used to flag
clusters. Three wallets in one economic cluster count as one convergence event.
Unknown linkage remains flagged and cannot be treated as independent evidence.

### Point-in-time reputation

At signal time `t`, a participant profile can use only completed outcomes with
`outcome_ts < t`. The implementation enforces this boundary. Activity and
volume are recomputed from trades; stale summary tables are not used.

### Realized P&L and skill decomposition

FIFO trade reconstruction separates discovery skill, realized P&L, entry timing,
exit quality, consistency, and open inventory. An unrealized peak is never
called realized profit. Possible states are `REALIZED_WIN`, `REALIZED_LOSS`,
`PARTIAL_REALIZATION`, `OPEN / UNKNOWN`, `UNEXITABLE`, and
`INSUFFICIENT_DATA`.

### Burst and Runner specializations

Burst specialists would be evaluated against executable +100% within 60m and
+200% within 4h targets after realistic delays. Runner specialists would be
evaluated at early entry relative to the Runner transition, including after
burst, graduation, BOOST end, or an absorbed sell shock. No specialization can
be assigned from the current journal.

### Activity-matched controls and incremental information

Participant presence must be compared with activity-matched tokens and with a
token-only model controlling for age, curve progress, mcap, liquidity, volume,
buyers, momentum, protocol state, launch time, and market regime. The required
question is whether participants add out-of-sample information beyond token
features, not whether they appear in winners.

### Convergence and latency decay

The implemented convergence helper counts distinct economic clusters over 30s,
60s, and 300s windows. Arrival is simulated at 0s, +2s, +5s, +15s, +30s, and
+60s. No exact-block assumption is permitted.

### Anti-insider exclusions

Creator-funded wallets, bundle participants, sybil clusters, coordinated exits,
and pre-public token transfers are separate flagged categories. The preferred
research class is `ORGANIC INFORMATIVE PARTICIPANT`; flagged categories cannot
be used as bullish evidence.

### Leave-one-participant-out robustness and archetypes

The implementation supports identity leave-one-out summaries. Any apparent
result must also be rerun after removing the top participant, the top five,
using unseen participants, and using behavioral archetypes only. No identity or
archetype result exists.

### Information cascade and precursor research

The future panel must reconstruct T-60s through T+5m around first informative
participant arrival and determine whether sell absorption, liquidity refill,
relative strength, graduation proximity, or another observable event preceded
the participant. If participant arrival is only a late consequence of momentum,
the participant trigger is falsified and precursor research becomes primary.

### Historical notification simulation

No notification was activated or simulated on unavailable data. The eventual
research-only notification, if independently validated, must explain participant
counts, point-in-time evidence, current organic demand, execution quality, and
risk state. It must never say “smart wallet bought — buy now.”

Participant conclusion: **BLOCKED BY PARTICIPANT DATA**.

## EXECUTION SIMULATION

No historical execution result is available. The isolated module includes a
constant-product output calculation and an explicit 0.25%-of-liquidity size
gate. The replay must additionally reconstruct historical bonding-curve/AMM
reserves, protocol/creator/LP fees, spread, price impact, priority/network cost
assumptions, and failed/partial-exit risk where observable.

The three frozen cost scenarios are:

| Scenario | Fees RT | Spread/slippage | Failed/partial exit allowance |
|---|---:|---:|---:|
| Optimistic | 0.50% | 0.50% | 0.50% |
| Base | 1.00% | 2.00% | 2.00% |
| Stressed | 1.50% | 5.00% | 5.00% |

Missing historical route/depth is not treated as a successful exit. For
verified entries, missing pool/route becomes DEAD or UNEXITABLE as appropriate;
provider outage stays PROVIDER_UNAVAILABLE; end-of-collection censoring stays
UNKNOWN.

## WALK-FORWARD RESULTS

Not run. Required split is chronological 60% development / 20% validation /
20% untouched holdout, with horizon-based purge/embargo. Training examples
overlapping 48h/72h validation or holdout outcomes must be purged.

Required metrics, once data exists, are precision, recall, PR-AUC, base rate,
precision lift, calibration/Brier score, net expectancy after costs, false
positive rate, candidate count, MAE/MFE, dead/unexitability rate, top-1 and
top-5 P&L contribution, and temporal-block results. Accuracy is not an
acceptable primary metric for rare Runners.

## FINAL UNTOUCHED HOLDOUT

No final holdout exists. Holdout outcomes were not accessed, no thresholds were
tuned, and no result can be promoted. The manifest records `holdout_unlocked:
false`.

Minimum evidence gate remains frozen:

- at least 1,000 eligible launches;
- at least 200 holdout signal events;
- at least 90% coverage at every primary horizon;
- at least 200 resolved holdout 60m events;
- positive net expectancy under base and stressed costs;
- improvement over simple, activity/time-matched baselines;
- stable direction across temporal regimes and no tiny-winner dependence.

## FAILED / FALSIFIED HYPOTHESES

No hypothesis was fairly tested, so no new economic hypothesis is labeled
falsified. The following prior paths remain rejected for evidence reasons:

- current active-feed momentum/score pipeline: rejected as a validated strategy
  path by the reassessment report because it is not an early-launch universe and
  lacks valid primary outcomes;
- individual-wallet ranking/copying: deferred and not a valid inference from
  the current evidence;
- fixed +20%/60m exit as a Runner discovery tool: rejected as a design error,
  not as evidence that Runners do not exist;
- current DexScreener resolution as historical same-pool outcome: rejected as
  insufficient for this task.

## REMAINING BLIND SPOTS

- No complete PumpApi historical replay is present.
- No public corpus query was performed after reading its issues.
- Historical pool identity and reserves are not reconstructed.
- Historical fee schedules and route/failure behavior are not reconstructed.
- BOOST rollout dates and instruction-level generated-flow classification remain
  to be verified for the relevant period.
- Owner/cluster-adjusted holder concentration is unavailable in the NAVE panel.
- Participant funding and sybil relationships are not available.
- Market-regime controls cannot be computed from the current journal.
- Right-censored 48h/72h labels need a complete collection end and explicit
  censoring rules.

## NEXT HIGHEST-INFORMATION EXPERIMENT

Acquire the smallest contiguous PumpApi replay slice that contains enough
complete launches to test panel construction, then expand chronologically while
reserving the final 20% as untouched holdout. The first slice must validate:

1. event schema and timestamps;
2. mint/pool-epoch deduplication;
3. historical pool identity and reserve reconstruction;
4. quality flags and protocol-generated-flow exclusion;
5. 5m–72h right-censor handling;
6. one frozen trajectory clustering pass;
7. one participant point-in-time/realized-P&L audit;
8. the full relevant test suite and manifest checksums.

Only after that panel passes QA should the two heads, post-BOOST survival, sell
absorption, buyer turnover, and participant convergence be evaluated. The
correct current decision is no edge claim and no notification.

## REPRODUCIBILITY ARTIFACTS

- [M3 dual-horizon data manifest](m3-dual-horizon-data-manifest-20260831.json)
- [M3 experiment ledger](m3-experiment-ledger-20260831.json)
- [dual-horizon research primitives](../../../trading/memecoin/m3_dual_horizon.py)
- [dual-horizon invariant tests](../../../tests/test_memecoin/test_m3_dual_horizon.py)

Test result in the isolated worktree: `16 passed`; Ruff check passed after the
unused-import correction.
