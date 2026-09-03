STATISTICAL SIGNAL SANITY INCONCLUSIVE

# NAVE M3 Statistical Signal Sanity Check — 2026-08-31

## EXECUTIVE RESULT

The experiment infrastructure is partially exercised, but the statistical
comparison is inconclusive. Day 2's complete launch denominator and
outcome-independent 1,000-mint sample were acquired. The selected first-hour
event query then consumed the remaining iteration budget through an unexpected
cost path and no Day 2 event panel was exported. Consequently A/B/C/D scores,
bootstrap differences, matched controls, and temporal stability were not
estimated. No edge is validated.

The valid evidence remains structural:

- Day 1 has descriptive first-hour mark proxies, not executable returns.
- The previously audited targeted slice contained 1,107 participant-self-flow
  trades out of 2,367 first-30-minute trades (46.8%); raw flow is not exogenous.
- Day 1's compact panel has only 60-minute aggregate state, so using it at a
  1m/3m/5m/10m decision point would violate the frozen feature contract.
- Participant reputation, matched controls, placebos, leave-one-out, and
  Runner continuation remain data-blocked rather than negative findings.

## EXPERIMENT CONTRACT

The frozen contract is
[`m3-signal-sanity-contract-20260831.json`](m3-signal-sanity-contract-20260831.json),
with feature definitions in
[`m3-feature-contract-20260831.json`](m3-feature-contract-20260831.json).
Decision times are 1m, 3m, 5m, and 10m. Day 1 is development/exploratory and
Day 2 is chronological sanity validation. The four information sets are:

| Set | Information | Status |
|---|---|---|
| A | token state only | Day 1 descriptive inputs exist; frozen decision-time rows unavailable |
| B | A + point-in-time participant information | not fit; full-cohort matured reputation absent |
| C | A + precursor microstructure | not fit; Day 2 event panel absent and Day 1 precursor coverage targeted |
| D | A + precursor + participant information | not fit |

Primary comparisons are B−A, C−A, D−C, and D−B. A score difference is not
reported when the chronological validation sample is zero.

## SECOND-DAY ACQUISITION

Selected date: **2026-08-28 UTC**. It is adjacent to Day 1, historical, has a
72-hour look-ahead by the run date, and is outside the documented July outage
period. The complete denominator returned 48,330 launches. The deterministic
SHA-256 sample (`nave-2026-08-27-v2`, ascending digest then mint) returned
1,000 mints. Selection was independent of outcomes and retains dead,
inactive, failed, non-migrated, migrated, and censored candidates in the
denominator.

The selected first-hour event extraction was attempted twice after the first
attempt exceeded the local command wait. The result was not exported. Dune
usage increased past the iteration cap before the selected event panel could
be materialized; therefore Day 2 has **0 usable event-panel rows** for this
experiment. The denominator and selected-mint metadata are retained locally
as acquisition evidence only.

## DUNE CREDIT USAGE

| Measurement | Consumed credits |
|---|---:|
| Start, recorded before calls | 1,863.570 |
| After Day 2 denominator | 1,915.196 |
| After selected-event attempts | 1,979.104 |
| New usage this iteration | **115.534** |
| Included balance remaining | **520.896** |

The requested iteration hard stop was 75 credits and the single-query target
was below 5 credits (single-query hard stop 15). The denominator stage alone
cost 51.626 credits, and the selected-event attempts cost 63.908 credits in
aggregate. No further Dune calls, result exports, credit purchases, upgrades,
or reruns were made. The prior giant `50_windows` query was not rerun.

## FEATURE SET A — TOKEN ONLY

The prior Day 1 descriptive panel contains 1,000 token rows, 917 with
first-hour trades, and 887 usable first-hour mark-return proxy rows. Its
proxy distribution was median 1.99%, mean 47.46%, and +100%/+200%/+500%
counts of 110/53/19. These are quoted mark proxies, not executable returns.

A point-in-time token-only model at the frozen 1m/3m/5m/10m decisions was not
fit: the acquired Day 1 compact panel exposes 60-minute aggregates, and the
Day 2 event panel is unavailable. This prevents silent look-ahead.

## FEATURE SET B — TOKEN + PARTICIPANT

Not fit. The targeted Day 1 participant slice covers 7 migrated mints, about
2,367 Pump.fun first-hour events, 1,786 wallet-token episodes, and 1,666
wallets. It is not a full 1,000-launch participant panel, and the available
episodes do not provide a statistically mature, point-in-time reputation
history. Unknown outcomes remain unknown rather than failures.

## FEATURE SET C — TOKEN + PRECURSOR

Not fit. Precursor features require ordered event history ending at each frozen
decision time. The Day 1 event file is targeted to migrated mints, and the Day
2 selected event extraction was not recovered. T+ windows remain diagnostics,
not predictive features.

## FEATURE SET D — FULL

Not fit. There is no valid chronological Day 2 matrix containing both
precursor and participant features. No in-sample ranking is promoted as
evidence.

## A VS B

**INCONCLUSIVE / insufficient data.** No out-of-sample delta PR-AUC, Brier,
calibration, log loss, precision lift, or ranking delta is available. The
participant addition cannot be assessed.

## A VS C

**INCONCLUSIVE / insufficient data.** Precursor addition cannot be assessed
without event-level rows at the frozen decision times and a chronological
validation panel.

## C VS D

**INCONCLUSIVE / insufficient data.** The central test of participant
incremental information after precursor state was not reached.

## B VS D

**INCONCLUSIVE / insufficient data.** The precursor addition after participant
information was not reached.

## SELF-FLOW CONTAMINATION

The prior targeted audit found 1,107 of 2,367 first-30-minute trades
attributable to the locally selected first-ten buyer wallets: 46.8%. The
previous reported flow table was:

| View | Trades | Buyers | Buy SOL | Sell SOL | Net SOL |
|---|---:|---:|---:|---:|---:|
| Raw total | 2,367 | 655 | 531.869 | 274.690 | 257.179 |
| Participant self-flow | 1,107 | 70 | 131.529 | 133.195 | -1.666 |
| Participant-excluded | 1,260 | 585 | 400.341 | 141.496 | 258.845 |

This is classified **SELF-FLOW CONTAMINATED** for naive raw participant-
related flow interpretation. It is not a participant edge or causal result.
The new helpers and tests preserve raw and exogenous variants.

## ACTIVITY-MATCHED CONTROLS

Not run. Full participant treatment rows and Day 2 outcomes are unavailable.
The deterministic activity matcher exists and passes offline tests; planned
matching variables remain activity count, launch exposure, time-of-day,
prior eligible entries, token age, curve state, prior return/volume, buyers,
imbalance, launch hour, protocol state, and market regime.

## PLACEBO TESTS

Not run on outcomes. Deterministic identity permutation is implemented and
tested, but a placebo score without a valid Day 2 outcome panel would be
misleading. Time-shifted arrivals and activity-matched random wallets are
deferred.

## LEAVE-ONE-OUT

Not run on model results because no model result exists. The offline helper
supports top-wallet removal; top five wallets, top winner token, largest cohort,
and identity-free archetype checks remain pending a valid participant panel.

## TOP-WINNER DEPENDENCE

For the Day 1 descriptive mark proxies, the top-1 proxy contributed about
3.18% of the sum of positive proxy returns and the top-5 contributed about
12.51%. This does not make the proxies executable or predictive, and no
model is called promising from this distribution.

## SELL-SHOCK ABSORPTION

Not evaluated. The planned shock size, drawdown, 30s/60s/120s recovery,
participant-excluded new demand, reserve recovery, and future mark outcome
require event-level rows plus matched controls. Classification:
**INSUFFICIENT DATA**.

## TEMPORAL STABILITY

**INSUFFICIENT.** Day 1 development data exist only as a compact aggregate /
targeted event package. Day 2 has denominator/sample metadata but no usable
event panel or outcomes. Two calendar days therefore do not yet provide a
directional temporal comparison.

## RUNNER COVERAGE

**BLOCKED.** Day 1 has only 7 migrated targeted continuations, with Pump.fun
long-horizon marks sparse (4h/24h/48h/72h resolved rows 7/2/1/0 in the
1,000-token panel). Day 2 continuation was not acquired. Graduation is not
called Runner success.

## POST-REJECTION STATUS

**BLOCKED BY HISTORICAL GATE LOGGING.** Scanner code exposes aggregate
`passed`/`skipped_reason` values and archive snapshots, but this worktree does
not contain a stable historical per-gate contract with candidate state,
gate-name, decision timestamp, reason, and future outcome. No rejection audit
was fabricated. The required future logging contract is:

`candidate_id, mint, decision_time, candidate_state_before_gate, gate,
decision(PASS|REJECT), rejection_reason, feature_snapshot, available_at,
future_observation_end, outcome_status, censor_reason`.

## PUMPAPI AUDIT STATUS

**NOT TESTED.** Archive reachability and schema feasibility were previously
recorded, but no event-agreement download was attempted in this iteration.
The next raw-data audit should be considered only after the Dune cost path is
understood.

## HELIUS DECISION

**USEFUL LATER, NOT REQUIRED NOW.** The gaps that would matter later are
independent PumpSwap reserve/depth validation, failed exits, priority/Jito or
bundle evidence, funding/economic-actor clustering, and BOOST attribution.
None is needed to explain the current blocker, which is temporal event-panel
acquisition and Dune cost behavior.

## HYPOTHESIS LEDGER

| ID | Classification |
|---|---|
| H_PART_01 | INSUFFICIENT DATA |
| H_PREC_01 | INSUFFICIENT DATA |
| H_REDUNDANCY_01 | INSUFFICIENT DATA |
| H_ABSORB_01 | INSUFFICIENT DATA |
| H_SELF_FLOW_01 | SELF-FLOW CONTAMINATED / machinery evidence only |
| H_REJECT_01 | BLOCKED BY HISTORICAL GATE LOGGING |

## FINAL QUESTIONS

1. **Does token-only state contain useful descriptive information?** Limited
   descriptive information exists in Day 1 mark proxies; predictive usefulness
   at a valid decision time is untested.
2. **Do participant features improve over token-only state?** Inconclusive;
   no valid comparison.
3. **Does precursor microstructure improve over token-only state?** Inconclusive;
   no valid chronological event panel.
4. **Does participant identity still add information after precursor features?**
   Inconclusive; Model D was not estimable.
5. **How much naive participant signal disappears after self-flow exclusion?**
   46.8% of targeted first-30-minute trades were self-flow; the raw flow
   contrast must be treated as contaminated. The exact apparent model delta
   was not estimable.
6. **Does the signal direction survive from Day 1 to Day 2?** Insufficient;
   Day 2 outcomes/events are unavailable.
7. **Is any result dependent on one wallet or one token?** No model result was
   obtained; top-winner proxy dependence is separately reported, and wallet
   leave-one-out is pending.
8. **Is participant reputation statistically mature enough to continue?** No;
   not with this panel. Continue only after a full point-in-time, multi-day
   matured history is acquired.
9. **Is Runner research still blocked by continuation coverage?** Yes.
10. **Is PumpApi worth using as the next raw-data audit?** Not yet; first
    repair or preflight the Dune cost path, then run one tiny overlap audit.
11. **Is Helius needed now?** No; useful later for the specific depth/failure/
    funding/bundle/BOOST gaps above.
12. **What ONE next experiment has the highest expected information value?**
    Run one tiny, server-side compact Dune aggregate with explicit cost
    preflight and no raw export, then re-acquire the same 2026-08-28 sample
    only if its measured cost is below 15 credits; this directly tests whether
    a corrected acquisition path can unlock the temporal A/B/C/D experiment.

## CLASSIFICATION

This iteration is **STATISTICAL SIGNAL SANITY INCONCLUSIVE**. The appropriate
economic classifications are INSUFFICIENT DATA, SELF-FLOW CONTAMINATED, and
BLOCKED BY OUTCOME COVERAGE. It does not change NAVE's status: **NO EDGE
VALIDATED**.
