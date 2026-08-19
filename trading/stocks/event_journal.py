"""Persistent, human-gated journal for material stock events.

The journal keeps an event visible after it stops being "new".  This prevents
important disclosures or portfolio signals from disappearing after one daily
scan.  It is read/write local state only; it never executes trades.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

DEFAULT_PATH = Path(os.path.expanduser("~/.hermes/state/portfolio_manager/event_journal.json"))
STATUSES = {"new", "watching", "reviewed", "closed"}


def _path(path: str | Path | None = None) -> Path:
    return Path(path or os.getenv("PORTFOLIO_EVENT_JOURNAL") or DEFAULT_PATH)


def _load(path: str | Path | None = None) -> dict[str, Any]:
    target = _path(path)
    if not target.exists():
        return {"version": 1, "events": []}
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "events": []}
    if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
        return {"version": 1, "events": []}
    return {"version": 1, "events": payload["events"]}


def _save(payload: dict[str, Any], path: str | Path | None = None) -> None:
    target = _path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _legacy_event_id(event: dict[str, Any]) -> str:
    source = str(event.get("source_url") or event.get("source") or "unknown")
    ticker = str(event.get("ticker") or "?").upper()
    event_date = str(event.get("event_date") or "unknown")
    return f"{source}|{ticker}|{event_date}"


def _event_id(event: dict[str, Any]) -> str:
    """Return a stable identity that preserves distinct rows in one filing."""
    identity = {
        key: event.get(key)
        for key in (
            "source_url",
            "source",
            "ticker",
            "event_date",
            "event_type",
            "amount_range",
            "politician",
            "disclosure_date",
            "asset_description",
        )
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]
    return f"{_legacy_event_id(event)}|{digest}"


def _same_trade_identity(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """Match legacy rows only when all available trade identity fields agree."""
    keys = (
        "source_url",
        "source",
        "ticker",
        "event_date",
        "event_type",
        "amount_range",
        "politician",
        "disclosure_date",
        "asset_description",
    )
    return all(
        left.get(key) is None
        or right.get(key) is None
        or left.get(key) == right.get(key)
        for key in keys
    )


def importance_for_trade(trade: dict[str, Any]) -> str:
    """Classify a disclosure for follow-up, without treating it as a signal."""
    amount = str(trade.get("amount_range") or "")
    lower_bound = min(
        (int(value.replace(",", "")) for value in re.findall(r"\$?([\d,]+)", amount)),
        default=0,
    )
    description = str(trade.get("asset_description") or "").lower()
    if lower_bound >= 50_001 or "option" in description:
        return "high"
    if lower_bound >= 15_001:
        return "medium"
    return "low"


def upsert_event(event: dict[str, Any], *, path: str | Path | None = None) -> dict[str, Any]:
    """Insert or update one event and return its stable journal row."""
    now = datetime.now(UTC).isoformat()
    row = dict(event)
    row["ticker"] = str(row.get("ticker") or "?").upper()
    row["event_id"] = row.get("event_id") or _event_id(row)
    row["importance"] = row.get("importance") or "medium"
    row["status"] = row.get("status") if row.get("status") in STATUSES else "new"
    row.setdefault("observed_at", now)
    row.setdefault("review_count", 0)
    legacy_id = _legacy_event_id(row)
    payload = _load(path)
    events = payload["events"]
    for index, existing in enumerate(events):
        if isinstance(existing, dict) and (
            existing.get("event_id") == row["event_id"]
            or (
                existing.get("event_id") == legacy_id
                and _same_trade_identity(existing, row)
            )
        ):
            preserved = dict(existing)
            preserved.update({key: value for key, value in row.items() if value is not None})
            row = preserved
            events[index] = row
            break
    else:
        events.append(row)
    _save(payload, path)
    return row


def record_politician_trades(
    trades: Iterable[dict[str, Any]], *, path: str | Path | None = None
) -> list[dict[str, Any]]:
    rows = []
    for trade in trades:
        row = dict(trade)
        row.update(
            {
                "source": "STOCK Act",
                "source_url": row.get("link"),
                "ticker": row.get("symbol") or "UNKNOWN",
                "event_date": row.get("transaction_date") or row.get("disclosure_date"),
                "event_type": str(row.get("transaction_type") or "disclosure").lower(),
                "importance": importance_for_trade(row),
                "review_status": "unreviewed",
                "next_review_date": (
                    datetime.now(UTC).date() + timedelta(days=7)
                ).isoformat(),
            }
        )
        rows.append(upsert_event(row, path=path))
    return rows


def list_events(
    *,
    status: str | None = None,
    ticker: str | None = None,
    due_only: bool = False,
    path: str | Path | None = None,
) -> list[dict[str, Any]]:
    today = datetime.now(UTC).date().isoformat()
    events = [event for event in _load(path)["events"] if isinstance(event, dict)]
    if status:
        events = [event for event in events if event.get("status") == status]
    if ticker:
        events = [event for event in events if str(event.get("ticker", "")).upper() == ticker.upper()]
    if due_only:
        events = [
            event
            for event in events
            if event.get("status") not in {"closed", "reviewed"}
            and str(event.get("next_review_date") or "") <= today
        ]
    return sorted(events, key=lambda event: (str(event.get("next_review_date") or "9999"), str(event.get("event_id"))))


def mark_event(
    event_id: str,
    *,
    status: str,
    note: str | None = None,
    next_review_date: str | None = None,
    path: str | Path | None = None,
) -> dict[str, Any]:
    if status not in STATUSES:
        raise ValueError(f"status must be one of {sorted(STATUSES)}")
    payload = _load(path)
    for event in payload["events"]:
        if isinstance(event, dict) and event.get("event_id") == event_id:
            event["status"] = status
            event["review_status"] = status
            event["review_count"] = int(event.get("review_count") or 0) + 1
            event["last_reviewed_at"] = datetime.now(UTC).isoformat()
            if note:
                event["review_note"] = note
            if next_review_date:
                event["next_review_date"] = next_review_date
            _save(payload, path)
            return event
    raise KeyError(f"event not found: {event_id}")
