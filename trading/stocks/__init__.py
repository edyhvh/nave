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
from trading.stocks.formatters import (
    render_ism_report_markdown_v2,
    render_x_summary_markdown_v2,
)
from trading.stocks.ism_scraper import (
    GICS_MAPPING,
    ISMIndustryRanking,
    ISMReport,
    ISMReportFetcher,
)
from trading.stocks.journal import StockJournal
from trading.stocks.portfolio_manager import (
    Action,
    Candidate,
    Decision,
    Evidence,
    PortfolioPolicy,
    Position,
    allocate_monthly_budget,
    monthly_review_date,
    rank_candidates,
    review_positions,
)
from trading.stocks.reporting import build_ism_industry_report
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
from trading.stocks.strategy import ISMSectorStrategy, ISMShortPerpStrategy, StockPlan
from trading.stocks.universe import DEFAULT_UNIVERSE
from trading.stocks.x_client import XClient, XClientError, XPost

__all__ = [
    "DEFAULT_UNIVERSE",
    "GICS_MAPPING",
    "X_POSTS_ANALYSIS_SYSTEM_PROMPT",
    "Action",
    "Candidate",
    "Decision",
    "Evidence",
    "ISMIndustryRanking",
    "ISMReport",
    "ISMReportFetcher",
    "ISMSectorStrategy",
    "ISMShortPerpStrategy",
    "MassiveClient",
    "MassiveRateLimitError",
    "PortfolioPolicy",
    "Position",
    "ScreenerMode",
    "SectorScreener",
    "StockCandidate",
    "StockJournal",
    "StockPlan",
    "StockScreenerError",
    "XClient",
    "XClientError",
    "XPost",
    "allocate_monthly_budget",
    "analyze_tickers",
    "analyze_tickers_async",
    "build_ism_industry_report",
    "monthly_review_date",
    "rank_candidates",
    "render_ism_report_markdown_v2",
    "render_x_summary_markdown_v2",
    "review_positions",
]
