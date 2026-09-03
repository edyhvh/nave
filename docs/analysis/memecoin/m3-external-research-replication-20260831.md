EXTERNAL RESEARCH LAYER PARTIALLY VALIDATED

# NAVE external research replication and signal discovery — 2026-08-31

## Executive result

The external research layer is partially validated as a methodology and audit
layer. It is not a validated predictive layer and no edge claim is made.

The highest-value conclusions are negative or structural:

1. RED-COHORT's current revision confirms that naive cohort-flow contrasts are
   vulnerable to participant self-flow and activity selection. Its published
   adjusted result is materially smaller than its naive result, and the paper
   treats the activity-matched placebo as a bias diagnostic rather than a clean
   null.
2. RED-PUMP v1.4 must not be used as evidence of a true 24-hour graduation
   rate. Its observer was a top-50 poller with a roughly six-minute effective
   visibility window; the virtual-reserve recovery estimate was withdrawn.
3. Trenches supplies the right leakage standard: every feature block needs a
   derivability timestamp, not merely an event timestamp.
4. MELT supplies useful feature families—typed swaps, transfers, wash traces,
   bundles and fund flow—but its CC-BY-NC license and very large artifacts mean
   NAVE should reimplement generic ideas independently.
5. PumpApi is a plausible low-cost raw-event audit source, but this iteration
   only verified archive reachability and the documented schema. It did not run
   an event-agreement test.

The seven-mint NAVE continuation is adequate to prove machinery, not signal
discovery. Raw first-30-minute flow contains 2,367 trades, including 1,107
trades from the locally identified first-ten buyer wallets. Raw buyer and flow
outcomes are therefore contaminated unless participant-excluded outcomes are
reported alongside them.

## External source registry

The full machine-readable registry is in
`external-research-registry-20260831.json`. Sources remain separate datasets;
no external rows were merged into NAVE. The reviewed set contains ten entries:
the prior Dune panel, Slinky21, RED-PUMP, RED-COHORT, PRFS, RED-2400, Trenches,
MELT, PumpApi replayer, and Graduate Oracle.

Evidence is tiered: A independently reconstructed on-chain events; B
reproducible published observations; C derived benchmarks; D third-party model
scores; E anecdotal claims. Dune is the current canonical local source. RED-
COHORT and RED-2400 are benchmarks, not NAVE labels. Graduate Oracle is a
future external baseline, not a model input.

## Slinky21 research update

**SLINKY RESEARCH STATUS: ACTIVE.** The Hugging Face release was modified on
2026-08-02 and its README still describes three research programs as in
progress: rug-risk/survival, first-10-minute graduation prediction, and creator
economics. No linked completed papers from the maintainer were located in this
pass; the README says citations are pending. The public author reference is
`Slinky21` / `Slink Dev (slink21taken)`; no personal identity was inferred.

NAVE can learn from Slinky’s schema and quantified issue handling: launch-time
metadata, first-seconds trade flow, curve snapshots, creator history, holder
concentration, regime segmentation, and explicit data-quality flags. It cannot
use stale `wallet_stats`, known leaking curve-balance fields, or the supplied
outcomes as canonical truth. There is also a license conflict: the dataset card
says MIT while the README says CC-BY-4.0. Until clarified, NAVE should inspect
methodology only and avoid redistributing it.

## RED-PUMP lessons

RED-PUMP-2026-v1.4 is a useful launch-metadata benchmark, not a graduation
ground truth. Candidate replication variables are on-chain creation time,
observer delay, initial market-cap proxy, description length, and presence of
Twitter/X, website, and Telegram links. NAVE can independently reconstruct the
on-chain fields and, if metadata URI retrieval is used, must timestamp the
availability of each social field.

Replication hypotheses are:

- H_META_01: metadata completeness changes graduation/survival rates after
  controlling for initial curve state and launch hour.
- H_META_02: metadata adds information beyond bonding-curve flow.

These are explanatory hypotheses, not causal claims. Social presence may proxy
for preparation, marketing, coordination, creator sophistication, or fraud.
The v1.4 corrigendum withdraws the virtual-reserve “ceiling crossing” recovery;
the true 24-hour rate is unknown from that release. NAVE will not import its
published social lifts or graduation labels.

## RED-COHORT replication

The current 8.4 MiB RED-COHORT v1.0.1 archive was downloaded within budget.
The catalogue contains 1,012 cohorts, 2,965 unique wallets, sizes 2–12, and
launch-hit counts 3–42. The release’s detector is a two-stage first-buyer
window plus cross-launch co-occurrence graph with union-find and a minimum edge
weight. It labels repeated co-occurrence, not proven economic identity.

Exact independent reproduction is **partial**. The released
`sniper_cohorts_intra.jsonl.gz` contains co-fire group observations, while the
published detector expects complete buyer-event JSONL with mint, wallet, slot,
blockTime, SOL input, signature, and buyer rank. Without the full input, exact
catalogue reproduction cannot be claimed. There is no temporal overlap with
the NAVE 2026-08-27 sample, so direct cross-dataset validation is invalid.

NAVE’s independent graph helper is implemented and deterministic. It produces
`REPEATED_COHORT` and explicitly sets economic-cluster proof to false unless
funding/bundle evidence exists. The current seven-mint targeted slice produced
no repeated cohort at a two-shared-launch threshold; this is a sample-size
result, not evidence of absence.

## Cohort contamination analysis

For each target mint, the first ten unique buyers are treated as triggering
participants for an audit only. In the first-30-minute targeted slice:

| Flow view | Trades | Buyers | Buy SOL | Sell SOL | Net SOL |
|---|---:|---:|---:|---:|---:|
| Raw total flow | 2,367 | 655 | 531.869 | 274.690 | 257.179 |
| Participant self-flow | 1,107 | 70 | 131.529 | 133.195 | -1.666 |
| Participant-excluded flow | 1,260 | 585 | 400.341 | 141.496 | 258.845 |

This proves the reusable accounting primitive and why raw buyer flow is not an
exogenous outcome. It does not estimate a cohort effect: the sample has seven
tokens, no activity-matched controls, no complete outcome panel, and no
economic-actor identity evidence.

## PRFS / rejection audit design

PRFS is adopted as a core NAVE principle. The new helper
`post_rejection_followup_audit` records candidate state before the gate, gate,
timestamp, PASS/REJECT, reason, future observation count, and future outcome.
It is provider-agnostic and offline. The correct future replay must retain all
rejected candidates, including dead, unexitable, unclassifiable, and censored
states. The helper is tested but no NAVE historical gate log currently exists,
so the false-negative audit is **partial**.

For each future filter, NAVE will report accepted and rejected counts, Burst and
Runner rates, dead/unexitability rate, median and tail return, false negatives,
and false positives. Marginal effects will be conditional on the prior gates,
not attributed to every filter simultaneously.

## RED-2400 lessons

RED-2400 and its small MIT replication toolkit were reviewed; the 33 MB dataset
was not downloaded because it is a methodology benchmark rather than a needed
NAVE input. Adopted elements are the five-tier outcome state, missed-over-saved
precedence, graveyard/death tracking, fixed forward windows, per-filter audit
tables, and reproducibility fixtures. NAVE will not merge RED-2400 labels with
the Dune day or claim replication across regimes.

## Trenches leakage audit

Trenches’ defining contribution is a per-field `tau__` derivability timestamp,
with a forward-only split and embargo. Its metadata was inspected without
downloading the 46 MB observations file. The NAVE helper
`validate_feature_derivability` enforces:

`feature_available_at <= decision_time`.

Missing timestamps are `UNKNOWN`; future availability is `LEAKED_FEATURE`.
`derive_available_at` adds source latency and never lets local derivation move
availability earlier. A 20-row on-chain timestamp audit passed 20/20, but this
is a contract test, not a provider-latency validation. Future NAVE rows should
carry `observed_at`, `available_at`, `source_latency_ms`, and `derived_at`.

## MELT coordination features

MELT’s paper, README, license, and feature-generation code were inspected. The
useful feature families are typed buy/sell/transfer/mint behavior, wash-trade
counts, same-bundle accounts, common funders, linked-account clusters,
accumulation concentration, timing, and coordinated exits. These map into a
future `CoordinationEvidence` schema with each field marked OBSERVED, INFERRED,
or UNKNOWN.

No MELT archive or pre-generated feature file was downloaded. The repository
uses CC-BY-NC-4.0 and advertises >1 TB raw transactions plus large Google Drive
artifacts. NAVE will implement generic graph and flow mathematics independently
and preserve attribution; no MELT code or data enters core NAVE.

## PumpApi replayer feasibility

The public replayer repository documents streaming hourly `.jsonl.zst` archives,
bounded sliding storage, create/buy/sell/migrate events, reserves, pool, block,
priority fee, post-balance, and trader fields. A HEAD request to a June 2026
archive returned HTTP 200, but the response did not provide a usable
`Content-Length`. No archive was downloaded and no event-agreement test was
run. Schema aliases are needed because `txType`/`solAmount`/`solInPool` were
renamed to `action`/`quoteAmount`/`quoteInPool`.

Classification: **AUDIT ONLY** this iteration. It is promising as a possible
independent raw-event source, but Dune overlap rates for mint, timestamp,
signature, side, amount, wallet, and reserves remain unmeasured.

## Graduate Oracle baseline

The public repository documents a moving calibrated-GBM/isotonic cascade,
historical curve matching, buyer-quality fields, forward predictions, and
graduation calibration. Exact weights and bot thresholds are proprietary.
NAVE will use any later public snapshot only as a competitor baseline, alongside
random, activity/time-matched, momentum, buyer acceleration, curve progress,
and liquidity/volume baselines. It is not a NAVE input, and no account or API
was created.

## Participant reputation model

`beta_binomial_reputation` is implemented with explicit successes/failures,
sample size, posterior estimate, 95% interval, and top-winner dependence. It
uses only explicit outcome labels and excludes future rows at `as_of`; missing
outcomes are not failures. This prevents 2/2 from automatically outranking
35/100. The acquired NAVE episodes lack complete future success labels, so
participant reputation is **INSUFFICIENT DATA**.

## Matched-control design

Treatment will be participant presence, convergence, or participant-excluded
flow at a frozen decision time. Controls will match activity frequency,
launch-hour exposure, market regime, age, initial state, prior return/volume,
unique buyers, curve progress, buy/sell balance, and creator/metadata fields
when legitimately available. The offline matcher is deterministic and avoids
control reuse. Propensity-score matching with calipers and balance reporting is
designed but not run: one day, seven targeted mints, and incomplete outcomes do
not support it.

Placebos will include random wallets, activity-matched wallets, time-shifted
events, permuted identities, and same-activity tokens without treatment.
Leave-one-out checks will remove the top wallet, top five, top cohort, and
largest winning token. These are diagnostics; none establishes causality alone.

## Precursor event design

The future panel preserves T-60s, T-30s, T-15s, T-5s, T0, T+5s, T+15s,
T+30s, T+60s, and T+5m around participant entry. Candidate features are new-
buyer acceleration, sell absorption, curve acceleration, liquidity/reserve
change, trade-size distribution, creator activity, independent volume, and
cohort activity. Event time and NAVE availability time remain separate.

## Signal discovery status

**PARTICIPANT SIGNAL: INSUFFICIENT DATA.** The seven-mint targeted data prove
that participant-excluded flow can be reconstructed, but they cannot measure
incremental information above token state. The 1,000-launch token panel is
descriptive only, has one calendar day, and has incomplete multi-day Runner
coverage. No substantive model was fit.

**FILTER FALSE-NEGATIVE AUDIT: PARTIAL.** The PRFS machinery is ready, but a
historical candidate/gate/reason/outcome log is not present.

No current external claim is promoted to a NAVE signal. The external
classification is therefore `INSUFFICIENT DATA` for participant signal, not
`WEAK / UNSTABLE SIGNAL` or `PROMISING EXPLORATORY SIGNAL`.

## License / IP risks

The registry records MIT, CC-BY, CC-BY-NC, and PolyForm Noncommercial terms.
The two highest-risk items are Slinky’s unresolved card/README conflict and
RED-COHORT’s patent notice. MELT and Trenches are non-commercially licensed.
NAVE may study ideas and independently reimplement generic mathematics, but
should not copy MELT or Trenches code/data into production. Future commercial
use requires legal review of all external artifacts and RED-COHORT patent
scope.

## Dune credit usage

Starting usage was 1,863.570 consumed of 2,500 included, leaving 636.430.
This iteration ran no new Dune query and used **0.000 new credits**. The
optional second calendar day was not acquired. The sample’s temporal and
participant limitations make a second compact day useful later, but not enough
to justify spending before the next experiment is frozen. If run later, keep
it below 75 credits and use compact first-hour aggregates plus migration-first
targeting only.

## Helius decision

**USEFUL LATER, NOT REQUIRED NOW.** PumpApi may independently fill typed raw
events, priority fees, post balances, and reserves. Helius remains the likely
future source for independent PumpSwap reserve/depth validation, failed
transaction/exit validation, funding chains, Jito/bundle evidence, and BOOST
instruction attribution if neither Dune nor PumpApi supplies them. No Helius
account, key, or request was used.

## Multi-chain relevance

PRFS, derivability auditing, activity matching, cohort graph construction, and
survival analysis are chain-neutral. The previous feasibility result remains:
Base/Clanker is a promising partial adapter; BNB/Four.meme lifecycle semantics
are unresolved; TON is currently insufficient. External research does not
change that conclusion and no multi-chain panel was built.

## Highest-information next experiment

Acquire one compact, deterministic second calendar-day Pump.fun sample only
after freezing the measurement contract: first-hour token features, migration
map, participant-excluded flow, and explicit `available_at`. Compare a
token-only descriptive model with a participant-augmented model across the two
days using a chronological split, activity/time-matched controls, and no raw
event export. Estimate cost before execution and cap it at 75 Dune credits.

This is a temporal sanity check, not a strategy backtest. It should be stopped
if the compact cost estimate or data coverage exceeds the cap.

