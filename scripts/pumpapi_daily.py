#!/usr/bin/env python3
"""Resumable streaming PumpApi day acquisition for selected mints."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="UTC date YYYY-MM-DD")
    parser.add_argument("--selected-mints", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--start-hour", type=int, default=0)
    parser.add_argument("--end-hour", type=int, default=23)
    parser.add_argument("--skip-hour", action="append", type=int, default=[])
    parser.add_argument("--continue-on-failure", action="store_true")
    args = parser.parse_args()
    checkpoint = args.output_root / f"date={args.date}" / "checkpoint.json"
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    state = json.loads(checkpoint.read_text()) if checkpoint.exists() else {"date": args.date, "hours": {}}
    for hour in range(args.start_hour, args.end_hour + 1):
        if hour in args.skip_hour:
            continue
        hour_key = f"{hour:02d}"
        hour_dir = args.output_root / f"date={args.date}" / f"hour={hour_key}"
        output = hour_dir / "events.jsonl"
        metrics = hour_dir / "metrics.json"
        if state["hours"].get(hour_key, {}).get("status") == "COMPLETE" and output.exists() and metrics.exists():
            continue
        hour_dir.mkdir(parents=True, exist_ok=True)
        archive_url = f"https://replay.pumpapi.io/{args.date[:4]}/{args.date[5:7]}/{args.date[8:10]}/{hour_key}.jsonl.zst"
        state["hours"][hour_key] = {"status": "DOWNLOADED_AND_PARSING", "archive_url": archive_url}
        checkpoint.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
        command = (
            "set -o pipefail; "
            f"curl --fail --silent --show-error --location {archive_url} "
            f"| zstd -dc | {sys.executable} scripts/pumpapi_stream_hour.py "
            f"--selected-mints {args.selected_mints} --output {output} --metrics {metrics}"
        )
        result = subprocess.run(command, shell=True, executable="/bin/bash", check=False)
        if result.returncode != 0:
            state["hours"][hour_key] = {"status": "FAILED", "return_code": result.returncode}
            checkpoint.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
            if not args.continue_on_failure:
                raise SystemExit(result.returncode)
            print(json.dumps({"date": args.date, "hour": hour, "status": "FAILED", "return_code": result.returncode}), flush=True)
            continue
        state["hours"][hour_key] = {"status": "COMPLETE", "output": str(output), "metrics": str(metrics)}
        checkpoint.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
        print(json.dumps({"date": args.date, "hour": hour, "status": "COMPLETE"}), flush=True)


if __name__ == "__main__":
    main()
