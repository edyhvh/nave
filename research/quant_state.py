"""Adapters for user-local Abi/Hermes Quant state.

The repository owns the adapter contract, not the user's live state. This
module reads a local watch-store file when present and converts only explicit
numeric conditions into the deterministic NAVE watch shape. Event and
natural-language responsibilities remain preserved as unparsed metadata so
they cannot be mistaken for a price ``NO_SETUP`` result.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


def default_quant_watch_state_path() -> Path | None:
    configured = os.getenv("NAVE_QUANT_WATCH_STATE_FILE")
    if configured:
        return Path(configured).expanduser()
    hermes_state = Path.home() / ".hermes" / "profiles" / "quant" / "watches" / "watches.json"
    return hermes_state if hermes_state.exists() else None


@dataclass(frozen=True)
class QuantWatchState:
    source_path: Path
    active_watches: tuple[Mapping[str, Any], ...]
    deterministic_watches: tuple[Mapping[str, Any], ...]
    unparsed_responsibilities: tuple[Mapping[str, Any], ...]

    @property
    def warnings(self) -> tuple[str, ...]:
        if not self.unparsed_responsibilities:
            return ()
        return (
            "some active Quant responsibilities are not price conditions and were preserved without evaluation: "
            + ", ".join(str(item.get("id") or "unknown") for item in self.unparsed_responsibilities),
        )


_TICKER_RE = re.compile(r"(?:^|\W)([A-Z]{2,5})(?=\s*(?:/|\())")
_RANGE_RE = re.compile(r"\$\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*[-–]\s*\$?\s*([0-9][0-9,]*(?:\.[0-9]+)?)")
_BELOW_RE = re.compile(r"price\s+below\s+\$\s*([0-9][0-9,]*(?:\.[0-9]+)?)", re.IGNORECASE)


def _number(value: str) -> float:
    return float(value.replace(",", ""))


def _ticker(subject: Any) -> str | None:
    match = _TICKER_RE.search(str(subject or ""))
    return match.group(1).upper() if match else None


def _numeric_condition(conditions: Any) -> dict[str, Any] | None:
    if not isinstance(conditions, list):
        return None
    for raw in conditions:
        text = str(raw or "")
        lowered = text.lower()
        below = _BELOW_RE.search(text)
        if below:
            return {"condition": "BELOW", "threshold": _number(below.group(1))}
        range_match = _RANGE_RE.search(text)
        if range_match and ("zone" in lowered or "pullback" in lowered):
            return {
                "condition": "ZONE",
                "zone": [_number(range_match.group(1)), _number(range_match.group(2))],
            }
    return None


def _canonical_watch(raw: Mapping[str, Any]) -> dict[str, Any] | None:
    if str(raw.get("state") or "").lower() != "active":
        return None
    ticker = _ticker(raw.get("subject"))
    numeric = _numeric_condition(raw.get("conditions"))
    if not ticker or not numeric:
        return None
    return {
        "ticker": ticker,
        **numeric,
        "thesis": raw.get("thesis_ref") or raw.get("name"),
        "source_strategy": "hermes.quant.watch_store",
        "source_reference": str(raw.get("id") or ""),
        "state_owner": str(raw.get("owner") or "quant"),
        "watch_kind": str(raw.get("kind") or "condition"),
        "conditions": list(raw.get("conditions") or []),
        "alert_criteria": list(raw.get("alert_criteria") or []),
        "data_source": raw.get("data_source"),
        "created": raw.get("created"),
        "updated": raw.get("updated"),
        "last_checked_at": raw.get("last_checked_at"),
        "expires_at": raw.get("expires_at"),
        "review_at": raw.get("review_at"),
    }


def load_quant_watch_state(path: Path | None = None) -> QuantWatchState | None:
    """Load the local Quant watch store without mutating it or Git state."""
    configured = os.getenv("NAVE_QUANT_WATCH_STATE_FILE")
    explicit = path is not None or bool(configured)
    source_path = path or default_quant_watch_state_path()
    if source_path is None:
        return None
    if not source_path.exists():
        if explicit:
            raise FileNotFoundError(source_path)
        return None
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    rows = payload.get("watches") if isinstance(payload, Mapping) else payload
    if not isinstance(rows, list):
        raise ValueError(f"{source_path} must contain a watches array")
    active = tuple(
        row for row in rows
        if isinstance(row, Mapping) and str(row.get("state") or "").lower() == "active"
    )
    deterministic = tuple(
        canonical for row in active if (canonical := _canonical_watch(row)) is not None
    )
    parsed_ids = {str(row.get("source_reference") or "") for row in deterministic}
    unparsed = tuple(row for row in active if str(row.get("id") or "") not in parsed_ids)
    return QuantWatchState(
        source_path=source_path,
        active_watches=active,
        deterministic_watches=deterministic,
        unparsed_responsibilities=unparsed,
    )


__all__ = ["QuantWatchState", "default_quant_watch_state_path", "load_quant_watch_state"]
