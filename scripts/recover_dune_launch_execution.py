#!/usr/bin/env python3
"""Recover one completed Dune launch execution into the shared NAVE manifest.

This is intentionally a local recovery helper: it never submits a query.  The
execution id must refer to an already-paid completed result.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execution-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed", required=True)
    args = parser.parse_args()

    command = [
        "dune", "execution", "results", args.execution_id,
        "--limit", "1000", "--offset", "0", "-o", "json",
    ]
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        return result.returncode
    payload = json.loads(result.stdout)
    rows = payload.get("result", {}).get("rows", [])
    if len(rows) != 1000:
        raise SystemExit(f"expected 1000 recovered rows, got {len(rows)}")
    denominator_values = {row.get("denominator") for row in rows}
    if len(denominator_values) != 1:
        raise SystemExit(f"inconsistent denominator values: {denominator_values}")
    denominator = next(iter(denominator_values))

    selected = []
    for row in rows:
        mint = str(row["mint"])
        selection_hash = hashlib.sha256(f"{args.seed}:{mint}".encode()).hexdigest()
        selected.append({
            **row,
            "selection_hash": selection_hash,
            "selected_for_general_sample": True,
        })
    selected.sort(key=lambda row: (row["selection_hash"], row["mint"]))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": "nave.daily-launch-manifest.v1",
        "date": "2026-08-29",
        "canonical_data_root": "/home/david/nave/data",
        "source": "dune.completed_execution_recovery",
        "execution_id": args.execution_id,
        "denominator": denominator,
        "sample_size": len(selected),
        "selection": {
            "seed": args.seed,
            "method": "sha256(seed || ':' || mint), ascending; outcome-independent",
            "frozen_before_event_replay": True,
        },
        "rows": selected,
        "retrieval_metadata": payload.get("result", {}).get("metadata", {}),
    }
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "output": str(args.output),
        "execution_id": args.execution_id,
        "denominator": denominator,
        "sample_size": len(selected),
        "result_set_bytes": payload.get("result", {}).get("metadata", {}).get("result_set_bytes"),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
