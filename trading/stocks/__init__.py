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
from trading.stocks.reporting import DEFAULT_UNIVERSE, build_ism_industry_report
from trading.stocks.formatters import (
    render_ism_report_markdown_v2,
    render_x_summary_markdown_v2,
)
from trading.stocks.screener import (
    ScreenerMode,
    SectorScreener,
    StockCandidate,
    StockScreenerError,
)
from trading.stocks.social_analyzer import (
    X_POSTS_ANALYSIS_SYSTEM_PROMPT,
    analyze_tickers,
    analyze_tickers_async,
)
from trading.stocks.strategy import ISMSectorStrategy, StockPlan
from trading.stocks.x_client import XClient, XClientError, XPost

__all__ = [
    "GICS_MAPPING",
    "ISMIndustryRanking",
    "ISMReport",
    "ISMReportFetcher",
    "ISMSectorStrategy",
    "MassiveClient",
    "MassiveRateLimitError",
    "DEFAULT_UNIVERSE",
    "render_ism_report_markdown_v2",
    "render_x_summary_markdown_v2",
    "ScreenerMode",
    "SectorScreener",
    "StockCandidate",
    "StockJournal",
    "StockPlan",
    "StockScreenerError",
    "X_POSTS_ANALYSIS_SYSTEM_PROMPT",
    "XClient",
    "XClientError",
    "XPost",
    "analyze_tickers",
    "analyze_tickers_async",
    "build_ism_industry_report",
]
