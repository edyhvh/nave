#!/usr/bin/env python3
"""Materialize a fully verified hourly replay into one compact Parquet file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


FIELDS = [
    "provider", "venue", "event_type", "mint", "event_time", "event_time_ms",
    "provider_received_at", "provider_received_at_ms", "available_at", "slot",
    "tx_signature", "transaction_index", "instruction_index", "wallet", "is_buy",
    "side", "token_amount", "quote_amount", "quote_mint", "price",
    "virtual_token_reserves", "virtual_quote_reserves", "real_token_reserves",
    "real_quote_reserves", "pool_id", "creator", "raw_schema",
    "protocol_state_json", "quality_flags_json",
]


def row(event: dict) -> dict:
    output = {field: event.get(field) for field in FIELDS}
    output["protocol_state_json"] = json.dumps(event.get("protocol_state"), sort_keys=True)
    output["quality_flags_json"] = json.dumps(event.get("quality_flags") or [])
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--day-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--batch-size", type=int, default=20_000)
    args = parser.parse_args()

    checkpoint = json.loads((args.day_dir / "checkpoint.json").read_text())
    hours = checkpoint.get("hours", {})
    incomplete = [
        f"{hour:02d}" for hour in range(24)
        if hours.get(f"{hour:02d}", {}).get("status")
        not in {"COMPLETE", "COMPLETE_WITH_WARNINGS"}
    ]
    if incomplete:
        raise SystemExit(
            "refusing to materialize a day with incomplete hours: "
            + ",".join(incomplete)
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    writer = None
    batch: list[dict] = []
    rows = 0
    mints: set[str] = set()
    try:
        for hour in range(24):
            path = args.day_dir / f"hour={hour:02d}" / "events.jsonl"
            for line in path.open(encoding="utf-8"):
                if not line.strip():
                    continue
                event = json.loads(line)
                batch.append(row(event))
                if event.get("mint"):
                    mints.add(str(event["mint"]))
                if len(batch) >= args.batch_size:
                    table = pa.Table.from_pylist(batch)
                    if writer is None:
                        writer = pq.ParquetWriter(args.output, table.schema, compression="zstd")
                    writer.write_table(table)
                    rows += len(batch)
                    batch.clear()
        if batch:
            table = pa.Table.from_pylist(batch)
            if writer is None:
                writer = pq.ParquetWriter(args.output, table.schema, compression="zstd")
            writer.write_table(table)
            rows += len(batch)
    finally:
        if writer is not None:
            writer.close()
    print(json.dumps({
        "rows": rows,
        "unique_mints": len(mints),
        "output": str(args.output),
        "schema_version": "nave-pumpapi-canonical-event-v2",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
