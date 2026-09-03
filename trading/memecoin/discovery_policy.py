"""Fail-closed admission policy for asymmetric Solana and TON research.

This module is intentionally provider-agnostic. Chain adapters normalize their
observations into :class:`CandidateEvidence`; this policy then decides whether
the evidence supports REVIEW, WATCH, or a human-gated ENTER candidate.

It never signs, submits, swaps, bridges, transfers, or touches a wallet.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

REQUIRED_GATES = (
    "asset_identity",
    "liquidity",
    "holder_concentration",
    "deployer_behavior",
    "authorities",
    "transfer_mechanics",
    "unlocks",
    "volume_integrity",
    "custody_bridge",
    "manipulation",
)


class Chain(str, Enum):
    SOLANA = "solana"
    TON = "ton"


class GateStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


class Recommendation(str, Enum):
    ENTER = "ENTER"
    WATCH = "WATCH"
    REVIEW = "REVIEW"


class RunOutcome(str, Enum):
    ENTER_CANDIDATES = "enter_candidates"
    WATCHLIST_ONLY = "watchlist_only"
    NO_VALID_SETUP = "no_valid_setup"
    DATA_INCOMPLETE = "data_incomplete"


@dataclass(frozen=True)
class GateEvidence:
    """One normalized gate result with provenance.

    A PASS without an observation timestamp and at least one source URL is not
    admissible. The policy treats it as untraceable evidence and fails closed.
    """

    status: GateStatus
    observed_at: str | None
    source_urls: tuple[str, ...] = ()
    details: str = ""

    @property
    def traceable(self) -> bool:
        return bool(self.observed_at and self.source_urls)


@dataclass(frozen=True)
class RiskPlan:
    """Human-gated long-only risk plan required before WATCH or ENTER."""

    entry_zone_low_usd: float | None
    entry_zone_high_usd: float | None
    invalidation_price_usd: float | None
    max_loss_usd: float | None
    max_loss_pct_nav: float | None
    max_position_usd: float | None
    max_exit_notional_usd: float | None
    liquidity_aware_exit: str
    monitoring_triggers: tuple[str, ...]
    execution_trigger: str
    time_stop: str
    targets_usd: tuple[float, ...] = ()
    fee_slippage_bps: float | None = None

    def blockers(self) -> list[str]:
        blockers: list[str] = []
        positive_fields = {
            "entry_zone_low_usd": self.entry_zone_low_usd,
            "entry_zone_high_usd": self.entry_zone_high_usd,
            "invalidation_price_usd": self.invalidation_price_usd,
            "max_loss_usd": self.max_loss_usd,
            "max_loss_pct_nav": self.max_loss_pct_nav,
            "max_position_usd": self.max_position_usd,
            "max_exit_notional_usd": self.max_exit_notional_usd,
            "fee_slippage_bps": self.fee_slippage_bps,
        }
        for name, value in positive_fields.items():
            if value is None or value <= 0:
                blockers.append(f"risk_plan:{name}")

        if (
            self.entry_zone_low_usd is not None
            and self.entry_zone_high_usd is not None
            and self.entry_zone_high_usd < self.entry_zone_low_usd
        ):
            blockers.append("risk_plan:entry_zone_order")
        if (
            self.invalidation_price_usd is not None
            and self.entry_zone_low_usd is not None
            and self.invalidation_price_usd >= self.entry_zone_low_usd
        ):
            blockers.append("risk_plan:invalidation_not_below_entry")
        if (
            self.max_position_usd is not None
            and self.max_exit_notional_usd is not None
            and self.max_position_usd > self.max_exit_notional_usd
        ):
            blockers.append("risk_plan:position_exceeds_exit_capacity")
        if self.max_loss_pct_nav is not None and self.max_loss_pct_nav > 100:
            blockers.append("risk_plan:max_loss_pct_nav")
        if not self.liquidity_aware_exit.strip():
            blockers.append("risk_plan:liquidity_aware_exit")
        if not self.monitoring_triggers:
            blockers.append("risk_plan:monitoring_triggers")
        if not self.execution_trigger.strip():
            blockers.append("risk_plan:execution_trigger")
        if not self.time_stop.strip():
            blockers.append("risk_plan:time_stop")
        if not self.targets_usd:
            blockers.append("risk_plan:targets_usd")
        return blockers


@dataclass(frozen=True)
class CandidateEvidence:
    chain: Chain
    asset_address: str
    symbol: str | None
    observed_at: str
    hypothesis: str
    timeframe: str
    gates: Mapping[str, GateEvidence]
    risk_plan: RiskPlan | None
    trigger_confirmed: bool = False


@dataclass(frozen=True)
class CandidateDecision:
    chain: Chain
    asset_address: str
    symbol: str | None
    recommendation: Recommendation
    eligible: bool
    terminal_rejection: bool
    trigger_confirmed: bool
    blockers: tuple[str, ...]
    observed_at: str
    human_gate_required: bool = True

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["chain"] = self.chain.value
        payload["recommendation"] = self.recommendation.value
        return payload


def evaluate_candidate(candidate: CandidateEvidence) -> CandidateDecision:
    """Apply all hard evidence and risk gates to one candidate.

    ENTER means only "eligible for a human decision". It does not authorize or
    imply execution.
    """

    blockers: list[str] = []
    hard_fail = False

    if not candidate.asset_address.strip():
        blockers.append("missing_asset_address")
    if not candidate.observed_at.strip():
        blockers.append("missing_observed_at")
    if not candidate.hypothesis.strip():
        blockers.append("missing_hypothesis")
    if not candidate.timeframe.strip():
        blockers.append("missing_timeframe")

    for gate_name in REQUIRED_GATES:
        evidence = candidate.gates.get(gate_name)
        if evidence is None:
            blockers.append(f"missing_gate:{gate_name}")
            continue
        if evidence.status == GateStatus.FAIL:
            hard_fail = True
            blockers.append(f"hard_fail:{gate_name}")
        elif evidence.status == GateStatus.UNKNOWN:
            blockers.append(f"unknown:{gate_name}")
        if not evidence.traceable:
            blockers.append(f"untraceable:{gate_name}")

    if candidate.risk_plan is None:
        blockers.append("missing_risk_plan")
    else:
        blockers.extend(candidate.risk_plan.blockers())

    evidence_incomplete = any(
        blocker in {"missing_asset_address", "missing_observed_at"}
        or blocker.startswith(("missing_gate:", "unknown:", "untraceable:"))
        for blocker in blockers
    )
    terminal_rejection = hard_fail and not evidence_incomplete
    eligible = not blockers
    if hard_fail or not eligible:
        recommendation = Recommendation.REVIEW
    elif candidate.trigger_confirmed:
        recommendation = Recommendation.ENTER
    else:
        recommendation = Recommendation.WATCH

    return CandidateDecision(
        chain=candidate.chain,
        asset_address=candidate.asset_address,
        symbol=candidate.symbol,
        recommendation=recommendation,
        eligible=eligible,
        terminal_rejection=terminal_rejection,
        trigger_confirmed=candidate.trigger_confirmed,
        blockers=tuple(blockers),
        observed_at=candidate.observed_at,
    )


@dataclass(frozen=True)
class DiscoveryRunSummary:
    """Coverage-aware run result; only complete runs may claim no setup."""

    outcome: RunOutcome
    valid_no_setup: bool
    universe_count: int
    evaluated_count: int
    decisions: tuple[CandidateDecision, ...]
    coverage_complete: bool
    source_errors: tuple[str, ...] = ()
    blocker_counts: Mapping[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome.value,
            "valid_no_setup": self.valid_no_setup,
            "universe_count": self.universe_count,
            "evaluated_count": self.evaluated_count,
            "coverage_complete": self.coverage_complete,
            "source_errors": list(self.source_errors),
            "blocker_counts": dict(self.blocker_counts),
            "decisions": [decision.to_dict() for decision in self.decisions],
        }


def summarize_run(
    decisions: list[CandidateDecision] | tuple[CandidateDecision, ...],
    *,
    universe_count: int,
    coverage_complete: bool,
    source_errors: list[str] | tuple[str, ...] = (),
) -> DiscoveryRunSummary:
    """Aggregate decisions without turning data failure into "no setup"."""

    if universe_count < 0:
        raise ValueError("universe_count must be >= 0")

    decision_tuple = tuple(decisions)
    errors = tuple(source_errors)
    evaluated_count = len(decision_tuple)
    complete = coverage_complete and not errors and evaluated_count == universe_count

    if not complete:
        outcome = RunOutcome.DATA_INCOMPLETE
    elif any(d.recommendation == Recommendation.ENTER for d in decision_tuple):
        outcome = RunOutcome.ENTER_CANDIDATES
    elif any(d.recommendation == Recommendation.WATCH for d in decision_tuple):
        outcome = RunOutcome.WATCHLIST_ONLY
    elif any(not d.terminal_rejection for d in decision_tuple):
        outcome = RunOutcome.DATA_INCOMPLETE
    else:
        outcome = RunOutcome.NO_VALID_SETUP

    blocker_counts = Counter(
        blocker for decision in decision_tuple for blocker in decision.blockers
    )
    return DiscoveryRunSummary(
        outcome=outcome,
        valid_no_setup=outcome == RunOutcome.NO_VALID_SETUP,
        universe_count=universe_count,
        evaluated_count=evaluated_count,
        decisions=decision_tuple,
        coverage_complete=complete,
        source_errors=errors,
        blocker_counts=dict(sorted(blocker_counts.items())),
    )
