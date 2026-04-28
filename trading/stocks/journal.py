"""
Asset-scoped stock journal.

Thin wrapper over :class:`trading.base.journal.BaseJournal` that pins the
asset class to :attr:`AssetClass.STOCK`. Used by :class:`ISMSectorStrategy`
when paper-trading so stock entries don't mix with the existing crypto
history in the shared SQLite DB.
"""

from __future__ import annotations

from typing import Optional

from trading.base.journal import BaseJournal
from trading.journal import AssetClass, TradeJournal


class StockJournal(BaseJournal):
    """Default journal for equity trades produced by the stocks workflow."""

    def __init__(self, journal: Optional[TradeJournal] = None):
        super().__init__(asset_class=AssetClass.STOCK, journal=journal)
