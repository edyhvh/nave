# COT Backtesting Testing Plan

> **Branch:** `feat/cot-integration` (PR #8)  
> **Date:** April 6, 2026  
> **Author:** Nave Trading Team

---

## Executive Summary

This document outlines the testing plan for two critical backtesting objectives:

1. **Backtest to understand the best way to find setups** — Optimize COT signal parameters and entry criteria
2. **Backtest strategy** — Validate the complete `CotWeeklyStrategy` performance

---

## 1. Objective 1: Setup Discovery Backtest

### Goal
Determine optimal COT thresholds, confidence scoring, and entry criteria for finding high-probability setups.

### Hypotheses to Test

| # | Hypothesis | Test Method | Success Criteria |
|---|------------|-------------|------------------|
| 1.1 | Net %OI >20% with increasing positions yields >60% win rate | Historical COT data vs price 7D/14D/30D forward returns | Win rate >60%, Sharpe >1.0 |
| 1.2 | Net %OI 10-20% with stable positions is viable for swing trades | Compare 10-20% vs >20% cohorts | Win rate >55%, lower drawdown |
| 1.3 | Change in net positions (momentum) adds predictive power | Test with/without change filter | Improved Sharpe, reduced false signals |
| 1.4 | BTC vs ETH comparison selects the better performer | Backtest selection algorithm | Selected asset outperforms by >5% |
| 1.5 | Low OI (<1000 contracts) filter eliminates bad liquidity | Compare filtered vs unfiltered | Reduced slippage costs, similar win rate |

### Data Requirements

```yaml
historical_data:
  cot_reports:
    source: CFTC COT (legacy futures)
    assets: [BTC, ETH]
    codes: [133741, 138741]
    frequency: Weekly (Tue report, Fri release)
    history_needed: 3+ years (2022-2025)
  
  price_data:
    source: Hyperliquid or Coinbase
    timeframe: [1H, 4H, Daily]
    metrics: [OHLCV, funding_rate, open_interest]
    history_needed: Match COT period
```

### Test Implementation

```python
# nave/tests/backtest/test_setup_discovery.py

class TestSetupDiscovery:
    """Backtest COT signal parameters for optimal setup discovery."""
    
    def test_threshold_optimization(self):
        """Test various net_pct_oi thresholds."""
        thresholds = [5, 10, 15, 20, 25, 30]
        results = []
        
        for threshold in thresholds:
            signals = generate_signals(
                threshold=threshold,
                require_momentum=True,
                lookback_weeks=4
            )
            perf = backtest_signals(signals, forward_days=14)
            results.append({
                'threshold': threshold,
                'win_rate': perf.win_rate,
                'sharpe': perf.sharpe,
                'max_dd': perf.max_drawdown,
                'trades': perf.total_trades
            })
        
        # Optimal: highest Sharpe with >50 trades/year
        return optimize(results, target='sharpe', min_trades=50)
    
    def test_momentum_filter(self):
        """Compare signals with/without momentum filter."""
        with_momentum = backtest_signals(
            require_change_filter=True,
            min_change_pct=0.05
        )
        without_momentum = backtest_signals(
            require_change_filter=False
        )
        
        assert with_momentum.sharpe > without_momentum.sharpe * 1.2
        assert with_momentum.false_positive_rate < without_momentum.false_positive_rate
    
    def test_btc_vs_eth_selection(self):
        """Validate asset selection algorithm."""
        weeks = get_all_cot_weeks()
        correct_selections = 0
        
        for week in weeks:
            selected = select_best_asset(week)
            actual_best = get_best_performer(week, forward_days=7)
            if selected == actual_best:
                correct_selections += 1
        
        accuracy = correct_selections / len(weeks)
        assert accuracy > 0.55  # Better than coin flip
```

### Metrics to Track

```python
@dataclass
class SetupMetrics:
    # Performance
    win_rate: float              # % of profitable signals
    profit_factor: float         # Gross profit / Gross loss
    sharpe_ratio: float          # Risk-adjusted returns
    sortino_ratio: float         # Downside risk-adjusted
    
    # Risk
    max_drawdown: float          # Peak-to-trough decline
    avg_drawdown: float          # Average decline
    max_consecutive_losses: int  # Worst streak
    
    # Signal Quality
    total_signals: int           # Raw count
    valid_signals: int           # After filters
    false_positive_rate: float   # Signals that didn't move
    avg_time_to_profit: float    # Days to profitable
    
    # Market Conditions
    performance_by_regime: Dict  # Bull/bear/range performance
    performance_by_volatility: Dict  # High/low vol periods
```

---

## 2. Objective 2: Strategy Backtest

### Goal
Validate the complete `CotWeeklyStrategy` including position sizing, leverage, and risk management.

### Strategy Components to Test

```yaml
strategy_components:
  signal_generation:
    - COT analyzer (weekly)
    - Macro signal integration (stub → real)
    - Perp scan for alts
  
  position_sizing:
    - Risk % per trade (10% default)
    - Leverage scaling (1-10x by confidence)
    - Capital allocation (100% to best asset)
  
  execution:
    - Entry: 75% retrace + confluence
    - Stop: Invalidation point
    - Take profit: 2:1 R:R minimum
  
  risk_management:
    - Max leverage: 10x
    - Max drawdown: 20% monthly
    - Correlation limits (BTC/ETH)
```

### Test Scenarios

| Scenario | Description | Expected Behavior |
|----------|-------------|-------------------|
| 2.1 Strong Bull COT | BTC net long >20%, increasing | 10x long, full allocation |
| 2.2 Weak Signal | Both BTC/ETH neutral | No trade, wait for setup |
| 2.3 Divergence | COT bullish, price breaking down | Reduce size, tight stops |
| 2.4 ETH Outperformance | ETH score > BTC score | Allocate to ETH |
| 2.5 High Volatility | VIX >30 | Reduce leverage by 50% |
| 2.6 Consecutive Losses | 3 losses in a row | Reduce risk to 5% |

### Backtest Implementation

```python
# nave/tests/backtest/test_strategy.py

class TestCotWeeklyStrategy:
    """Full strategy backtest with realistic execution."""
    
    def setup_method(self):
        """Initialize strategy with test parameters."""
        self.client = MockHyperliquidClient()
        self.strategy = CotWeeklyStrategy(
            client=self.client,
            capital_usd=10000,  # Larger for meaningful stats
            risk_pct=0.10,
            test_mode=True
        )
        self.backtest_engine = BacktestEngine(
            start_date='2022-01-01',
            end_date='2025-03-31',
            initial_capital=10000
        )
    
    def test_full_strategy_backtest(self):
        """Run complete strategy backtest."""
        results = self.backtest_engine.run(self.strategy)
        
        # Performance thresholds
        assert results.cagr > 0.25          # 25% annual return
        assert results.sharpe > 1.0         # Risk-adjusted return
        assert results.max_drawdown < 0.30  # Max 30% drawdown
        assert results.win_rate > 0.50      # Better than random
        
        # Risk management
        assert results.avg_leverage <= 8    # Not over-leveraged
        assert results.max_leverage <= 10   # Respects limit
        assert results.consecutive_losses <= 5  # Recovery ability
    
    def test_position_sizing_logic(self):
        """Verify position sizing matches confidence."""
        test_cases = [
            {'confidence': 0.9, 'expected_leverage': 9, 'expected_size_pct': 1.0},
            {'confidence': 0.7, 'expected_leverage': 7, 'expected_size_pct': 0.7},
            {'confidence': 0.5, 'expected_leverage': 5, 'expected_size_pct': 0.5},
            {'confidence': 0.3, 'expected_leverage': 0, 'expected_size_pct': 0.0},  # No trade
        ]
        
        for case in test_cases:
            sizing = self.strategy.calculate_position_sizing(
                confidence=case['confidence'],
                capital=10000,
                stop_distance=0.02
            )
            assert sizing['leverage'] == case['expected_leverage']
            assert sizing['size_pct'] == case['expected_size_pct']
    
    def test_risk_limits(self):
        """Verify strategy respects risk limits."""
        # Simulate drawdown scenario
        self.backtest_engine.simulate_drawdown(0.25)
        
        # Strategy should reduce risk
        new_risk = self.strategy.adjust_risk_for_drawdown()
        assert new_risk < self.strategy.risk_pct
        
        # After recovery, risk should normalize
        self.backtest_engine.simulate_recovery()
        assert self.strategy.risk_pct == 0.10
    
    def test_market_regime_performance(self):
        """Analyze performance across market regimes."""
        regimes = self.backtest_engine.identify_regimes()
        
        for regime, trades in regimes.items():
            metrics = calculate_metrics(trades)
            
            if regime == 'bull_trend':
                assert metrics.win_rate > 0.60
            elif regime == 'bear_trend':
                assert metrics.win_rate > 0.40  # Harder in bears
                assert metrics.avg_leverage < 5  # More conservative
            elif regime == 'range':
                assert metrics.trades < 20  # Fewer signals
```

### Walk-Forward Analysis

```python
# nave/tests/backtest/test_walk_forward.py

class TestWalkForward:
    """Validate strategy robustness with walk-forward optimization."""
    
    def test_walk_forward(self):
        """
        1. Train on 12 months of data
        2. Optimize parameters
        3. Test on next 3 months
        4. Roll forward
        5. Aggregate results
        """
        window_train = 52   # weeks
        window_test = 13    # weeks
        
        results = []
        start = datetime(2022, 1, 1)
        end = datetime(2025, 3, 31)
        
        while start + timedelta(weeks=window_train + window_test) < end:
            train_end = start + timedelta(weeks=window_train)
            test_end = train_end + timedelta(weeks=window_test)
            
            # Optimize on training data
            optimal_params = optimize_parameters(start, train_end)
            
            # Test on out-of-sample data
            test_result = backtest_with_params(train_end, test_end, optimal_params)
            results.append(test_result)
            
            # Roll forward
            start += timedelta(weeks=window_test)
        
        # Aggregate
        aggregate = AggregateResults(results)
        
        # Should be consistent across periods
        assert aggregate.consistency_score > 0.7
        assert aggregate.avg_sharpe > 1.0
        assert aggregate.max_drawdown < 0.35
```

---

## 3. Test Infrastructure

### Required Components

```
nave/tests/backtest/
├── __init__.py
├── conftest.py                    # Shared fixtures
├── test_setup_discovery.py        # Objective 1
├── test_strategy.py               # Objective 2
├── test_walk_forward.py           # Robustness
├── fixtures/
│   ├── cot_historical.csv         # 3 years COT data
│   ├── price_data.parquet         # OHLCV for BTC/ETH
│   └── macro_indicators.csv       # VIX, RRP, etc.
├── mocks/
│   ├── mock_hyperliquid.py        # Mock exchange
│   └── mock_cot_fetcher.py        # Historical COT replay
└── utils/
    ├── backtest_engine.py         # Core backtest logic
    ├── metrics.py                 # Performance calculations
    └── visualization.py           # Plotting/reporting
```

### Mock Implementations

```python
# nave/tests/backtest/mocks/mock_cot_fetcher.py

class HistoricalCotFetcher:
    """Replays historical COT data for backtesting."""
    
    def __init__(self, data_path: str):
        self.data = pd.read_csv(data_path, parse_dates=['report_date'])
        self.current_idx = 0
    
    def set_date(self, date: datetime):
        """Set current backtest date."""
        self.current_idx = self.data[self.data['report_date'] <= date].index[-1]
    
    def latest_btc(self) -> Dict[str, Any]:
        """Return COT data as of current backtest date."""
        row = self.data.iloc[self.current_idx]
        return self._parse_row(row)
    
    def advance(self, weeks: int = 1):
        """Advance time for next iteration."""
        self.current_idx += weeks
```

### Data Collection Script

```python
# nave/scripts/collect_historical_data.py

"""
Collect historical data for backtesting.

Usage:
    python scripts/collect_historical_data.py --start 2022-01-01 --end 2025-03-31
"""

import argparse
from cot_reports import COTReport
import pandas as pd


def collect_cot_data(start_date: str, end_date: str):
    """Collect historical COT reports."""
    btc_report = COTReport('legacy_futures', '133741')
    eth_report = COTReport('legacy_futures', '138741')
    
    # Get all historical data
    btc_data = btc_report.historical(start=start_date, end=end_date)
    eth_data = eth_report.historical(start=start_date, end=end_date)
    
    # Save
    btc_data.to_csv('tests/backtest/fixtures/cot_btc.csv', index=False)
    eth_data.to_csv('tests/backtest/fixtures/cot_eth.csv', index=False)
    print(f"Collected {len(btc_data)} BTC reports, {len(eth_data)} ETH reports")


def collect_price_data(start_date: str, end_date: str):
    """Collect price data from Hyperliquid or Coinbase."""
    # TODO: Implement API calls
    pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', default='2022-01-01')
    parser.add_argument('--end', default='2025-03-31')
    args = parser.parse_args()
    
    collect_cot_data(args.start, args.end)
    collect_price_data(args.start, args.end)
```

---

## 4. Execution Timeline

| Phase | Duration | Tasks |
|-------|----------|-------|
| **Phase 1: Data Collection** | 2 days | Collect COT history, price data, macro indicators |
| **Phase 2: Infrastructure** | 3 days | Build mocks, backtest engine, metrics |
| **Phase 3: Setup Discovery** | 5 days | Run threshold tests, optimize parameters |
| **Phase 4: Strategy Backtest** | 5 days | Full strategy validation, regime analysis |
| **Phase 5: Walk-Forward** | 3 days | Robustness testing, parameter stability |
| **Phase 6: Reporting** | 2 days | Generate reports, visualizations, recommendations |

**Total: ~3 weeks**

---

## 5. Success Criteria

### Minimum Viable

- [ ] Setup discovery: >55% win rate with >1.0 Sharpe
- [ ] Strategy backtest: >20% CAGR, <30% max drawdown
- [ ] Walk-forward: Consistent performance across periods

### Target Performance

- [ ] Setup discovery: >65% win rate with >1.5 Sharpe
- [ ] Strategy backtest: >40% CAGR, <25% max drawdown, >1.2 Sharpe
- [ ] Walk-forward: >0.8 consistency score

### Stretch Goals

- [ ] Setup discovery: >70% win rate
- [ ] Strategy backtest: >50% CAGR, <20% max drawdown
- [ ] Identify 2+ additional alpha factors

---

## 6. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Limited COT history (2020+) | Medium | Use synthetic data, focus on recent regimes |
| Overfitting to parameters | High | Walk-forward validation, parameter stability tests |
| Survivorship bias in perps | Medium | Only test assets that existed at time |
| Look-ahead bias | Critical | Strict date filtering, mock time advancement |
| Execution slippage | Medium | Add 0.1% slippage to all trades |

---

## 7. Next Steps

1. **Immediate:** Run `collect_historical_data.py` to gather COT history
2. **Week 1:** Build test infrastructure (mocks, engine, metrics)
3. **Week 2:** Execute setup discovery backtests
4. **Week 3:** Execute strategy backtests and walk-forward analysis
5. **Deliverable:** Final report with optimized parameters and performance metrics

---

## Appendix: Key Formulas

```python
# Sharpe Ratio
sharpe = (returns.mean() - risk_free_rate) / returns.std() * sqrt(252)

# Sortino Ratio
sortino = (returns.mean() - risk_free_rate) / downside_returns.std() * sqrt(252)

# Profit Factor
profit_factor = gross_profit / abs(gross_loss)

# Maximum Drawdown
peak = equity_curve.cummax()
drawdown = (equity_curve - peak) / peak
max_drawdown = drawdown.min()

# Calmar Ratio
calmar = cagr / abs(max_drawdown)
```
