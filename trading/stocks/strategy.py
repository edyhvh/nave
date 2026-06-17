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
from typing import Any, Literal, cast

from trading.base.broker import BaseBroker, BrokerResponse
from trading.base.strategy import AbstractStrategy
from trading.stocks.data_provider import MassiveClient
from trading.stocks.ism_scraper import ISMReport, ISMReportFetcher
from trading.stocks.ondo_universe import ONDO_STOCK_PERP_VENUE, is_ondo_stock_perp
from trading.stocks.screener import ScreenerMode, SectorScreener, StockCandidate

logger = logging.getLogger(__name__)

DEFAULT_MIN_SHORT_SCORE = 0.05
DEFAULT_SHORT_HOLDING_WINDOW_DAYS = 28
DEFAULT_SHORT_RISK_PCT = 0.01
DEFAULT_SHORT_MAX_LEVERAGE = 1.0
DEFAULT_SHORT_STOP_PCT = 0.08
DEFAULT_SHORT_TARGET_PCT = 0.15


@dataclass
class StockPlan:
    """A single paper-trade suggestion derived from ISM + fundamentals."""

    symbol: str
    sector: str
    side: Literal["long", "short"]
    size_usd: float
    score: float
    reason: str
    venue: str | None = None
    short_quality_score: float | None = None
    entry_rule: str | None = None
    entry_price: float | None = None
    target: dict[str, Any] | None = None
    stop: dict[str, Any] | None = None
    holding_window_days: int | None = None
    risk_pct: float | None = None
    max_leverage: float | None = None
    size_guidance: str | None = None

    def as_dict(self) -> dict[str, Any]:
        out = {
            "symbol": self.symbol,
            "sector": self.sector,
            "side": self.side,
            "size_usd": round(self.size_usd, 2),
            "score": round(self.score, 4),
            "reason": self.reason,
        }
        if self.venue is not None:
            out["venue"] = self.venue
        if self.short_quality_score is not None:
            out["short_quality_score"] = round(self.short_quality_score, 4)
        if self.entry_rule is not None:
            out["entry_rule"] = self.entry_rule
        if self.entry_price is not None:
            out["entry_price"] = round(self.entry_price, 4)
        if self.target is not None:
            out["target"] = self.target
        if self.stop is not None:
            out["stop"] = self.stop
        if self.holding_window_days is not None:
            out["holding_window_days"] = self.holding_window_days
        if self.risk_pct is not None:
            out["risk_pct"] = round(self.risk_pct, 4)
        if self.max_leverage is not None:
            out["max_leverage"] = round(self.max_leverage, 4)
        if self.size_guidance is not None:
            out["size_guidance"] = self.size_guidance
        if self.side == "short":
            out["trade_plan"] = {
                "entry_rule": self.entry_rule,
                "entry_price": out.get("entry_price"),
                "target": self.target,
                "stop": self.stop,
                "holding_window_days": self.holding_window_days,
                "risk_pct": out.get("risk_pct"),
                "size_guidance": self.size_guidance,
                "max_leverage": out.get("max_leverage"),
            }
        return out


class ISMSectorStrategy(AbstractStrategy):
    """Rotate into expanding-sector names that screen cheap vs their peers."""

    def __init__(
        self,
        broker: BaseBroker,
        *,
        massive: MassiveClient,
        universe: dict[str, list[str]],
        report_kind: Literal["manufacturing", "services"] = "manufacturing",
        mode: ScreenerMode | None = None,
        capital_usd: float = 10_000.0,
        max_positions: int = 5,
        min_eps_growth_next_year: float | None = None,
        min_confidence: float = 0.0,
        dry_run: bool = True,
        fetcher: ISMReportFetcher | None = None,
        screener: SectorScreener | None = None,
    ):
        super().__init__(broker, dry_run=dry_run)
        self.massive = massive
        self.universe = universe
        self.report_kind = report_kind
        # Default screening mode mirrors the ISM report kind so
        # ``report_kind="services"`` auto-selects the revenue-growth screener.
        self.mode: ScreenerMode = cast("ScreenerMode", mode or report_kind)
        self.capital_usd = capital_usd
        self.max_positions = max_positions
        self.min_eps_growth_next_year = min_eps_growth_next_year
        self.min_confidence = min_confidence
        self.fetcher = fetcher or ISMReportFetcher()
        self.screener = screener or SectorScreener(massive=massive, universe=universe)
        self._last_report: ISMReport | None = None

    def compute(self) -> list[StockPlan]:
        """Produce a list of target trades for the upcoming rebalance."""
        report = self.fetcher.fetch_report(cast("Any", self.report_kind))
        self._last_report = report
        picks: list[StockCandidate] = self.screener.rank_from_ism(
            report,
            top_n=self.max_positions,
            min_eps_growth_next_year=self.min_eps_growth_next_year,
            min_confidence=self.min_confidence,
            mode=self.mode,
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


class ISMShortPerpStrategy(AbstractStrategy):
    """Short contracting-sector names that are Ondo stock-perp eligible."""

    def __init__(
        self,
        broker: BaseBroker,
        *,
        massive: MassiveClient,
        universe: dict[str, list[str]],
        report_kind: Literal["manufacturing", "services"] = "manufacturing",
        mode: ScreenerMode | None = None,
        capital_usd: float = 10_000.0,
        max_positions: int = 5,
        min_eps_growth_next_year: float | None = None,
        min_confidence: float = 0.3,
        min_short_score: float | None = DEFAULT_MIN_SHORT_SCORE,
        research_mode: bool = False,
        dry_run: bool = True,
        fetcher: ISMReportFetcher | None = None,
        screener: SectorScreener | None = None,
    ):
        super().__init__(broker, dry_run=dry_run)
        self.massive = massive
        self.universe = universe
        self.report_kind = report_kind
        self.mode: ScreenerMode = cast("ScreenerMode", mode or report_kind)
        self.capital_usd = capital_usd
        self.max_positions = max_positions
        self.min_eps_growth_next_year = min_eps_growth_next_year
        self.min_confidence = min_confidence
        self.min_short_score = _normalize_min_short_score(
            min_short_score,
            research_mode=research_mode,
        )
        self.research_mode = research_mode
        self.fetcher = fetcher or ISMReportFetcher()
        self.screener = screener or SectorScreener(massive=massive, universe=universe)
        self._last_report: ISMReport | None = None

    def compute(self) -> list[StockPlan]:
        report = self.fetcher.fetch_report(cast("Any", self.report_kind))
        self._last_report = report
        picks = self.screener.rank_from_ism(
            report,
            trend="contracting",
            top_n=self.max_positions,
            min_eps_growth_next_year=self.min_eps_growth_next_year,
            min_confidence=self.min_confidence,
            mode=self.mode,
        )
        sector_badness_rank = _sector_badness_rank(report)
        ondo_picks = [
            pick
            for pick in picks
            if is_ondo_stock_perp(pick.symbol)
            and (
                pick.score > self.min_short_score
                or (self.research_mode and pick.score >= self.min_short_score)
            )
        ]
        ondo_picks.sort(
            key=lambda pick: short_candidate_quality(
                pick,
                sector_badness_rank=sector_badness_rank.get(pick.sector),
                ondo_available=True,
            ),
            reverse=True,
        )
        if not ondo_picks:
            logger.info(
                "ISMShortPerpStrategy: no Ondo-eligible shorts from %s",
                report.report_month,
            )
            return []

        allocation = self.capital_usd / len(ondo_picks)
        plans: list[StockPlan] = []
        for p in ondo_picks:
            quality = short_candidate_quality(
                p,
                sector_badness_rank=sector_badness_rank.get(p.sector),
                ondo_available=True,
            )
            entry_price = _safe_get_mid(self.broker, p.symbol)
            trade_plan = build_ism_short_trade_plan(
                p,
                allocation_usd=allocation,
                min_short_score=self.min_short_score,
                entry_price=entry_price,
            )
            plans.append(
                StockPlan(
                    symbol=p.symbol,
                    sector=p.sector,
                    side="short",
                    size_usd=allocation,
                    score=p.score,
                    reason=(
                        f"{p.reason} | short_score>{self.min_short_score:.2f} "
                        f"| quality={quality:.2f} "
                        f"| venue={ONDO_STOCK_PERP_VENUE}"
                    ),
                    venue=ONDO_STOCK_PERP_VENUE,
                    short_quality_score=quality,
                    **trade_plan,
                )
            )
        return plans

    def execute(self, plan: list[StockPlan]) -> list[BrokerResponse | dict[str, Any]]:
        if not plan:
            return []

        results: list[BrokerResponse | dict[str, Any]] = []
        for item in plan:
            if self.dry_run:
                logger.info(
                    "[DRY-RUN] short %s ~$%.2f via %s — %s",
                    item.symbol,
                    item.size_usd,
                    ONDO_STOCK_PERP_VENUE,
                    item.reason,
                )
                results.append({"dry_run": True, "venue": ONDO_STOCK_PERP_VENUE, **item.as_dict()})
                continue
            try:
                resp = self.broker.market_open(item.symbol, "sell", item.size_usd)
                results.append(resp)
            except NotImplementedError as exc:
                logger.warning(
                    "%s broker stubbed — skipping short %s: %s",
                    self.broker.name,
                    item.symbol,
                    exc,
                )
                results.append(
                    {"stubbed": True, "venue": ONDO_STOCK_PERP_VENUE, **item.as_dict()}
                )
        return results


def short_candidate_quality(
    item: StockCandidate,
    *,
    sector_badness_rank: int | None = None,
    ondo_available: bool = False,
) -> float:
    """Rank short candidates by bearish fundamentals plus ISM/Ondo context."""
    bearish_score = max(float(item.score), 0.0)
    confidence = max(float(item.confidence), 0.0)
    if sector_badness_rank is None or sector_badness_rank <= 0:
        sector_pressure = 0.0
    else:
        sector_pressure = 1.0 / float(sector_badness_rank)
    ondo_bonus = 0.15 if ondo_available else 0.0
    return round((bearish_score * 0.55) + (confidence * 0.25) + (sector_pressure * 0.20) + ondo_bonus, 4)


def build_ism_short_trade_plan(
    item: StockCandidate,
    *,
    allocation_usd: float,
    min_short_score: float = DEFAULT_MIN_SHORT_SCORE,
    entry_price: float | None = None,
    holding_window_days: int = DEFAULT_SHORT_HOLDING_WINDOW_DAYS,
    risk_pct: float = DEFAULT_SHORT_RISK_PCT,
    max_leverage: float = DEFAULT_SHORT_MAX_LEVERAGE,
) -> dict[str, Any]:
    """Create explicit execution/risk fields for an ISM Ondo short candidate."""
    rounded_entry = round(entry_price, 4) if entry_price and entry_price > 0 else None
    target_price = (
        round(rounded_entry * (1.0 - DEFAULT_SHORT_TARGET_PCT), 4)
        if rounded_entry is not None
        else None
    )
    stop_price = (
        round(rounded_entry * (1.0 + DEFAULT_SHORT_STOP_PCT), 4)
        if rounded_entry is not None
        else None
    )
    return {
        "entry_rule": (
            f"Enter short {item.symbol} on the next Ondo stock-perp session after an ISM "
            f"contracting-sector signal when confidence >= candidate floor and "
            f"short score > {min_short_score:.2f}; use a limit near current mid if available."
        ),
        "entry_price": rounded_entry,
        "target": {
            "price": target_price,
            "rule": f"Cover into {DEFAULT_SHORT_TARGET_PCT:.0%} favorable move or before next ISM release.",
        },
        "stop": {
            "price": stop_price,
            "rule": f"Cover on {DEFAULT_SHORT_STOP_PCT:.0%} adverse move or thesis invalidation.",
        },
        "holding_window_days": holding_window_days,
        "risk_pct": risk_pct,
        "max_leverage": max_leverage,
        "size_guidance": (
            f"Cap notional near ${allocation_usd:,.2f}; keep account risk near "
            f"{risk_pct:.1%} and do not exceed {max_leverage:.1f}x leverage."
        ),
    }


def _normalize_min_short_score(
    min_short_score: float | None,
    *,
    research_mode: bool = False,
) -> float:
    if min_short_score is None:
        return DEFAULT_MIN_SHORT_SCORE
    value = float(min_short_score)
    if research_mode:
        return value
    return max(value, DEFAULT_MIN_SHORT_SCORE)


def _safe_get_mid(broker: BaseBroker, symbol: str) -> float | None:
    try:
        value = broker.get_mid(symbol)
    except Exception:
        return None
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    return price if price > 0 else None


def _sector_badness_rank(report: ISMReport) -> dict[str, int]:
    ranks: dict[str, int] = {}
    for item in report.contracting:
        if not item.gics_sector:
            continue
        ranks[item.gics_sector] = min(item.rank, ranks.get(item.gics_sector, item.rank))
    return ranks
