#!/usr/bin/env python3
"""Build a compact manifest for canonical local research artifacts."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def entry(name: str, provider: str, path: Path, *, start: str, end: str, rows: int | None, mints: int | None, wallets: int | None, completeness: str, gaps: list[str]) -> dict:
    return {
        "dataset_name": name,
        "provider": provider,
        "schema_version": "pumpapi-canonical-event-v1" if provider == "pumpapi" else "existing-nave-artifact",
        "date_start": start,
        "date_end": end,
        "rows": rows,
        "unique_mints": mints,
        "unique_wallets": wallets,
        "compressed_bytes": path.stat().st_size,
        "sha256": sha256(path),
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_completeness": completeness,
        "known_gaps": gaps,
        "path": str(path),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pumpapi-parquet", type=Path)
    parser.add_argument("--pumpapi-day", type=Path)
    parser.add_argument("--day1-events", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    records = []
    if args.pumpapi_parquet and args.pumpapi_parquet.exists():
        import pyarrow.parquet as pq

        table = pq.read_table(args.pumpapi_parquet, columns=["mint", "wallet"])
        records.append(entry("pumpapi_day2_selected_events", "pumpapi", args.pumpapi_parquet, start="2026-08-28", end="2026-08-28", rows=table.num_rows, mints=len(set(table.column("mint").to_pylist())), wallets=len(set(x for x in table.column("wallet").to_pylist() if x)), completeness="PARTIAL_IF_FAILED_HOURS", gaps=[]))
    if args.day1_events and args.day1_events.exists():
        import pyarrow.parquet as pq

        table = pq.read_table(args.day1_events, columns=["mint", "wallet"])
        records.append(entry("dune_day1_pumpfun_first_hour_events", "dune", args.day1_events, start="2026-08-27", end="2026-08-27", rows=table.num_rows, mints=len(set(table.column("mint").to_pylist())), wallets=len(set(x for x in table.column("wallet").to_pylist() if x)), completeness="COMPLETE_FOR_RETAINED_FIRST_HOUR_ARTIFACT", gaps=[]))
    if args.pumpapi_day and args.pumpapi_day.exists():
        failed = []
        for path in sorted(args.pumpapi_day.glob("hour=*/metrics.json")):
            hour = path.parent.name.split("=", 1)[1]
            checkpoint = args.pumpapi_day / "checkpoint.json"
            if checkpoint.exists() and json.loads(checkpoint.read_text())["hours"].get(hour, {}).get("status") == "FAILED":
                failed.append(hour)
        records.append({"dataset_name": "pumpapi_day2_hourly_replay", "provider": "pumpapi", "schema_version": "pumpapi-canonical-event-v1", "date_start": "2026-08-28", "date_end": "2026-08-28", "rows": None, "unique_mints": None, "unique_wallets": None, "compressed_bytes": None, "sha256": None, "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "source_completeness": "PARTIAL", "known_gaps": [f"FAILED_HOUR_{hour}" for hour in failed], "path": str(args.pumpapi_day)})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"schema_version": "m3-multiday-data-manifest-v1", "datasets": records}, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
