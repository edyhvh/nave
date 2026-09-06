"""Human-gated portfolio research workflow.

This is a thin NAVE adapter around the existing ISM equity funnel. Portfolio
state is deliberately user-local; the public repository contains only the
schema and deterministic evaluation rules.
"""

from __future__ import annotations

import json
import math
import os
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

from research.core.contracts import (
    EvidenceKind,
    EvidenceReference,
    PointInTime,
    ProvenanceCategory,
    ResearchResult,
    ResearchStatus,
    RunMetadata,
    StateOwner,
)
from research.core.store import ResearchStore
from trading.stocks.ism_equity_pipeline import build_ism_equity_pipeline


class PortfolioAction:
    ADD_CANDIDATE = "ADD_CANDIDATE"
    HOLD = "HOLD"
    REDUCE_CANDIDATE = "REDUCE_CANDIDATE"
    EXIT_CANDIDATE = "EXIT_CANDIDATE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


@dataclass(frozen=True)
class PositionState:
    ticker: str
    position_status: str = "open"
    approximate_entry: float | None = None
    thesis: str = ""
    source_strategy: str = "manual"
    watch_target: float | None = None
    candidate_status: str = "current"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {"ticker": self.ticker.upper()}


@dataclass(frozen=True)
class PortfolioState:
    updated_at: str | None = None
    ledger_history_complete: bool | None = None
    positions: tuple[PositionState, ...] = ()
    watchlist: tuple[Mapping[str, Any], ...] = ()
    portfolio_review_universe: tuple[Mapping[str, Any], ...] = ()
    ism_candidates: tuple[Mapping[str, Any], ...] = ()
    disclosure_candidates: tuple[Mapping[str, Any], ...] = ()
    strategy_candidates: tuple[Mapping[str, Any], ...] = ()
    case_studies: tuple[Mapping[str, Any], ...] = ()

    @staticmethod
    def _records(payload: Mapping[str, Any], key: str) -> tuple[Mapping[str, Any], ...]:
        values = payload.get(key) or []
        return tuple(item for item in values if isinstance(item, Mapping))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PortfolioState":
        positions = tuple(
            PositionState(
                ticker=str(item.get("ticker") or "").upper(),
                position_status=str(item.get("position_status") or "open"),
                approximate_entry=item.get("approximate_entry"),
                thesis=str(item.get("thesis") or ""),
                source_strategy=str(item.get("source_strategy") or "manual"),
                watch_target=item.get("watch_target"),
                candidate_status=str(item.get("candidate_status") or "current"),
            )
            for item in payload.get("positions") or []
            if isinstance(item, Mapping) and str(item.get("ticker") or "").strip()
        )
        return cls(
            updated_at=payload.get("updated_at"),
            ledger_history_complete=payload.get("ledger_history_complete"),
            positions=positions,
            watchlist=cls._records(payload, "watchlist"),
            portfolio_review_universe=cls._records(payload, "portfolio_review_universe"),
            ism_candidates=cls._records(payload, "ism_candidates"),
            disclosure_candidates=cls._records(payload, "disclosure_candidates"),
            strategy_candidates=cls._records(payload, "strategy_candidates"),
            case_studies=cls._records(payload, "case_studies"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "updated_at": self.updated_at,
            "ledger_history_complete": self.ledger_history_complete,
            "positions": [position.to_dict() for position in self.positions],
            "watchlist": [dict(item) for item in self.watchlist],
            "portfolio_review_universe": [dict(item) for item in self.portfolio_review_universe],
            "ism_candidates": [dict(item) for item in self.ism_candidates],
            "disclosure_candidates": [dict(item) for item in self.disclosure_candidates],
            "strategy_candidates": [dict(item) for item in self.strategy_candidates],
            "case_studies": [dict(item) for item in self.case_studies],
        }


def default_portfolio_state_path() -> Path:
    configured = os.getenv("NAVE_PORTFOLIO_STATE_FILE")
    if configured:
        return Path(configured).expanduser()
    hermes_state = Path.home() / ".hermes" / "state" / "portfolio_manager" / "portfolio.json"
    if hermes_state.exists():
        return hermes_state
    return Path.home() / ".nave" / "portfolio.json"


def load_portfolio_state(path: Path | None = None) -> PortfolioState:
    state_path = path or default_portfolio_state_path()
    if not state_path.exists():
        return PortfolioState()
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("portfolio state must be a JSON object")
    return PortfolioState.from_dict(payload)


def _result(
    workflow: str,
    status: ResearchStatus,
    payload: Mapping[str, Any],
    *,
    evidence: list[EvidenceReference] | None = None,
    warnings: list[str] | None = None,
    now: datetime | None = None,
    input_available_at: datetime | None = None,
) -> ResearchResult:
    decision_time = now or datetime.now(UTC)
    return ResearchResult(
        workflow=workflow,
        status=status,
        metadata=RunMetadata(
            strategy_name="portfolio-research",
            strategy_version="1.0.0",
            run_id=str(uuid.uuid4()),
            decision_time=decision_time,
            started_at=decision_time,
            completed_at=decision_time,
            input_available_at=input_available_at,
        ),
        payload=payload,
        evidence=tuple(evidence or []),
        warnings=tuple(warnings or []),
    )


def fresh_timestamp(value: Any, now: datetime, max_age: timedelta = timedelta(days=3)) -> bool:
    try:
        timestamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return timestamp.tzinfo is not None and timedelta(0) <= now - timestamp <= max_age
    except (ValueError, TypeError):
        return False


def positive_number(value: Any) -> bool:
    try:
        return not isinstance(value, bool) and math.isfinite(float(value)) and float(value) > 0
    except (ValueError, TypeError, OverflowError):
        return False


def review_positions(
    state: PortfolioState,
    evidence_by_ticker: Mapping[str, Mapping[str, Any]] | None = None,
    *,
    now: datetime | None = None,
) -> ResearchResult:
    """Review each position and preserve the original thesis/provenance."""
    evidence_by_ticker = evidence_by_ticker or {}
    decisions: list[dict[str, Any]] = []
    evidence: list[EvidenceReference] = []
    decision_time = now or datetime.now(UTC)
    for position in state.positions:
        ticker = position.ticker.upper()
        observed = evidence_by_ticker.get(ticker, {})
        reasons: list[str] = []
        market = observed.get("market_state") or {}
        company = observed.get("company_information") or {}
        missing = []
        if not fresh_timestamp(state.updated_at, decision_time):
            missing.append("portfolio_state_stale_or_undated")
        if state.ledger_history_complete is False:
            missing.append("ledger_history_incomplete")
        if not positive_number(market.get("current_price")) or not fresh_timestamp(market.get("as_of"), decision_time):
            missing.append("price_missing_stale_or_invalid")
        meaningful_company = any(
            isinstance(company.get(key), (int, float)) and not isinstance(company.get(key), bool) and math.isfinite(company[key])
            for key in ("revenue", "pe_ratio", "forward_pe", "eps_growth_next_year", "revenue_growth_long_term")
        )
        if not meaningful_company or company.get("unavailable_reason") or company.get("source") == "unavailable":
            missing.append("company_information_missing")
        if observed.get("technical_condition") not in {"healthy", "weak", "breakdown"}:
            missing.append("technical_evidence_missing")
        if observed.get("invalidation") is True or position.candidate_status in {"invalidated", "broken"}:
            action = PortfolioAction.EXIT_CANDIDATE
            reasons.append("thesis_invalidated")
        elif observed.get("meaningful_new_information") is True:
            action = PortfolioAction.REVIEW_REQUIRED
            reasons.append("meaningful_new_information")
        elif missing:
            action = PortfolioAction.REVIEW_REQUIRED
            reasons.extend(missing)
        elif observed.get("technical_condition") in {"weak", "breakdown"}:
            action = PortfolioAction.REDUCE_CANDIDATE
            reasons.append("technical_weakness")
        elif observed.get("macro_regime") in {None, "unknown", "UNKNOWN"}:
            action = PortfolioAction.REVIEW_REQUIRED
            reasons.append("macro_context_missing")
        else:
            action = PortfolioAction.HOLD
            reasons.append("thesis_and_current_evidence_have_no_recorded_break")
        decisions.append(
            {
                "ticker": ticker,
                "action": action,
                "thesis": position.thesis,
                "source_strategy": position.source_strategy,
                "watch_target": position.watch_target,
                "reasons": reasons,
                "evidence": dict(observed),
                "human_decision_required": True,
            }
        )
        evidence.append(
            EvidenceReference(
                reference_id=f"portfolio-position-{ticker}",
                source="private.portfolio.state",
                claim=f"Position state for {ticker} was supplied by the user-local portfolio file",
                kind=EvidenceKind.FACT,
                # The ledger's source freshness is not part of PortfolioState;
                # do not invent availability at the decision time.
                point_in_time=PointInTime(available_at=None, decision_time=now),
                metadata={"private_state": True},
                provenance_category=ProvenanceCategory.USER_STATE.value,
                state_owner=StateOwner.USER_RUNTIME.value,
                lifecycle="RECURRING",
            )
        )
    status = ResearchStatus.ACTION_REQUIRED if decisions else ResearchStatus.DATA_UNAVAILABLE
    result = _result(
        "portfolio.review",
        status,
        {"positions": decisions, "read_only": True, "human_decision_required": True},
        evidence=evidence,
        warnings=["position state is user-local and is not committed to Git"] if decisions else ["portfolio state is unavailable"],
        now=now,
    )
    return result


def portfolio_candidates(
    manufacturing: Mapping[str, Any],
    services: Mapping[str, Any],
    *,
    state: PortfolioState = PortfolioState(),
    additional_candidates: list[Mapping[str, Any]] | None = None,
    research_by_symbol: Mapping[str, Mapping[str, Any]] | None = None,
    now: datetime | None = None,
) -> ResearchResult:
    """Rank ISM-derived candidates while keeping source provenance attached."""
    held = [position.ticker for position in state.positions if position.position_status == "open"]
    watched = [str(item.get("ticker") or "") for item in state.watchlist]
    pipeline = build_ism_equity_pipeline(
        manufacturing,
        services,
        portfolio_symbols=held,
        watch_symbols=watched,
        additional_candidates=additional_candidates or [],
        research_by_symbol=research_by_symbol,
        limit=6,
    )
    candidates = []
    evidence: list[EvidenceReference] = []
    decision_time = now or datetime.now(UTC)
    for item in pipeline.get("candidate_pool") or []:
        sources = sorted(set(item.get("sources") or []))
        why = [f"ISM {source} candidate" for source in sources] or ["explicitly supplied watch/portfolio candidate"]
        candidates.append(
            {
                "ticker": item.get("symbol"),
                "why_is_this_here": why,
                "provenance": {
                    "sources": sources,
                    "ism_signals": item.get("ism_signals") or [],
                    "portfolio_state": item.get("portfolio_state"),
                    "discovery_score": item.get("discovery_score"),
                },
                "status": "RESEARCH_REQUIRED",
                "research_only": True,
            }
        )
        evidence.append(
            EvidenceReference(
                reference_id=f"ism-candidate-{item.get('symbol')}",
                source="nave.trading.stocks.ism_equity_pipeline",
                claim=f"{item.get('symbol')} entered the bounded ISM candidate pool",
                kind=EvidenceKind.INFERENCE,
                point_in_time=PointInTime(decision_time=decision_time, available_at=None),
                metadata={"sources": sources},
                provenance_category=ProvenanceCategory.RESEARCH_CANDIDATE.value,
                state_owner=StateOwner.NAVE_RESEARCH.value,
                lifecycle="CANDIDATE",
            )
        )
    status = ResearchStatus.SETUP_FOUND if candidates else ResearchStatus.NO_SETUP
    result = _result(
        "portfolio.candidates",
        status,
        {
            "candidates": candidates,
            "pipeline": pipeline,
            "state_categories": {
                "positions": len(state.positions),
                "active_watches": len(state.watchlist),
                "portfolio_review_universe": len(state.portfolio_review_universe),
                "ism_candidates": len(state.ism_candidates),
                "disclosure_candidates": len(state.disclosure_candidates),
                "strategy_candidates": len(state.strategy_candidates),
                "case_studies": len(state.case_studies),
            },
            "why_is_this_here_required": True,
            "human_decision_required": True,
        },
        evidence=evidence,
        warnings=["ISM rankings are discovery context, not standalone buy signals"] if candidates else ["no candidate entered the bounded ISM pool"],
        now=now,
    )
    return result


def ism_rank(
    manufacturing: Mapping[str, Any],
    services: Mapping[str, Any],
    *,
    state: PortfolioState = PortfolioState(),
    now: datetime | None = None,
) -> ResearchResult:
    result = portfolio_candidates(manufacturing, services, state=state, now=now)
    payload = dict(result.payload)
    payload["mapping"] = "ISM industries → sectors → companies through the repo-native mapping/funnel"
    return ResearchResult(
        workflow="portfolio.ism",
        status=result.status,
        metadata=result.metadata,
        payload=payload,
        evidence=result.evidence,
        warnings=result.warnings,
    )


def check_watch(
    watches: list[Mapping[str, Any]],
    prices: Mapping[str, float],
    *,
    previous_prices: Mapping[str, float] | None = None,
    price_timestamps: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> ResearchResult:
    """Cheap deterministic condition check; model escalation is always false."""
    events: list[dict[str, Any]] = []
    checked_prices: dict[str, float | None] = {}
    unavailable: list[str] = []
    invalid_watches: list[str] = []
    valid_watch_count = 0
    missing_previous: list[str] = []
    previous_prices = previous_prices or {}
    decision_time = now or datetime.now(UTC)
    for watch in watches:
        ticker = str(watch.get("ticker") or "").upper()
        price = prices.get(ticker)
        if not ticker:
            continue
        if not positive_number(price) or (price_timestamps is not None and not fresh_timestamp(price_timestamps.get(ticker), decision_time)):
            checked_prices[ticker] = None
            unavailable.append(ticker)
            continue
        checked_prices[ticker] = float(price)
        condition_raw = watch.get("condition")
        condition = str(condition_raw or "ZONE").upper()
        if condition not in {"ABOVE", "BELOW", "CROSS_ABOVE", "CROSS_BELOW", "ZONE"}:
            invalid_watches.append(ticker)
            continue
        try:
            if price is None:
                continue
            current = float(price)
            threshold = watch.get("threshold")
            lower = upper = None
            zone = watch.get("zone")
            if isinstance(zone, (list, tuple)) and len(zone) == 2:
                lower, upper = float(zone[0]), float(zone[1])
            elif isinstance(watch.get("lower"), (int, float)) or isinstance(watch.get("upper"), (int, float)):
                lower = float(watch["lower"]) if watch.get("lower") is not None else None
                upper = float(watch["upper"]) if watch.get("upper") is not None else None
            if condition in {"ABOVE", "BELOW", "CROSS_ABOVE", "CROSS_BELOW"} and threshold is None:
                invalid_watches.append(ticker)
                continue
            if condition == "ZONE" and not (
                (lower is not None and upper is not None)
                or (not condition_raw and threshold is not None)
            ):
                invalid_watches.append(ticker)
                continue
            bounds = [value for value in (threshold, lower, upper) if value is not None]
            if any(not positive_number(value) for value in bounds) or (lower is not None and upper is not None and lower > upper):
                invalid_watches.append(ticker)
                continue
            valid_watch_count += 1
            if condition in {"CROSS_ABOVE", "CROSS_BELOW"} and not positive_number(previous_prices.get(ticker)):
                missing_previous.append(ticker)
                continue
            if condition == "ABOVE":
                reached = current >= float(threshold)
            elif condition == "BELOW":
                reached = current <= float(threshold)
            elif condition == "CROSS_ABOVE":
                previous = previous_prices.get(ticker)
                reached = previous is not None and float(previous) < float(threshold) <= current
            elif condition == "CROSS_BELOW":
                previous = previous_prices.get(ticker)
                reached = previous is not None and current <= float(threshold) < float(previous)
            else:
                # Backwards-compatible rows with only ``threshold`` retain
                # the former zone/reached behavior.
                reached = (
                    current >= float(threshold)
                    if not condition_raw and threshold is not None
                    else lower is not None and current >= lower and
                    upper is not None and current <= upper
                )
            previous = previous_prices.get(ticker)
            if reached and positive_number(previous) and condition in {"ZONE", "ABOVE", "BELOW"}:
                prior = float(previous)
                previously_reached = (
                    prior <= float(threshold) if condition == "BELOW" else
                    prior >= float(threshold) if condition == "ABOVE" or (not condition_raw and threshold is not None) else
                    lower <= prior <= upper
                )
                reached = not previously_reached
        except (TypeError, ValueError):
            invalid_watches.append(ticker)
            continue
        if reached:
            event = "ZONE_REACHED" if condition == "ZONE" else condition
            item = {
                "ticker": ticker,
                "price": current,
                "condition": condition,
                "threshold": float(threshold) if threshold is not None else None,
                "thesis": watch.get("thesis"),
                "source_strategy": watch.get("source_strategy"),
                "source_reference": watch.get("source_reference"),
                "watch_kind": watch.get("watch_kind"),
                "event": event,
            }
            if lower is not None or upper is not None:
                item["zone"] = {"lower": lower, "upper": upper}
            events.append(item)
    grouped: dict[str, dict[str, Any]] = {}
    for event in events:
        ticker = event["ticker"]
        if ticker not in grouped:
            grouped[ticker] = {**event, "matched_rules": []}
        grouped[ticker]["matched_rules"].append(event)
    events = list(grouped.values())
    status = (
        ResearchStatus.ACTION_REQUIRED
        if events
        else ResearchStatus.INSUFFICIENT_EVIDENCE
        if missing_previous
        else ResearchStatus.NO_SETUP
        if valid_watch_count and not unavailable and not invalid_watches
        else ResearchStatus.DATA_UNAVAILABLE
    )
    result = _result(
        "portfolio.watch",
        status,
        {
            "events": events,
            "checked": len(watches),
            "valid_watch_count": valid_watch_count,
            "invalid_watches": sorted(set(invalid_watches)),
            "missing_previous": sorted(set(missing_previous)),
            "prices": checked_prices,
            "unavailable_prices": unavailable,
            "model_escalation": False,
            "reason": "deterministic condition comparison only",
        },
        warnings=[
            *(["no actionable user-local watch conditions were supplied; no-setup was not inferred"] if not valid_watch_count else []),
            *([f"watch conditions are incomplete or invalid for: {', '.join(sorted(set(invalid_watches)))}"] if invalid_watches else []),
            *(["previous observation unavailable for: " + ", ".join(missing_previous)] if missing_previous else []),
            *(["watch events notify a human; they never execute"] if events else []),
            *([f"current price unavailable for: {', '.join(unavailable)}"] if unavailable else []),
        ],
        now=now,
    )
    return result


class PortfolioWorkflow:
    def __init__(self, *, store: ResearchStore | None = None):
        self.store = store or ResearchStore()

    def save(self, result: ResearchResult) -> ResearchResult:
        self.store.save_result(result)
        return result

    def status(self) -> dict[str, Any]:
        output = {}
        for workflow in ("portfolio.review", "portfolio.candidates", "portfolio.ism", "portfolio.watch"):
            result = self.store.load_result(workflow)
            if result:
                output[workflow] = {"status": result.status.value, "run_id": result.metadata.run_id}
        return output
