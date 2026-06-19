"""
Sector screener.

Given an ISM report (which sectors are expanding vs contracting) and a
fundamentals client, rank candidate tickers by one of two modes:

- ``mode="manufacturing"`` (default) — rank purely by EPS growth (next
  year). Confidence = 0.6 * match_confidence + 0.4 * eps_growth_confidence.
  Score = eps_growth_next_year / 100 (negated for shorts).

- ``mode="services"`` — rank by long-term revenue growth forecast
  (FMP analyst-estimates CAGR, yfinance trailing revenueGrowth as fallback).
  A secondary PE-relative filter drops names where company PE ≥ sector
  average PE. No complex scoring — revenue growth is the sole ranking input.

Ticker universe: the caller passes ``universe={sector: [tickers]}``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Iterable, Literal, Mapping, Protocol

from trading.stocks.data_provider import FundamentalSnapshot
from trading.stocks.ism_scraper import ISMIndustryRanking, ISMReport
from trading.stocks.mapping import best_ism_match

logger = logging.getLogger(__name__)


ScreenerMode = Literal["manufacturing", "services"]


class MassiveLike(Protocol):
    """Minimal fundamentals client contract needed by the screener."""

    def batch_fundamentals(self, symbols: Iterable[str]) -> list[FundamentalSnapshot]:
        ...

    def sector_average_pe(
        self,
        sector: str,
        *,
        symbols: Iterable[str] | None = None,
    ) -> float | None:
        ...


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
    # Services-mode metadata (None for manufacturing rows).
    revenue_growth_long_term: float | None = None
    revenue_growth_source: str | None = None
    mode: ScreenerMode = "manufacturing"
    fundamentals: FundamentalSnapshot | None = field(default=None, repr=False)


class SectorScreener:
    """
    EPS-growth / revenue-growth screener driven by ISM sector momentum.

    Manufacturing mode ranks tickers purely by EPS growth (next year).
    Services mode ranks tickers by long-term revenue growth forecast and
    applies a ``company PE < sector PE`` secondary filter.

    Industry-to-ISM match confidence and data-source confidence are
    combined into a single confidence score used as a secondary sort and
    filter in both modes.

    Usage:
        screener = SectorScreener(massive=MassiveClient(), universe=universe)
        picks = screener.rank_from_ism(report, top_n=5, mode="services")
    """

    def __init__(
        self,
        massive: MassiveLike,
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
        mode: ScreenerMode = "manufacturing",
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
            mode=mode,
        )

    def rank_sectors(
        self,
        sectors: list[str],
        *,
        top_n: int = 5,
        side: str = "long",
        min_eps_growth_next_year: float | None = None,
        industry_rankings_by_sector: Mapping[str,
                                             list[ISMIndustryRanking]] | None = None,
        min_confidence: float = 0.0,
        mode: ScreenerMode = "manufacturing",
    ) -> list[StockCandidate]:
        """Rank tickers within ISM-driven sectors."""
        candidates: list[StockCandidate] = []
        for sector in sectors:
            tickers = self.universe.get(sector, [])
            if not tickers:
                logger.info(
                    "No tickers configured for sector %r — skipping", sector)
                continue
            try:
                snapshots = self.massive.batch_fundamentals(tickers)
            except Exception as exc:
                logger.warning(
                    "Failed to fetch fundamentals for sector %r — skipping: %s", sector, exc
                )
                continue
            sector_rankings = (
                industry_rankings_by_sector or {}).get(sector, [])

            # Services mode uses sector-average PE as a secondary "company
            # PE < sector PE" filter. Manufacturing mode doesn't need it.
            sector_avg_pe: float | None = None
            if mode == "services":
                sector_avg_pe = _safe_sector_avg_pe(self.massive, sector)

            for snap in snapshots:
                # Manufacturing-specific pre-filter (explicit EPS growth floor).
                if mode == "manufacturing" and min_eps_growth_next_year is not None and (
                    snap.eps_growth_next_year is None
                    or snap.eps_growth_next_year < min_eps_growth_next_year
                ):
                    continue

                # Services-mode filters: require a revenue forecast, and
                # apply the PE-relative secondary check when both values
                # are available.
                if mode == "services":
                    if snap.revenue_growth_long_term is None:
                        continue
                    if (
                        sector_avg_pe is not None
                        and snap.pe_ratio is not None
                        and snap.pe_ratio >= sector_avg_pe
                    ):
                        # Too expensive vs peers — fails the PE relative check.
                        continue

                driver_industry, match_confidence = best_ism_match(
                    snap.industry, sector_rankings)
                if driver_industry is None and sector_rankings:
                    driver_industry = sector_rankings[0].industry
                score, reason, confidence = self._score(
                    snap,
                    match_confidence=match_confidence,
                    side=side,
                    mode=mode,
                    sector_avg_pe=sector_avg_pe,
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
                        revenue_growth_long_term=snap.revenue_growth_long_term,
                        revenue_growth_source=snap.revenue_growth_source,
                        mode=mode,
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
        mode: ScreenerMode = "manufacturing",
        sector_avg_pe: float | None = None,
    ) -> tuple[float, str, float]:
        """Return (score, reason, confidence)."""
        if mode == "services":
            return self._score_services(
                snap,
                match_confidence=match_confidence,
                side=side,
                sector_avg_pe=sector_avg_pe,
            )
        return self._score_manufacturing(
            snap,
            match_confidence=match_confidence,
            side=side,
        )

    def _score_manufacturing(
        self,
        snap: FundamentalSnapshot,
        *,
        match_confidence: float,
        side: str,
    ) -> tuple[float, str, float]:
        """Manufacturing scoring (unchanged from the original EPS-only flow).

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
        confidence = round(0.6 * match_confidence + 0.4 *
                           snap.eps_growth_confidence, 4)
        notes.append(f"final conf {confidence:.2f}")
        score = -eps if side.lower().strip() == "short" else eps
        return score, "; ".join(notes), confidence

    def _score_services(
        self,
        snap: FundamentalSnapshot,
        *,
        match_confidence: float,
        side: str,
        sector_avg_pe: float | None,
    ) -> tuple[float, str, float]:
        """Services scoring — long-term revenue growth as the ranking input.

        score = revenue_growth_long_term / 100 (negated for shorts).
        confidence = 0.6 * match_confidence + 0.4 * source_confidence,
            where source_confidence is higher for FMP analyst estimates
            than for yfinance trailing revenueGrowth.

        The PE-relative secondary filter is applied by the caller before
        scoring; here we just surface the comparison in the reason string.
        """
        notes: list[str] = []
        revenue_growth = snap.revenue_growth_long_term or 0.0
        rev = revenue_growth / 100.0
        notes.append(f"rev growth {revenue_growth:.1f}%")

        if snap.pe_ratio is not None and sector_avg_pe is not None:
            notes.append(
                f"PE {snap.pe_ratio:.1f} vs sector {sector_avg_pe:.1f}"
            )
        elif snap.pe_ratio is not None:
            notes.append(f"PE {snap.pe_ratio:.1f} (sector PE n/a)")

        source_conf = _revenue_source_confidence(snap.revenue_growth_source)
        notes.append(f"match conf {match_confidence:.2f}")
        notes.append(
            f"rev src={snap.revenue_growth_source or '?'} conf {source_conf:.2f}")
        confidence = round(0.6 * match_confidence + 0.4 * source_conf, 4)
        notes.append(f"final conf {confidence:.2f}")
        score = -rev if side.lower().strip() == "short" else rev
        return score, "; ".join(notes), confidence


def _revenue_source_confidence(source: str | None) -> float:
    """Map the revenue-forecast provenance to a [0,1] confidence score."""
    if source == "fmp_analyst_estimate":
        return 0.9
    if source == "yfinance_trailing_revenue_growth":
        # Trailing, not forward — usable but clearly weaker.
        return 0.6
    return 0.0


def _safe_sector_avg_pe(massive: MassiveLike, sector: str) -> float | None:
    """Call ``sector_average_pe`` without assuming the client exposes kwargs.

    Test doubles (e.g. ``_FakeMassive``) implement a simple ``(sector)``
    signature. The real ``FMPClient`` also accepts a ``symbols=`` fallback;
    we prefer the no-kwarg form so both paths work.
    """
    try:
        value = massive.sector_average_pe(sector)
    except Exception as exc:  # pragma: no cover - defensive against client errors
        logger.debug("sector_average_pe(%r) failed: %s", sector, exc)
        return None
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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
