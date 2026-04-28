"""
Asset-scoped journal facade.

Wraps :class:`trading.journal.TradeJournal` and pins every write to a single
``AssetClass``. Stocks and crypto can run side by side against the same DB
without mixing queries.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from trading.journal import (
    AssetClass,
    Trade,
    TradeEnvironment,
    TradeJournal,
    TradeStatus,
)


class BaseJournal:
    """Thin, asset-aware wrapper over :class:`TradeJournal`."""

    def __init__(
        self,
        asset_class: AssetClass,
        *,
        journal: Optional[TradeJournal] = None,
    ):
        self.asset_class = asset_class
        self.journal = journal or TradeJournal()

    def record_entry(
        self,
        *,
        symbol: str,
        direction: str,
        entry_price: float,
        size_usd: float,
        environment: TradeEnvironment = TradeEnvironment.PAPER,
        strategy_name: str = "unknown",
        leverage: float = 1.0,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        entry_signals: Optional[dict[str, Any]] = None,
        tags: Optional[list[str]] = None,
        notes: str = "",
    ) -> Trade:
        """Record an entry and tag it with this journal's asset class."""
        trade = self.journal.record_entry(
            coin=symbol,
            direction=direction,
            entry_price=entry_price,
            size_usd=size_usd,
            environment=environment,
            strategy_name=strategy_name,
            leverage=leverage,
            stop_loss=stop_loss,
            take_profit=take_profit,
            entry_signals=entry_signals,
            tags=tags,
            notes=notes,
        )
        # TradeJournal.record_entry defaults asset_class to CRYPTO; rewrite if needed.
        if trade.asset_class != self.asset_class:
            trade.asset_class = self.asset_class
            self.journal.storage.save_trade(trade)
        return trade

    def record_exit(
        self,
        trade_id: str,
        exit_price: float,
        *,
        exit_fee: float = 0.0,
        exit_signals: Optional[dict[str, Any]] = None,
        notes_addition: str = "",
    ) -> Optional[Trade]:
        return self.journal.record_exit(
            trade_id,
            exit_price=exit_price,
            exit_fee=exit_fee,
            exit_signals=exit_signals,
            notes_addition=notes_addition,
        )

    def history(
        self,
        *,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 1000,
    ) -> list[Trade]:
        return self.journal.storage.get_trades(
            asset_class=self.asset_class,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )

    def open_trades(self) -> list[Trade]:
        return self.journal.storage.get_trades(
            asset_class=self.asset_class,
            status=TradeStatus.OPEN,
        )

    def stats(self, *, environment: Optional[TradeEnvironment] = None) -> dict[str, Any]:
        """Aggregate stats for this asset class only.

        ``TradeJournal.get_stats`` doesn't filter by asset class yet, so we
        compute a minimal breakdown directly from filtered history.
        """
        trades = self.journal.storage.get_trades(
            asset_class=self.asset_class,
            environment=environment,
            status=TradeStatus.CLOSED,
            limit=10_000,
        )
        if not trades:
            return {"total_trades": 0, "asset_class": self.asset_class.value}

        wins = sum(1 for t in trades if t.pnl_absolute and t.pnl_absolute > 0)
        losses = sum(1 for t in trades if t.pnl_absolute and t.pnl_absolute < 0)
        total_pnl = sum((t.pnl_absolute or 0.0) for t in trades)
        return {
            "asset_class": self.asset_class.value,
            "total_trades": len(trades),
            "wins": wins,
            "losses": losses,
            "win_rate": wins / len(trades) if trades else 0.0,
            "total_pnl": total_pnl,
            "avg_pnl": total_pnl / len(trades) if trades else 0.0,
        }
