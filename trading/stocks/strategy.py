"""
ISM-driven sector-rotation strategy.

Plan:
  1. Pull latest ISM report (Manufacturing or Services) via :class:`ISMReportFetcher`.
  2. Map expanding industries → GICS sectors.
  3. Fetch fundamentals via :class:`MassiveClient` + run :class:`SectorScreener`.
  4. Translate top candidates into :class:`StockPlan` items the broker can execute.

The strategy defaults to ``dry_run=True`` — brokers are stubs today, so
live execution is unavailable regardless. When a real broker lands we only
need to flip the default once the Alpaca integration is verified.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal

from trading.base.broker import BaseBroker, BrokerResponse
from trading.base.strategy import AbstractStrategy
from trading.stocks.data_provider import MassiveClient
from trading.stocks.ism_scraper import ISMReport, ISMReportFetcher
from trading.stocks.screener import SectorScreener, StockCandidate

logger = logging.getLogger(__name__)


@dataclass
class StockPlan:
    """A single paper-trade suggestion derived from ISM + fundamentals."""

    symbol: str
    sector: str
    side: Literal["long"]  # ISM rotation is long-only today
    size_usd: float
    score: float
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "sector": self.sector,
            "side": self.side,
            "size_usd": round(self.size_usd, 2),
            "score": round(self.score, 4),
            "reason": self.reason,
        }


class ISMSectorStrategy(AbstractStrategy):
    """Rotate into expanding-sector names that screen cheap vs their peers."""

    def __init__(
        self,
        broker: BaseBroker,
        *,
        massive: MassiveClient,
        universe: dict[str, list[str]],
        report_kind: Literal["manufacturing", "services"] = "manufacturing",
        capital_usd: float = 10_000.0,
        max_positions: int = 5,
        max_pe_ratio: float | None = None,
        min_eps_growth_next_year: float | None = None,
        dry_run: bool = True,
        fetcher: ISMReportFetcher | None = None,
        screener: SectorScreener | None = None,
    ):
        super().__init__(broker, dry_run=dry_run)
        self.massive = massive
        self.universe = universe
        self.report_kind = report_kind
        self.capital_usd = capital_usd
        self.max_positions = max_positions
        self.max_pe_ratio = max_pe_ratio
        self.min_eps_growth_next_year = min_eps_growth_next_year
        self.fetcher = fetcher or ISMReportFetcher()
        self.screener = screener or SectorScreener(massive=massive, universe=universe)
        self._last_report: ISMReport | None = None

    def compute(self) -> list[StockPlan]:
        """Produce a list of target trades for the upcoming rebalance."""
        report = self.fetcher.fetch_report(self.report_kind)
        self._last_report = report
        picks: list[StockCandidate] = self.screener.rank_from_ism(
            report,
            top_n=self.max_positions,
            max_pe_ratio=self.max_pe_ratio,
            min_eps_growth_next_year=self.min_eps_growth_next_year,
        )
        if not picks:
            logger.info("ISMSectorStrategy: no candidates from %s", report.report_month)
            return []

        # Equal-weight across selected names. Keeps sizing predictable while
        # the broker integration is still stubbed — swap for risk-parity
        # later if/when we have a real PnL stream to learn from.
        allocation = self.capital_usd / len(picks)
        return [
            StockPlan(
                symbol=p.symbol,
                sector=p.sector,
                side="long",
                size_usd=allocation,
                score=p.score,
                reason=p.reason,
            )
            for p in picks
        ]

    def execute(self, plan: list[StockPlan]) -> list[BrokerResponse | dict[str, Any]]:
        """Route each :class:`StockPlan` through the broker unless ``dry_run``."""
        if not plan:
            return []

        results: list[BrokerResponse | dict[str, Any]] = []
        for item in plan:
            if self.dry_run:
                logger.info("[DRY-RUN] long %s ~$%.2f — %s", item.symbol, item.size_usd, item.reason)
                results.append({"dry_run": True, **item.as_dict()})
                continue
            try:
                resp = self.broker.market_open(item.symbol, "buy", item.size_usd)
                results.append(resp)
            except NotImplementedError as exc:
                logger.warning("%s broker stubbed — skipping %s: %s", self.broker.name, item.symbol, exc)
                results.append({"stubbed": True, **item.as_dict()})
        return results
