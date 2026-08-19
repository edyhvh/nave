"""Human-gated long-term stock portfolio decision engine.

This module is deliberately provider-agnostic. It does not fetch prices, place
orders, or treat a single data source as a buy signal. Adapters can feed it
normalised evidence from ISM, congressional disclosures, ONDO availability,
technical analysis, X sentiment, and Reserve AI index research.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Any

from trading.stocks.portfolio_calendar import next_business_day_for_monthly_review


class Action(StrEnum):
    ENTER = "enter"
    WATCH = "watch"
    HOLD = "hold"
    EXIT = "exit"
    REVIEW = "review"


@dataclass(frozen=True)
class Evidence:
    """Normalised evidence; missing sources remain explicit rather than inferred."""

    ism_score: float = 0.0
    congress_score: float = 0.0
    technical_score: float = 0.0
    reserve_ai_score: float = 0.0
    social_score: float = 0.0
    ondo_available: bool = False
    ondo_liquid: bool = False
    # A candidate cannot become ENTER without fresh primary-web and X research.
    research_verified: bool = False
    research_sources: Mapping[str, str] = field(default_factory=dict)
    source_dates: Mapping[str, str] = field(default_factory=dict)

    def bounded(self) -> Evidence:
        values = {
            key: max(0.0, min(1.0, float(getattr(self, key))))
            for key in (
                "ism_score",
                "congress_score",
                "technical_score",
                "reserve_ai_score",
                "social_score",
            )
        }
        return Evidence(
            **values,
            ondo_available=self.ondo_available,
            ondo_liquid=self.ondo_liquid,
            research_verified=self.research_verified,
            research_sources=self.research_sources,
            source_dates=self.source_dates,
        )


@dataclass(frozen=True)
class Position:
    ticker: str
    cost_basis: float
    market_value: float
    thesis_status: str = "active"
    high_water_mark: float | None = None
    evidence: Evidence = field(default_factory=Evidence)

    @property
    def return_pct(self) -> float:
        if self.cost_basis <= 0:
            return 0.0
        return (self.market_value / self.cost_basis) - 1.0


@dataclass(frozen=True)
class Candidate:
    ticker: str
    evidence: Evidence
    price: float | None = None
    entry_zone: tuple[float, float] | None = None
    invalidation: float | None = None
    direct_defense: bool = False


@dataclass(frozen=True)
class Decision:
    ticker: str
    action: Action
    score: float
    reason_codes: tuple[str, ...]
    allocation_usd: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["action"] = self.action.value
        return payload


@dataclass(frozen=True)
class PortfolioPolicy:
    """Conservative defaults for a small, long-term, human-executed portfolio."""

    monthly_budget: float = 300.0
    max_single_new_weight: float = 0.35
    reserve_cash_weight: float = 0.15
    min_entry_score: float = 0.68
    min_watch_score: float = 0.48
    max_positions: int = 8
    review_day: int = 26
    drawdown_review_pct: float = -0.15
    profit_review_pct: float = 0.20


def _research_gate_passes(evidence: Evidence) -> bool:
    """Require fresh web and X evidence before allowing an ENTER decision."""
    if not evidence.research_verified:
        return False
    required = ("web", "x")
    if any(not str(evidence.research_sources.get(key) or "").strip() for key in required):
        return False
    if any(not str(evidence.source_dates.get(key) or "").strip() for key in required):
        return False
    today = date.today()
    for key in required:
        try:
            observed = datetime.fromisoformat(evidence.source_dates[key].replace("Z", "+00:00")).date()
        except (TypeError, ValueError):
            return False
        if observed > today or today - observed > timedelta(days=7):
            return False
    return True


def monthly_review_date(year: int, month: int, review_day: int = 26) -> date:
    """Return the funding date, skipping weekends and configured holidays."""
    return next_business_day_for_monthly_review(year, month, review_day=review_day)


def _score(evidence: Evidence) -> float:
    e = evidence.bounded()
    score = (
        0.28 * e.ism_score
        + 0.18 * e.congress_score
        + 0.30 * e.technical_score
        + 0.14 * e.reserve_ai_score
        + 0.10 * e.social_score
    )
    if not e.ondo_available:
        score *= 0.85
    if e.ondo_available and not e.ondo_liquid:
        score *= 0.75
    return round(score, 4)


def rank_candidates(candidates: Iterable[Candidate], *, policy: PortfolioPolicy) -> list[Decision]:
    """Rank candidates without allocating money; useful for research/watchlists."""
    decisions: list[Decision] = []
    for candidate in candidates:
        evidence = candidate.evidence.bounded()
        score = _score(evidence)
        reasons: list[str] = []
        if candidate.direct_defense:
            decisions.append(Decision(candidate.ticker.upper(), Action.REVIEW, score,
                                      ("direct_defense_excluded",)))
            continue
        if evidence.ism_score >= 0.6:
            reasons.append("ism_support")
        if evidence.congress_score >= 0.6:
            reasons.append("congress_support")
        if evidence.reserve_ai_score >= 0.6:
            reasons.append("reserve_ai_support")
        if evidence.technical_score < 0.5:
            reasons.append("technical_confirmation_missing")
        if not evidence.ondo_available:
            reasons.append("ondo_unavailable")
        elif not evidence.ondo_liquid:
            reasons.append("ondo_liquidity_unverified")
        action = Action.ENTER if score >= policy.min_entry_score else (
            Action.WATCH if score >= policy.min_watch_score else Action.REVIEW
        )
        if candidate.price is None or candidate.entry_zone is None:
            action = Action.WATCH
            reasons.append("entry_zone_not_checked")
        else:
            low, high = candidate.entry_zone
            if not (low <= candidate.price <= high):
                action = Action.WATCH
                reasons.append("price_outside_entry_zone")
        if action is Action.ENTER and not _research_gate_passes(evidence):
            action = Action.WATCH
            reasons.append("fresh_web_and_x_research_required")
        decisions.append(Decision(candidate.ticker.upper(), action, score, tuple(reasons)))
    return sorted(decisions, key=lambda decision: decision.score, reverse=True)


def allocate_monthly_budget(
    decisions: Iterable[Decision],
    *,
    policy: PortfolioPolicy,
    open_tickers: Iterable[str] = (),
) -> list[Decision]:
    """Allocate only to new ENTER names that fit remaining position slots."""
    open_set = {ticker.upper() for ticker in open_tickers}
    new_entries = [
        decision
        for decision in decisions
        if decision.action is Action.ENTER and decision.ticker.upper() not in open_set
    ]
    slots = max(0, policy.max_positions - len(open_set))
    chosen = new_entries[:slots]
    if not chosen:
        return []
    investable = max(0.0, policy.monthly_budget * (1.0 - policy.reserve_cash_weight))
    amount = min(investable / len(chosen), policy.monthly_budget * policy.max_single_new_weight)
    return [
        Decision(d.ticker, d.action, d.score, d.reason_codes, round(amount, 2))
        for d in chosen
    ]


def review_positions(positions: Iterable[Position], *, policy: PortfolioPolicy) -> list[Decision]:
    """Produce explicit hold/review/exit prompts; never auto-sells."""
    decisions: list[Decision] = []
    for position in positions:
        reasons: list[str] = []
        status = position.thesis_status.lower()
        if status in {"broken", "invalidated", "unknown"}:
            decisions.append(Decision(position.ticker.upper(), Action.EXIT, 0.0,
                                      ("thesis_invalidated",)))
            continue
        if position.return_pct <= policy.drawdown_review_pct:
            reasons.append("drawdown_review")
        if position.return_pct >= policy.profit_review_pct:
            reasons.append("profit_rebalance_review")
        if not position.evidence.technical_score >= 0.4:
            reasons.append("technical_weakness")
        action = Action.REVIEW if reasons else Action.HOLD
        decisions.append(Decision(position.ticker.upper(), action, round(_score(position.evidence), 4),
                                  tuple(reasons)))
    return decisions
