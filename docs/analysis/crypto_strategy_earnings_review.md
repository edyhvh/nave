# Crypto Strategy & Earnings Review — PR #34 + Historical Backtest

> **Date:** 2026-06-16  
> **Scope:** Full analysis of `qa/crypto_review` changes, momentum baseline (2017–2025), exit-policy A/B, and earnings improvement roadmap.

---

## Executive summary

| Layer | Verdict | Earnings impact |
|-------|---------|-----------------|
| **PR #34** (regime + secondary lanes) | Ship — fixes real blind spot | **High** for operator capture during relief rallies |
| **Momentum primary** (4H/1H breakout) | Strong baseline | **+1.83R/trade** pooled (185 trades, 78.9% WR) |
| **Exit policy** (scale-out / BE / runner) | Do **not** adopt for earnings | Partial exits **reduce** expectancy (−14% vs baseline) |
| **Score threshold** | Already near-optimal at 78 | Raising to 88 removes 5 trades, +0.04R marginal |
| **Adaptive cadence** | Enable in operator stack | Tightens in quiet markets (78→81); now default in review |

**Bottom line:** The strategy already has real edge. PR #34's biggest earnings contribution is **not missing WATCH/fade setups** when COT percentile normalizes but macro bear thesis persists. The next earnings lift comes from **backtesting secondary lanes**, **conviction sizing**, and **regime-specific filters** — not from partial exits.

---

## PR #34 goal check

### What it set out to fix

1. Regime disarmed when COT percentile dropped P97→P50 after relief rally, despite ~72% confidence and 16–18% drawdown from highs.
2. `relief_rally_fade` logic existed but never surfaced when primary action was `stand_aside`.
3. Forming shorts (momentum score 52, theory blocked) invisible to operator.

### What it delivers (live 2026-06-16)

| Coin | Before | After |
|------|--------|-------|
| BTC | `neutral` / stand aside | `relief_rally_fade` / **WATCH short** with stop + targets |
| ETH | `neutral` / stand aside | **WATCH short** + secondary `forming_short` (score 52) |

### Earnings mechanism

- **Primary path:** Regime WATCH now carries execution levels (stop/targets backfilled from secondary lane).
- **Secondary path:** Additive lanes only (`forming_short`, `notrend_range_long`) with explicit `size_fraction` (50% / 25%).
- **Not yet in backtest:** Secondary lanes are advisory-only — no historical P&L validation yet.

---

## Historical momentum baseline (8 regimes, BTC+ETH)

Source: `docs/analysis/raw/unified_backtest_20260601T222143Z.json`

| Metric | Value |
|--------|-------|
| Pooled trades | 185 |
| Win rate | 78.9% |
| Expectancy | **+1.83R** |
| Regimes with trades | 8/8 |
| Losing regimes | 0 |
| Confidence | medium (partial 2017 coverage) |

### Per-regime highlights

| Period | BTC exp | ETH exp | Notes |
|--------|---------|---------|-------|
| 2017-bull+2018-bear | +2.64R | +2.77R | Strong; partial data |
| 2019-recovery | +1.76R | +1.40R | Most losers originate here |
| 2020-covid-crash | +1.62R | +2.61R | ETH outperforms |
| 2020-recovery+2021-ATH | +0.95R | +2.53R | **Weakest BTC regime** |
| 2022-bear | +1.28R | +3.41R | PR scenario analogue |
| 2023-recovery | +2.25R | +1.13R | **Weakest ETH regime** |
| 2024-ETF-approval | +1.31R | +0.55R | Chop; low extension rate |
| 2024-2025-bull | +1.43R | +1.82R | Current cycle |

### Side split

- **Long:** 94 trades, +1.80R avg, 75.5% WR  
- **Short:** 91 trades, +1.87R avg, 82.4% WR  

Shorts slightly outperform — aligns with PR's relief-rally fade focus.

### Score bands

| Band | Trades | Win% | Avg R |
|------|--------|------|-------|
| 90+ | 172 | 79.7% | +1.87R |
| 80–89 | 12 | 75.0% | +1.61R |
| 75–79 | 1 | 0.0% | −1.00R |

Threshold sensitivity: raising from 78→88 removes only 5 trades and adds +0.04R expectancy — **marginal**. The engine already filters aggressively; most losers are full −1R stops at score 85–100 (2019-recovery cluster).

---

## Exit policy A/B experiment

Source: `docs/analysis/raw/exit_policy_ab_20260616_clean.json`  
Periods: 2022-bear, 2023-recovery, 2024-2025-bull (63 identical entries)

| Policy | Trades | Win% | Exp (R) | Total R | Max DD |
|--------|--------|------|---------|---------|--------|
| **baseline** (100% @ tp2) | 63 | 79.4% | **+1.82** | +114.5 | 3.0 |
| tp1_be_tp2 (50% tp1, 50% tp2) | 63 | 88.9% | +1.56 | +98.2 | 1.2 |
| tp1_tp2_be (50% tp1, 50% tp3) | 63 | 88.9% | +1.59 | +100.3 | 1.2 |
| tp1_be_runner (40/30/30 + trail) | 63 | 88.9% | +1.66 | +104.3 | 1.2 |

**Conclusion:** Partial scale-outs improve win rate and cut drawdown but **sacrifice ~14% expectancy**. For earnings maximization, keep baseline exit (full position to tp2). Use partial exits only if drawdown tolerance is the binding constraint.

Tool: `python scripts/exit_policy_experiment.py --periods 2022-bear 2023-recovery 2024-2025-bull`

---

## Secondary lane validation

COT source: official CFTC Historical Compressed annual archives
Backfill artifact: `docs/analysis/raw/cot_backfill_20260616.json`
Touch-mode source: `docs/analysis/raw/secondary_lane_experiment_touch_20260616.json`
Rejection-mode source: `docs/analysis/raw/secondary_lane_experiment_rejection_20260616.json`

Backfill command:
`python scripts/backfill_cot_history.py --years 2022 2023 2024 2025 2026 --report-types futures_and_options --assets BTC ETH`

Experiment command:
`python scripts/secondary_lane_experiment.py --periods 2022-bear 2023-recovery 2024-ETF-approval 2024-2025-bull --symbols BTC ETH --step-bars 24 --entry-mode [touch|rejection]`

| Item | Result |
|------|--------|
| BTC cached COT rows | 232 (`2022-01-04` → `2026-06-09`) |
| ETH cached COT rows | 232 (`2022-01-04` → `2026-06-09`) |
| Historical source | CFTC annual compressed futures-and-options combined files |
| Scan density | Every 24 4H bars (sampled research run) |
| COT replay fidelity | Directional net-position percentile proxy; cached history does not include full live OI/F.I.T.S. context |

### Touch vs rejection

| Entry mode | Trades | Win% | Exp (R) | Sized exp | Max DD |
|------------|-------:|-----:|--------:|----------:|-------:|
| touch | 115 | 31.3% | **−0.168** | −0.074 | 8.56R |
| 1H rejection | 76 | 43.4% | **−0.045** | −0.023 | 2.19R |

**Conclusion:** secondary lanes should not be executed on zone touch. Requiring
a 1H rejection candle materially improves win rate, expectancy, and drawdown,
but the full secondary stack is still slightly negative in this sampled run.
Keep secondary lanes as WATCH/advisory unless a stricter trigger or lane filter
turns the rejection-mode results positive.

### Lane split under 1H rejection

| Lane | Trades | Win% | Exp (R) | Sized exp | Verdict |
|------|-------:|-----:|--------:|----------:|---------|
| `notrend_range_long` | 18 | 55.6% | **+0.011** | +0.003 | Fragile positive, keep researching |
| `relief_rally_fade` | 50 | 40.0% | −0.048 | −0.024 | Needs tighter supply/rejection filter |
| `forming_short` | 8 | 37.5% | −0.154 | −0.077 | Do not execute yet |

### Notrend target-policy check

Follow-up isolated `notrend_range_long` so fade/forming active windows could not
interfere with the lane:

| Lane setup | Trades | Win% | Exp (R) | Sized exp | Max DD |
|------------|-------:|-----:|--------:|----------:|-------:|
| rejection + target 2 | 18 | 55.6% | **+0.011** | +0.003 | 0.38R |
| rejection + playbook target 1 | 18 | 33.3% | −0.137 | −0.034 | 0.75R |

The previous small positive notrend result remains very thin when isolated.
Do not promote it to executable logic yet. The next notrend experiment should
filter the lane, not change exits: require a stronger lower-range location,
clearer 1H reversal, or a volatility-adjusted stop before considering real
allocation.

### Trend-alignment read

Counter-trend status is not, by itself, the defect. Under rejection mode:

| Trend bucket | Trades | Win% | Exp (R) |
|--------------|-------:|-----:|--------:|
| aligned | 39 | 41.0% | −0.066 |
| counter_trend | 20 | 40.0% | −0.026 |
| mixed | 9 | 33.3% | −0.067 |
| neutral | 8 | 75.0% | +0.035 |

That matches the playbook intent: secondary lanes may be counter-trend. The
engine should label alignment and use it for sizing/review, not hard-block every
counter-trend secondary idea. The immediate quality issue is trigger precision,
especially for `forming_short` and broad `relief_rally_fade` zones.

The implementation also fixed a COT cache parsing issue: cached rows use
`report_date` / `report_date_as_yyyy_mm_dd`, while the previous parser only
accepted CFTC-style `report_week` labels.

Research fidelity note: the secondary experiment now uses directional
net-position percentile rank rather than absolute net magnitude percentile, but
it still remains a proxy because cached history lacks the full live OI/F.I.T.S.
inputs. Treat the secondary-lane artifacts as directional research, not as a
production-grade replay of `position-review`.

---

## Conviction sizing experiment

Source: `docs/analysis/raw/conviction_sizing_20260616_partial.json`
Recent sampled source: `docs/analysis/raw/conviction_sizing_recent_sampled6_20260616.json`
Tool: `python scripts/conviction_sizing_experiment.py`

This experiment changes only risk sizing on already-generated primary momentum
trades. Entries and exits are identical. Current artifact coverage is partial:
only trade-level momentum artifacts for `2017-bull+2018-bear` and
`2019-recovery` were available locally (33 trades). Attempts to regenerate the
full historical trade set were too slow in this environment, so do **not** treat
this as production-ready until all periods are represented.

| Policy | Trades | Avg risk | Return | Max DD | Delta return vs flat | Delta DD vs flat |
|--------|-------:|---------:|-------:|-------:|---------------------:|-----------------:|
| flat 0.50% | 33 | 0.500% | 43.43% | 0.14% | 0.00% | 0.00% |
| proposed: 90+ → 0.75%, else 0.50% | 33 | 0.727% | 63.12% | 0.22% | +19.69% | +0.08% |
| conservative: 95+ → 0.75%, 90-94 → 0.625% | 33 | 0.701% | 60.29% | 0.22% | +16.86% | +0.08% |
| quality gate: only 90+ at 0.75% | 30 | 0.750% | 59.06% | 0.22% | +15.63% | +0.08% |

Partial read: conviction sizing behaves as expected on high-quality early
artifacts: larger return with only modest incremental drawdown. Because the
available sample is unusually strong (96.97% win rate), this is **not enough**
to alter production sizing. The next validation must use a full trade-level
artifact set across all historical regimes, especially 2022-bear,
2024-ETF-approval, and 2024-2025-bull.

### Recent COT-backed sampled validation

To avoid relying only on early-cycle artifacts, a sampled primary artifact set
was generated for 2022-bear, 2023-recovery, 2024-ETF-approval, and
2024-2025-bull with `step_bars=6` (daily cadence over 4H setup bars). This is
still sampled, not exhaustive, but it covers the recent COT-backed regimes.

Generation:
`python scripts/sample_primary_momentum_artifacts.py --periods 2022-bear 2023-recovery 2024-ETF-approval 2024-2025-bull --symbols BTC ETH --step-bars 6`

Sizing:
`python scripts/conviction_sizing_experiment.py --artifacts docs/analysis/raw/momentum_backtest_2022-bear_sampled6_20260616T185325Z.json docs/analysis/raw/momentum_backtest_2023-recovery_sampled6_20260616T185325Z.json docs/analysis/raw/momentum_backtest_2024-ETF-approval_sampled6_20260616T185325Z.json docs/analysis/raw/momentum_backtest_2024-2025-bull_sampled6_20260616T185325Z.json`

| Policy | Trades | Win% | Avg risk | Return | Max DD | Delta return vs flat | Delta DD vs flat |
|--------|-------:|-----:|---------:|-------:|-------:|---------------------:|-----------------:|
| flat 0.50% | 13 | 76.9% | 0.500% | 11.59% | 0.50% | 0.00% | 0.00% |
| proposed: 90+ → 0.75% | 13 | 76.9% | 0.750% | 17.39% | 0.75% | +5.80% | +0.25% |
| conservative: 95+ → 0.75%, 90-94 → 0.625% | 13 | 76.9% | 0.731% | 16.64% | 0.75% | +5.05% | +0.25% |
| quality gate: only 90+ at 0.75% | 13 | 76.9% | 0.750% | 17.39% | 0.75% | +5.80% | +0.25% |

Recent sampled read: every trade in this sample scored 90+, so the proposed and
quality-gate policies are equivalent here. The overlay improves return by
~50%, while max drawdown also increases from 0.50% to 0.75%. That is expected:
the strategy is applying more risk to the same high-score entries. The result
supports further validation of 0.75% risk for 90+ primary entries, but the
sample is only 13 trades and should remain a research result until an exhaustive
run is practical.

### Live-review implementation stance

The branch now exposes conviction sizing as an **advisory hint only**:

- Applies only to primary `ENTER` recommendations from momentum-backed entries.
- Requires score `90+`.
- Suggests `0.75%` risk, capped by momentum config `max_risk_pct`.
- Never applies to `WATCH`, `stand_aside`, or secondary lanes.
- Blocks the raised hint when COT history has fewer than 12 rows or is stale.
- Does not change the `risk_pct` passed into momentum scanning, options scans,
  or execution paths.
- Adaptive score thresholds remain enabled by default for operator review, but
  callers can disable them with `apply_cadence_policy=False` or
  `--no-adaptive-threshold`.

This gives the operator visibility into the sizing candidate without silently
changing production risk.

Hermes handling: `position_review` receives the same `suggested_risk` field
from the shared crypto review service. `recommend_position` also preserves this
field as `safety.risk_advisory`, including the hypothetical 0.75% size, but
keeps actual sizing tied to the caller-provided `risk_pct`.

Candidate if full-history validation holds:

| Score band | Risk |
|------------|------|
| 90+ | 0.75% |
| 78-89 | 0.50% |
| below trade threshold | 0% |

Guardrail: reject the sizing change unless full-history max drawdown increases
less than the return lift and no recent regime flips negative under the sizing
overlay.

---

## Infrastructure improvements (this iteration)

1. **COT history cache** (`cot_gate.py`) — eliminates per-bar JSON file reads during backtests (~10× speedup).
2. **`iter_entries()`** on `MomentumBacktester` — enables A/B exit policy testing on identical entries.
3. **Adaptive cadence in review** — `review_positions()` now applies cadence-recommended threshold by default (quiet → 81).
4. **Explicit `size_fraction`** on secondary opportunities (0.5 fade/forming, 0.25 notrend scalp).
5. **COT historical backfill** — seeds BTC/ETH weekly COT history from official CFTC annual compressed files.
6. **Secondary-lane experiment scaffold** — validates WATCH lanes separately from production entry logic, with touch vs 1H rejection modes and trend-alignment buckets.
7. **Cached COT date parsing** — supports both `report_week` labels and cached ISO report-date fields.
8. **Conviction-sizing experiment scaffold** — evaluates primary-entry score-band risk overlays without changing entries/exits.
9. **Advisory conviction sizing in live review** — `suggested_risk` appears only for eligible primary ENTER rows; execution sizing remains unchanged.
10. **Review hardening pass** — adaptive-threshold opt-outs, directional COT proxy replay, per-lane secondary overlap, resilient COT backfill, ordered zones, structured daily blocker handling, and blocked-risk display.

---

## Prioritized earnings roadmap

### Tier 1 — Ship now (PR #34 + this iteration)

- [x] Regime confidence arming (COT conf ≥ 65% OR crowded percentile)
- [x] Secondary lanes with execution detail + sizing fractions
- [x] Adaptive cadence threshold in operator review
- [x] COT cache for backtest iteration speed

### Tier 2 — Next sprint (highest ROI)

1. **Tighten secondary triggers before execution** — do not use zone-touch entries. Keep `notrend_range_long` as the only candidate for further execution research, but treat it as breakeven until filtering improves.
2. **Refine relief-rally fade supply selection** — broad supply zones produce too many weak fades. Test tighter supply definitions: 4H lower-high only, prior breakdown retest only, or rejection above 20 EMA with close back below it.
3. **Demote forming_short from executable research** — sampled rejection mode is strongly negative. Keep it as a context alert until daily confirmation is codified.
4. **Complete exhaustive conviction sizing validation** — sampled recent regimes support 90+ risk scaling, but trade count is still small. Regenerate exhaustive trade-level momentum artifacts for all periods, then rerun `scripts/conviction_sizing_experiment.py`.
5. **Regime-aware threshold** — auto-raise to 85+ in 2024-ETF-style chop (pct_reaching_8 < 40%).

### Tier 3 — Medium term

4. **1H rejection trigger automation** — secondary fade currently requires manual 1H rejection; codify as entry trigger.
5. **Options executable path** — bear put debit spreads when relief_rally_fade + touch gate passes (currently advisory-only).
6. **Weekly frame in live engine** — reduce theory overlay false blocks on forming shorts.

### Do NOT pursue (backtest-negative)

- Partial scale-out exits for earnings (reduces expectancy)
- Lowering score threshold below 78 (adds low-quality trades)
- Chasing relief-rally longs against COT bear bias

---

## Operator workflow (updated)

```bash
# Full stack with secondary lanes + adaptive threshold
nave crypto position-review --coins BTC,ETH

# Momentum detail
nave crypto momentum-scan --symbols BTCUSDT,ETHUSDT --adaptive-threshold --json

# Historical validation
python scripts/unified_backtest.py --symbols BTC ETH --fast

# Exit policy comparison
python scripts/exit_policy_experiment.py --periods 2022-bear 2023-recovery 2024-2025-bull
```

---

## Open questions resolved

| Question | Answer |
|----------|--------|
| P50 + 72% conf → full leg_down or softer? | Full bear regime arms; relief_rally_fade when bounce into supply |
| Notrend sizing explicit? | Yes — `size_fraction` on secondary output |
| Lower threshold for forming shorts? | No — keep 78 base; use secondary `forming_short` watch lane instead |
| Partial exits for earnings? | No — baseline tp2 exit wins on expectancy |

---

## Files reference

| File | Role |
|------|------|
| `trading/crypto/analysis/opportunities.py` | Secondary lane detection |
| `trading/crypto/analysis/regime.py` | Confidence-based regime arming |
| `trading/crypto/analysis/review.py` | Operator stack + cadence + backfill |
| `trading/crypto/momentum/backtest.py` | Historical simulation + `iter_entries` |
| `scripts/exit_policy_experiment.py` | Exit policy A/B tool |
| `scripts/backfill_cot_history.py` | Official CFTC annual archive backfill into COT cache |
| `scripts/secondary_lane_experiment.py` | Secondary WATCH-lane validation scaffold |
| `scripts/conviction_sizing_experiment.py` | Primary-entry score-band risk overlay experiment |
| `scripts/sample_primary_momentum_artifacts.py` | Sampled primary trade artifact generator for sizing research |
| `docs/analysis/crypto_review_20260616.md` | PR scenario analysis |
| `docs/analysis/raw/unified_backtest_20260601T222143Z.json` | Full 8-regime baseline |
| `docs/analysis/raw/exit_policy_ab_20260616_clean.json` | Exit A/B results |
| `docs/analysis/raw/cot_backfill_20260616.json` | COT backfill coverage |
| `docs/analysis/raw/secondary_lane_experiment_touch_20260616.json` | Secondary touch-entry A/B result |
| `docs/analysis/raw/secondary_lane_experiment_rejection_20260616.json` | Secondary 1H rejection-entry A/B result |
| `docs/analysis/raw/secondary_lane_notrend_rejection_tp2_20260616.json` | Isolated notrend rejection with target 2 |
| `docs/analysis/raw/secondary_lane_notrend_rejection_playbook_20260616.json` | Isolated notrend rejection with playbook target |
| `docs/analysis/raw/conviction_sizing_20260616_partial.json` | Partial primary conviction-sizing result |
| `docs/analysis/raw/conviction_sizing_recent_sampled6_20260616.json` | Recent COT-backed sampled conviction-sizing result |
