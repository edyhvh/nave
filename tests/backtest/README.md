# COT Strategy Backtesting Framework

This directory contains the backtesting infrastructure for the COT (Commitment of Traders) Weekly Strategy.

## Structure

```
tests/backtest/
├── README.md                    # This file
├── conftest.py                  # Pytest configuration
├── run_backtests.py             # CLI runner for backtests
├── test_setup_discovery.py      # Objective 1: Setup optimization
├── test_strategy.py             # Objective 2: Strategy validation
├── mocks/                       # Mock implementations
│   ├── mock_cot_fetcher.py      # Historical COT data replay
│   └── mock_hyperliquid.py      # Simulated exchange
├── utils/                       # Backtesting utilities
│   ├── backtest_engine.py       # Core backtest engine
│   └── metrics.py               # Performance metrics
└── fixtures/                    # Test data
    └── cot_historical.csv       # Historical COT data (add manually)
```

## Objectives

### Objective 1: Setup Discovery Optimization

**Goal:** Find the optimal way to identify high-probability setups using COT data.

**Key Tests:**
- `test_threshold_optimization`: Find optimal net_pct_oi thresholds
- `test_momentum_filter_impact`: Validate change filter effectiveness
- `test_btc_vs_eth_selection`: Test asset selection algorithm
- `test_low_oi_filter`: Verify OI filtering improves performance
- `test_confidence_scoring`: Ensure confidence correlates with returns
- `test_regime_dependence`: Analyze performance across market regimes

**Run:**
```bash
python run_backtests.py --objective setup-discovery
# or
pytest test_setup_discovery.py -v
```

### Objective 2: Strategy Validation

**Goal:** Validate the complete CotWeeklyStrategy with realistic execution.

**Key Tests:**
- `test_full_strategy_backtest`: End-to-end strategy performance
- `test_position_sizing_logic`: Verify sizing respects limits
- `test_risk_limits_respected`: Test risk management
- `test_leverage_scaling_by_confidence`: Validate leverage formula
- `test_trade_execution_simulation`: Test slippage and fees
- `test_correlation_and_diversification`: Handle correlated assets
- `test_market_regime_performance`: Performance across regimes

**Run:**
```bash
python run_backtests.py --objective strategy-validation
# or
pytest test_strategy.py -v
```

## Usage

### Quick Start

```bash
# Run all backtests
python run_backtests.py --all

# Run specific objective
python run_backtests.py --objective setup-discovery

# Generate HTML report
python run_backtests.py --report

# Run with pytest directly
pytest tests/backtest/ -v
```

### Adding Historical Data

1. Download historical COT data from CFTC
2. Process into the expected CSV format
3. Place in `fixtures/cot_historical.csv`

Expected format:
```csv
report_date,noncomm_long,noncomm_short,noncomm_net,open_interest,noncomm_pct_oi,change_noncomm_net
2022-01-04,45000,35000,10000,80000,12.5,500
...
```

### Running Walk-Forward Optimization

```python
from tests.backtest.utils.backtest_engine import WalkForwardOptimizer

wfo = WalkForwardOptimizer(train_weeks=52, test_weeks=13)
results = wfo.run(
    strategy_class=CotWeeklyStrategy,
    param_grid={
        'threshold': [10, 15, 20],
        'min_change': [0, 500, 1000],
    },
    start_date=datetime(2022, 1, 1),
    end_date=datetime(2025, 3, 31)
)

# Analyze stability
stability = wfo.analyze_stability(results)
print(f"Consistency score: {stability['consistency_score']:.2f}")
```

## Performance Metrics

The framework calculates comprehensive metrics:

### Returns
- Total Return
- CAGR (Compound Annual Growth Rate)
- Annualized Volatility

### Risk-Adjusted
- Sharpe Ratio
- Sortino Ratio
- Calmar Ratio

### Drawdown
- Max Drawdown
- Average Drawdown
- Max Drawdown Duration

### Trade Stats
- Win Rate
- Profit Factor
- Average Win/Loss
- Max Consecutive Losses
- Average Trade Duration

### Distribution
- Skewness
- Kurtosis
- VaR (95%)
- CVaR (95%)

## Mock Implementations

### HistoricalCotFetcher

Replays historical COT data for backtesting:

```python
from tests.backtest.mocks.mock_cot_fetcher import HistoricalCotFetcher

fetcher = HistoricalCotFetcher('fixtures/cot_historical.csv')
fetcher.set_date(datetime(2023, 6, 1))
data = fetcher.latest_btc()  # Returns COT as of that date
```

### MockHyperliquidClient

Simulates exchange with realistic execution:

```python
from tests.backtest.mocks.mock_hyperliquid import MockHyperliquidClient

client = MockHyperliquidClient(slippage_pct=0.001)
client.set_date(datetime(2023, 6, 1))

# Open position
trade = client.open_position(
    coin='BTC',
    direction='long',
    size_usd=10000,
    leverage=5
)

# Close position
closed = client.close_position('BTC')
print(f"PnL: ${closed.pnl:.2f}")
```

## Extending the Framework

### Adding New Tests

1. Create test file in `tests/backtest/`
2. Use fixtures from `conftest.py`
3. Import utilities from `utils/` and `mocks/`
4. Run with `pytest test_your_file.py -v`

### Adding New Metrics

Extend `PerformanceMetrics` dataclass in `utils/metrics.py`:

```python
@dataclass
class PerformanceMetrics:
    # ... existing fields ...
    your_new_metric: float = 0.0
```

Update `calculate_metrics()` to compute the new metric.

### Adding New Mocks

Create new mock in `mocks/` directory following the pattern:

```python
class MockYourService:
    def __init__(self, ...):
        pass
    
    def set_date(self, date: datetime):
        """Set current backtest date."""
        pass
```

## Configuration

### BacktestConfig

```python
from tests.backtest.utils.backtest_engine import BacktestConfig

config = BacktestConfig(
    start_date=datetime(2022, 1, 1),
    end_date=datetime(2025, 3, 31),
    initial_capital=10000.0,
    slippage_pct=0.001,        # 0.1%
    trading_fee_pct=0.0005,    # 0.05%
    max_leverage=10.0,
    max_drawdown_pct=0.30,     # Halt at 30% DD
    max_risk_per_trade=0.12,   # 12% risk per trade
)
```

## CI/CD Integration

Add to your CI pipeline:

```yaml
# .github/workflows/backtest.yml
- name: Run Backtests
  run: |
    cd nave/tests/backtest
    python run_backtests.py --all
    
- name: Upload Report
  uses: actions/upload-artifact@v3
  with:
    name: backtest-report
    path: nave/tests/backtest/backtest_report.html
```

## Notes

- Tests use synthetic data by default for structure validation
- Replace with real historical data for accurate results
- Weekly frequency matches COT report schedule
- All dates use the COT report date (Tuesday)
