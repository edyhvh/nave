# M3 reassessment and next bounded probe

Date: 2026-08-31
Scope: Hermes/Quant and NAVE only. No OpenClaw changes.
Mode: read-only research; no watchlist, orders, signing, or capital.

## Executive conclusion

**Current M3 momentum/score pipeline: REJECT as a validated strategy path.**

This does not prove that every memecoin strategy is impossible. It means the
current implementation cannot support a positive edge claim:

- The active-pair feed is not an early-token universe. It mixes fresh and old
  survivors because it sorts by recent trading activity; pair age is also used
  as a proxy for token age.
- The current journal contains 1,885 signals, 482 passed signals, and no
  resolved 7-day outcomes. At 24 hours, only 402 passed observations were
  resolved; their median return was approximately -99.92% and positive-return
  rate 8.71% before costs.
- A missing pair is currently recorded as `DATA_UNAVAILABLE`, so disappeared
  tokens are omitted from outcome metrics instead of being treated as losses or
  separately censored. This is a material survivorship/data-integrity defect.
- The current safety checks are useful triage, but several are proxies rather
  than proofs: largest token accounts are not owner/cluster-adjusted holders,
  a Jupiter route is not a completed buy/sell honeypot test, and non-Pump pairs
  are treated as locked without proving the actual LP lock/burn state.

**Wallet persistence: INCONCLUSIVE, not rejected.** The supplied 3/16 versus
775/1,667 comparison is directionally concerning, but the sampling frame,
denominator construction, wallet definition, and missingness mechanism must be
audited before assigning a scientific p-value. Individual-wallet ranking
should be deprioritized; behaviorally defined cohorts should be tested with an
activity-matched placebo.

**NEXT STATE: NEXT_BOUNDED_EXPERIMENT.** No WATCH and no trade.

## Short-term holding constraint

The intended strategy is **short term**, not buy-and-hold. The primary research
horizons are therefore 5 minutes, 15 minutes, 30 minutes, 60 minutes, and 4
hours. The 24-hour and 7-day outcomes remain only as context for delayed rug
risk, regime drift, and survivorship diagnostics; they must not force a long
holding period or gate a short-term decision.

The current pilot's weak 15m/60m coverage is consequently a first-order
blocker. More launches must be replayed before any short-horizon edge can be
judged.

## Hidden-gem search map

Treat “hidden gem” as a conditional, executable outcome rather than simply the
largest raw return:

1. **Coin branch:** identify tokens with early organic breadth and enough depth
   to survive a 5m–60m trade after costs.
2. **Trader branch:** identify repeatable owner/cohort behavior that predicts
   those short outcomes using only prior history; do not assume one wallet is
   one stable economic actor.
3. **Risk branch:** test whether early rug/unexitability detection has more
   stable value than upside prediction. Removing catastrophic losses may be
   useful even if the filter does not identify the biggest winners.
4. **Pullback branch:** after a verified early burst, test whether a controlled
   retracement with intact liquidity has a short rebound tendency. This is a
   separate contrarian hypothesis and must not be blended with launch momentum.

Keep these branches separate in evaluation. Combining weak signals into one
score before measuring them would hide whether any edge came from coin
behavior, trader behavior, or merely selection against obvious failures.

For the next coin-level paper replay, freeze one simple trade definition before
looking at validation or holdout outcomes: enter at the first complete 5-minute
post-migration window when the signal passes; take profit at +20%, stop at -15%,
and time-stop at 60 minutes. If target and stop occur on the same event, use
stop-first. Report mark-to-market returns at 5m/15m/30m/60m as well, but do not
change the fixed exit rule after observing results. This is a research
convention, not an execution recommendation.

### M2.6 data audit

The first short-horizon pass found that the existing M3 journal cannot execute
this protocol: it contains 1,885 scan observations but zero 5m/15m/30m/60m/4h
outcomes, no launch timestamp for 1,885/1,885 entries, and no pair address for
572/1,885 entries. Its 24h/48h values come from current market resolution and
are not same-pool historical outcomes. Result: **INCONCLUSIVE / BLOCKED — event
replay required**.

## Audit findings

| Finding | Classification | Consequence |
|---|---|---|
| M3 records one first observation per mint while scanning the active list | FACT | The journal is not a fixed-time early-launch panel |
| `SORT_ACTIVE=last_trade_timestamp` mixes new, graduated, and old active pairs | FACT | “Early” results are not identified cleanly |
| `age_minutes` is pair age, not reliably token age | FACT | Age rules can be misclassified |
| No-pair resolution becomes `DATA_UNAVAILABLE` | FACT | Missing outcomes can bias results upward |
| 7-day gate is 0/200 | FACT | M3 has not reached its stated validation gate |
| Small slices look better at older age, moderate FDV/liquidity, and negative recent momentum | INFERENCE | These are exploratory correlations and may be selection artifacts |
| A persistent-wallet signal is causal or tradeable | UNKNOWN | Requires a clean cohort test and placebo |

Local evidence was read from NAVE's ignored M3 artifacts, especially
`var/memecoin_m3/signal_journal.json` and `var/memecoin_m3/metrics_report.md`,
generated through 2026-08-31. These figures are gross provider returns, not
executable net returns.

## Next experiment: post-migration breadth and flow

### 1. Hypothesis and mechanism

**Hypothesis:** After a Pump.fun token migrates to a tradable pool, broad,
non-concentrated participation with positive net buy flow predicts better
short-horizon *executable* outcomes than a liquidity/age-only baseline.

**Mechanism (HYPOTHESIS):** broad participation may indicate organic demand;
positive flow may indicate continuation; concentration, bundles, creator-linked
activity, and bot-like timing may instead indicate temporary or controlled
volume.

**Falsification:** no positive net expectancy after costs, no improvement over
the baseline, the result disappears under reasonable cost assumptions or time
blocks, or performance is explained by one/few tokens or a single market regime.

### 2. Market and sample definition

- Ecosystem: Solana only.
- Venues: Pump.fun launch events and the first post-migration pool on
  PumpSwap/Raydium/Meteora when the pool can be reconstructed historically.
- Universe: all launches in the fixed replay interval, not the current active
  survivor list; one observation per mint.
- Observation: migration event plus the first complete 10-minute post-migration
  window. Token age must come from the creation event; pair age is not an
  acceptable substitute.
- Primary horizons: 5 minutes, 15 minutes, 30 minutes, 60 minutes, and 4 hours
  after the signal timestamp. Secondary context horizons: 24 hours and 7 days.
- Notional: paper-only $100, capped at 0.25% of reconstructed pool liquidity.
  If historical depth or price impact cannot be reconstructed, the result is
  `UNKNOWN`, not silently excluded.

### 3. Signal and gates

Pre-register one composite signal before reading holdout outcomes. The signal
must include, at minimum:

- unique buyers and sellers in the first 10 minutes;
- buy/sell SOL flow and trade count;
- largest buyer/trader share;
- creator/deployer-linked and bundle/cluster share;
- pool liquidity, reserve depth, spread, and estimated impact at the paper
  notional;
- mint/freeze authority and Token-2022 extension status;
- holder concentration using owner-level aggregation where possible;
- evidence of liquidity withdrawal or other pool-risk events.

Safety or execution data that is missing, stale, or contradictory is
`UNKNOWN`/`NEEDS REVIEW`; it does not pass the gate. Creator, bundle, bot, and
sybil indicators are exclusions or risk strata, not bullish signals.

### 4. Outcome and missingness rules

- Use the same historical pool or a deterministic venue-selection rule at entry
  and exit; do not select the most liquid current pair at resolution.
- Model fees, spread, slippage, and failed exits in three fixed scenarios:
  optimistic, base, and stressed.
- A token with no pool/exit route at a horizon is `DEAD`/`UNEXITABLE` and gets a
  -100% paper outcome unless the provider itself is demonstrably unavailable.
- Provider outage is a separate `DATA_UNAVAILABLE` status and must be reported
  with coverage by horizon.
- Preserve every eligible launch, including rejected and failed candidates;
  never resolve only the survivors.

### 5. Evaluation plan

- Source: PumpApi historical replay, with event timestamps and a documented
  latency buffer; corroborate bundle classification where possible.
- Split chronologically into 60% development, 20% validation, and 20% untouched
  holdout. Thresholds and feature transforms are frozen before holdout access.
- Compare against: all eligible launches, the existing age/liquidity-only
  baseline, and a placebo built from activity-matched wallets/cohorts.
- Bootstrap by launch hour/day, not by individual trade, because launches in a
  common regime are correlated.
- Minimum evidence gate: 1,000 eligible launches, at least 200 holdout signal
  events, at least 90% coverage at each primary horizon, and at least 200
  resolved 60-minute signal events. The 7-day count is reported as context,
  not as a requirement for a short-term strategy.

Proposed acceptance criteria, fixed before the run:

1. positive net expectancy in the holdout under base and stressed costs;
2. improvement over the baseline that survives time-block resampling;
3. no dependence on a single token, hour, venue, or market regime;
4. dead/unexitability and severe-loss rates are explicitly reported and do not
   make permanent-loss risk unacceptable;
5. if any criterion fails, classify `INCONCLUSIVE` or `REJECT`, not `WATCH`.

## Data sources and limitations

- PumpApi states that historical replay archives event-identical stream data
  from 2026-04-18 as hourly compressed JSONL files. Retrieval checked:
  2026-08-31 UTC. https://pumpapi.io/historical-replay
- PumpApi notes that bundles are not explicitly labeled and require heuristic
  grouping/cross-checking. Retrieval checked: 2026-08-31 UTC.
- Jupiter quote data exposes price impact and route fields, but a quote is not
  proof that a future exit will execute. Retrieval checked: 2026-08-31 UTC.
  https://developers.jup.ag/docs/swap/v1/get-quote
- Solana Token-2022 extensions can introduce transfer fees, permanent
  delegates, and other authority risks that must be checked explicitly.
  Retrieval checked: 2026-08-31 UTC.
  https://solana.com/docs/tokens/extensions
- Recent academic work supports testing wallet cohorts with matched placebos,
  but it is a preprint and is not evidence that this NAVE implementation has an
  edge. Retrieval checked: 2026-08-31 UTC.
  https://arxiv.org/abs/2607.02795
- A recent Solana preprint studies first-five-minute features for early rug
  detection and reports that rug characteristics often appear within the first
  hour. This is a research direction, not validation of a trading edge.
  Retrieval checked: 2026-08-31 UTC.
  https://arxiv.org/abs/2608.20271

## Implementation order for Hermes/NAVE

1. Freeze this protocol and record the exact replay interval and data version.
2. Correct outcome accounting so no-pair outcomes cannot disappear from the
   denominator; add regression tests for `DEAD`, `UNEXITABLE`, and provider
   outage.
3. Build the deterministic full-launch event panel and deduplicate by mint.
4. Compute the single pre-registered cohort/flow signal and baseline.
5. Resolve fixed horizons, publish coverage and missingness tables, then run
   the chronological holdout.
6. Return the required Quant report. Do not create a watchlist unless every
   safety, data-quality, and validation gate passes.

## Ideas explicitly deferred

- Individual-wallet copy/ranking: defer until cohort definitions and placebo
  controls are sound.
- Social/X/Telegram scraping: not needed to fix the current on-chain/data
  defects; revisit only after a clean on-chain baseline.
- TON: defer until equivalent historical event, authority, liquidity, and
  execution data are available.
- Parameter search across many score bands: prohibited until the split and
  multiple-testing plan are frozen.
