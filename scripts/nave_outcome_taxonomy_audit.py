#!/usr/bin/env python3
"""Audit short-horizon unresolved outcomes without provider calls.

This is deliberately a local, deterministic analysis.  It uses the frozen
launch sample, a normalized event Parquet, and a collection boundary.  It
does not inspect returns when defining the taxonomy or the mark tolerance.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from research.nave.outcome_taxonomy import OutcomeEvidence, classify_outcome


UTC = timezone.utc
TRADE_TYPES = {"BUY", "SELL"}


def _ms(value: str) -> int:
    return int(datetime.fromisoformat(value.replace(" UTC", "+00:00")).timestamp() * 1000)


def _valid_price(value: Any) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(value) and value > 0


def _load_rows(path: Path, *keys: str) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text())
    for key in keys:
        if isinstance(payload, dict) and key in payload:
            payload = payload[key]
    if not isinstance(payload, list):
        raise ValueError(f"expected a list at {path}")
    return payload


def audit(launch_path: Path, selected_path: Path, events_path: Path, collection_end: str) -> dict[str, Any]:
    launches = _load_rows(launch_path, "result", "rows")
    selected = _load_rows(selected_path, "rows")
    selected_mints = {str(row["mint"]) for row in selected}
    launch_by = {str(row["mint"]): row for row in launches if str(row["mint"]) in selected_mints}
    events_by_mint: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in pq.read_table(events_path).to_pylist():
        mint = str(event.get("mint") or "")
        if mint in selected_mints and event.get("event_time_ms") is not None:
            events_by_mint[mint].append(event)
    for events in events_by_mint.values():
        events.sort(key=lambda row: int(row["event_time_ms"]))

    boundary = _ms(collection_end)
    per_horizon: dict[str, Any] = {}
    for horizon_minutes in (15, 30, 60):
        counts: Counter[str] = Counter()
        activity: Counter[str] = Counter()
        nearest_five_minute = 0
        observations: list[dict[str, Any]] = []
        horizon_ms = horizon_minutes * 60 * 1000
        for mint, launch in launch_by.items():
            launch_ms = _ms(str(launch["launch_ts"]))
            target_ms = launch_ms + horizon_ms
            events = events_by_mint.get(mint, [])
            trades = [row for row in events if row.get("event_type") in TRADE_TYPES]
            if target_ms > boundary:
                evidence = OutcomeEvidence(interval_complete=True, target_right_censored=True)
                activity["RIGHT_CENSORED"] += 1
            else:
                post = [
                    row for row in trades
                    if target_ms <= int(row["event_time_ms"]) <= boundary
                ]
                prior_to_target = [
                    row for row in trades
                    if launch_ms < int(row["event_time_ms"]) <= target_ms
                ]
                valid = [row for row in post if _valid_price(row.get("price"))]
                migration = any(
                    row.get("event_type") == "MIGRATE"
                    and launch_ms < int(row["event_time_ms"]) <= target_ms
                    for row in events
                )
                near = [
                    row for row in trades
                    if abs(int(row["event_time_ms"]) - target_ms) <= 5 * 60 * 1000
                    and _valid_price(row.get("price"))
                ]
                nearest_five_minute += bool(near)
                evidence = OutcomeEvidence(
                    interval_complete=True,
                    target_right_censored=False,
                    valid_mark_count=len(valid),
                    future_trade_count=len(post),
                    no_activity_through_horizon=not prior_to_target,
                    migration_before_horizon=migration,
                )
                activity["HAS_TRADE_THROUGH_HORIZON"] += bool(prior_to_target)
                activity["NO_ACTIVITY_THROUGH_HORIZON"] += not prior_to_target
                activity["FUTURE_TRADE_AFTER_HORIZON"] += bool(post)
            status, reason = classify_outcome(evidence)
            counts[status.value if reason is None else reason] += 1
            observations.append({
                "mint": mint,
                "horizon_minutes": horizon_minutes,
                "status": status.value,
                "reason": reason,
                "decision_time": datetime.fromtimestamp((launch_ms + 0) / 1000, tz=UTC).isoformat(),
            })
        per_horizon[f"{horizon_minutes}m"] = {
            "counts": dict(counts),
            "activity": dict(activity),
            "nearest_valid_mark_within_5m": nearest_five_minute,
            "observations": observations,
        }
    return {
        "selected_mints": len(selected_mints),
        "launch_rows_found": len(launch_by),
        "event_mints_found": len(events_by_mint),
        "collection_end": collection_end,
        "horizons": per_horizon,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--launches", type=Path, required=True)
    parser.add_argument("--selected", type=Path, required=True)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--collection-end", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = audit(args.launches, args.selected, args.events, args.collection_end)
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered)
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
