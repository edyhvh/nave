#!/usr/bin/env python3
"""Inventory existing launch manifests locally; never acquire data or validate edge."""
from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path


def inspect_manifest(path: Path) -> dict:
    raw = path.read_bytes()
    data = json.loads(raw)
    acquired = None
    execution_id = str(data.get("execution_id", ""))
    if execution_id.startswith("inline:"):
        try:
            acquired = datetime.fromisoformat(execution_id[7:].replace("Z", "+00:00"))
            if acquired.tzinfo is None:
                acquired = None
        except ValueError:
            pass
    end = datetime.fromisoformat(data["date"]).replace(tzinfo=UTC) + timedelta(days=1)
    rows = data.get("rows", [])
    return {
        "date": data["date"], "manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "sample_size": data.get("sample_size"), "denominator": data.get("denominator"),
        "unique_sample_identities": len({row.get("mint") for row in rows if row.get("mint")}),
        "acquired_after_close": acquired >= end if acquired else None,
        "complete_population_proven": False,
        "reason": "Existing selected launch samples are feasibility input only; no source completeness proof, receiver tape or executable costed outcomes.",
    }


def preflight(root: Path, spec_path: Path) -> dict:
    spec_raw = spec_path.read_bytes()
    spec = json.loads(spec_raw)
    return {
        "experiment_id": spec["experiment_id"], "spec_sha256": hashlib.sha256(spec_raw).hexdigest(),
        "status": "NEXT_BOUNDED_EXPERIMENT", "edge_validated": False,
        "local_manifests": [inspect_manifest(p) for p in sorted(root.glob("*/launch_manifest.json"))],
        "unmet_gates": spec["required_gates"],
        "remote_calls": 0, "paid_credits": 0, "holdout_accessed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest-root", type=Path, required=True)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(preflight(args.manifest_root, args.spec), indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
