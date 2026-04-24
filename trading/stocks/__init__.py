"""
Stocks asset class — ISM-driven equity workflow.

Pipeline:
    1. ``ism_scraper``   — pull the latest monthly ISM Manufacturing /
                           Services "Report On Business®" and rank
                           industries as expanding vs contracting.
    2. ``data_provider`` — fetch per-company fundamentals from Massive.com
                           (PE, forward PE, EPS growth) with rate-limit
                           aware batching (free tier: 5 req/min).
    3. ``screener``      — map ISM industries → GICS sectors, rank
                           companies on PE-vs-sector + EPS-growth, return
                           the top candidates as :class:`StockCandidate`.
    4. ``strategy``      — produce paper-trade signals for a broker.
    5. ``journal``       — asset-scoped facade over ``trading.journal``.

The flow is deliberately read-only by default: brokers are stubs until a
full Alpaca/Ondo integration is wired up.
"""

from trading.stocks.data_provider import MassiveClient, MassiveRateLimitError
from trading.stocks.ism_scraper import (
    ISMIndustryRanking,
    ISMReport,
    ISMReportFetcher,
    GICS_MAPPING,
)
from trading.stocks.journal import StockJournal
from trading.stocks.screener import (
    SectorScreener,
    StockCandidate,
    StockScreenerError,
)
from trading.stocks.strategy import ISMSectorStrategy, StockPlan

__all__ = [
    "GICS_MAPPING",
    "ISMIndustryRanking",
    "ISMReport",
    "ISMReportFetcher",
    "ISMSectorStrategy",
    "MassiveClient",
    "MassiveRateLimitError",
    "SectorScreener",
    "StockCandidate",
    "StockJournal",
    "StockPlan",
    "StockScreenerError",
]
