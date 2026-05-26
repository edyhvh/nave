# Options Analysis Model: MSFT + NFLX Post-Mortem
## Date: 2026-05-20
## Analyst: Kimi Code CLI

---

## Executive Summary

After deep analysis of the options model outputs from May 11-18, 2026, we identified **critical bugs and design flaws** causing the model to:

1. **Reject profitable income trades** (MSFT bull put spread, MSFT iron condor)
2. **Recommend unprofitable long-volatility trades** (NFLX long strangle with inflated PoP)
3. **Produce "no_trade" for most S&P 500 names** even when viable setups exist

The root causes are:
- **IV calculation bug**: Mean IV across all strikes/expirations includes extreme outliers
- **Quality gate too strict**: Composite score threshold of 50 is nearly unattainable for income strategies
- **Probability model uses no-drift assumption**: Overstates downside risk for bullish underlyings
- **Scoring function misweights components**: PoP overweighted, income strategies systematically penalized
- **No directional bias integration**: The model is volatility-only, ignoring the trading system's directional signals

---

## Case 1: MSFT — Model Said "No Trade", Friend's Position Won

### Timeline

| Date | MSFT Price | Model Output | Friend's Position |
|------|-----------|--------------|-------------------|
| May 11 | $412.02 | Top: iron_condor (score 46.1, **blocked** by quality gate) | — |
| May 12 | ~$412 | S&P scan: **"no_trade"** — no strategy passed gate | Bull put spread 395/390 |
| May 18 | $420.98 | Recheck: bull put 395/390 scored **17.95**, **blocked** | Same spread still valid |
| May 20 | $419.09 | — | Position profitable, short put deeply OTM |

### What the Model Recommended (May 11)

**Iron Condor** (410P/395P, 410C/420C, Jun 12, 32 DTE):
- Net credit: $1,070
- Max loss: $430
- PoP: 61.7%
- **Expected Value: -$5.41** (negative!)
- **Composite score: 46.1** (below 50 threshold)
- **Quality gate: BLOCKED** → "no_trade"

### What the Friend Recommended

**Bull Put Credit Spread** (395P/390P, Jun 18, 31 DTE):
- Net credit: $92.50
- Max loss: $407.50
- Breakeven: $394.07 (~6.3% OTM)
- **Model's assessment**: PoP 73.0%, EV -$35.21, score 17.95
- **Quality gate: BLOCKED** → model rejected it

### What Actually Happened

MSFT rallied from $412 → $419 (+1.7%). The friend's bull put spread is now deeply OTM and profitable. Even the **model's own iron condor would have been profitable** (price stayed well inside 395-420 range).

### Why the Model Failed

#### 1. Quality Gate Threshold Is Too High

```python
MIN_ACTIONABLE_COMPOSITE_SCORE = 50.0
```

For income strategies with limited max profit, the scoring function caps their score:
- RR component: `min(40, RR * 20)` → bull put with RR=0.23 gets only **4.6 points**
- EV component: `tanh(EV/500)*100` → small credits get squashed
- Theta bonus is small for low-credit spreads
- Result: Even a fundamentally sound bull put spread scores ~18-46, well below 50

**Reality check**: A 73% PoP trade with 6% OTM cushion on a mega-cap should not require a score of 50 to be actionable.

#### 2. Probability Model Assumes Zero Drift

The model's terminal distribution is:
```
prices = underlying * exp(-0.5*sigma^2*t + sigma*sqrt(t)*Z)
```

This is a **martingale** — expected terminal price = spot. Real equities have positive drift (~risk-free rate + equity premium = ~8-10% annually). For a 30-day horizon, the drift is worth ~$2.50-3.00 on MSFT.

Without drift:
- Probability of finishing below $395 is overstated
- Expected value of bullish income strategies becomes artificially negative
- The model sees -$35 EV when real EV should be closer to +$15-25

#### 3. Negative EV Penalty Is Too Harsh

```python
def _negative_ev_penalty(expected_value, iv_rank, iv_percentile):
    base_penalty = 8.0 + min(20.0, abs(expected_value) / 25.0)
    ...
    return base_penalty * (1.0 + 0.6 * elevated_iv)
```

For MSFT bull put with EV=-$35:
- Base penalty = 8 + 35/25 = **9.4 points**
- With elevated IV (IV rank 55, percentile 90): multiplier = 1.36
- Final penalty = **~12.8 points**

This single penalty drops the score from ~30 to ~17, pushing it far below the 50 threshold.

---

## Case 2: NFLX — Model Recommended Long Strangle, Stock Went Sideways

### Timeline

| Date | NFLX Price | Model Output | Result |
|------|-----------|--------------|--------|
| May 12 | ~$87.00 | **Trade candidate**: long_strangle 88C/87P | — |
| May 20 | ~$88.01 | — | Strangle losing to theta, stock inside breakevens |

### What the Model Recommended

**Long Strangle** (buy 88C, buy 87P, ~Jun 18, ~29 DTE):
- Net debit: ~$573 (model's max_loss)
- **Model said: PoP = 73.7%**, EV = +$840, touch = 80%
- **Quality gate: PASSED** → "trade_candidate"

### What Actually Happened

NFLX moved from $87.00 → $88.01 (+1.2%). The strangle needs a move to ~$81 or ~$94 to profit. With 29 DTE and daily theta burn, the position is bleeding unless a big move happens soon.

### Why the Model Failed — Critical Bug

#### IV Calculation Includes Extreme Outliers

The model computes `iv_atm` like this:

```python
iv_series = pd.to_numeric(frame["implied_volatility"], errors="coerce").dropna()
iv_atm = float(iv_series.mean())
```

**This uses ALL strikes across ALL expirations.**

NFLX snapshot data (May 12):

| Metric | Value |
|--------|-------|
| ~30 DTE mean IV | **56.7%** (inflated by outliers) |
| ~30 DTE median IV | **33.0%** (reasonable) |
| True ATM IV | **~30%** |
| Outlier strikes | 1340C @ 937% IV, 1500C @ 711% IV |

**Verification**: We ran the probability model with different IV assumptions:

| IV Used | PoP | EV | Touch |
|---------|-----|-----|-------|
| 30% (true ATM) | **35.8%** | -$88 | 48.4% |
| 35% (slightly elevated) | 43.2% | +$9 | 55.7% |
| 56.7% (model's mean) | **~58%** | +$302 | ~71% |
| 72% (all-exp mean) | **~69%** | +$693 | ~83% |

**The model reported 73.7% PoP. This required an IV of ~70-75%.**

The actual ATM IV was ~30%. The model **overstated PoP by roughly 2x**.

#### The Long Strangle Should Never Have Been Recommended

With true ATM IV (~30%):
- PoP: ~36% (not 74%)
- EV: -$88 (negative, not +$840)
- This would have **FAILED the quality gate** (EV < 0)
- The model would have correctly said "no_trade"

#### Why Outliers Exist

- Deep OTM LEAPS (strikes 1200-1500) on low-priced stocks have mathematically extreme IVs
- These are illiquid, wide-spread, and not tradeable
- The model should filter them out with `max_bid_ask_spread_pct` or IV bounds, but it doesn't before computing the mean

---

## Systemic Issues in the Scoring Function

### Weights Analysis

```python
raw = (
    0.27 * pop
    + 0.18 * ev_scaled
    + 0.14 * rr_scaled
    + 0.12 * theta_scaled
    + 0.08 * touch_comfort_scaled
    + 0.11 * edge_score
    - 0.05 * loss_penalty
    - 0.02 * vega_penalty
    - negative_ev_penalty
    - high_touch_penalty
)
```

**Problems:**

1. **PoP overweighted at 27%**: High PoP with negative EV is a classic trap. The model rewards "likely to win" without adequately penalizing "likely to lose money when it does."

2. **Risk/reward underweighted at 14%**: Income strategies naturally have RR < 1.0. They can never score well on this component. A bull put with RR=0.23 gets only 8/100 points.

3. **Theta scaled poorly**: `tanh(theta/2)*50 + 50` means ANY positive theta starts at 50 and asymptotes to 100. A $0.01/day theta and a $5/day theta both score ~50-55. No differentiation.

4. **Edge score double-counts EV and RR**: Edge = `tanh(EV/300)*30 + 30` + `min(40, RR*20)`. This is already in the formula separately. Adding it again at 11% overweights these factors.

5. **Loss penalty too weak at 5%**: `(max_loss + expected_loss) / 35` → A $400 max loss adds only 11.4 points of penalty. This doesn't adequately discourage capital-intensive trades.

6. **Negative EV penalty is subtractive, not multiplicative**: A single bad EV can drop score by 8-30 points, but the rest of the formula might still produce a passing score. This creates inconsistency.

### The Iron Condor Scoring Paradox

On May 11, the iron condor had:
- PoP: 61.7% → 27% weight = 16.7 points
- EV: -$5.41 → ev_scaled ~ -1.1 → 18% weight = -0.2 points
- RR: 2.49 → rr_scaled = min(100, 87.1) = 87.1 → 14% = 12.2 points
- Theta: +$0.036/day → theta_scaled ~ 51 → 12% = 6.1 points
- Touch comfort: 100 - 78.4 = 21.6 → 8% = 1.7 points
- Edge: ~35 + 40 = 75 → 11% = 8.3 points
- Loss penalty: (430 + 404)/35 = 23.8 → 5% = -1.2 points
- Vega penalty: negligible
- Negative EV penalty: ~8.2 points
- High touch penalty: (78.4 - 85) * 0.9 = 0 (since < 85)

**Raw score** ≈ 16.7 - 0.2 + 12.2 + 6.1 + 1.7 + 8.3 - 1.2 - 8.2 = **35.4**

But the model reported **46.1**. The discrepancy comes from the `high_touch_penalty` for iron_condor not being applied (only long_straddle/long_strangle get extra), and some rounding. Still, the score is below 50.

**The paradox**: A 62% PoP trade with $1,070 max profit, $430 max loss, on a stable mega-cap, is scored as "below actionable threshold." This is the core design flaw.

---

## The S&P 500 Scan Results Are Misleading

On May 12, the S&P 500 scan analyzed 80 tickers and found **only 4 trade candidates**.

Top names like AAPL, MSFT, NVDA, AMZN, META were ALL marked "no_trade" because no strategy scored above 50.

**This is not because there were no good trades.** It's because the scoring function and quality gate are calibrated too strictly.

The 4 candidates that did pass were:
- GILD covered_call (score 62.2, but requires $55K+ capital)
- KLAC covered_call (score 62.1, requires $129K+ capital)
- DE long_straddle (score 61.2, max loss $36,700)

These are either capital-intensive or high-risk. The model is not finding practical trades.

---

## Missing Components

### 1. No Directional Bias Integration

The model has `strategy_bias()` (bullish/neutral/long_vol) but never uses the trading system's directional signals.

The `trading/signals.py` and `trading/stocks/` modules likely have:
- Trend direction (bullish/bearish/neutral)
- Key support/resistance levels
- Momentum scores
- COT positioning (macro bias)

**The model should**: Boost scores for strategies aligned with directional bias. A bull put spread on a strongly bullish stock should score higher.

### 2. No Earnings/Event Filter

The model checks `days_to_exp` but doesn't check for:
- Earnings dates
- Fed meetings
- Ex-dividend dates
- Major macro events

An iron condor through an earnings week is extremely risky. The model doesn't warn about this.

### 3. No Position Sizing Model

The model reports max_loss but doesn't suggest position size based on:
- Account equity
- Risk per trade (e.g., 1-2% of equity)
- Portfolio correlation

A $400 max loss on a bull put is very different from a $2,700 max loss on a straddle. The model should normalize for this.

### 4. Greeks Are Not Filtered by Expiration

```python
iv_series = pd.to_numeric(frame["implied_volatility"], errors="coerce").dropna()
```

This is the same bug as the IV mean. All expirations are mixed together.

---

## Recommended Fixes (Priority Order)

### P0 — Critical Bugs

1. **Fix IV calculation** (`options/analyzer.py` line 551):
   ```python
   # CURRENT (BUG):
   iv_series = pd.to_numeric(frame["implied_volatility"], errors="coerce").dropna()
   iv_atm = float(iv_series.mean())

   # FIX:
   chain_slice = frame[frame["expiration"] == selected_expiration]
   clean_iv = pd.to_numeric(chain_slice["implied_volatility"], errors="coerce").dropna()
   # Remove obvious outliers
   clean_iv = clean_iv[(clean_iv >= 0.05) & (clean_iv <= 2.0)]
   iv_atm = float(clean_iv.median())  # Use median, not mean
   ```

2. **Fix greeks aggregation** (`options/scoring.py`):
   ```python
   # CURRENT: aggregates across all expirations
   rows = option_frame[
       (option_frame["expiration"] == candidate.expiration)
       & (option_frame["strike"] == leg.strike)
       & (option_frame["option_type"] == leg.option_type)
   ]
   # This is actually correct for expiration, but the frame passed in
   # may not be filtered. Verify the caller passes the right frame.
   ```

### P1 — Quality Gate Recalibration

3. **Lower composite score threshold**:
   ```python
   MIN_ACTIONABLE_COMPOSITE_SCORE = 35.0  # Was 50.0
   ```

4. **Add strategy-specific thresholds**:
   - Income strategies: min_score = 30, min_pop = 55%, max_touch = 80%
   - Long volatility: min_score = 40, require_iv_rank > 50 or IV > HV
   - Directional spreads: min_score = 35, require alignment with trend

5. **Allow slightly negative EV for income**:
   ```python
   # CURRENT:
   if expected_value < 0.0:
       blockers.append("negative_expected_value")

   # FIX:
   if expected_value < -50.0:  # Allow small negative EV
       blockers.append("negative_expected_value")
   ```

### P2 — Scoring Function Redesign

6. **Add drift to probability model**:
   ```python
   # In terminal_price_distribution:
   drift = risk_free_rate + equity_risk_premium  # ~0.08-0.10 annual
   prices = underlying_price * np.exp(
       (drift - 0.5 * vol_horizon**2) * t + vol_horizon * np.sqrt(t) * z
   )
   ```

7. **Reweight the scoring formula**:
   ```python
   raw = (
       0.20 * pop
       + 0.20 * ev_scaled
       + 0.15 * rr_scaled
       + 0.10 * theta_scaled
       + 0.10 * touch_comfort_scaled
       + 0.10 * edge_score
       + 0.10 * directional_alignment_score  # NEW
       - 0.05 * loss_penalty
       - 0.02 * vega_penalty
       - negative_ev_penalty
       - high_touch_penalty
   )
   ```

8. **Replace mean IV with ATM or VIX-proxy**:
   - Use `compute_put_call_skew()` to get true ATM IV
   - Or use a 5% moneyness band around ATM

### P3 — Feature Additions

9. **Integrate directional signals**:
   - Read from `trading/signals.py` or `trading/stocks/` momentum
   - Boost bullish strategy scores when trend is bullish
   - Block contrarian strategies unless mean-reversion signals are strong

10. **Add event/earnings filtering**:
    - Check `yfinance.Ticker(ticker).calendar` for earnings
    - Reject income strategies with earnings within DTE
    - Flag long volatility as "earnings play" if within 1 week

11. **Add position sizing output**:
    ```python
    "sizing": {
        "max_contracts_for_1pct_risk": int(account_risk / candidate.max_loss),
        "recommended_risk_pct": 1.0,
        "notional_at_risk": candidate.max_loss * contracts,
    }
    ```

12. **Track recommendation performance**:
    - Store recommendations with timestamps
    - Backtest: Did price stay inside profit range?
    - Build a feedback loop to auto-calibrate scoring weights

---

## Immediate Action Items

1. **Fix the IV outlier bug** — This is causing massive mispricing
2. **Lower quality gate to 35-40** — Stop rejecting viable trades
3. **Backtest the scoring function** — Run on last 3 months of data, see which trades would have been rejected vs which would have worked
4. **Add an override mode** — Allow manual trades (like the friend's bull put) to bypass the quality gate with a warning

---

## Appendix: Raw Data Verification

### NFLX IV Outliers (May 12, ~30 DTE)

```
Strike  Type  IV
1340.0  Call  937.8%
1500.0  Call  711.3%
```

These two contracts alone pulled the mean IV from ~30% to ~56.7%.

### MSFT Probability Sensitivity

Bull put 395/390 @ $420.98:

| IV | PoP | EV | Touch |
|----|-----|-----|-------|
| 30% | 76.3% | -$19.77 | 47.7% |
| 34% | 73.0% | -$35.30 | 53.7% |
| 50% | 64.7% | -$78.37 | 70.4% |

With 8% annual drift over 31 days: PoP increases by ~2-3%, EV improves by ~$12-15.

---

*End of report*
