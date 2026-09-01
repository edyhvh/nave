#!/usr/bin/env python3
"""Write a compact, auditable committed manifest from a day checkpoint."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--day-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    checkpoint = json.loads((args.day_dir / "checkpoint.json").read_text())
    date = checkpoint["date"]
    entries = []
    for hour in range(24):
        key = f"{hour:02d}"
        entry = checkpoint["hours"][key]
        event_path = args.day_dir / f"hour={key}" / "events.jsonl"
        metrics_path = args.day_dir / f"hour={key}" / "metrics.json"
        metrics = json.loads(metrics_path.read_text())
        counters = metrics["metrics"]
        entries.append({
            "date": date, "hour": key,
            "archive_url": entry["archive_url"],
            "remote_status": "HTTP_200" if entry.get("curl_returncode") == 0 else "HTTP_OR_TRANSPORT_FAILURE",
            "integrity": "ZSTD_PASS" if entry.get("zstd_returncode") == 0 else "ZSTD_WARNING_OR_FAILURE",
            "parser_status": "PARSED" if entry.get("consumer_returncode") == 0 else "PARSE_FAILED",
            "rows_parsed": counters.get("input_lines", 0),
            "rows_retained": counters.get("retained_lines", 0),
            "sample_mints_observed": metrics.get("retained_mints", 0),
            "checksum": hashlib.sha256(event_path.read_bytes()).hexdigest(),
            "schema_version": "nave-pumpapi-canonical-event-v2",
            "quality_status": entry["status"],
            "compressed_bytes": entry.get("compressed_bytes"),
            "elapsed_seconds": entry.get("elapsed_seconds"),
        })
    output = {
        "schema_version": "nave.pumpapi.hour-manifest.v2",
        "canonical_data_root": "/home/david/nave/data",
        "date": date,
        "selection_manifest": str(args.day_dir / "launch_manifest.json"),
        "filter_union": {"general_sample_mints": 1000, "prior_day_migrant_mints": 30, "union_mints": checkpoint.get("selected_mints", 1030)},
        "combined_filtered_parquet": str(args.day_dir / "pumpapi_events_recovered_full.parquet"),
        "combined_sha256": hashlib.sha256((args.day_dir / "pumpapi_events_recovered_full.parquet").read_bytes()).hexdigest(),
        "entries": entries,
        "raw_decompressed_archives_retained": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(args.output), "hours": len(entries), "combined_sha256": output["combined_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
