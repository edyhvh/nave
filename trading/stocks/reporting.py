"""Shared ISM industry report builder for CLI, MCP, and Hermes surfaces."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from trading.stocks.data_provider import MassiveClient
from trading.stocks.ism_scraper import ISMReportFetcher
from trading.stocks.screener import SectorScreener, StockCandidate, StockScreenerError

# Keep this short so free-tier Massive usage (5 rpm) remains practical.
DEFAULT_UNIVERSE: dict[str, list[str]] = {
    "Information Technology": ["AAPL", "MSFT", "NVDA"],
    "Industrials": ["GE", "CAT", "HON"],
    "Health Care": ["LLY", "JNJ", "UNH"],
    "Consumer Discretionary": ["AMZN", "HD", "NKE"],
    "Materials": ["LIN", "FCX", "ECL"],
    "Energy": ["XOM", "CVX", "COP"],
    "Financials": ["JPM", "BAC", "V"],
    "Consumer Staples": ["PG", "KO", "COST"],
    "Communication Services": ["GOOGL", "META", "NFLX"],
    "Utilities": ["NEE", "DUK", "SO"],
    "Real Estate": ["PLD", "AMT", "EQIX"],
}


def build_ism_industry_report(
    *,
    kind: str = "manufacturing",
    top_n: int = 5,
    max_pe_ratio: float | None = None,
    min_eps_growth_next_year: float | None = None,
    universe: Mapping[str, list[str]] | None = None,
    fetcher: ISMReportFetcher | None = None,
    massive: MassiveClient | None = None,
) -> dict[str, Any]:
    """Build a complete ISM report with hottest/worst sectors and filtered names."""
    if kind not in {"manufacturing", "services"}:
        raise ValueError("kind must be 'manufacturing' or 'services'")

    report_fetcher = fetcher or ISMReportFetcher()
    report = report_fetcher.fetch_report(kind=kind)
    effective_universe = (
        {sector: list(tickers) for sector, tickers in universe.items()}
        if universe is not None
        else DEFAULT_UNIVERSE
    )
    screener = SectorScreener(massive=massive or MassiveClient(), universe=effective_universe)

    expanding = _safe_rank(
        screener,
        report=report,
        trend="expanding",
        top_n=top_n,
        max_pe_ratio=max_pe_ratio,
        min_eps_growth_next_year=min_eps_growth_next_year,
    )
    contracting = _safe_rank(
        screener,
        report=report,
        trend="contracting",
        top_n=top_n,
        max_pe_ratio=max_pe_ratio,
        min_eps_growth_next_year=min_eps_growth_next_year,
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "kind": report.kind,
        "report_month": report.report_month,
        "pmi": report.pmi,
        "source_url": report.source_url,
        "criteria": {
            "top_n": top_n,
            "max_pe_ratio": max_pe_ratio,
            "min_eps_growth_next_year": min_eps_growth_next_year,
        },
        "hottest_industries": [
            {
                "rank": item.rank,
                "industry": item.industry,
                "gics_sector": item.gics_sector,
            }
            for item in report.expanding
        ],
        "worst_industries": [
            {
                "rank": item.rank,
                "industry": item.industry,
                "gics_sector": item.gics_sector,
            }
            for item in report.contracting
        ],
        "candidates": {
            "expanding": [_candidate_to_dict(item) for item in expanding],
            "contracting": [_candidate_to_dict(item) for item in contracting],
        },
        "summary": {
            "hottest_sector_count": len(report.by_sector("expanding")),
            "worst_sector_count": len(report.by_sector("contracting")),
            "expanding_candidates": len(expanding),
            "contracting_candidates": len(contracting),
        },
    }


def _safe_rank(
    screener: SectorScreener,
    *,
    report,
    trend: str,
    top_n: int,
    max_pe_ratio: float | None,
    min_eps_growth_next_year: float | None,
) -> list[StockCandidate]:
    try:
        return screener.rank_from_ism(
            report,
            trend=trend,
            top_n=top_n,
            max_pe_ratio=max_pe_ratio,
            min_eps_growth_next_year=min_eps_growth_next_year,
        )
    except StockScreenerError:
        return []


def _candidate_to_dict(item: StockCandidate) -> dict[str, Any]:
    return {
        "symbol": item.symbol,
        "sector": item.sector,
        "score": round(item.score, 4),
        "pe_ratio": item.pe_ratio,
        "forward_pe": item.forward_pe,
        "sector_avg_pe": item.sector_avg_pe,
        "eps_growth_next_year": item.eps_growth_next_year,
        "reason": item.reason,
    }

