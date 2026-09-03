#!/usr/bin/env python3
"""Acquire a selected PumpApi day with resumable, bounded hour parallelism.

The archive is streamed HTTP -> zstd -> JSONL.  A byte-level mint projection
rejects unrelated records before JSON decoding/normalization.  Only selected
normalized rows are retained; no decompressed archive is materialized.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time


MINT_FIELD = re.compile(rb'"(?:mint|tokenMint|token_mint)"\s*:\s*"([^"]+)"')
UTC = timezone.utc


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def _selected_mints(manifest: Path, prior_events: Path | None) -> set[str]:
    payload = json.loads(manifest.read_text())
    mints = {str(row["mint"]) for row in payload.get("rows", [])}
    if prior_events is not None:
        try:
            import pyarrow.parquet as pq
        except ImportError as exc:  # pragma: no cover - environment guard
            raise SystemExit("pyarrow is required to include prior migrants") from exc
        table = pq.read_table(prior_events, columns=["mint", "event_type"])
        for mint, event_type in zip(table.column("mint").to_pylist(), table.column("event_type").to_pylist()):
            if event_type == "MIGRATE" and mint:
                mints.add(str(mint))
    return mints


def _run_hour(date: str, hour: int, selected: set[str], day_dir: Path) -> dict:
    hour_key = f"{hour:02d}"
    hour_dir = day_dir / f"hour={hour_key}"
    output = hour_dir / "events.jsonl"
    metrics = hour_dir / "metrics.json"
    hour_dir.mkdir(parents=True, exist_ok=True)
    url = f"https://replay.pumpapi.io/{date[:4]}/{date[5:7]}/{date[8:10]}/{hour_key}.jsonl.zst"
    started = time.monotonic()
    worker = [
        sys.executable, str(Path(__file__).with_name("pumpapi_stream_projected.py")),
        "--selected-mints-json", json.dumps(sorted(selected)),
        "--output", str(output), "--metrics", str(metrics),
    ]
    curl = subprocess.Popen(
        ["curl", "--fail", "--silent", "--show-error", "--location", "--retry", "2", "--retry-all-errors", "--retry-delay", "2",
         "--write-out", "%{stderr}\n__COMPRESSED_BYTES__%{size_download}\n", url],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert curl.stdout is not None
    zstd = subprocess.Popen(["zstd", "-dc"], stdin=curl.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    curl.stdout.close()
    assert zstd.stdout is not None
    worker_env = os.environ.copy()
    worker_env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1]) + os.pathsep + worker_env.get("PYTHONPATH", "")
    consumer = subprocess.Popen(worker, stdin=zstd.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=worker_env)
    zstd.stdout.close()
    consumer_out, consumer_err = consumer.communicate()
    zstd_err = zstd.stderr.read().decode(errors="replace") if zstd.stderr else ""
    zstd_code = zstd.wait()
    curl_err = curl.stderr.read().decode(errors="replace") if curl.stderr else ""
    curl_code = curl.wait()
    elapsed = time.monotonic() - started
    compressed_bytes = None
    match = re.search(r"__COMPRESSED_BYTES__(\d+)", curl_err)
    if match:
        compressed_bytes = int(match.group(1))
    consumer_summary = None
    if consumer_out.strip():
        try:
            consumer_summary = json.loads(consumer_out.strip().splitlines()[-1])
        except json.JSONDecodeError:
            consumer_summary = None
    retained_lines = ((consumer_summary or {}).get("metrics") or {}).get("retained_lines", 0)
    if consumer.returncode == 0 and curl_code == 0 and zstd_code == 0:
        status = "COMPLETE"
    elif consumer.returncode == 0 and curl_code == 0 and retained_lines:
        status = "COMPLETE_WITH_WARNINGS"
    else:
        status = "FAILED"
    result = {
        "date": date, "hour": hour_key, "archive_url": url, "status": status,
        "consumer_returncode": consumer.returncode, "zstd_returncode": zstd_code,
        "curl_returncode": curl_code, "compressed_bytes": compressed_bytes,
        "elapsed_seconds": round(elapsed, 3), "output_bytes": output.stat().st_size if output.exists() else 0,
        "metrics": str(metrics), "output": str(output),
    }
    if consumer_summary is not None:
        result["consumer_summary"] = consumer_summary
    elif consumer_out.strip():
        result["consumer_stdout"] = consumer_out[-1000:]
    if status != "COMPLETE":
        result["stderr_tail"] = (curl_err + zstd_err + consumer_err)[-2000:]
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--selected-manifest", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--prior-events", type=Path)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--start-hour", type=int, default=0)
    parser.add_argument("--end-hour", type=int, default=23)
    args = parser.parse_args()
    if not 1 <= args.workers <= 4:
        raise SystemExit("workers must be between 1 and 4")
    if not 0 <= args.start_hour <= args.end_hour <= 23:
        raise SystemExit("hour range must be within 00..23")
    selected = _selected_mints(args.selected_manifest, args.prior_events)
    day_dir = args.output_root / f"date={args.date}"
    checkpoint_path = day_dir / "checkpoint.json"
    checkpoint = json.loads(checkpoint_path.read_text()) if checkpoint_path.exists() else {
        "schema_version": "nave.pumpapi.day-checkpoint.v2", "date": args.date, "hours": {},
        "selected_mints": len(selected), "parallel_workers": args.workers,
    }
    checkpoint["selected_mints"] = len(selected)
    checkpoint["parallel_workers"] = args.workers
    _write_json(checkpoint_path, checkpoint)

    pending = []
    for hour in range(args.start_hour, args.end_hour + 1):
        key = f"{hour:02d}"
        entry = checkpoint.get("hours", {}).get(key, {})
        if entry.get("status") in {"COMPLETE", "COMPLETE_WITH_WARNINGS"} and Path(entry.get("output", "")).exists() and Path(entry.get("metrics", "")).exists():
            continue
        checkpoint["hours"][key] = {"status": "RUNNING", "updated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z")}
        pending.append(hour)
    _write_json(checkpoint_path, checkpoint)
    if not pending:
        print(json.dumps({"date": args.date, "status": "COMPLETE", "hours": "already complete"}))
        return 0

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(_run_hour, args.date, hour, selected, day_dir): hour for hour in pending}
        for future in as_completed(futures):
            hour = futures[future]
            try:
                result = future.result()
            except Exception as exc:  # persist failure and continue other hours
                result = {"date": args.date, "hour": f"{hour:02d}", "status": "FAILED", "error": repr(exc)}
            checkpoint["hours"][f"{hour:02d}"] = result
            _write_json(checkpoint_path, checkpoint)
            print(json.dumps(result, sort_keys=True), flush=True)
    statuses = [checkpoint.get("hours", {}).get(f"{hour:02d}", {}).get("status") for hour in range(24)]
    checkpoint["status"] = "COMPLETE" if all(status == "COMPLETE" for status in statuses) else "PARTIAL"
    checkpoint["updated_at"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    _write_json(checkpoint_path, checkpoint)
    return 0 if checkpoint["status"] == "COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
