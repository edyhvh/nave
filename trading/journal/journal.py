"""
Main TradeJournal class - high-level interface for trade recording.
"""

from datetime import datetime, timedelta, timezone
import logging
import os
from typing import List, Optional, Dict, Any

from .models import Trade, TradeEnvironment, TradeStatus, PositionUpdate, TradeReview, TradeOutcome, TradeJournalEntry
from .storage import StorageBackend, SQLiteStorage
from .github_sync import GitHubDataRepoSync

logger = logging.getLogger(__name__)


class TradeJournal:
    """
    High-level interface for recording and analyzing trades.

    Supports multiple environments (backtest, paper, live) with
    unified storage and reporting.

    Usage:
        journal = TradeJournal()  # Uses SQLite by default

        # Record entry
        trade = journal.record_entry(
            coin="BTC",
            direction="long",
            entry_price=65000,
            size_usd=1000,
            environment=TradeEnvironment.PAPER
        )

        # Update position
        journal.record_position_update(trade.id, current_price=66000)

        # Close trade
        journal.record_exit(trade.id, exit_price=68000)

        # Review
        journal.add_review(trade.id, setup_quality=8, notes="Good setup")

        # Get report
        stats = journal.get_stats(environment=TradeEnvironment.PAPER)
    """

    def __init__(
        self,
        storage: Optional[StorageBackend] = None,
        github_sync: Optional[GitHubDataRepoSync] = None,
        auto_github_sync: bool = False,
    ):
        """
        Initialize journal.

        Args:
            storage: Storage backend (defaults to SQLite)
            github_sync: Optional GitHub sync client for data-repo writes
            auto_github_sync: If True, auto-sync trade changes to GitHub data repo
        """
        self.storage = storage or SQLiteStorage()
        self.github_sync = github_sync
        self.auto_github_sync = auto_github_sync

        if self.auto_github_sync and self.github_sync is None:
            self.github_sync = GitHubDataRepoSync.from_env()

    def _safe_auto_sync(self, event: str, trade: Optional[Trade] = None) -> None:
        """Attempt GitHub sync without breaking trading flow."""
        if not self.auto_github_sync or self.github_sync is None:
            return

        try:
            if trade is not None:
                self.github_sync.sync_trade(trade, event=event)

            trades = self.storage.get_trades(limit=10000)
            stats = self.get_stats()
            metadata = {
                "event": event,
                "trade_id": trade.id if trade else None,
            }
            self.github_sync.sync_snapshot(
                trades=trades, stats=stats, metadata=metadata)
        except Exception:
            # Never fail core journal operations due to sync/network issues.
            logger.warning(
                "GitHub auto-sync failed for event '%s' (trade_id=%s). "
                "Check NAVE_GITHUB_TOKEN and data-repo settings.",
                event,
                trade.id if trade else None,
                exc_info=True,
            )
            return

    def sync_to_github(self, trade_id: Optional[str] = None) -> bool:
        """Manually sync journal data to configured GitHub data repo."""
        if self.github_sync is None:
            return False

        trade = self.storage.get_trade(trade_id) if trade_id else None
        try:
            if trade is not None:
                self.github_sync.sync_trade(trade, event="manual")

            trades = self.storage.get_trades(limit=10000)
            stats = self.get_stats()
            self.github_sync.sync_snapshot(
                trades=trades,
                stats=stats,
                metadata={
                    "event": "manual",
                    "trade_id": trade.id if trade else None,
                },
            )
            return True
        except Exception:
            return False

    @classmethod
    def with_github_sync_from_env(
        cls,
        storage: Optional[StorageBackend] = None,
        auto_github_sync: Optional[bool] = None,
    ) -> "TradeJournal":
        """Create journal with GitHub sync configured from env vars."""
        sync = GitHubDataRepoSync.from_env()
        if auto_github_sync is None:
            auto_github_sync = os.getenv(
                "NAVE_GITHUB_AUTO_SYNC", "false").lower() == "true"
        return cls(storage=storage, github_sync=sync, auto_github_sync=auto_github_sync)

    def record_entry(
        self,
        coin: str,
        direction: str,
        entry_price: float,
        size_usd: float,
        environment: TradeEnvironment = TradeEnvironment.BACKTEST,
        strategy_name: str = "unknown",
        leverage: float = 1.0,
        entry_fee: float = 0.0,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        entry_signals: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        notes: str = "",
    ) -> Trade:
        """
        Record a new trade entry.

        Args:
            coin: Trading pair (e.g., "BTC", "ETH")
            direction: "long" or "short"
            entry_price: Entry price
            size_usd: Position size in USD
            environment: BACKTEST, PAPER, or LIVE
            strategy_name: Name of the strategy
            leverage: Position leverage
            entry_fee: Entry fee paid
            stop_loss: Stop loss price
            take_profit: Take profit price
            entry_signals: Dict of signals that triggered entry
            tags: List of tags for categorization
            notes: Initial notes

        Returns:
            The created Trade object
        """
        trade = Trade(
            coin=coin,
            direction=direction,
            entry_price=entry_price,
            size_usd=size_usd,
            environment=environment,
            strategy_name=strategy_name,
            leverage=leverage,
            entry_fee=entry_fee,
            stop_loss=stop_loss,
            take_profit=take_profit,
            entry_signals=entry_signals or {},
            tags=tags or [],
            notes=notes,
            status=TradeStatus.OPEN,
        )

        self.storage.save_trade(trade)
        self._safe_auto_sync(event="entry", trade=trade)
        return trade

    def record_exit(
        self,
        trade_id: str,
        exit_price: float,
        exit_fee: float = 0.0,
        exit_signals: Optional[Dict[str, Any]] = None,
        notes_addition: str = "",
    ) -> Optional[Trade]:
        """
        Record trade exit.

        Args:
            trade_id: Trade ID
            exit_price: Exit price
            exit_fee: Exit fee paid
            exit_signals: Dict of signals that triggered exit
            notes_addition: Additional notes to append

        Returns:
            Updated Trade object or None if not found
        """
        trade = self.storage.get_trade(trade_id)
        if not trade:
            return None

        # Close the trade (set exit_fee first so P&L includes it)
        trade.exit_fee = exit_fee
        trade.close(exit_price)
        trade.exit_signals = exit_signals or {}

        if notes_addition:
            trade.notes += f"\n[Exit] {notes_addition}"

        self.storage.save_trade(trade)
        self._safe_auto_sync(event="exit", trade=trade)
        return trade

    def record_position_update(
        self,
        trade_id: str,
        current_price: float,
        funding_paid: float = 0.0,
        margin_used: float = 0.0,
        liquidation_price: Optional[float] = None,
    ) -> None:
        """
        Record a position update (periodic snapshots).

        Args:
            trade_id: Trade ID
            current_price: Current market price
            funding_paid: Cumulative funding paid
            margin_used: Margin used
            liquidation_price: Liquidation price
        """
        trade = self.storage.get_trade(trade_id)
        if not trade:
            return

        unrealized_pnl = trade.calculate_pnl(current_price)

        update = PositionUpdate(
            trade_id=trade_id,
            timestamp=datetime.now(timezone.utc).replace(tzinfo=None),
            current_price=current_price,
            unrealized_pnl=unrealized_pnl,
            funding_paid=funding_paid,
            margin_used=margin_used,
            liquidation_price=liquidation_price,
        )

        self.storage.save_position_update(update)

    def add_funding_fee(self, trade_id: str, amount: float) -> None:
        """
        Add funding fee to a trade.

        Args:
            trade_id: Trade ID
            amount: Funding fee amount (positive = paid, negative = received)
        """
        trade = self.storage.get_trade(trade_id)
        if trade:
            trade.funding_fees += amount
            self.storage.save_trade(trade)

    def add_review(
        self,
        trade_id: str,
        setup_quality: int = 0,
        entry_quality: int = 0,
        exit_quality: int = 0,
        risk_management: int = 0,
        what_went_well: str = "",
        what_went_wrong: str = "",
        lessons_learned: str = "",
        would_take_again: bool = True,
        improvements: str = "",
    ) -> TradeReview:
        """
        Add a trade review.

        Args:
            trade_id: Trade ID
            setup_quality: 1-10 rating
            entry_quality: 1-10 rating
            exit_quality: 1-10 rating
            risk_management: 1-10 rating
            what_went_well: Description
            what_went_wrong: Description
            lessons_learned: Key lessons
            would_take_again: Whether you'd take this trade again
            improvements: What to improve

        Returns:
            The created TradeReview
        """
        review = TradeReview(
            trade_id=trade_id,
            setup_quality=setup_quality,
            entry_quality=entry_quality,
            exit_quality=exit_quality,
            risk_management=risk_management,
            what_went_well=what_went_well,
            what_went_wrong=what_went_wrong,
            lessons_learned=lessons_learned,
            would_take_again=would_take_again,
            improvements=improvements,
        )

        self.storage.save_review(review)
        trade = self.storage.get_trade(trade_id)
        self._safe_auto_sync(event="review", trade=trade)
        return review

    def update_notes(self, trade_id: str, notes: str, append: bool = False) -> None:
        """
        Update trade notes.

        Args:
            trade_id: Trade ID
            notes: New notes
            append: If True, append to existing notes
        """
        trade = self.storage.get_trade(trade_id)
        if trade:
            if append and trade.notes:
                trade.notes += f"\n{notes}"
            else:
                trade.notes = notes
            self.storage.save_trade(trade)
            self._safe_auto_sync(event="notes", trade=trade)

    def add_tags(self, trade_id: str, tags: List[str]) -> None:
        """
        Add tags to a trade.

        Args:
            trade_id: Trade ID
            tags: Tags to add
        """
        trade = self.storage.get_trade(trade_id)
        if trade:
            for tag in tags:
                if tag not in trade.tags:
                    trade.tags.append(tag)
            self.storage.save_trade(trade)
            self._safe_auto_sync(event="tags", trade=trade)

    def get_trade(self, trade_id: str) -> Optional[Trade]:
        """Get a trade by ID."""
        return self.storage.get_trade(trade_id)

    def get_journal_entry(self, trade_id: str) -> Optional[TradeJournalEntry]:
        """
        Get a full journal entry (trade + position updates + review).

        Args:
            trade_id: Trade ID

        Returns:
            TradeJournalEntry or None if trade not found
        """
        trade = self.storage.get_trade(trade_id)
        if not trade:
            return None
        updates = self.storage.get_position_updates(trade_id)
        review = self.storage.get_review(trade_id)
        return TradeJournalEntry(trade=trade, position_updates=updates, review=review)

    def get_open_trades(
        self,
        environment: Optional[TradeEnvironment] = None,
        coin: Optional[str] = None,
    ) -> List[Trade]:
        """
        Get all open trades.

        Args:
            environment: Filter by environment
            coin: Filter by coin

        Returns:
            List of open trades
        """
        return self.storage.get_trades(
            environment=environment,
            status=TradeStatus.OPEN,
            coin=coin,
        )

    def get_trade_history(
        self,
        environment: Optional[TradeEnvironment] = None,
        coin: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 1000,
    ) -> List[Trade]:
        """
        Get trade history.

        Args:
            environment: Filter by environment
            coin: Filter by coin
            start_date: Start date filter
            end_date: End date filter
            limit: Maximum number of trades

        Returns:
            List of trades
        """
        return self.storage.get_trades(
            environment=environment,
            coin=coin,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )

    def get_stats(
        self,
        environment: Optional[TradeEnvironment] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Get performance statistics.

        Args:
            environment: Filter by environment
            start_date: Start date filter
            end_date: End date filter

        Returns:
            Dict with performance statistics
        """
        return self.storage.get_performance_stats(
            environment=environment,
            start_date=start_date,
            end_date=end_date,
        )

    def generate_report(
        self,
        environment: Optional[TradeEnvironment] = None,
        days: int = 30,
    ) -> str:
        """
        Generate a formatted performance report.

        Args:
            environment: Filter by environment
            days: Number of days to include

        Returns:
            Formatted report string
        """
        end_date = datetime.now(timezone.utc).replace(tzinfo=None)
        start_date = end_date - timedelta(days=days)

        stats = self.get_stats(
            environment=environment,
            start_date=start_date,
            end_date=end_date,
        )

        env_str = environment.value.upper() if environment else "ALL"

        if stats['total_trades'] == 0:
            return f"""
╔══════════════════════════════════════════════════════════════╗
║           TRADE JOURNAL REPORT - {env_str:<20}           ║
╠══════════════════════════════════════════════════════════════╣
║ Period: Last {days} days                                     ║
║                                                              ║
║ No trades found for this period.                             ║
╚══════════════════════════════════════════════════════════════╝
"""

        return f"""
╔══════════════════════════════════════════════════════════════╗
║           TRADE JOURNAL REPORT - {env_str:<20}           ║
╠══════════════════════════════════════════════════════════════╣
║ Period: Last {days} days                                     ║
╠══════════════════════════════════════════════════════════════╣
║ TRADE SUMMARY                                                ║
║ ─────────────                                                ║
║ Total Trades:     {stats['total_trades']:>5}                                    ║
║ Wins:             {stats['wins']:>5}    Win Rate: {stats['win_rate']:.1%}                    ║
║ Losses:           {stats['losses']:>5}    Profit Factor: {stats.get('profit_factor', 0):.2f}              ║
║ Breakevens:       {stats['breakevens']:>5}                                    ║
╠══════════════════════════════════════════════════════════════╣
║ P&L PERFORMANCE                                              ║
║ ────────────────                                             ║
║ Total P&L:        ${stats['total_pnl']:>10,.2f}                             ║
║ Avg P&L:          ${stats['avg_pnl']:>10,.2f}                             ║
║ Avg Win:          ${stats['avg_win']:>10,.2f}                             ║
║ Avg Loss:         ${stats['avg_loss']:>10,.2f}                             ║
║ Best Trade:       ${stats['best_trade']:>10,.2f}                             ║
║ Worst Trade:      ${stats['worst_trade']:>10,.2f}                             ║
║ Avg Return:       {stats['avg_return_pct']:>10.2f}%                            ║
╠══════════════════════════════════════════════════════════════╣
║ TRADE METRICS                                                ║
║ ─────────────                                                ║
║ Avg Duration:     {stats.get('avg_duration_hours', 0):>8.1f} hours                         ║
╚══════════════════════════════════════════════════════════════╝
"""

    def export_trades(
        self,
        filepath: str,
        environment: Optional[TradeEnvironment] = None,
        export_format: str = "csv",
    ) -> None:
        """
        Export trades to file.

        Args:
            filepath: Output file path
            environment: Filter by environment
            export_format: "csv" or "json"
        """
        trades = self.storage.get_trades(environment=environment, limit=10000)

        if export_format == "json":
            import json
            with open(filepath, 'w') as f:
                json.dump([t.to_dict()
                          for t in trades], f, indent=2, default=str)

        elif export_format == "csv":
            import csv
            if trades:
                with open(filepath, 'w', newline='') as f:
                    writer = csv.DictWriter(
                        f, fieldnames=trades[0].to_dict().keys())
                    writer.writeheader()
                    for trade in trades:
                        writer.writerow(trade.to_dict())
