# Testing Guide

This document outlines the testing strategy for the Nave trading system.

## Test Structure

```
tests/
├── unit/                    # Unit tests for individual components
├── integration/             # Integration tests
├── backtest/               # Backtesting framework (NEW)
│   ├── test_setup_discovery.py
│   ├── test_strategy.py
│   ├── mocks/
│   └── utils/
└── conftest.py             # Shared pytest fixtures
```

## Running Tests

### All Tests
```bash
pytest
```

### Unit Tests Only
```bash
pytest tests/unit/ -v
```

### Integration Tests
```bash
pytest tests/integration/ -v
```

### Backtests
```bash
# Run all backtests
python tests/backtest/run_backtests.py --all

# Setup discovery only
python tests/backtest/run_backtests.py --objective setup-discovery

# Strategy validation only
python tests/backtest/run_backtests.py --objective strategy-validation

# Generate HTML report
python tests/backtest/run_backtests.py --report
```

## Backtesting Framework

### Objectives

1. **Setup Discovery Optimization** (`test_setup_discovery.py`)
   - Find optimal COT signal thresholds
   - Validate momentum filter effectiveness
   - Test BTC vs ETH selection algorithm
   - Verify confidence scoring correlation

2. **Strategy Validation** (`test_strategy.py`)
   - Full strategy backtest with realistic execution
   - Position sizing and leverage validation
   - Risk limit compliance
   - Market regime performance analysis

### Key Metrics

- **Returns:** Total Return, CAGR, Volatility
- **Risk-Adjusted:** Sharpe, Sortino, Calmar ratios
- **Drawdown:** Max DD, DD duration
- **Trade Stats:** Win rate, Profit factor, Consecutive losses

See [tests/backtest/README.md](tests/backtest/README.md) for detailed documentation.

## Test Data

### Unit/Integration Tests
- Use mocks and fixtures in `tests/conftest.py`
- No external dependencies required

### Backtests
- Requires historical COT data in `tests/backtest/fixtures/`
- Can use synthetic data for structure validation
- Real data recommended for accurate results

## CI/CD

Tests run automatically on PR:
1. Unit tests (fast)
2. Integration tests (medium)
3. Backtests (slow, optional)

## Adding Tests

### Unit Test Example
```python
def test_cot_analyzer_threshold():
    analyzer = CotAnalyzer(threshold=15)
    signal = analyzer.analyze({
        'noncomm_pct_oi': 20,
        'change_noncomm_net': 1000
    })
    assert signal.direction == Direction.LONG
```

### Backtest Test Example
```python
def test_threshold_optimization(synthetic_cot_data):
    for threshold in [5, 10, 15, 20, 25]:
        signals = generate_signals(synthetic_cot_data, threshold)
        perf = simulate_returns(signals)
        results.append({'threshold': threshold, **perf})
    
    best = find_optimal(results)
    assert best['sharpe'] > 0
```

## Coverage

Target coverage: 80%+

```bash
pytest --cov=trading --cov-report=html
```

## Debugging

```bash
# Run single test with verbose output
pytest test_strategy.py::TestCotWeeklyStrategy::test_full_strategy_backtest -v -s

# Run with debugger
pytest --pdb test_strategy.py

# Profile slow tests
pytest --durations=10
```
