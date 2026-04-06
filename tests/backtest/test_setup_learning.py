"""Tests for setup learning ML pipeline."""

from __future__ import annotations

from datetime import datetime

from trading.learning.setup_learner import SetupLearner
from trading.journal import TradeEnvironment, TradeJournal
from trading.journal.storage import SQLiteStorage
from trading.strategy import CotWeeklyStrategy
from tests.backtest.mocks.mock_cot_fetcher import HistoricalCotFetcher
from tests.backtest.mocks.mock_hyperliquid import MockHyperliquidClient
from tests.backtest.utils.backtest_engine import BacktestEngine


def test_setup_learning_trains_and_ranks():
    strategy = CotWeeklyStrategy(
        client=MockHyperliquidClient(),
        cot_fetcher=HistoricalCotFetcher(),
        test_mode=True,
    )
    engine = BacktestEngine(
        start_date=datetime(2023, 1, 1),
        end_date=datetime(2024, 6, 1),
        initial_capital=10000.0,
    )
    engine.run(strategy)

    ranked = strategy.setup_learner.rank_setups(["75_retracement", "order_block", "fvg"])
    assert len(ranked) == 3
    assert strategy.setup_learner.has_model()


def test_discover_new_patterns_returns_list():
    strategy = CotWeeklyStrategy(
        client=MockHyperliquidClient(),
        cot_fetcher=HistoricalCotFetcher(),
        test_mode=True,
    )
    engine = BacktestEngine(
        start_date=datetime(2023, 1, 1),
        end_date=datetime(2024, 12, 31),
        initial_capital=10000.0,
    )
    result = engine.run(strategy)
    patterns = strategy.setup_learner.discover_new_patterns(result)
    assert isinstance(patterns, list)


def test_save_and_load_model(tmp_path):
    learner = SetupLearner()
    strategy = CotWeeklyStrategy(
        client=MockHyperliquidClient(),
        cot_fetcher=HistoricalCotFetcher(),
        test_mode=True,
    )
    engine = BacktestEngine(
        start_date=datetime(2023, 1, 1),
        end_date=datetime(2024, 12, 31),
        initial_capital=10000.0,
    )
    result = engine.run(strategy)
    learner.fit(result)

    path = tmp_path / "setup_learner.joblib"
    learner.save_model(path)

    loaded = SetupLearner()
    assert loaded.load_model(path) is True
    assert loaded.has_model()


def test_backtest_trades_are_journaled(tmp_path):
    journal_db = tmp_path / "trades.db"
    journal = TradeJournal(storage=SQLiteStorage(str(journal_db)))
    strategy = CotWeeklyStrategy(
        client=MockHyperliquidClient(),
        cot_fetcher=HistoricalCotFetcher(),
        test_mode=True,
    )
    engine = BacktestEngine(
        start_date=datetime(2023, 1, 1),
        end_date=datetime(2023, 6, 1),
        initial_capital=10000.0,
        journal_enabled=True,
        journal=journal,
    )
    engine.run(strategy)

    stats = journal.get_stats(environment=TradeEnvironment.BACKTEST)
    assert stats.get("total_trades", 0) > 0
