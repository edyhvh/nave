STOCKS: BTC 63k–78k missed-move diagnosis and experiment plan

# Decision

**REVIEW — do not promote or retune a strategy from this case.**

The miss has two different causes that must not be conflated:

1. **Actual operational cause:** Nave did not have the present end-to-end stack during most of the move. The first 1H/4H momentum module arrived on 2026-03-31, theory v2 on 2026-04-11, the COT gate on 2026-04-15, agent exposure on 2026-04-21, the current momentum engine on 2026-04-28, and entry-zone alerts on 2026-05-07. The BTC reference move had already closed above 78k on 2026-04-22.
2. **Counterfactual strategy cause:** when today's engine is replayed with only information available at each timestamp, the price stack does not become fully confirmed until BTC is 77,345. The COT extreme-long rule then hard-blocks that mature long. Disabling COT alone produces a first tradeable plan at 77,345, after 93.5% of the 64,133-to-78,261 path is complete. COT is therefore the final veto, but not the reason the model was late from 64k to roughly 75k.

No live order, strategy promotion, or execution change is recommended.

## Scope and as-of

- Research as of: **2026-08-21 10:43:52 UTC / 12:43:52 CEST**.
- Repository: `d0323edf8b0f52e0201268fe18ff7c2f79e43cf1` in the clean portfolio-integrity worktree.
- Price source: Hyperliquid `candleSnapshot`, which documents the POST info endpoint, candle schema, supported 1H/4H/1D intervals, and a 5,000-candle availability limit.[1]
- COT source: Nave's local CFTC futures-and-options history cache, originally built from the CFTC annual historical files; CFTC publishes the annual combined files by year.[3]
- COT availability correction: Tuesday report dates were shifted to the official Friday 15:30 America/New_York publication time. CFTC states that Friday releases normally contain the previous Tuesday's data.[2]
- Point-in-time rule: only fully closed 1D, 4H, and 1H candles and fully completed W-SUN bars were eligible.
- Funding and open-interest snapshots for the historical timestamps were not available. They were passed as missing and the replay is explicitly **not execution-valid**.

Reproducible artifacts:

- `scripts/btc_missed_move_replay.py`
- `docs/analysis/raw/btc_missed_move_replay_20260821.json`
- Prior contaminated case analysis: `docs/analysis/iterations/iter_16.md` and `iter_18.md`

# 1. Case definition

Hyperliquid observations:

| Observation | UTC timestamp | BTC price |
|---|---:|---:|
| Intrabar low | 2026-02-06 00:00 4H bar | 60,000 |
| Reference start close | 2026-02-06 03:59:59.999 | 64,133 |
| First 4H close at or above 78k | 2026-04-22 11:59:59.999 | 78,261 |
| Subsequent case high | 2026-04-27 00:00 4H bar | 79,434 |

The reference close-to-close move was **+22.03%**. The commonly used “63k–78k” label is directionally correct but imprecise; this report uses 64,133 and 78,261 so latency calculations are reproducible.

# 2. What Nave could actually know at the time

## Deployment chronology

| Date | Available component | Consequence |
|---|---|---|
| 2026-02-06 | No committed 1H/4H momentum strategy | No systematic signal or alert existed at the reference start. |
| 2026-03-31 | `8ce23bb` adds the original momentum/volatility/liquidity strategy | It required an operator-supplied `--liquidity-pulse`; there was no canonical data source, scheduler, entry zone, or alert. |
| 2026-04-05 to 2026-04-08 | COT and historical theory tools arrive | Research became possible, but not yet a unified operator path. |
| 2026-04-11 | `6bc37e0` adds theory v2 | Weekly/daily/4H/1H gates became code, after much of the move. |
| 2026-04-15 | `98b5729` integrates the weekly COT gate | Extreme non-commercial longs could block fresh long signals. |
| 2026-04-21 | `f0ecd86` diagnoses this rally; `8a76f3a` exposes theory to Hermes; `ce226a5` adds the range-breakout fallback | The case had already been observed and was therefore in-sample for the new fallback. |
| 2026-04-22 | BTC first closes above 78k | Target reference reached. |
| 2026-04-28 | `5f61a73` adds the current momentum production surfaces | Too late for this move. |
| 2026-05-07 | `d3c921d` adds entry-zone monitoring | Too late for this move. |
| 2026-06-02 | `b8b7900` adds regime analysis and the current COT overlay | The current regime layer cannot have caused the February–April miss. |

The March 31 historical strategy was replayed at its commit time using the exact committed code. With a neutral or positive manually supplied liquidity pulse, its **1H** output was long; the **4H** output remained neutral for every pulse in the tested `[-1, -0.5, 0, 0.5, 1]` grid. This does not prove an actionable signal existed: the liquidity pulse was a required manual input with no archived value, and the module had no concrete entry or alert path.

## Hindsight boundary

`iter_16.md` correctly identified the range-breakout pattern on 2026-04-21. The range-breakout fallback added the same day in iter 18 was then validated on a pool that included the motivating case and gained one BTC winner. That is a regression test, not untouched validation. Its “strict Pareto improvement” language must not be used as evidence of a general edge until a locked out-of-sample period passes.

# 3. Point-in-time replay of today's engine

This is a diagnostic counterfactual. It answers “which current gates would suppress the case?” It does not claim those gates were deployed at the time.

| UTC checkpoint | Price | Price evidence | Score | Theory | COT | Result |
|---|---:|---|---:|---|---|---|
| 2026-02-06 03:59 | 64,133 | Daily/4H/breakout/participation all false | 48 | Weekly bias conflicts with long | Caution, P44 | Invalid |
| 2026-03-31 19:59 | 67,803 | Daily/4H/breakout/participation all false | 45 | Weekly neutral deferral | **Block, P91** | Invalid |
| 2026-04-06 19:59 | 69,706 | 4H trend, breakout/retest, volatility, and participation pass; daily trend fails | 74 | Weekly neutral deferral | **Block, P94** | Invalid |
| 2026-04-13 19:59 | 73,267 | 4H trend only; no fresh breakout/retest or participation | 40 | Weekly neutral deferral | **Block, P97** | Invalid |
| 2026-04-15 23:59 | 74,774 | Daily trend first passes, but no fresh breakout/participation | 44 | Weekly neutral deferral | **Block, P97** | Invalid |
| 2026-04-17 19:59 | 77,345 | Daily + 4H + structure + breakout/retest + volatility + participation pass | 90 | Weekly neutral deferral | **Block, P90** | Confirmed but not tradeable |
| 2026-04-22 11:59 | 78,261 | Daily + 4H + breakout/retest + volatility + participation pass; structure fails | 80 | Weekly neutral deferral | **Block, P90** | Invalid |

Important timing results:

- Theory first stopped opposing/deferred neutrally on 2026-03-09 at 67,170, when only 21.5% of the reference move was complete. Other price gates still failed.
- The clearest early transition appeared on 2026-04-06 at 69,706, when 39.4% of the move was complete. It missed the 78 score threshold by four points, failed the daily hard gate, and was blocked by COT.
- Daily trend first passed at 74,774, when 75.3% of the move was complete.
- The first fully confirmed price plan appeared at 77,345, when 93.5% of the move was complete.
- Production gates produced **no tradeable long** and therefore no tradeable entry-zone watch during the case.
- With COT disabled for attribution only, the first tradeable long appears at 77,345. Its entry zone is 75,705–76,927 while spot is already 77,345, so it is not an immediate zone-touch execution.

## Layer-by-layer diagnosis

### Data — material integrity gap

Evidence:

- `trading/crypto/momentum/service.py:323-365` loads historical OHLCV but fetches the **current** funding rate and only the latest 30 open-interest points.
- `trading/crypto/momentum/backtest.py:108-117` reuses those same funding/OI values at every historical bar.
- `backtest.py:93-107` slices frames by candle-open index, so the final 4H candle and current daily candle may contribute completed OHLC values before their real close.
- `backtest.py:234-283` assumes the plan enters at its zone on the next trigger bar without first proving that market price touched the zone.
- `trading/crypto/cot/cot_gate.py:94-100` filters COT by report date, not release availability; without the replay's Friday shift, historical evaluation can see Tuesday positioning before publication.

Inference: existing historical performance metrics are useful research clues but are not yet promotion-grade because candle availability, derivatives context, and fills are not fully causal.

### Regime — not a cause of this miss

The current regime module was committed on 2026-06-02. It cannot explain a February–April operational miss. In today's counterfactual stack, weekly theory is neutral from March 9 onward and does not block the eventual April 17 price setup.

### Momentum/structure — primary source of latency

The model requires a full daily EMA trend, 4H trend, swing structure, recent 4H breakout, 1H retest, volatility, participation, risk/reward, score, theory, and COT. On April 6 the market already had a credible 4H transition, but the daily trend had not flipped and score was 74. Full conjunction arrived only on April 17.

This supports testing a separate **transition WATCH lane**, not lowering every threshold and not treating the April 6 row as an ENTER retrospectively.

### COT — final veto, not complete root cause

COT shifted from caution around P44 at the start to hard blocks around P90–P97 during the advance. Once price confirmation matured on April 17, COT was the only remaining hard veto. That is a genuine interaction problem: a contrarian extreme can remain bearish while price is demonstrating a breakout or short squeeze.

One winner does not falsify contrarian COT. The falsifiable question is whether a hard block should become a risk/sizing caution **only after** a pre-registered price-transition condition passes, across many regimes.

### Alerting — deployment miss plus taxonomy defect

Actual: the entry-zone monitor did not exist until May 7, so it could not alert during the move.

Current clean-branch counterfactual: `trading/alerts/entry_zone_monitor.py:45-81` admits high-score plans without checking `tradeable`. The replay's first same-scan alert-like event would occur on February 25 at 68,994 with score 84 even though the plan is invalid, theory still points short, and COT blocks it. This is not a recovered trade; it is an unsafe false-positive alert.

A separate user worktree contains overlapping alert changes and was inspected read-only. No file in `<repo-root>` was modified.

### Execution — no verified fill

Even the COT-disabled counterfactual arms late and above its entry zone. The current backtester would still simulate a fill at the zone on the next bar. Until zone touch, spread/slippage, fees, funding, and stop/target ordering are modeled causally, “caught the move” cannot be claimed.

# 4. First safe test — completed

## Hypothesis

A causal, read-only replay can identify the first suppressing gate and alert/fill integrity defects without changing strategy logic or using future data.

## Market and instrument

- Market: BTC perpetual/spot proxy.
- Instrument for research: BTC on Hyperliquid candles; no order or simulated leverage recommendation.
- Timeframes: completed weekly and daily context, 4H setup, 1H trigger.

## Inputs and controls

- Hyperliquid OHLCV, fully closed at each as-of timestamp.[1]
- CFTC BTC futures-and-options combined history, available only after official publication.[2][3]
- Production-gate baseline.
- COT-disabled, theory-disabled, and COT+theory-disabled attribution controls.
- Funding/OI missing and explicitly non-executable.

## Result

The hypothesis was supported:

1. Operational deployment lag explains why no complete system alert existed.
2. Price confirmation latency explains most of the path.
3. COT is the final hard veto at the first mature setup.
4. Removing COT alone does not create an early entry; it creates a late plan at 77,345.
5. The clean alert monitor can surface an invalid high-score plan, proving that “more alerts” is not equivalent to better recall.
6. No strategy change is justified yet.

Falsification condition for this diagnostic: if a fully causal replay had produced a deployed, tradeable, in-zone alert materially before 78k, the “miss” would be an operations/delivery failure rather than strategy/data latency. It did not.

# 5. Pre-registered experiment backlog

## Shared controls

All experiments remain paper-only and human-gated.

- **Costs:** report gross and net results over a stress grid; do not promote an edge that disappears under conservative costs. Crypto grid: 6/12/20 bps round trip plus point-in-time funding. Futures grid: 1/2 ticks per side plus actual broker/exchange commissions. Options: mid, mid ±25% of quoted spread, and marketable fills plus actual per-contract fees.
- **Risk:** 0.25% hypothetical equity for a transition probe, 0.50% for a fully confirmed paper entry, and 1.00% aggregate correlated directional exposure. These are experiment caps, not live sizing advice.
- **Liquidity:** BTC/ETH first. Alts require archived spread, depth, volume, OI, funding, contract and venue quality. Futures start with front-contract ES/MES and NQ/MNQ. Options require executable bid/ask, volume, OI, and defined maximum loss.
- **Execution:** no fill unless the market touches the entry price after signal availability; adverse same-bar stop/target ordering; no use of final OHLC before candle close.
- **Invalidation:** 1H close back through the broken range for transition probes; 4H close through structural invalidation for confirmed entries; options cannot risk more than paid debit or defined spread max loss.

## Crypto experiments

### C0 — Point-in-time research tape (P0 prerequisite)

- Hypothesis: most apparent strategy ambiguity can be separated into data, signal, alert, and execution stages if every scan is archived.
- Data: candle open/close times, raw OHLCV, venue, funding, OI, spread/depth, COT report date and `available_at`, config hash, git SHA, every gate, recommendation, watch state, and delivery outcome.
- Success: at least 99.5% expected bars present; 100% of used COT rows have valid publication timestamps; no missing funding/OI can silently pass an execution result.
- Falsification: the tape cannot reproduce a previously emitted scan from stored inputs.

### C1 — Causal backtester and fill model (P0 prerequisite)

- Hypothesis: corrected timestamps and zone-touch fills materially reduce optimistic expectancy but preserve any real rank ordering.
- Change under test: closed-bar availability, historical funding/OI alignment, COT release lag, zone-touch entry, fees/slippage/funding, and trade overlap rules.
- Success: old and corrected metrics are both reported; every trade has signal, order-eligible, fill, and exit timestamps; no phantom fill.
- Falsification: the corrected engine cannot reproduce hand-audited bars or materially changes results without traceable reasons.

### C2 — Transition WATCH lane

- Hypothesis: when weekly theory is neutral, a 4H breakout/retest with volume and volatility plus a daily fast-EMA reclaim can emit an early WATCH without degrading ENTER precision.
- Market/instruments: BTC and ETH perpetuals; 1D/4H/1H.
- Entry assumption: WATCH only at transition; paper probe only after a subsequent 1H range hold. Full ENTER still requires existing confirmation.
- Invalidation: 1H close back inside range or 4H close below breakout level.
- Primary metric: meaningful-move recall before 50% of the move path is complete.
- Falsification: recall improves less than 10 percentage points, precision drops more than 5 points, or net expectancy/tail loss worsens after costs.

### C3 — COT hard-block interaction

- Hypothesis: extreme COT should remain a hard block for unconfirmed/chase setups but become a caution and size cap after a price transition passes C2.
- Control: current hard block.
- Variants: hard block; caution/no score bonus; caution with 50% paper risk cap.
- Metrics: precision, recall, latency, net R, maximum drawdown, worst-decile R, and performance by COT percentile/regime.
- Falsification: the conditional variant only improves the April case, loses after 20 bps crypto costs, or worsens worst-decile R by more than 0.20R.

### C4 — Alert taxonomy and delivery integrity

- Hypothesis: separate `WATCH` (forming/blocked), `ENTER` (tradeable and in-zone), and `REVIEW` (data incomplete) events improve useful recall without unsafe execution language.
- Required fields: `alert_kind`, `tradeable`, failed gates, price, frozen zone, invalidation, targets, expected move, as-of, data completeness, and dedupe key.
- Success: zero ENTER alerts from non-tradeable plans; every emitted event maps to exactly one archived scan and delivery record.
- Falsification: alert count rises without improvement in confirmed-event precision or invalid plans are labeled ENTER.

### C5 — Liquid-alt relative-strength selection

- Hypothesis: after BTC/ETH transition confirmation, ranking liquid alts by 4H relative strength, breadth, OI participation, funding, and spread can improve net expectancy versus BTC without increasing tail loss.
- Universe: pre-filtered venue-quality assets only; exclude new/illiquid contracts and any asset failing custody, contract, or manipulation checks.
- Control: BTC paper entry at the same timestamps.
- Success: positive incremental net R after 20 bps costs, no worse maximum drawdown, and stable results across at least three liquidity buckets.
- Falsification: outperformance depends on one token, disappears after costs, or requires hindsight universe selection.

## Stock futures and options experiments

The repository has an equity-options snapshot/scoring stack but no dedicated ES/NQ futures research module. `options/analyzer.py:98-129` fetches or reuses current chain snapshots; this is not a survivorship-free historical options tape. Data acquisition is therefore the first experiment, not a strategy backtest.

### S0 — Futures/options point-in-time data contract (P0 prerequisite)

- Markets: ES/MES, NQ/MNQ; later SPX/XSP or QQQ defined-risk options.
- Data: contract-specific OHLCV, roll calendar, tick value, RTH/overnight sessions, spread/depth, macro release timestamps, and option chain bid/ask/IV/Greeks/OI/volume snapshots.
- Success: continuous series can be reconstructed from explicit contracts; no future roll, revised macro, future earnings, or final option quote leaks into a prior timestamp.
- Falsification: chain/roll history is incomplete enough that executable P&L cannot be reconstructed.

### S1 — Index-futures transition breakout

- Hypothesis: daily regime plus 4H range breakout and 1H retest captures 2-ATR five-session moves earlier than daily trend-only confirmation.
- Instruments: one front contract at a time in ES/MES and NQ/MNQ, with explicit roll and session rules.
- Liquidity: regular front-contract sessions only; skip roll-transition and major-release blackout windows unless the event variant is explicitly tested.
- Invalidation: 1H close back inside range; hard exit on 4H structural break or time stop after five sessions.
- Costs: 1/2 tick per side stress plus actual commissions/exchange fees.
- Falsification: event recall gain is below 10 points, net expectancy is non-positive, or overnight/roll tails dominate results.

### S2 — Defined-risk option wrapper after futures confirmation

- Hypothesis: a 14–45 DTE SPX/XSP or QQQ debit spread entered only after S1 confirmation has better tail control than naked directional options and comparable net expectancy to futures.
- Structures: bull-call or bear-put debit spread only in phase 1.
- Liquidity: each leg OI ≥500, daily volume ≥100, quoted spread ≤10% of mid, and complete executable quote.
- Risk: premium paid is maximum loss; no short naked leg; exit at 50–75% of max profit, structural invalidation, or seven DTE.
- Costs: mid, adverse 25%-spread, and marketable-fill scenarios plus actual fees.
- Falsification: positive results exist only at mid, fewer than 40 independent trades are available, or adverse-fill expectancy is non-positive.

### S3 — Equity-option directional alignment

- Hypothesis: the existing liquid S&P 500 option scanner improves when defined-risk spreads require a pre-registered underlying 1D/4H/1H trend/transition state rather than option-score ranking alone.
- Universe: point-in-time S&P 500 membership with minimum stock/option liquidity; earnings and corporate-event labels known at the timestamp.
- Control: existing options ranking.
- Success: higher net expectancy and lower max loss per unit of expected value with no hidden survivorship or earnings leakage.
- Falsification: improvement vanishes on point-in-time chains or is explained by one ticker/event.

# 6. Evaluation protocol and metrics

## Event definitions

- Crypto swing event: directional move of at least 8% within 20 calendar days after an eligible 4H range break.
- Crypto execution event: TP2 or invalidation within the existing 72 one-hour-bar horizon.
- Index-futures event: directional move of at least 2 daily ATRs within five sessions.
- Options outcome: executable spread P&L at fixed checkpoints and exit rules, not underlying direction alone.

## Required metrics

1. Signal latency: bars and percentage of move path elapsed before WATCH and ENTER.
2. Precision/recall for meaningful moves, with explicit false-positive count.
3. Net expectancy in R after fees, spread, slippage, and funding.
4. Maximum drawdown, worst trade, worst-decile R, and expected shortfall.
5. Turnover, average holding time, overlap/correlation, and capacity/liquidity rejects.
6. Alert precision, delivery latency, duplicate rate, and recommendation/alert mismatch.
7. Data completeness and number of signals excluded for missing point-in-time evidence.
8. Robustness by bull, bear, range, high/low volatility, crowded COT, event, and liquidity regime.

## Promotion gates

A research candidate remains **WATCH** unless all are true:

- At least 40 independent signals across multiple regimes and instruments.
- Positive net expectancy under the conservative cost scenario.
- The lower bound of a pre-specified bootstrap confidence interval is above zero on development data, and both locked OOS windows are non-negative.
- Recall improves by at least 10 points with no more than a 5-point precision loss, or expectancy improves without increasing tail loss.
- Median signal latency is below 50% of move elapsed.
- Maximum drawdown and worst-decile R do not materially deteriorate versus control.
- Results are not driven by the April BTC case, one token, one ticker, one event, or one volatility regime.
- A paper trial passes, then Joni explicitly approves any next stage.

# 7. Untouched evaluation periods

The following are **not untouched** and may only be used for development/regression:

- BTC February–April 2026, including this case.
- Existing 2017–2025 Nave theory periods.
- April 2026 range-breakout iter 18 validation.
- June–July 2026, inspected while locating the case.

Locked future periods:

| Lane | OOS-A | OOS-B | Unlock rule |
|---|---|---|---|
| Crypto | 2026-09-01 through 2026-11-30 | 2026-12-01 through 2027-02-28 | Freeze hypothesis, parameters, costs, code hash, and event labels before each window. |
| Futures/options | 2026-09-01 through 2026-12-31 | 2027-01-01 through 2027-03-31 | Freeze data contract, roll/session rules, structures, fills, and risk before each window. |

No parameter may be changed after an OOS window is opened. A change creates a new experiment ID and the used window becomes development data.

# 8. Recommended next action

**REVIEW:** implement C0 + C1 first: an immutable point-in-time research tape and causal fill/backtest audit. Do not lower the daily threshold or relax COT yet. Once the corrected baseline is frozen, run C2 and C3 as independent experiments, with C4 as an alert-integrity requirement rather than a profit claim.

What would falsify this conclusion: a read-back of archived contemporaneous scans showing a deployed, tradeable, in-zone long alert before the move was mostly complete. No such archive was found in the clean repository, and the deployment chronology makes it unlikely.

## Sources

[1] https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint — Hyperliquid Info endpoint
    > "The info endpoint is used to fetch information about the exchange and specific users."
    > "Only the most recent 5000 candles are available"
[2] https://www.cftc.gov/MarketReports/CommitmentsofTraders/ReleaseSchedule/index.htm — CFTC COT Release Schedule
    > "The Commitments of Traders reports are released at 3:30 p.m. Eastern time. The Futures Only reports and Futures and Options Combined reports are usually released on Friday. The release usually includes data from the previous Tuesday."
[3] https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalCompressed/index.htm — CFTC Historical Compressed COT
    > "The complete Disaggregated Commitments of Traders Futures-and-Options Combined reports file from September 2009 is included by year."
