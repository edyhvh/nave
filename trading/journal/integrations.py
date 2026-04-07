"""
Integrations for trade journaling with strategy and backtest systems.
"""

from typing import Optional, Dict, Any, List

from .journal import TradeJournal
from .models import Trade, TradeEnvironment, TradeReview


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
            strategy_name=getattr(self, "name", self.__class__.__name__),
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

    def journal_position_update(self, coin: str, current_price: float, **kwargs) -> None:
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
            trade_id=trade_id, current_price=current_price, **kwargs
        )

    def get_journal_trade_id(self, coin: str) -> Optional[str]:
        """Get journal trade ID for an open position."""
        return self._open_trades.get(coin)

    def get_open_journal_trades(self) -> List[Trade]:
        """Get all open trades from journal."""
        if not self.journal:
            return []
        return self.journal.get_open_trades(environment=self.journal_env)

    def review_trade(self, trade_id: str, **review_kwargs) -> Optional[TradeReview]:
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
