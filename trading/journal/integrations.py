"""
Integrations for trade journaling with strategy and backtest systems.
"""

from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta, timezone

from .journal import TradeJournal
from .models import Trade, TradeEnvironment, PositionUpdate, TradeReview
from .storage import StorageBackend


class StrategyJournalMixin:
    """
    Mixin to add journaling to trading strategies.

    Add to BaseStrategy to automatically record all trades.

    Usage:
        class MyStrategy(BaseStrategy, StrategyJournalMixin):
            def __init__(self, client, **kwargs):
                super().__init__(client, **kwargs)
                self.setup_journal(environment=TradeEnvironment.PAPER)

            def _open(self, coin, direction, size_usd):
                # Record in journal
                trade = self.journal.record_entry(...)
                self._track_open_trade(coin, trade.id)

                # Execute trade
                super()._open(coin, direction, size_usd)
    """

    journal: Optional[TradeJournal] = None
    _open_trades: Dict[str, str]  # coin -> trade_id mapping

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)

    def setup_journal(
        self,
        environment: TradeEnvironment = TradeEnvironment.PAPER,
        journal: Optional[TradeJournal] = None,
    ) -> None:
        """
        Setup the trade journal.

        Args:
            environment: Trading environment
            journal: Custom journal instance (creates default if None)
        """
        self.journal = journal or TradeJournal()
        self.journal_env = environment
        self._open_trades = {}

    def journal_entry(
        self,
        coin: str,
        direction: str,
        entry_price: float,
        size_usd: float,
        leverage: float = 1.0,
        entry_signals: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        notes: str = "",
    ) -> Optional[Trade]:
        """
        Record trade entry in journal.

        Args:
            coin: Trading pair
            direction: "long" or "short"
            entry_price: Entry price
            size_usd: Position size
            leverage: Position leverage
            entry_signals: Signals that triggered entry
            tags: Trade tags
            notes: Initial notes

        Returns:
            Created Trade object
        """
        if not self.journal:
            return None

        trade = self.journal.record_entry(
            coin=coin,
            direction=direction,
            entry_price=entry_price,
            size_usd=size_usd,
            environment=self.journal_env,
            strategy_name=getattr(self, 'name', self.__class__.__name__),
            leverage=leverage,
            entry_signals=entry_signals,
            tags=tags,
            notes=notes,
        )

        self._open_trades[coin] = trade.id
        return trade

    def journal_exit(
        self,
        coin: str,
        exit_price: float,
        exit_signals: Optional[Dict[str, Any]] = None,
        notes: str = "",
    ) -> Optional[Trade]:
        """
        Record trade exit in journal.

        Args:
            coin: Trading pair
            exit_price: Exit price
            exit_signals: Signals that triggered exit
            notes: Exit notes

        Returns:
            Updated Trade object
        """
        if not self.journal or coin not in self._open_trades:
            return None

        trade_id = self._open_trades.pop(coin)
        return self.journal.record_exit(
            trade_id=trade_id,
            exit_price=exit_price,
            exit_signals=exit_signals,
            notes_addition=notes,
        )

    def journal_position_update(
        self,
        coin: str,
        current_price: float,
        **kwargs
    ) -> None:
        """
        Record position update in journal.

        Args:
            coin: Trading pair
            current_price: Current market price
            **kwargs: Additional update fields
        """
        if not self.journal or coin not in self._open_trades:
            return

        trade_id = self._open_trades[coin]
        self.journal.record_position_update(
            trade_id=trade_id,
            current_price=current_price,
            **kwargs
        )

    def get_journal_trade_id(self, coin: str) -> Optional[str]:
        """Get journal trade ID for an open position."""
        return self._open_trades.get(coin)

    def get_open_journal_trades(self) -> List[Trade]:
        """Get all open trades from journal."""
        if not self.journal:
            return []
        return self.journal.get_open_trades(environment=self.journal_env)

    def review_trade(
        self,
        trade_id: str,
        **review_kwargs
    ) -> Optional[TradeReview]:
        """
        Add a review to a trade.

        Args:
            trade_id: Trade ID
            **review_kwargs: Review fields

        Returns:
            Created TradeReview
        """
        if not self.journal:
            return None
        return self.journal.add_review(trade_id, **review_kwargs)


class BacktestJournalMixin:
    """
    Mixin to add journaling to backtest engine.

    Records all backtest trades for analysis and comparison.

    Usage:
        engine = BacktestEngine(...)
        engine.setup_journal()  # Auto-records all trades
        result = engine.run(strategy)

        # Get backtest trades
        trades = engine.get_journal_trades()
    """

    journal: Optional[TradeJournal] = None
    _journal_storage: Optional[StorageBackend] = None
    _backtest_trade_ids: List[str]

    def setup_journal(self, journal: Optional[TradeJournal] = None) -> None:
        """
        Setup journal for backtest recording.

        Args:
            journal: Custom journal instance
        """
        self.journal = journal or TradeJournal()
        self._journal_storage = self.journal.storage
        self._backtest_trade_ids = []

    def record_backtest_trade(self, trade: Trade) -> None:
        """
        Record a trade from backtest.

        Args:
            trade: Trade object to record
        """
        if not self.journal:
            return

        # Ensure it's marked as backtest
        trade.environment = TradeEnvironment.BACKTEST

        if self._journal_storage:
            self._journal_storage.save_trade(trade)
        self._backtest_trade_ids.append(trade.id)

    def get_backtest_trades(self) -> List[Trade]:
        """Get all trades recorded during backtest."""
        if not self.journal:
            return []

        trades = []
        for trade_id in self._backtest_trade_ids:
            trade = self.journal.get_trade(trade_id)
            if trade:
                trades.append(trade)
        return trades

    def compare_to_live(
        self,
        coin: Optional[str] = None,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Compare backtest performance to live/paper trading.

        Args:
            coin: Filter by coin
            days: Number of days to compare

        Returns:
            Comparison statistics
        """
        if not self.journal:
            return {}

        end_date = datetime.now(timezone.utc).replace(tzinfo=None)
        start_date = end_date - timedelta(days=days)

        backtest_stats = self.journal.get_stats(
            environment=TradeEnvironment.BACKTEST,
            start_date=start_date,
            end_date=end_date,
        )

        live_stats = self.journal.get_stats(
            environment=TradeEnvironment.LIVE,
            start_date=start_date,
            end_date=end_date,
        )

        paper_stats = self.journal.get_stats(
            environment=TradeEnvironment.PAPER,
            start_date=start_date,
            end_date=end_date,
        )

        return {
            'backtest': backtest_stats,
            'paper': paper_stats,
            'live': live_stats,
            'comparison': {
                'backtest_vs_live_pnl': (
                    backtest_stats.get('total_pnl', 0) -
                    live_stats.get('total_pnl', 0)
                ),
                'backtest_vs_paper_pnl': (
                    backtest_stats.get('total_pnl', 0) -
                    paper_stats.get('total_pnl', 0)
                ),
            }
        }
