# Testing Guide

This document outlines the testing strategy for the Nave trading system.

## Test Structure

```
tests/
├── test_journal/            # Trade journal tests
├── test_*.py                # Feature and integration tests
└── conftest.py              # Shared pytest fixtures
```

## Running Tests

### All Tests
```bash
pytest
```

### Journal Tests
```bash
pytest tests/test_journal/ -v
```

### COT/Trading Tests
```bash
pytest tests/ -v
```

### Key Metrics

- **Returns:** Total Return, CAGR, Volatility
- **Risk-Adjusted:** Sharpe, Sortino, Calmar ratios
- **Drawdown:** Max DD, DD duration
- **Trade Stats:** Win rate, Profit factor, average expectancy

## Test Data

### Unit/Integration Tests
- Use mocks and fixtures in `tests/conftest.py`
- No external dependencies required

## CI/CD

Tests run automatically on PR:
1. Unit tests (fast)
2. Integration tests (medium)

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

## Coverage

Target coverage: 80%+

```bash
pytest --cov=trading --cov-report=html
```

## Debugging

```bash
# Run single test with verbose output
pytest tests/test_journal/test_journal.py -v -s

# Run with debugger
pytest --pdb test_strategy.py

# Profile slow tests
pytest --durations=10
```
