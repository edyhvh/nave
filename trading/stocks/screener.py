"""
Sector screener.

Given an ISM report (which sectors are expanding vs contracting) and a
Massive-backed fundamentals client, rank candidate tickers on:

  1. PE ratio vs sector average   (lower is better when expanding)
  2. Forward PE vs trailing PE    (contraction ⇒ earnings accelerating)
  3. EPS growth (next year)       (higher is better)

The scoring function is intentionally simple — it mirrors the "discount
to sector + growth tailwind" heuristic the rest of the repo uses for
crypto. Tune via :class:`SectorScreener` constructor args.

Ticker universe: this module does not ship its own ticker database. The
caller passes ``universe={sector: [tickers]}`` so the mapping can live
wherever makes sense (static file, external data vendor, Hermes input).
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
from trading.stocks.ism_scraper import ISMReport

logger = logging.getLogger(__name__)


class StockScreenerError(RuntimeError):
    """Raised when the screener can't produce a ranking."""


@dataclass
class StockCandidate:
    """A single screener output row."""

    symbol: str
    sector: str
    pe_ratio: float | None
    forward_pe: float | None
    sector_avg_pe: float | None
    eps_growth_next_year: float | None
    score: float
    reason: str
    fundamentals: FundamentalSnapshot | None = field(default=None, repr=False)


class SectorScreener:
    """
    PE vs sector + EPS-growth screener.

    Usage:
        screener = SectorScreener(massive=MassiveClient(), universe=universe)
        picks = screener.rank_from_ism(report, top_n=5)
    """

    def __init__(
        self,
        massive: MassiveClient,
        universe: Mapping[str, list[str]],
        *,
        eps_growth_weight: float = 1.0,
        pe_discount_weight: float = 1.0,
        forward_pe_weight: float = 0.5,
    ):
        self.massive = massive
        self.universe = {k: list(v) for k, v in universe.items()}
        self.w_eps = eps_growth_weight
        self.w_pe = pe_discount_weight
        self.w_fpe = forward_pe_weight

    # ── Entry points --------------------------------------------------
    def rank_from_ism(
        self,
        report: ISMReport,
        *,
        top_n: int = 5,
        trend: str = "expanding",
        max_pe_ratio: float | None = None,
        min_eps_growth_next_year: float | None = None,
    ) -> list[StockCandidate]:
        """Pull candidates for each expanding sector and return the top ``top_n``."""
        sectors = report.by_sector(trend=trend)
        if not sectors:
            raise StockScreenerError(
                f"No {trend} sectors resolvable from ISM report {report.report_month!r}."
            )
        return self.rank_sectors(
            sectors,
            top_n=top_n,
            max_pe_ratio=max_pe_ratio,
            min_eps_growth_next_year=min_eps_growth_next_year,
        )

    def rank_sectors(
        self,
        sectors: list[str],
        *,
        top_n: int = 5,
        max_pe_ratio: float | None = None,
        min_eps_growth_next_year: float | None = None,
    ) -> list[StockCandidate]:
        """Core ranking: fetch fundamentals + sector average, compute score."""
        candidates: list[StockCandidate] = []
        for sector in sectors:
            tickers = self.universe.get(sector, [])
            if not tickers:
                logger.info("No tickers configured for sector %r — skipping", sector)
                continue
            try:
                sector_avg_pe = self.massive.sector_average_pe(sector)
            except MassiveRateLimitError:
                raise
            except Exception:
                logger.exception("Failed to fetch sector average PE for %r", sector)
                sector_avg_pe = None

            snapshots = self.massive.batch_fundamentals(tickers)
            for snap in snapshots:
                if max_pe_ratio is not None and (
                    snap.pe_ratio is None or snap.pe_ratio > max_pe_ratio
                ):
                    continue
                if min_eps_growth_next_year is not None and (
                    snap.eps_growth_next_year is None
                    or snap.eps_growth_next_year < min_eps_growth_next_year
                ):
                    continue
                score, reason = self._score(snap, sector_avg_pe=sector_avg_pe)
                candidates.append(
                    StockCandidate(
                        symbol=snap.symbol,
                        sector=sector,
                        pe_ratio=snap.pe_ratio,
                        forward_pe=snap.forward_pe,
                        sector_avg_pe=sector_avg_pe,
                        eps_growth_next_year=snap.eps_growth_next_year,
                        score=score,
                        reason=reason,
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
        sector_avg_pe: float | None,
    ) -> tuple[float, str]:
        """Return (score, human-readable reason).

        Components (higher is better):
            pe_discount   = (sector_avg_pe - pe_ratio) / sector_avg_pe
            forward_bias  = (pe_ratio - forward_pe) / pe_ratio   # earnings accel
            eps_growth    = eps_growth_next_year / 100           # already pct

        Missing components contribute 0 and are noted in the reason.
        """
        pe_disc = 0.0
        fwd_bias = 0.0
        eps = 0.0
        notes: list[str] = []

        if snap.pe_ratio and sector_avg_pe and sector_avg_pe > 0:
            pe_disc = (sector_avg_pe - snap.pe_ratio) / sector_avg_pe
            notes.append(f"PE {snap.pe_ratio:.1f} vs sector avg {sector_avg_pe:.1f}")
        else:
            notes.append("PE-vs-sector unavailable")

        if snap.pe_ratio and snap.forward_pe and snap.pe_ratio > 0:
            fwd_bias = (snap.pe_ratio - snap.forward_pe) / snap.pe_ratio
            notes.append(f"fwd PE {snap.forward_pe:.1f}")

        if snap.eps_growth_next_year is not None:
            eps = snap.eps_growth_next_year / 100.0
            notes.append(f"EPS growth {snap.eps_growth_next_year:.1f}%")

        score = self.w_pe * pe_disc + self.w_fpe * fwd_bias + self.w_eps * eps
        return score, "; ".join(notes)
