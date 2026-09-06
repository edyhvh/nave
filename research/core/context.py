"""Read-only shared context interfaces for downstream NAVE workflows."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from research.core.store import ResearchStore


def context_is_usable(context: Mapping[str, Any] | None, *, now: datetime | None = None,
                      max_age: timedelta = timedelta(days=3)) -> bool:
    """Only complete, uncontradicted, fresh context can enter a decision.

    Three days accommodates a weekend, but never carries old commentary into
    a new week. Producer expiry can shorten this consumer ceiling.
    """
    if not context or context.get("validated") is not True:
        return False
    if context.get("evidence_quality") != "VALIDATED" or context.get("corroboration_status") != "VALIDATED":
        return False
    if context.get("contradictions") or context.get("warnings"):
        return False
    current = now or datetime.now(UTC)
    try:
        stamps = [datetime.fromisoformat(str(context[key]).replace("Z", "+00:00"))
                  for key in ("published_at", "validated_at", "expires_at")]
        if current.tzinfo is None or any(stamp.tzinfo is None for stamp in stamps):
            return False
        published, validated, expires = stamps
        return published <= validated <= current < expires and current - published <= max_age
    except (KeyError, TypeError, ValueError):
        return False


class ResearchContext(Protocol):
    """Context surface that keeps downstream workflows provider-agnostic."""

    def latest_macro_context(self) -> Mapping[str, Any] | None: ...

    def latest_cava_context(self) -> Mapping[str, Any] | None: ...

    def portfolio_state(self) -> Mapping[str, Any] | None: ...

    def strategy_results(self, workflow: str | None = None) -> list[Mapping[str, Any]]: ...


class FileResearchContext:
    """Read-only context backed by a :class:`ResearchStore`."""

    def __init__(self, root: Path | None = None):
        self.store = ResearchStore(root)

    def latest_macro_context(self) -> Mapping[str, Any] | None:
        value = self.store.load_context("macro")
        return value if context_is_usable(value) else None

    def latest_cava_context(self) -> Mapping[str, Any] | None:
        value = self.store.load_context("cava")
        return value if context_is_usable(value) else None

    def portfolio_state(self) -> Mapping[str, Any] | None:
        return self.store.load_context("portfolio")

    def strategy_results(self, workflow: str | None = None) -> list[Mapping[str, Any]]:
        return self.store.list_results(workflow=workflow)
