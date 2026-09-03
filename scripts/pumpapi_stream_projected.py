#!/usr/bin/env python3
"""Project selected mints from a JSONL stream before normalization."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
import re
import sys

from research.nave.pumpapi_replay import normalize_event


MINT_FIELD = re.compile(rb'"(?:mint|tokenMint|token_mint)"\s*:\s*"([^"]+)"')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selected-mints-json", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--metrics", required=True, type=Path)
    args = parser.parse_args()
    selected = {value.encode() for value in json.loads(args.selected_mints_json)}
    counters = Counter()
    retained_mints: set[str] = set()
    output = args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for line_number, line in enumerate(sys.stdin.buffer, 1):
            counters["input_lines"] += 1
            match = MINT_FIELD.search(line)
            if match is None or match.group(1) not in selected:
                counters["projected_out"] += 1
                continue
            counters["candidate_lines"] += 1
            try:
                raw = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError):
                counters["malformed_candidate_lines"] += 1
                continue
            if not isinstance(raw, dict):
                counters["malformed_candidate_lines"] += 1
                continue
            event = normalize_event(raw)
            counters["retained_lines"] += 1
            retained_mints.add(str(event.get("mint")))
            counters[f"retained_event_type:{event.get('event_type') or 'UNKNOWN'}"] += 1
            handle.write(json.dumps(event, sort_keys=True) + "\n")
    summary = {
        "selected_mints": len(selected), "retained_mints": len(retained_mints),
        "metrics": dict(counters), "streaming": True,
        "mint_projection_before_json_decode": True, "source_raw_events_retained": False,
    }
    args.metrics.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
