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

## Infrastructure improvements (this iteration)

1. **COT history cache** (`cot_gate.py`) — eliminates per-bar JSON file reads during backtests (~10× speedup).
2. **`iter_entries()`** on `MomentumBacktester` — enables A/B exit policy testing on identical entries.
3. **Adaptive cadence in review** — `review_positions()` now applies cadence-recommended threshold by default (quiet → 81).
4. **Explicit `size_fraction`** on secondary opportunities (0.5 fade/forming, 0.25 notrend scalp).

---

## Prioritized earnings roadmap

### Tier 1 — Ship now (PR #34 + this iteration)

- [x] Regime confidence arming (COT conf ≥ 65% OR crowded percentile)
- [x] Secondary lanes with execution detail + sizing fractions
- [x] Adaptive cadence threshold in operator review
- [x] COT cache for backtest iteration speed

### Tier 2 — Next sprint (highest ROI)

1. **Backtest secondary lanes** — simulate `relief_rally_fade` and `forming_short` entries on 2022-bear + 2023-recovery. This is the largest unvalidated earnings surface.
2. **Regime-aware threshold** — auto-raise to 85+ in 2024-ETF-style chop (pct_reaching_8 < 40%).
3. **Conviction sizing on primary ENTER** — scale risk_pct by score band (90+ = 0.75%, 78–89 = 0.5%) — could add ~15–20% capital efficiency without changing entry count much.

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
| `docs/analysis/crypto_review_20260616.md` | PR scenario analysis |
| `docs/analysis/raw/unified_backtest_20260601T222143Z.json` | Full 8-regime baseline |
| `docs/analysis/raw/exit_policy_ab_20260616_clean.json` | Exit A/B results |
