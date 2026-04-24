"""
Sector screener.

Given an ISM report (which sectors are expanding vs contracting) and a
fundamentals client, rank candidate tickers purely on EPS growth (next year).

Score  = eps_growth_next_year / 100  (signed; negated for shorts)
Confidence = 0.6 * match_confidence + 0.4 * eps_growth_confidence

Ticker universe: the caller passes ``universe={sector: [tickers]}``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Mapping

from trading.stocks.data_provider import (
    FundamentalSnapshot,
    MassiveClient,
    MassiveRateLimitError,
)
from trading.stocks.ism_scraper import ISMIndustryRanking, ISMReport
from trading.stocks.mapping import best_ism_match

logger = logging.getLogger(__name__)


class StockScreenerError(RuntimeError):
    """Raised when the screener can't produce a ranking."""


@dataclass
class StockCandidate:
    """A single screener output row."""

    symbol: str
    sector: str
    industry: str | None
    driver_industry: str | None
    eps_growth_next_year: float | None
    eps_growth_source: str | None
    eps_growth_confidence: float
    match_confidence: float
    confidence: float
    score: float
    reason: str
    side: str = "long"
    company_name: str | None = None
    fundamentals: FundamentalSnapshot | None = field(default=None, repr=False)


class SectorScreener:
    """
    EPS-growth screener driven by ISM sector momentum.

    Ranks tickers purely by EPS growth (next year). Industry-to-ISM match
    confidence and EPS data confidence are combined into a single confidence
    score used as a secondary sort and filter.

    Usage:
        screener = SectorScreener(massive=MassiveClient(), universe=universe)
        picks = screener.rank_from_ism(report, top_n=5)
    """

    def __init__(
        self,
        massive: MassiveClient,
        universe: Mapping[str, list[str]],
    ):
        self.massive = massive
        self.universe = {k: list(v) for k, v in universe.items()}

    # ── Entry points --------------------------------------------------
    def rank_from_ism(
        self,
        report: ISMReport,
        *,
        top_n: int = 5,
        trend: str = "expanding",
        side: str | None = None,
        min_eps_growth_next_year: float | None = None,
        min_confidence: float = 0.0,
    ) -> list[StockCandidate]:
        """Pull candidates for each expanding sector and return the top ``top_n``."""
        sectors = report.by_sector(trend=trend)
        if not sectors:
            raise StockScreenerError(
                f"No {trend} sectors resolvable from ISM report {report.report_month!r}."
            )
        sector_rankings = _rankings_by_sector(
            report.expanding if trend == "expanding" else report.contracting,
            sectors,
        )
        return self.rank_sectors(
            sectors,
            top_n=top_n,
            side=side or ("short" if trend == "contracting" else "long"),
            min_eps_growth_next_year=min_eps_growth_next_year,
            industry_rankings_by_sector=sector_rankings,
            min_confidence=min_confidence,
        )

    def rank_sectors(
        self,
        sectors: list[str],
        *,
        top_n: int = 5,
        side: str = "long",
        min_eps_growth_next_year: float | None = None,
        industry_rankings_by_sector: Mapping[str, list[ISMIndustryRanking]] | None = None,
        min_confidence: float = 0.0,
    ) -> list[StockCandidate]:
        """Rank tickers by EPS growth within ISM-driven sectors."""
        candidates: list[StockCandidate] = []
        for sector in sectors:
            tickers = self.universe.get(sector, [])
            if not tickers:
                logger.info("No tickers configured for sector %r — skipping", sector)
                continue
            snapshots = self.massive.batch_fundamentals(tickers)
            sector_rankings = (industry_rankings_by_sector or {}).get(sector, [])
            for snap in snapshots:
                if min_eps_growth_next_year is not None and (
                    snap.eps_growth_next_year is None
                    or snap.eps_growth_next_year < min_eps_growth_next_year
                ):
                    continue
                driver_industry, match_confidence = best_ism_match(snap.industry, sector_rankings)
                if driver_industry is None and sector_rankings:
                    driver_industry = sector_rankings[0].industry
                score, reason, confidence = self._score(
                    snap,
                    match_confidence=match_confidence,
                    side=side,
                )
                if confidence < min_confidence:
                    continue
                candidates.append(
                    StockCandidate(
                        symbol=snap.symbol,
                        sector=sector,
                        industry=snap.industry,
                        driver_industry=driver_industry,
                        eps_growth_next_year=snap.eps_growth_next_year,
                        eps_growth_source=snap.eps_growth_source,
                        eps_growth_confidence=snap.eps_growth_confidence,
                        match_confidence=match_confidence,
                        confidence=confidence,
                        score=score,
                        reason=reason,
                        side=side,
                        company_name=snap.company_name,
                        fundamentals=snap,
                    )
                )

        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates[:top_n]

    # ── Scoring -------------------------------------------------------
    def _score(
        self,
        snap: FundamentalSnapshot,
        *,
        match_confidence: float,
        side: str = "long",
    ) -> tuple[float, str, float]:
        """Return (score, reason, confidence).

        score = eps_growth_next_year / 100 (negated for shorts).
        confidence = 0.6 * match_confidence + 0.4 * eps_growth_confidence.
        """
        notes: list[str] = []
        if snap.eps_growth_next_year is not None:
            eps = snap.eps_growth_next_year / 100.0
            notes.append(f"EPS growth {snap.eps_growth_next_year:.1f}%")
        else:
            eps = 0.0
            notes.append("EPS growth unavailable")
        notes.append(f"match conf {match_confidence:.2f}")
        notes.append(f"eps conf {snap.eps_growth_confidence:.2f}")
        confidence = round(0.6 * match_confidence + 0.4 * snap.eps_growth_confidence, 4)
        notes.append(f"final conf {confidence:.2f}")
        score = -eps if side.lower().strip() == "short" else eps
        return score, "; ".join(notes), confidence


def _rankings_by_sector(
    rankings: list[ISMIndustryRanking],
    sectors: list[str],
) -> dict[str, list[ISMIndustryRanking]]:
    allowed = set(sectors)
    out: dict[str, list[ISMIndustryRanking]] = {}
    for item in rankings:
        if item.gics_sector and item.gics_sector in allowed:
            out.setdefault(item.gics_sector, []).append(item)
    return out



