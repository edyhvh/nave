#!/usr/bin/env python3
"""Stream one decompressed PumpApi hour and retain selected normalized events."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
import sys

from research.memecoin.pumpapi_replay import normalize_event


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selected-mints", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--metrics", required=True)
    args = parser.parse_args()
    payload = json.loads(Path(args.selected_mints).read_text())
    selected = {str(row["mint"]) for row in payload.get("rows", [])}
    metrics = Counter()
    schema_examples: dict[str, dict] = {}
    retained_mints: set[str] = set()
    retained_wallets: set[str] = set()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for line_number, line in enumerate(sys.stdin.buffer, 1):
            metrics["input_lines"] += 1
            try:
                raw = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError):
                metrics["malformed_lines"] += 1
                continue
            if not isinstance(raw, dict):
                metrics["malformed_lines"] += 1
                continue
            metrics["normalized_lines"] += 1
            raw_mint = raw.get("mint") or raw.get("tokenMint") or raw.get("token_mint")
            if raw_mint not in selected:
                continue
            event = normalize_event(raw)
            event_type = str(event.get("event_type") or "UNKNOWN")
            metrics[f"all_event_type:{event_type}"] += 1
            metrics["retained_lines"] += 1
            metrics[f"retained_event_type:{event_type}"] += 1
            retained_mints.add(str(event["mint"]))
            if event.get("wallet"):
                retained_wallets.add(str(event["wallet"]))
            schema_examples.setdefault(event_type, event)
            handle.write(json.dumps(event, sort_keys=True) + "\n")
    summary = {"selected_mints": len(selected), "retained_mints": len(retained_mints), "retained_wallets": len(retained_wallets), "metrics": dict(metrics), "schema_examples": schema_examples, "streaming": True, "source_raw_events_retained": False}
    Path(args.metrics).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
