"""Explicit outcome and observability taxonomy for NAVE.

The resolver is intentionally evidence-driven.  It never converts a missing
mark into a loss and never calls a token dead merely because a short horizon
contains no trade.  Callers provide the point-in-time event evidence and this
module returns a stable, auditable class.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class OutcomeStatus(str, Enum):
    RESOLVED = "RESOLVED"
    RIGHT_CENSORED = "RIGHT_CENSORED"
    UNRESOLVED = "UNRESOLVED"


class UnresolvedReason(str, Enum):
    NO_FUTURE_TRADE = "NO_FUTURE_TRADE"
    TOKEN_INACTIVE = "TOKEN_INACTIVE"
    TOKEN_DEAD_OR_DORMANT = "TOKEN_DEAD_OR_DORMANT"
    MIGRATED_BEFORE_HORIZON = "MIGRATED_BEFORE_HORIZON"
    VENUE_CHANGED = "VENUE_CHANGED"
    PUMPSWAP_CONTINUATION_REQUIRED = "PUMPSWAP_CONTINUATION_REQUIRED"
    PRICE_INPUT_MISSING = "PRICE_INPUT_MISSING"
    INVALID_RESERVE_STATE = "INVALID_RESERVE_STATE"
    PROVIDER_EVENT_GAP = "PROVIDER_EVENT_GAP"
    DUPLICATE_OR_ORDERING_AMBIGUITY = "DUPLICATE_OR_ORDERING_AMBIGUITY"
    PROTOCOL_GENERATED_FLOW_AMBIGUITY = "PROTOCOL_GENERATED_FLOW_AMBIGUITY"
    RIGHT_CENSORED = "RIGHT_CENSORED"
    TRUE_UNKNOWN = "TRUE_UNKNOWN"


@dataclass(frozen=True)
class OutcomeEvidence:
    """Evidence available for one token and one horizon.

    Counts refer only to the post-decision horizon interval.  A valid mark
    wins over a migration flag because a validated venue-aware mark resolves
    the outcome.  Otherwise failure reasons are ordered from data integrity
    to economic inactivity so the result is deterministic.
    """

    interval_complete: bool
    target_right_censored: bool
    valid_mark_count: int = 0
    future_trade_count: int = 0
    no_activity_through_horizon: bool = False
    migration_before_horizon: bool = False
    venue_changed: bool = False
    pumpswap_continuation_required: bool = False
    missing_price_count: int = 0
    invalid_reserve_count: int = 0
    ordering_ambiguity: bool = False
    protocol_generated_flow_ambiguity: bool = False


def classify_outcome(evidence: OutcomeEvidence) -> tuple[OutcomeStatus, str | None]:
    """Return ``(status, reason)`` without collapsing distinct failure modes."""

    if evidence.target_right_censored:
        return OutcomeStatus.RIGHT_CENSORED, UnresolvedReason.RIGHT_CENSORED.value
    if not evidence.interval_complete:
        return OutcomeStatus.UNRESOLVED, UnresolvedReason.PROVIDER_EVENT_GAP.value
    if evidence.valid_mark_count > 0:
        return OutcomeStatus.RESOLVED, None
    if evidence.ordering_ambiguity:
        return OutcomeStatus.UNRESOLVED, UnresolvedReason.DUPLICATE_OR_ORDERING_AMBIGUITY.value
    if evidence.protocol_generated_flow_ambiguity:
        return OutcomeStatus.UNRESOLVED, UnresolvedReason.PROTOCOL_GENERATED_FLOW_AMBIGUITY.value
    if evidence.migration_before_horizon:
        return OutcomeStatus.UNRESOLVED, UnresolvedReason.MIGRATED_BEFORE_HORIZON.value
    if evidence.pumpswap_continuation_required:
        return OutcomeStatus.UNRESOLVED, UnresolvedReason.PUMPSWAP_CONTINUATION_REQUIRED.value
    if evidence.venue_changed:
        return OutcomeStatus.UNRESOLVED, UnresolvedReason.VENUE_CHANGED.value
    if evidence.future_trade_count == 0:
        reason = (
            UnresolvedReason.TOKEN_INACTIVE
            if evidence.no_activity_through_horizon
            else UnresolvedReason.NO_FUTURE_TRADE
        )
        return OutcomeStatus.UNRESOLVED, reason.value
    if evidence.missing_price_count > 0:
        return OutcomeStatus.UNRESOLVED, UnresolvedReason.PRICE_INPUT_MISSING.value
    if evidence.invalid_reserve_count > 0:
        return OutcomeStatus.UNRESOLVED, UnresolvedReason.INVALID_RESERVE_STATE.value
    return OutcomeStatus.UNRESOLVED, UnresolvedReason.TRUE_UNKNOWN.value
