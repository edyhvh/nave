# Proposed Code Fixes for Options Analysis Model

## Issue #1: IV Outlier Bug (CRITICAL)

**Location**: `options/analyzer.py`, lines 551-564

**Current buggy code**:
```python
iv_series = pd.to_numeric(
    frame["implied_volatility"], errors="coerce").dropna()
iv_history = self.cache.iv_history(
    symbol,
    lookback_days=self.config.iv_history_lookback_days,
    source=self.fetcher_source,
)
if not iv_series.empty:
    iv_history = pd.concat([iv_history, pd.Series(
        [float(iv_series.mean())], dtype=float)], ignore_index=True)
iv_rank, iv_percentile = compute_iv_rank_percentile(
    iv_history if not iv_history.empty else iv_series,
    lookback=self.config.iv_history_lookback_days,
)
```

**Problem**: `iv_series.mean()` averages IV across **all strikes and all expirations**, including deep OTM illiquid options with IV > 500%.

**Fix**:
```python
# Filter to selected expiration and reasonable strikes
expirations = sorted(frame["expiration"].dropna().unique().tolist())
from datetime import datetime, timezone
pairs = [(exp, max(1, (datetime.fromisoformat(exp).date() - datetime.now(timezone.utc).date()).days)) 
         for exp in expirations]
ordered = sorted(pairs, key=lambda item: (abs(item[1] - days_to_exp), item[1]))
selected_exp = ordered[0][0] if ordered else None

if selected_exp:
    chain_slice = frame[frame["expiration"] == selected_exp]
    clean_iv = pd.to_numeric(chain_slice["implied_volatility"], errors="coerce").dropna()
    # Remove obvious data errors
    clean_iv = clean_iv[(clean_iv >= 0.05) & (clean_iv <= 2.0)]
    iv_atm = float(clean_iv.median()) if not clean_iv.empty else 0.25
else:
    iv_atm = 0.25

# Also fix the history append
if not iv_history.empty:
    iv_history = pd.concat([iv_history, pd.Series([iv_atm], dtype=float)], ignore_index=True)
iv_rank, iv_percentile = compute_iv_rank_percentile(
    iv_history if not iv_history.empty else pd.Series([iv_atm], dtype=float),
    lookback=self.config.iv_history_lookback_days,
)
```

---

## Issue #2: Quality Gate Too Strict

**Location**: `options/analysis_overlay.py`, lines 16, 226-227

**Current**:
```python
MIN_ACTIONABLE_COMPOSITE_SCORE = 50.0

if composite < MIN_ACTIONABLE_COMPOSITE_SCORE:
    blockers.append("composite_score_below_actionable_threshold")
```

**Fix**: Lower threshold and make it strategy-dependent:
```python
MIN_ACTIONABLE_COMPOSITE_SCORE = 35.0
MAX_ACTIONABLE_COMPOSITE_SCORE = 50.0

def _min_score_for_strategy(strategy_name: str) -> float:
    if strategy_name in INCOME_STRATEGIES:
        return 30.0
    if strategy_name in AGGRESSIVE_STRATEGIES:
        return 40.0
    return 35.0

# In _quality_gate:
min_required = _min_score_for_strategy(strategy_name)
if composite < min_required:
    blockers.append(f"composite_score_below_{min_required}_threshold")
```

---

## Issue #3: Negative EV Penalty Too Harsh for Income

**Location**: `options/analysis_overlay.py`, lines 228-229

**Current**:
```python
if expected_value < 0.0:
    blockers.append("negative_expected_value")
```

**Fix**: Allow small negative EV (within noise of the probability model):
```python
if expected_value < -50.0:
    blockers.append("negative_expected_value")
elif expected_value < 0.0:
    warnings.append("slightly_negative_expected_value")
```

---

## Issue #4: Probability Model Lacks Drift

**Location**: `options/analytics/probability.py`, lines 32-44

**Current**:
```python
prices = underlying_price * \
    np.exp(-0.5 * vol_horizon * vol_horizon + vol_horizon * z)
```

**Fix**: Add risk-free rate drift:
```python
def terminal_price_distribution(
    underlying_price: float,
    implied_volatility: float,
    days_to_expiration: int,
    *,
    risk_free_rate: float = 0.04,
    points: int = 801,
    z_max: float = 4.5,
) -> tuple[np.ndarray, np.ndarray]:
    t = max(1, days_to_expiration) / 365.0
    sigma = max(0.001, implied_volatility)
    vol_horizon = sigma * math.sqrt(t)
    
    z = np.linspace(-z_max, z_max, max(51, points), dtype=float)
    # Add drift: (r - 0.5*sigma^2)*t + sigma*sqrt(t)*Z
    prices = underlying_price * np.exp(
        (risk_free_rate - 0.5 * sigma * sigma) * t + vol_horizon * z
    )
    weights = norm.pdf(z)
    weight_sum = float(weights.sum())
    if weight_sum <= 0:
        return prices, np.ones_like(prices) / len(prices)
    return prices, weights / weight_sum
```

---

## Issue #5: Scoring Function Underweights Income Strategies

**Location**: `options/scoring.py`, lines 64-108

**Current** (problematic components):
```python
ev_scaled = np.tanh(expected_value / 500.0) * 100.0
rr_scaled = min(100.0, risk_reward * 35.0)
edge_score = _edge_score(expected_value=expected_value, risk_reward=risk_reward)
theta_scaled = np.tanh(theta_per_day / 2.0) * 50.0 + 50.0

touch_comfort_scaled = 100.0 - probability_of_touch

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

**Fix**: Reweight and add strategy-specific adjustments:
```python
def _composite_score(..., directional_bias: str = "neutral"):
    # Normalize EV per dollar of max risk
    ev_per_risk = expected_value / max(1.0, max_loss) * 1000.0
    ev_scaled = np.tanh(ev_per_risk / 100.0) * 100.0
    
    # Better RR scaling for income strategies
    rr_scaled = min(100.0, risk_reward * 40.0)
    if strategy_name in INCOME_STRATEGIES and risk_reward >= 0.15:
        rr_scaled = min(100.0, 40.0 + risk_reward * 20.0)  # Floor for income
    
    edge_score = _edge_score(expected_value=expected_value, risk_reward=risk_reward)
    
    # Theta should differentiate small from large
    theta_scaled = min(100.0, max(0.0, theta_per_day * 20.0 + 50.0))
    
    touch_comfort_scaled = 100.0 - probability_of_touch
    
    # Directional alignment bonus
    directional_bonus = 0.0
    if strategy_name in {"bull_put_credit_spread", "bull_call_debit_spread", "covered_call", "cash_secured_put"}:
        if directional_bias == "bullish":
            directional_bonus = 8.0
        elif directional_bias == "bearish":
            directional_bonus = -5.0
    
    raw = (
        0.22 * pop
        + 0.18 * ev_scaled
        + 0.12 * rr_scaled
        + 0.10 * theta_scaled
        + 0.08 * touch_comfort_scaled
        + 0.08 * edge_score
        + 0.05 * directional_bonus
        - 0.04 * loss_penalty
        - 0.02 * vega_penalty
        - negative_ev_penalty
        - high_touch_penalty
    )
    return float(max(0.0, min(100.0, raw)))
```

---

## Issue #6: No Earnings/Event Filter

**Location**: `options/analyzer.py`, `options/strategies/builders.py`

**New function** (add to `options/analyzer.py`):
```python
def _has_earnings_within_dte(self, ticker: str, dte: int) -> tuple[bool, int | None]:
    """Check if earnings is within DTE. Returns (has_earnings, days_to_earnings)."""
    if yf is None:
        return False, None
    try:
        cal = yf.Ticker(ticker).calendar
        if cal is None or cal.empty:
            return False, None
        next_earnings = pd.to_datetime(cal.index[0]).date()
        days_to_earnings = (next_earnings - datetime.now(timezone.utc).date()).days
        return 0 <= days_to_earnings <= dte, days_to_earnings
    except Exception:
        return False, None
```

**Usage in `run()`**:
```python
has_earnings, days_to_earnings = self._has_earnings_within_dte(symbol, days_to_exp)
if has_earnings:
    underlying_analysis["event_warning"] = {
        "type": "earnings",
        "days_to_event": days_to_earnings,
        "recommendation": "avoid_income_strategies_through_earnings",
    }
```

---

## Issue #7: S&P Scan Hides Underlying Analysis

**Location**: `cli/commands/options.py`

The scan only stores `results[ticker]` with limited fields. It should also store:
- `underlying_analysis` per ticker
- `all_recommendations_ranked` per ticker
- `analysis_overlay` per ticker

This would allow post-hoc analysis of why a ticker was rejected.

---

## Testing Plan

1. **Unit test for IV outlier fix**:
   ```python
   def test_iv_calculation_excludes_outliers():
       frame = pd.DataFrame({
           "expiration": ["2026-06-18", "2026-06-18", "2026-06-18"],
           "strike": [100.0, 1500.0, 100.0],
           "implied_volatility": [0.30, 9.0, 0.32],
           "option_type": ["call", "call", "put"],
       })
       # After fix, iv_atm should be ~0.31, not ~3.2
   ```

2. **Backtest scoring function**:
   - Run model on last 90 days for MSFT, AAPL, NVDA
   - Compare "trade_candidate" vs actual price movement
   - Calculate precision/recall of the quality gate

3. **Sensitivity analysis**:
   - Vary composite score threshold from 25 to 60
   - Measure how many trade candidates appear
   - Measure how many would have been profitable

---

*These fixes should be implemented and tested before the next options scan.*
