"""Human-gated long-term stock portfolio decision engine.

This module is deliberately provider-agnostic. It does not fetch prices, place
orders, or treat a single data source as a buy signal. Adapters can feed it
normalised evidence from ISM, congressional disclosures, ONDO availability,
technical analysis, X sentiment, and Reserve AI index research.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from enum import StrEnum
from typing import Any


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
        return Evidence(**values, ondo_available=self.ondo_available,
                        ondo_liquid=self.ondo_liquid, source_dates=self.source_dates)


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


def monthly_review_date(year: int, month: int, review_day: int = 26) -> date:
    """Return the first weekday on/after the funding date (no forced execution)."""
    if not 1 <= review_day <= 28:
        raise ValueError("review_day must be between 1 and 28")
    current = date(year, month, review_day)
    while current.weekday() >= 5:
        current += timedelta(days=1)
    return current


def _score(evidence: Evidence) -> float:
    e = evidence.bounded()
    # Fundamentals/macro and execution quality dominate; social is confirmation only.
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
        decisions.append(Decision(candidate.ticker.upper(), action, score, tuple(reasons)))
    return sorted(decisions, key=lambda decision: decision.score, reverse=True)


def allocate_monthly_budget(
    decisions: Iterable[Decision], *, policy: PortfolioPolicy
) -> list[Decision]:
    """Allocate only to actionable entries, preserving cash and position caps."""
    entries = [decision for decision in decisions if decision.action is Action.ENTER]
    investable = max(0.0, policy.monthly_budget * (1.0 - policy.reserve_cash_weight))
    if not entries:
        return []
    amount = min(investable / len(entries), policy.monthly_budget * policy.max_single_new_weight)
    return [
        Decision(d.ticker, d.action, d.score, d.reason_codes, round(amount, 2))
        for d in entries[:policy.max_positions]
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
