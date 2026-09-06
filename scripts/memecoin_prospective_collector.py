#!/usr/bin/env python3
"""Start or inspect the frozen, research-only memecoin collector."""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import signal
import sys

from research.nave.prospective_collection import (
    HoldoutLocked,
    ProspectiveCollector,
    holdout_lock_path,
    load_contract,
    operational_status,
    require_holdout_unlock,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = REPO_ROOT / "research/nave/experiments/closed-day-participant-history-v1.json"
DEFAULT_DATA_ROOT = REPO_ROOT / "data/research/memecoin/prospective"


def _dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("timestamp must include a timezone")
    return parsed.astimezone(UTC)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start", help="start prospective validation + locked holdout collection")
    start.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    start.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    start.add_argument("--stream-uri", default="wss://stream.pumpapi.io/")
    start.add_argument("--stop-at", type=_dt)
    start.add_argument("--heartbeat-seconds", type=int, default=60)
    start.add_argument("--reconnect-max-seconds", type=int, default=60)

    dry = sub.add_parser("dry-run", help="bounded live-feed connectivity/schema dry run")
    dry.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    dry.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    dry.add_argument("--seconds", type=int, default=15)
    dry.add_argument("--stream-uri", default="wss://stream.pumpapi.io/")
    dry.add_argument("--heartbeat-seconds", type=int, default=5)

    status = sub.add_parser("status", help="operational status only; no strategy metrics")
    status.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)

    guard = sub.add_parser("analysis-guard", help="fail closed unless a split is formally consumable")
    guard.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    guard.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    guard.add_argument("--split", choices=("validation", "holdout"), required=True)
    guard.add_argument("--date", help="validation UTC date to consume")
    return parser


def _validation_guard(data_root: Path, contract: dict, split_date: str | None) -> dict:
    days = list(contract["validation_days"])
    if split_date is not None and split_date not in days:
        raise RuntimeError("requested date is not a frozen validation date")
    target_days = [split_date] if split_date else days
    checkpoints = []
    for day in target_days:
        path = data_root / "validation" / f"date={day}" / "checkpoint.json"
        if not path.exists():
            raise RuntimeError(f"VALIDATION_ANALYSIS_LOCKED: missing checkpoint for {day}")
        payload = json.loads(path.read_text())
        if payload.get("status") != "COMPLETE_CLOSED_DAY":
            raise RuntimeError(
                f"VALIDATION_ANALYSIS_LOCKED: {day} is {payload.get('status')}, not COMPLETE_CLOSED_DAY"
            )
        checkpoints.append(path)
    return {"allowed": True, "split": "validation", "dates": target_days, "checkpoints": [str(p) for p in checkpoints]}


def main() -> int:
    args = _build_parser().parse_args()
    if args.command == "status":
        print(json.dumps(operational_status(args.data_root), indent=2, sort_keys=True))
        return 0

    contract, contract_sha256 = load_contract(args.contract)
    if args.command == "analysis-guard":
        try:
            if args.split == "holdout":
                unlock = require_holdout_unlock(args.data_root, contract_sha256)
                result = {"allowed": True, "split": "holdout", "unlock_artifact": str(args.data_root / "holdout-unlock.json"), "unlock": unlock}
            else:
                result = _validation_guard(args.data_root, contract, args.date)
        except (HoldoutLocked, RuntimeError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    if args.command == "dry-run":
        if not 1 <= args.seconds <= 300:
            raise SystemExit("dry-run seconds must be between 1 and 300")
        run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        run_root = args.data_root / "dry-run" / f"run={run_id}"
        collector = ProspectiveCollector(
            repo_root=REPO_ROOT,
            data_root=run_root,
            contract_path=args.contract,
            stream_uri=args.stream_uri,
            mode="DRY_RUN_ONLY",
            heartbeat_seconds=args.heartbeat_seconds,
        )
        stop_at = datetime.now(UTC) + timedelta(seconds=args.seconds)
    else:
        first_day = datetime.fromisoformat(contract["validation_days"][0]).replace(tzinfo=UTC)
        now = datetime.now(UTC)
        if now >= first_day:
            raise SystemExit(
                "WINDOW_INVALID_REFREEZE_REQUIRED: validation collection did not start before the first frozen UTC day"
            )
        stop_at = args.stop_at or datetime.fromisoformat(contract["untouched_holdout_days"][-1]).replace(tzinfo=UTC) + timedelta(days=1)
        collector = ProspectiveCollector(
            repo_root=REPO_ROOT,
            data_root=args.data_root,
            contract_path=args.contract,
            stream_uri=args.stream_uri,
            mode="PROSPECTIVE",
            heartbeat_seconds=args.heartbeat_seconds,
        )

    signal.signal(signal.SIGTERM, collector.request_stop)
    signal.signal(signal.SIGINT, collector.request_stop)
    print(json.dumps({
        "status": "STARTING",
        "mode": collector.mode,
        "contract_sha256": collector.contract_sha256,
        "data_root": str(collector.data_root),
        "stop_at": stop_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "holdout_lock": str(holdout_lock_path(collector.data_root)) if collector.mode == "PROSPECTIVE" else "DRY_RUN_ONLY",
    }, sort_keys=True), flush=True)
    return asyncio.run(collector.run(stop_at=stop_at, reconnect_max_seconds=args.reconnect_max_seconds if args.command == "start" else 10))


if __name__ == "__main__":
    raise SystemExit(main())
