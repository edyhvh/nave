#!/usr/bin/env python3
"""Verify a frozen cached cohort without acquisition or treating an intraday sample as a full day."""
from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pandas as pd

from scripts.nave_stage1_audit import build_rows, model_comparison


def verify(day_dir: Path) -> dict:
    checkpoint = json.loads((day_dir / "checkpoint.json").read_text())
    manifest_path = day_dir / "launch_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    rows = manifest["rows"]
    if len(rows) != manifest["sample_size"] or len({row["mint"] for row in rows}) != len(rows):
        raise ValueError("frozen sample count/identity mismatch")
    if manifest["selection"].get("frozen_before_event_replay") is not True:
        raise ValueError("sample was not frozen")
    hours = []
    for hour in range(24):
        key = f"{hour:02d}"
        entry = checkpoint["hours"][key]
        if entry.get("status") != "COMPLETE" or any(entry.get(name) != 0 for name in ("curl_returncode", "zstd_returncode", "consumer_returncode")):
            raise ValueError(f"incomplete or unverified hour: {key}")
        path = day_dir / f"hour={key}" / "events.jsonl"
        metrics = json.loads((path.parent / "metrics.json").read_text())["metrics"]
        if metrics.get("malformed_candidate_lines", 0):
            raise ValueError(f"malformed selected events: {key}")
        digest, count = hashlib.sha256(), 0
        with path.open("rb") as handle:
            for line in handle:
                digest.update(line)
                count += 1
        if count != metrics["retained_lines"] or path.stat().st_size != entry["output_bytes"]:
            raise ValueError(f"cached output count/size mismatch: {key}")
        hours.append({"hour": key, "rows": count, "sha256": digest.hexdigest()})
    acquired = datetime.fromisoformat(manifest["execution_id"].removeprefix("inline:").replace("Z", "+00:00"))
    day_end = datetime.fromisoformat(manifest["date"]).replace(tzinfo=UTC) + timedelta(days=1)
    return {
        "date": manifest["date"], "hours": hours, "complete_hours": len(hours),
        "sample_size": len(rows), "denominator_at_acquisition": manifest["denominator"],
        "sample_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "selection": manifest["selection"], "acquired_at": acquired.isoformat(),
        "latest_sample_launch": max(row["launch_ts"] for row in rows),
        "full_calendar_day_sample": acquired >= day_end,
        "sample_warning": "Acquisition timestamp is a necessary, not sufficient, check of full-day source coverage.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--day-dir", required=True, type=Path)
    parser.add_argument("--train-events", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    audit = verify(args.day_dir)
    events = args.day_dir / "pumpapi_events_verified_20260906.parquet"
    if not events.exists():
        subprocess.run([sys.executable, str(Path(__file__).with_name("materialize_pumpapi_day.py")),
                        "--day-dir", str(args.day_dir), "--output", str(events)], check=True)
    train, _ = build_rows("2026-08-28", args.train_events, None)
    frame, coverage = build_rows(audit["date"], events, args.day_dir / "launch_manifest.json")
    output = {"schema_version": "nave.cached-stage1-verification.v1", "verified_at": datetime.now(UTC).isoformat(),
              "acquisition": audit, "coverage": coverage,
              "model_comparison": model_comparison(pd.concat([train, frame], ignore_index=True), evaluation_day=audit["date"]),
              "classification": "DESCRIPTIVE_FROZEN_INTRADAY_COHORT" if not audit["full_calendar_day_sample"] else "PRELIMINARY_TEMPORAL_SANITY",
              "edge_validated": False, "dune_queries": 0, "additional_provider_downloads": 0,
              "limitations": ["Activity survival is not tradable profit.", "No participant-excluded model or execution-cost evaluation.",
                              "Legacy Stage-1 features use event time, not a receiver-latency replay; online availability is unproven.",
                              "Do not admit an intraday launch sample as a comparable full-day sample.",
                              "PONS social case study is not linked to this Solana launch cohort."]}
    output["model_comparison"]["status"] = output["classification"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"output": str(args.output), "classification": output["classification"]}))


if __name__ == "__main__":
    main()
