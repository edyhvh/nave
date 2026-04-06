"""
Trade journaling system for nave.

Records all trades across backtest, paper, and live environments.
Provides systematic tracking, performance analysis, and trade reviews.

Usage:
    from trading.journal import TradeJournal, Trade, TradeEnvironment
    
    # Initialize journal
    journal = TradeJournal()
    
    # Record a trade
    trade = Trade(
        coin="BTC",
        direction="long",
        entry_price=65000,
        size_usd=1000,
        environment=TradeEnvironment.PAPER
    )
    journal.record_entry(trade)
    
    # Close the trade
    journal.record_exit(trade_id, exit_price=68000)
    
    # Get performance report
    report = journal.get_performance_report()
"""

from .models import (
    Trade,
    TradeStatus,
    TradeEnvironment,
    TradeOutcome,
    TradeJournalEntry,
    PositionUpdate,
    TradeReview,
)
from .journal import TradeJournal
from .storage import SQLiteStorage, JSONStorage
from .integrations import StrategyJournalMixin, BacktestJournalMixin

__all__ = [
    "Trade",
    "TradeStatus",
    "TradeEnvironment",
    "TradeOutcome",
    "TradeJournalEntry",
    "PositionUpdate",
    "TradeReview",
    "TradeJournal",
    "SQLiteStorage",
    "JSONStorage",
    "StrategyJournalMixin",
    "BacktestJournalMixin",
]