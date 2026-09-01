#!/usr/bin/env python3
"""Run a compact Dune/PumpApi overlap comparison on local artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from research.memecoin.pumpapi_agreement import compare_events


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dune-json", required=True, type=Path)
    parser.add_argument("--pumpapi-jsonl", required=True, type=Path)
    parser.add_argument("--prefix", default=None, help="Only retain Dune timestamps starting with this prefix")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    dune_rows = json.loads(args.dune_json.read_text())["result"]["rows"]
    if args.prefix:
        dune_rows = [row for row in dune_rows if row.get("event_time", "").startswith(args.prefix)]
    pump_rows = [json.loads(line) for line in args.pumpapi_jsonl.read_text().splitlines() if line.strip()]
    result = compare_events(dune_rows, pump_rows)
    result["dune_source"] = str(args.dune_json)
    result["pumpapi_source"] = str(args.pumpapi_jsonl)
    result["time_prefix"] = args.prefix
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
