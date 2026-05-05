"""Politician trades — Congressional STOCK Act disclosure tracker.

Pulls daily-published House and Senate transaction reports from FMP and
surfaces newly-disclosed trades through a Hermes-friendly daily scan.
"""

from trading.stocks.politicians.provider import (
    FMPPoliticianTradesProvider,
    PoliticianTrade,
    PoliticianTradesError,
)
from trading.stocks.politicians.scanner import run_daily_scan
from trading.stocks.politicians.store import SeenStore, default_store_path

__all__ = [
    "FMPPoliticianTradesProvider",
    "PoliticianTrade",
    "PoliticianTradesError",
    "SeenStore",
    "default_store_path",
    "run_daily_scan",
]
