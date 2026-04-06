"""Pytest configuration for backtest tests."""

import pytest
from datetime import datetime
from pathlib import Path


# Add project root to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "optimization: marks tests as parameter optimization tests"
    )


@pytest.fixture(scope="session")
def test_data_dir():
    """Return path to test data directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def backtest_start_date():
    """Default backtest start date."""
    return datetime(2022, 1, 1)


@pytest.fixture(scope="session")
def backtest_end_date():
    """Default backtest end date."""
    return datetime(2025, 3, 31)


@pytest.fixture(scope="session")
def initial_capital():
    """Default initial capital for backtests."""
    return 10000.0
