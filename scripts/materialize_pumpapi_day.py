#!/usr/bin/env python3
"""Materialize completed hourly normalized replay rows into compact Parquet."""

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
]


def row(event: dict) -> dict:
    output = {field: event.get(field) for field in FIELDS}
    output["protocol_state_json"] = json.dumps(event.get("protocol_state"), sort_keys=True)
    output["quality_flags_json"] = json.dumps(event.get("quality_flags") or [])
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--day-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--batch-size", type=int, default=10_000)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_path = args.day_dir / "checkpoint.json"
    checkpoint = json.loads(checkpoint_path.read_text()) if checkpoint_path.exists() else {"hours": {}}
    writer = None
    batch: list[dict] = []
    total = 0
    try:
        for path in sorted(args.day_dir.glob("hour=*/events.jsonl")):
            hour = path.parent.name.split("=", 1)[1]
            if checkpoint.get("hours", {}).get(hour, {}).get("status") != "COMPLETE":
                continue
            for line in path.open(encoding="utf-8"):
                if not line.strip():
                    continue
                batch.append(row(json.loads(line)))
                if len(batch) >= args.batch_size:
                    table = pa.Table.from_pylist(batch)
                    if writer is None:
                        writer = pq.ParquetWriter(args.output, table.schema, compression="zstd")
                    writer.write_table(table)
                    total += len(batch)
                    batch.clear()
        if batch:
            table = pa.Table.from_pylist(batch)
            if writer is None:
                writer = pq.ParquetWriter(args.output, table.schema, compression="zstd")
            writer.write_table(table)
            total += len(batch)
    finally:
        if writer is not None:
            writer.close()
    print(json.dumps({"rows": total, "output": str(args.output), "schema_version": "pumpapi-canonical-event-v1"}))


if __name__ == "__main__":
    main()
