"""
Tests for the trade journaling system.
"""

import pytest
from datetime import datetime, timezone
from pathlib import Path
import tempfile

from trading.journal import (
    TradeJournal,
    Trade,
    TradeStatus,
    TradeEnvironment,
    TradeOutcome,
    PositionUpdate,
    TradeReview,
)
from trading.journal.storage import SQLiteStorage, JSONStorage
from trading.journal.manual_trade import ManualTrade, ManualTradeStore


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    yield path
    Path(path).unlink(missing_ok=True)


@pytest.fixture
def temp_json_dir():
    """Create a temporary directory for JSON storage."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def sqlite_storage(temp_db):
    """SQLite storage fixture."""
    return SQLiteStorage(db_path=temp_db)


@pytest.fixture
def json_storage(temp_json_dir):
    """JSON storage fixture."""
    return JSONStorage(data_dir=temp_json_dir)


@pytest.fixture
def journal(sqlite_storage):
    """TradeJournal fixture."""
    return TradeJournal(storage=sqlite_storage)


# ─────────────────────────────────────────────────────────────────────────────
# Trade Model Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestTrade:
    """Tests for Trade model."""

    def test_create_trade(self):
        """Test creating a trade."""
        trade = Trade(
            coin="BTC",
            direction="long",
            entry_price=65000,
            size_usd=1000,
            leverage=5.0,
        )

        assert trade.coin == "BTC"
        assert trade.direction == "long"
        assert trade.entry_price == 65000
        assert trade.size_usd == 1000
        assert trade.leverage == 5.0
        assert trade.status == TradeStatus.PENDING
        assert trade.environment == TradeEnvironment.BACKTEST
        assert trade.id is not None

    def test_trade_properties(self):
        """Test trade computed properties."""
        trade = Trade(
            coin="ETH",
            direction="short",
            entry_price=3000,
            size_usd=500,
            leverage=10.0,
        )

        assert trade.notional_size == 5000  # 500 * 10
        assert trade.position_value == 5000
        assert not trade.is_long
        assert not trade.is_closed

    def test_calculate_pnl_long_winner(self):
        """Test P&L calculation for winning long."""
        trade = Trade(
            coin="BTC",
            direction="long",
            entry_price=60000,
            size_usd=1000,
            leverage=10,
        )

        # Move up 10%
        pnl = trade.calculate_pnl(current_price=66000)

        # 10% move on notional $10000 = $1000 gross
        expected = (66000 - 60000) * (10000 / 60000)
        assert abs(pnl - expected) < 1

    def test_calculate_pnl_short_winner(self):
        """Test P&L calculation for winning short."""
        trade = Trade(
            coin="ETH",
            direction="short",
            entry_price=3000,
            size_usd=500,
            leverage=5,
        )

        # Move down 10%
        pnl = trade.calculate_pnl(current_price=2700)

        # 10% down on notional $2500 = $250 gross
        expected = (3000 - 2700) * (2500 / 3000)
        assert abs(pnl - expected) < 1

    def test_close_trade(self):
        """Test closing a trade."""
        trade = Trade(
            coin="BTC",
            direction="long",
            entry_price=60000,
            size_usd=1000,
            leverage=1,
        )

        trade.close(exit_price=65000)

        assert trade.is_closed
        assert trade.exit_price == 65000
        assert trade.exit_time is not None
        assert trade.pnl_absolute is not None
        assert trade.pnl_percent is not None
        assert trade.outcome == TradeOutcome.WIN

    def test_trade_to_dict_roundtrip(self):
        """Test serialization roundtrip."""
        trade = Trade(
            coin="SOL",
            direction="long",
            entry_price=100,
            size_usd=200,
            leverage=3,
            entry_signals={"rsi": 30, "macd": "bullish"},
            tags=["momentum", "breakout"],
        )

        data = trade.to_dict()
        restored = Trade.from_dict(data)

        assert restored.coin == trade.coin
        assert restored.direction == trade.direction
        assert restored.entry_price == trade.entry_price
        assert restored.leverage == trade.leverage
        assert restored.entry_signals == trade.entry_signals
        assert restored.tags == trade.tags


# ─────────────────────────────────────────────────────────────────────────────
# Storage Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestSQLiteStorage:
    """Tests for SQLite storage backend."""

    def test_save_and_get_trade(self, sqlite_storage):
        """Test saving and retrieving a trade."""
        trade = Trade(
            coin="BTC",
            direction="long",
            entry_price=50000,
            size_usd=1000,
            environment=TradeEnvironment.PAPER,
        )

        sqlite_storage.save_trade(trade)
        retrieved = sqlite_storage.get_trade(trade.id)

        assert retrieved is not None
        assert retrieved.coin == "BTC"
        assert retrieved.direction == "long"
        assert retrieved.entry_price == 50000
        assert retrieved.environment == TradeEnvironment.PAPER

    def test_update_trade(self, sqlite_storage):
        """Test updating an existing trade."""
        trade = Trade(
            coin="ETH",
            direction="short",
            entry_price=3000,
            size_usd=500,
        )

        sqlite_storage.save_trade(trade)

        # Update and save again
        trade.close(exit_price=2800)
        sqlite_storage.save_trade(trade)

        retrieved = sqlite_storage.get_trade(trade.id)
        assert retrieved.is_closed
        assert retrieved.outcome == TradeOutcome.WIN

    def test_get_trades_with_filters(self, sqlite_storage):
        """Test querying trades with filters."""
        # Create trades in different environments
        for i, env in enumerate(
            [TradeEnvironment.BACKTEST, TradeEnvironment.PAPER, TradeEnvironment.LIVE]
        ):
            trade = Trade(
                coin=["BTC", "ETH", "SOL"][i],
                direction="long",
                entry_price=100 * (i + 1),
                size_usd=100,
                environment=env,
            )
            trade.status = TradeStatus.OPEN
            sqlite_storage.save_trade(trade)

        # Query by environment
        paper_trades = sqlite_storage.get_trades(environment=TradeEnvironment.PAPER)
        assert len(paper_trades) == 1
        assert paper_trades[0].coin == "ETH"

    def test_save_and_get_position_update(self, sqlite_storage):
        """Test position updates."""
        trade = Trade(
            coin="BTC",
            direction="long",
            entry_price=50000,
            size_usd=1000,
        )
        sqlite_storage.save_trade(trade)

        update = PositionUpdate(
            trade_id=trade.id,
            timestamp=datetime.now(timezone.utc),
            current_price=52000,
            unrealized_pnl=400,
        )
        sqlite_storage.save_position_update(update)

        updates = sqlite_storage.get_position_updates(trade.id)
        assert len(updates) == 1
        assert updates[0].current_price == 52000

    def test_save_and_get_review(self, sqlite_storage):
        """Test trade reviews."""
        trade = Trade(
            coin="BTC",
            direction="long",
            entry_price=50000,
            size_usd=1000,
        )
        sqlite_storage.save_trade(trade)

        review = TradeReview(
            trade_id=trade.id,
            setup_quality=8,
            entry_quality=7,
            what_went_well="Good entry timing",
            lessons_learned="Wait for confirmation",
        )
        sqlite_storage.save_review(review)

        retrieved = sqlite_storage.get_review(trade.id)
        assert retrieved is not None
        assert retrieved.setup_quality == 8
        assert "confirmation" in retrieved.lessons_learned

    def test_performance_stats(self, sqlite_storage):
        """Test performance statistics calculation."""
        # Create some closed trades
        for pnl in [100, -50, 200, -30, 0]:
            trade = Trade(
                coin="BTC",
                direction="long",
                entry_price=50000,
                size_usd=1000,
                environment=TradeEnvironment.PAPER,
            )
            if pnl > 0:
                trade.close(exit_price=50000 + pnl)
            elif pnl < 0:
                trade.close(exit_price=50000 + pnl)
            else:
                trade.close(exit_price=50000)
            sqlite_storage.save_trade(trade)

        stats = sqlite_storage.get_performance_stats(environment=TradeEnvironment.PAPER)

        assert stats["total_trades"] == 5
        assert stats["wins"] == 2
        assert stats["losses"] == 2
        assert stats["breakevens"] == 1


class TestJSONStorage:
    """Tests for JSON storage backend."""

    def test_save_and_get_trade(self, json_storage):
        """Test JSON storage."""
        trade = Trade(
            coin="BTC",
            direction="long",
            entry_price=50000,
            size_usd=1000,
        )

        json_storage.save_trade(trade)
        retrieved = json_storage.get_trade(trade.id)

        assert retrieved is not None
        assert retrieved.coin == "BTC"


# ─────────────────────────────────────────────────────────────────────────────
# Journal Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestTradeJournal:
    """Tests for TradeJournal high-level interface."""

    def test_record_entry_and_exit(self, journal):
        """Test complete trade lifecycle."""
        # Record entry
        trade = journal.record_entry(
            coin="BTC",
            direction="long",
            entry_price=50000,
            size_usd=1000,
            environment=TradeEnvironment.PAPER,
            stop_loss=48000,
            take_profit=55000,
            entry_signals={"rsi": 25, "cot_bias": "bullish"},
            tags=["reversal", "cot_aligned"],
        )

        assert trade.id is not None
        assert trade.coin == "BTC"
        assert trade.status == TradeStatus.OPEN

        # Record exit
        closed = journal.record_exit(
            trade_id=trade.id,
            exit_price=55000,
            exit_signals={"rsi": 70},
        )

        assert closed is not None
        assert closed.is_closed
        assert closed.outcome == TradeOutcome.WIN

    def test_position_updates(self, journal):
        """Test position update tracking."""
        trade = journal.record_entry(
            coin="ETH",
            direction="long",
            entry_price=3000,
            size_usd=500,
        )

        # Record several updates
        for price in [3100, 3200, 3150]:
            journal.record_position_update(
                trade_id=trade.id,
                current_price=price,
            )

        updates = journal.storage.get_position_updates(trade.id)
        assert len(updates) == 3

    def test_add_review(self, journal):
        """Test adding trade review."""
        trade = journal.record_entry(
            coin="SOL",
            direction="long",
            entry_price=100,
            size_usd=200,
        )
        journal.record_exit(trade.id, exit_price=120)

        review = journal.add_review(
            trade_id=trade.id,
            setup_quality=9,
            entry_quality=8,
            exit_quality=7,
            what_went_well="Perfect entry on support",
            what_went_wrong="Exited too early",
            lessons_learned="Let winners run longer",
        )

        assert review.trade_id == trade.id
        assert review.setup_quality == 9

    def test_get_stats(self, journal):
        """Test performance stats retrieval."""
        # Create trades in different environments
        for env, pnl in [
            (TradeEnvironment.BACKTEST, 100),
            (TradeEnvironment.BACKTEST, -50),
            (TradeEnvironment.PAPER, 75),
        ]:
            trade = journal.record_entry(
                coin="BTC",
                direction="long",
                entry_price=50000,
                size_usd=100,
                environment=env,
            )
            journal.record_exit(trade.id, exit_price=50000 + pnl)

        backtest_stats = journal.get_stats(environment=TradeEnvironment.BACKTEST)
        assert backtest_stats["total_trades"] == 2

    def test_get_open_trades(self, journal):
        """Test getting open trades."""
        # Open trades
        t1 = journal.record_entry("BTC", "long", 50000, 1000)
        journal.record_entry("ETH", "long", 3000, 500)

        # Closed trade
        t3 = journal.record_entry("SOL", "long", 100, 200)
        journal.record_exit(t3.id, exit_price=120)

        open_trades = journal.get_open_trades()
        assert len(open_trades) == 2
        assert t1.id in [t.id for t in open_trades]
        assert t3.id not in [t.id for t in open_trades]

    def test_generate_report(self, journal):
        """Test report generation."""
        # Create some trades
        for pnl in [100, -50, 200]:
            trade = journal.record_entry(
                coin="BTC",
                direction="long",
                entry_price=50000,
                size_usd=100,
                environment=TradeEnvironment.PAPER,
            )
            journal.record_exit(trade.id, exit_price=50000 + pnl)

        report = journal.generate_report(environment=TradeEnvironment.PAPER)

        assert "TRADE JOURNAL REPORT" in report
        assert "PAPER" in report
        assert "Total Trades:" in report
        assert "3" in report


# ─────────────────────────────────────────────────────────────────────────────
# Integration Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestIntegrations:
    """Tests for strategy journaling integrations."""

    def test_strategy_journal_mixin(self, journal):
        """Test StrategyJournalMixin functionality."""
        from trading.journal.integrations import StrategyJournalMixin

        class MockStrategy(StrategyJournalMixin):
            pass

        strategy = MockStrategy()
        strategy.setup_journal(
            environment=TradeEnvironment.PAPER,
            journal=journal,
        )

        # Record entry
        trade = strategy.journal_entry(
            coin="BTC",
            direction="long",
            entry_price=50000,
            size_usd=1000,
            leverage=5,
            entry_signals={"cot": "bullish"},
        )

        assert trade is not None
        assert strategy.get_journal_trade_id("BTC") == trade.id

        # Record exit
        closed = strategy.journal_exit("BTC", exit_price=55000)
        assert closed is not None
        assert closed.is_closed


class TestManualTradeStore:
    """Tests for manual per-trade JSON storage."""

    def test_create_and_get_manual_trade(self, temp_json_dir):
        store = ManualTradeStore(data_dir=temp_json_dir)
        trade = ManualTrade(
            asset="BTC",
            platform="binance",
            side="long",
            market_type="futures",
            trading_mode="demo",
            entry_price=65000,
            target_price=70000,
            stop_loss_price=62000,
            fees=12.5,
            size=1000,
            leverage=5,
            setup="order_block",
        )

        store.create_trade(trade)
        restored = store.get_trade(trade.trade_id)

        assert restored is not None
        assert restored.trade_id == trade.trade_id
        assert restored.trading_mode == "demo"
        assert restored.status == "open"
        assert len(restored.event_history) == 1
        assert restored.event_history[0]["action"] == "create"

    def test_take_profit_updates_and_close_rule(self, temp_json_dir):
        store = ManualTradeStore(data_dir=temp_json_dir)
        trade = ManualTrade(
            side="long",
            entry_price=100,
            target_price=120,
            stop_loss_price=90,
            trading_mode="live",
        )
        store.create_trade(trade)

        updated_tp1 = store.apply_update(
            trade.trade_id,
            "take_profit_price_1",
            110,
        )
        assert updated_tp1.status == "open"
        assert updated_tp1.take_profit_price_1 == 110
        assert updated_tp1.tp1_progress_percent == 50.0

        updated_final = store.apply_update(
            trade.trade_id,
            "take_profit_final_price",
            120,
        )
        assert updated_final.take_profit_final_price == 120
        assert updated_final.status == "closed"

    def test_unsynced_and_mark_synced(self, temp_json_dir):
        store = ManualTradeStore(data_dir=temp_json_dir)
        trade = ManualTrade(
            asset="ETH",
            side="short",
            market_type="spot",
            trading_mode="demo",
            entry_price=3000,
            target_price=2600,
            stop_loss_price=3200,
        )
        store.create_trade(trade)

        unsynced = store.unsynced_trades()
        assert len(unsynced) == 1
        assert unsynced[0].trade_id == trade.trade_id

        store.mark_synced([trade.trade_id], "Journal-2026-04")
        after = store.unsynced_trades()
        assert len(after) == 0

        restored = store.get_trade(trade.trade_id)
        assert restored is not None
        assert restored.sync.get("wiki_page") == "Journal-2026-04"
