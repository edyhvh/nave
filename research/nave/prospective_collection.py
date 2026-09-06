"""Prospective, research-only collection for the frozen memecoin experiment.

This module deliberately contains collection and operational locking only.  It
does not score launches, resolve returns, inspect holdout outcomes, call a
trading endpoint, or modify the production scanner.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, date, datetime, timedelta
import heapq
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import time
from typing import Any, Callable, Iterable

from research.nave.pumpapi_replay import normalize_event


CHAIN_ID = "solana:mainnet"
DEFAULT_STREAM_URI = "wss://stream.pumpapi.io/"
DEFAULT_MAX_EVENT_BYTES = 8 * 1024 * 1024
TRACKED_ACTIONS = {
    "transfer",
    "create",
    "createpool",
    "create_pool",
    "buy",
    "sell",
    "migrate",
    "add",
    "remove",
    "claimcreatorfees",
    "claimcashback",
}
TARGET_HORIZONS = {
    "30s": timedelta(seconds=30),
    "60m": timedelta(minutes=60),
}


def iso(dt: datetime) -> str:
    """Serialize a timezone-aware UTC timestamp without fractional noise."""
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse_provider_timestamp(value: Any) -> datetime | None:
    """Parse a provider epoch timestamp without substituting a local clock."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not number == number or number in {float("inf"), float("-inf")}:
        return None
    if number < 10_000_000_000:
        number *= 1000
    try:
        return datetime.fromtimestamp(number / 1000, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def provider_event_key(raw: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(raw).encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git_commit(repo_root: Path) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    value = completed.stdout.strip()
    return value or None


def load_contract(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("experiment contract must be a JSON object")
    return payload, hashlib.sha256(raw).hexdigest()


def ensure_dates_unchanged(contract: dict[str, Any], validation: list[str], holdout: list[str]) -> None:
    if validation != list(contract["validation_days"]):
        raise ValueError("validation dates differ from frozen contract")
    if holdout != list(contract["untouched_holdout_days"]):
        raise ValueError("holdout dates differ from frozen contract")


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def _safe_date(value: str | date) -> date:
    return value if isinstance(value, date) else date.fromisoformat(value)


def partition_for_event(
    event_time: datetime | None,
    received_at: datetime,
    validation_days: Iterable[str],
    holdout_days: Iterable[str],
) -> tuple[str, str]:
    """Classify by provider event day; invalid provider time is quarantined."""
    if event_time is None:
        return "quarantine", received_at.date().isoformat()
    event_day = event_time.date().isoformat()
    if event_day in set(validation_days):
        return "validation", event_day
    if event_day in set(holdout_days):
        return "holdout", event_day
    return "warmup", event_day


def _participant_rows(raw: dict[str, Any]) -> list[dict[str, Any]]:
    action = str(raw.get("action") or raw.get("txType") or "").strip().lower()
    if action not in {"buy", "sell"}:
        return []
    breakdown = raw.get("breakdown")
    if isinstance(breakdown, list):
        rows = [
            row for row in breakdown
            if isinstance(row, dict) and row.get("trader") is not None
        ]
        if rows:
            return [
                {
                    "participant_id": str(row["trader"]),
                    "participant_source": "breakdown.trader",
                    "token_amount": row.get("tokenAmount"),
                    "quote_amount": row.get("quoteAmount"),
                }
                for row in rows
            ]
        if isinstance(breakdown, list) and breakdown:
            return [{"participant_id": None, "participant_source": "ambiguous_breakdown"}]
    involved = raw.get("tradersInvolved")
    if isinstance(involved, dict) and involved:
        return [
            {"participant_id": str(key), "participant_source": "tradersInvolved"}
            for key in involved
        ]
    return [{"participant_id": None, "participant_source": "missing_participant"}]


class HoldoutLocked(RuntimeError):
    """Raised when a command tries to analyze holdout data before unlock."""


def holdout_lock_path(data_root: Path) -> Path:
    return data_root / "holdout-lock.json"


def write_or_verify_holdout_lock(
    data_root: Path,
    *,
    contract_sha256: str,
    validation_days: list[str],
    holdout_days: list[str],
    created_at: datetime,
) -> Path:
    path = holdout_lock_path(data_root)
    existing = json.loads(path.read_text()) if path.exists() else None
    expected = {
        "schema_version": "nave.memecoin.holdout-lock.v1",
        "status": "HOLDOUT_LOCKED",
        "contract_sha256": contract_sha256,
        "validation_days": validation_days,
        "holdout_days": holdout_days,
        "created_at": iso(created_at),
        "unlock_artifact": None,
        "unlock_rule": "validation report hash + acceptance-gate decision + explicit unlock event required",
    }
    if existing is not None:
        for key in ("status", "contract_sha256", "validation_days", "holdout_days"):
            if existing.get(key) != expected[key]:
                raise ValueError(f"existing holdout lock mismatch: {key}")
        if existing.get("status") != "HOLDOUT_LOCKED":
            raise ValueError("holdout lock is not locked")
        return path
    _atomic_json(path, expected)
    return path


def require_holdout_unlock(data_root: Path, contract_sha256: str) -> dict[str, Any]:
    """Fail closed unless an explicit, contract-matched unlock artifact exists."""
    lock = holdout_lock_path(data_root)
    unlock = data_root / "holdout-unlock.json"
    if not lock.exists() or not unlock.exists():
        raise HoldoutLocked("HOLDOUT_LOCKED: no explicit unlock artifact")
    lock_payload = json.loads(lock.read_text())
    payload = json.loads(unlock.read_text())
    report_hash = str(payload.get("validation_report_sha256") or "")
    if (
        lock_payload.get("status") != "HOLDOUT_UNLOCKED"
        or payload.get("contract_sha256") != contract_sha256
        or len(report_hash) != 64
        or payload.get("acceptance_gate_decision") not in {"PERMIT_HOLDOUT", "INSUFFICIENT_DATA"}
        or payload.get("explicit_unlock_event") is not True
    ):
        raise HoldoutLocked("HOLDOUT_LOCKED: unlock artifact failed validation")
    return payload


class ProspectiveCollector:
    """One reconnecting PumpApi data stream with restart-safe local state."""

    def __init__(
        self,
        *,
        repo_root: Path,
        data_root: Path,
        contract_path: Path,
        stream_uri: str = DEFAULT_STREAM_URI,
        mode: str = "PROSPECTIVE",
        clock: Callable[[], datetime] | None = None,
        source_commit: str | None = None,
        max_event_bytes: int = DEFAULT_MAX_EVENT_BYTES,
        heartbeat_seconds: int = 60,
        receive_timeout_seconds: float = 60,
    ):
        self.repo_root = repo_root
        self.data_root = data_root
        self.contract_path = contract_path
        self.contract, self.contract_sha256 = load_contract(contract_path)
        self.validation_days = list(self.contract["validation_days"])
        self.holdout_days = list(self.contract["untouched_holdout_days"])
        ensure_dates_unchanged(self.contract, self.validation_days, self.holdout_days)
        self.stream_uri = stream_uri
        self.mode = mode
        self.clock = clock or (lambda: datetime.now(UTC))
        self.source_commit = source_commit or git_commit(repo_root)
        self.max_event_bytes = max_event_bytes
        self.heartbeat_seconds = heartbeat_seconds
        self.receive_timeout_seconds = receive_timeout_seconds
        self.started_at = self.clock().astimezone(UTC)
        self.stop_requested = False
        self.connection_number = 0
        self._handles: dict[Path, Any] = {}
        self._checkpoint_cache: dict[tuple[str, str], dict[str, Any]] = {}
        self._last_checkpoint_flush = time.monotonic()
        self._active_capture_hour: str | None = None
        self._last_heartbeat = 0.0
        self._counters: Counter[str] = Counter()
        self._outcome_jobs: dict[str, dict[str, Any]] = {}
        self._outcome_heap: list[tuple[float, int, str]] = []
        self._outcome_heap_sequence = 0
        self._pool_states: dict[str, dict[str, Any]] = {}
        self._batch_active = False
        self._new_output_dirs: set[Path] = set()
        self._db = self._open_db()
        self._manifest_path = self.data_root / "collector-manifest.json"
        self._initialize_state()

    def _open_db(self) -> sqlite3.Connection:
        self.data_root.mkdir(parents=True, exist_ok=True)
        # One serialized persistence worker owns this connection after startup.
        db = sqlite3.connect(self.data_root / "collector.sqlite3", check_same_thread=False)
        db.execute("PRAGMA journal_mode=WAL")
        # The live dedupe index outgrows SQLite's default ~2 MiB page cache.
        # Bound the writer cache at 512 MiB, with at most 2 GiB of demand-paged
        # mapped reads. This avoids repeated pread/index-page churn in the
        # growing dedupe database. FULL durability and schema are unchanged.
        db.execute("PRAGMA cache_size=-524288")
        db.execute("PRAGMA mmap_size=2147483648")
        db.execute(
            """CREATE TABLE IF NOT EXISTS events (
                event_key TEXT PRIMARY KEY,
                event_time TEXT,
                available_at TEXT NOT NULL,
                mint TEXT,
                pool_address TEXT,
                action TEXT,
                output_path TEXT NOT NULL
            )"""
        )
        db.execute(
            """CREATE TABLE IF NOT EXISTS launches (
                mint TEXT PRIMARY KEY,
                launch_time TEXT NOT NULL,
                decision_time TEXT NOT NULL,
                pool_address TEXT,
                output_path TEXT NOT NULL,
                source_event_key TEXT NOT NULL
            )"""
        )
        db.execute(
            """CREATE TABLE IF NOT EXISTS outcome_jobs (
                job_key TEXT PRIMARY KEY,
                mint TEXT NOT NULL,
                horizon TEXT NOT NULL,
                target_time TEXT NOT NULL,
                output_path TEXT NOT NULL
            )"""
        )
        db.execute(
            """CREATE TABLE IF NOT EXISTS outcome_snapshots (
                job_key TEXT PRIMARY KEY,
                output_path TEXT NOT NULL,
                record_json TEXT NOT NULL
            )"""
        )
        db.commit()
        return db

    def _initialize_state(self) -> None:
        if self.mode == "PROSPECTIVE":
            write_or_verify_holdout_lock(
                self.data_root,
                contract_sha256=self.contract_sha256,
                validation_days=self.validation_days,
                holdout_days=self.holdout_days,
                created_at=self.started_at,
            )
        manifest = json.loads(self._manifest_path.read_text()) if self._manifest_path.exists() else None
        self.previous_manifest = dict(manifest) if manifest else None
        if manifest is not None and manifest.get("contract_sha256") != self.contract_sha256:
            raise ValueError("existing collector manifest has a different contract hash")
        if manifest is None:
            cli_path = self.repo_root / "scripts/memecoin_prospective_collector.py"
            manifest = {
                "schema_version": "nave.memecoin.prospective-collector-manifest.v1",
                "mode": self.mode,
                "status": "STARTING",
                "operator_authorized_by_task": True,
                "contract_path": str(self.contract_path),
                "contract_sha256": self.contract_sha256,
                "source_commit": self.source_commit,
                "collector_code_files": {
                    "research/nave/prospective_collection.py": sha256_file(Path(__file__)),
                    "scripts/memecoin_prospective_collector.py": sha256_file(cli_path)
                    if cli_path.exists() else None,
                },
                "provider": {
                    "name": "PumpApi",
                    "stream_uri": self.stream_uri,
                    "authentication": "none",
                    "trade_api_used": False,
                    "dune_used": False,
                },
                "validation_days": self.validation_days,
                "holdout_days": self.holdout_days,
                "holdout_lock": str(holdout_lock_path(self.data_root)) if self.mode == "PROSPECTIVE" else "DRY_RUN_ONLY",
                "destination_root": str(self.data_root),
                "started_at": iso(self.started_at),
                "pid": os.getpid(),
                "connections": [],
                "provider_failures": [],
                "counts": {},
            }
        else:
            previous_connections = manifest.get("connections") or []
            self.connection_number = max(
                (int(item.get("connection_number", 0)) for item in previous_connections),
                default=0,
            )
            manifest.setdefault("first_started_at", manifest.get("started_at"))
            manifest["restart_count"] = int(manifest.get("restart_count", 0)) + 1
        cli_path = self.repo_root / "scripts/memecoin_prospective_collector.py"
        manifest["collector_code_files"] = {
            "research/nave/prospective_collection.py": sha256_file(Path(__file__)),
            "scripts/memecoin_prospective_collector.py": sha256_file(cli_path)
            if cli_path.exists() else None,
        }
        manifest.update(
            {
                "status": "RUNNING",
                "pid": os.getpid(),
                "started_at": iso(self.started_at),
                "run_started_at": iso(self.started_at),
                "last_updated_at": iso(self.clock()),
            }
        )
        self.manifest = manifest
        self._write_manifest()
        if self.mode == "PROSPECTIVE":
            for partition, days in (("validation", self.validation_days), ("holdout", self.holdout_days)):
                for event_day in days:
                    payload = self._checkpoint(partition, event_day)
                    if (
                        payload.get("event_rows", 0) == 0
                        and payload.get("unique_launches", 0) == 0
                        and payload.get("status") == "COLLECTED_PENDING_RECONCILIATION"
                    ):
                        payload["status"] = "NOT_STARTED"
                        payload["source_reconciliation"] = "PENDING_AFTER_UTC_CLOSE"
                    if (
                        payload.get("event_rows", 0) == 0
                        and payload.get("unique_launches", 0) == 0
                        and event_day > self.clock().astimezone(UTC).date().isoformat()
                    ):
                        payload["provider_failures"] = 0
                    self._write_checkpoint(partition, event_day, payload)
        self._load_pending_outcome_jobs()

    def _load_pending_outcome_jobs(self) -> None:
        rows = self._db.execute(
            """SELECT j.job_key,j.mint,j.horizon,j.target_time,j.output_path,
                      l.pool_address,l.launch_time,l.decision_time
                 FROM outcome_jobs AS j
                 LEFT JOIN launches AS l ON l.mint = j.mint
                WHERE NOT EXISTS (
                    SELECT 1 FROM outcome_snapshots AS s WHERE s.job_key = j.job_key
                )"""
        ).fetchall()
        for row in rows:
            self._queue_outcome_job(
                {
                    "job_key": row[0],
                    "contract_address": row[1],
                    "horizon": row[2],
                    "target_time": row[3],
                    "output_path": row[4],
                    "pool_address": row[5],
                    "launch_time": row[6],
                    "decision_time": row[7],
                }
            )

    def _queue_outcome_job(self, job: dict[str, Any]) -> None:
        job_key = str(job["job_key"])
        if job_key in self._outcome_jobs:
            return
        target = datetime.fromisoformat(str(job["target_time"]).replace("Z", "+00:00"))
        self._outcome_jobs[job_key] = job
        self._outcome_heap_sequence += 1
        heapq.heappush(self._outcome_heap, (target.timestamp(), self._outcome_heap_sequence, job_key))

    def _write_manifest(self) -> None:
        if self._batch_active:
            return
        self.manifest["counts"] = dict(self._counters)
        self.manifest["last_updated_at"] = iso(self.clock())
        _atomic_json(self._manifest_path, self.manifest)

    def _checkpoint(self, partition: str, event_day: str) -> dict[str, Any]:
        cache_key = (partition, event_day)
        if cache_key in self._checkpoint_cache:
            return self._checkpoint_cache[cache_key]
        path = self.data_root / partition / f"date={event_day}" / "checkpoint.json"
        if path.exists():
            payload = json.loads(path.read_text())
        else:
            payload = {
                "schema_version": "nave.memecoin.prospective-day-checkpoint.v1",
                "partition": partition,
                "event_date": event_day,
                "contract_sha256": self.contract_sha256,
                "status": "OPEN",
                "expected_hours": [f"{hour:02d}" for hour in range(24)],
                "hours": {f"{hour:02d}": {"status": "NOT_STARTED"} for hour in range(24)},
                "event_rows": 0,
                "unique_launches": 0,
                "participant_rows": 0,
                "outcome_jobs": 0,
                "provider_failures": 0,
                "invalid_timestamp_rows": 0,
                "duplicate_events": 0,
                "duplicate_launches": 0,
                "late_appends": 0,
                "source_reconciliation": "PENDING_AFTER_UTC_CLOSE",
                "last_updated_at": iso(self.clock()),
            }
        self._checkpoint_cache[cache_key] = payload
        return payload

    def _write_checkpoint(self, partition: str, event_day: str, payload: dict[str, Any]) -> None:
        path = self.data_root / partition / f"date={event_day}" / "checkpoint.json"
        payload["last_updated_at"] = iso(self.clock())
        self._checkpoint_cache[(partition, event_day)] = payload
        _atomic_json(path, payload)

    def _flush_checkpoints(self, *, force: bool = False) -> None:
        if self._batch_active:
            return
        if not force and time.monotonic() - self._last_checkpoint_flush < 5:
            return
        for (partition, event_day), payload in self._checkpoint_cache.items():
            self._write_checkpoint(partition, event_day, payload)
        self._last_checkpoint_flush = time.monotonic()

    def _commit(self) -> None:
        if not self._batch_active:
            self._db.commit()

    def process_batch(self, frames: list[tuple[str | bytes, datetime]]) -> None:
        """Fsync JSONL before one FULL SQLite commit; retain crash ambiguity.

        Interrupted pre-commit batches can leave keyed JSONL tails. The durable
        marker requires reconciliation on restart, never silent completeness.
        """
        from research.nave.prospective_runtime import durable_json

        marker = self.data_root / "batch-state.json"
        durable_json(marker, {"status": "IN_FLIGHT", "started_at": iso(self.clock()),
                              "frames": len(frames)})
        self._batch_active = True
        try:
            for message, received_at in frames:
                self._rotate_segments(received_at)
                self.process_message(message, received_at)
            fsync_started = time.perf_counter()
            for handle in self._handles.values():
                handle.flush()
                os.fsync(handle.fileno())
            for directory in sorted(self._new_output_dirs, key=lambda path: len(path.parts), reverse=True):
                descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
            self._new_output_dirs.clear()
            self.last_jsonl_fsync_seconds = time.perf_counter() - fsync_started
            commit_started = time.perf_counter()
            self._db.commit()
            self.last_sqlite_commit_seconds = time.perf_counter() - commit_started
        except BaseException:
            self._db.rollback()
            raise
        finally:
            self._batch_active = False
        durable_json(marker, {"status": "COMMITTED", "finished_at": iso(self.clock()),
                              "frames": len(frames)})
        self._flush_checkpoints()

    def _append_line(self, path: Path, row: dict[str, Any]) -> None:
        handle = self._handles.get(path)
        if handle is None:
            path.parent.mkdir(parents=True, exist_ok=True)
            handle = path.open("a", encoding="utf-8")
            self._handles[path] = handle
            directory = path.parent
            while directory.is_relative_to(self.data_root):
                self._new_output_dirs.add(directory)
                if directory == self.data_root:
                    break
                directory = directory.parent
        handle.write(canonical_json(row) + "\n")
        if not self._batch_active:
            handle.flush()

    def _segment_path(self, partition: str, event_day: str, received_at: datetime) -> Path:
        return (
            self.data_root
            / partition
            / f"date={event_day}"
            / f"capture_date={received_at.date().isoformat()}"
            / f"hour={received_at.hour:02d}"
            / "events.jsonl"
        )

    def _record_error(self, message: str, received_at: datetime, *, connection: int | None = None) -> None:
        self._counters["provider_errors"] += 1
        row = {
            "schema_version": "nave.memecoin.provider-error.v1",
            "provider": "pumpapi",
            "observed_at": iso(received_at),
            "available_at": iso(received_at),
            "retrieved_at": iso(self.clock()),
            "connection_number": connection,
            "error": message[:2000],
        }
        self._append_line(self.data_root / "provider-errors.jsonl", row)

    def _upsert_launch(
        self,
        *,
        raw: dict[str, Any],
        event: dict[str, Any],
        event_key: str,
        received_at: datetime,
        retrieved_at: datetime,
        output_path: Path,
        checkpoint: dict[str, Any],
    ) -> tuple[datetime | None, bool]:
        launch_time = parse_provider_timestamp(raw.get("timestamp"))
        mint = event.get("contract_address")
        if str(raw.get("action") or raw.get("txType") or "").lower() not in {"create", "createtoken"} or not mint or launch_time is None:
            return None, False
        decision_time = launch_time + timedelta(minutes=5)
        cursor = self._db.execute(
            "INSERT OR IGNORE INTO launches(mint,launch_time,decision_time,pool_address,output_path,source_event_key) VALUES(?,?,?,?,?,?)",
            (
                str(mint),
                iso(launch_time),
                iso(decision_time),
                raw.get("poolId"),
                str(output_path),
                event_key,
            ),
        )
        inserted = cursor.rowcount == 1
        if not inserted:
            checkpoint["duplicate_launches"] += 1
            self._counters["duplicate_launches"] += 1
            return launch_time, False
        launch_row = {
            "schema_version": "nave.memecoin.launch-snapshot.v1",
            "chain_id": CHAIN_ID,
            "contract_address": str(mint),
            "pool_address": raw.get("poolId"),
            "launch_time": iso(launch_time),
            "event_time": iso(launch_time),
            "observed_at": iso(received_at),
            "available_at": iso(received_at),
            "retrieved_at": iso(retrieved_at),
            "decision_time": iso(decision_time),
            "provider": "pumpapi",
            "venue": raw.get("pool") or raw.get("dex"),
            "event_type": "CREATE",
            "source_event_key": event_key,
            "name": raw.get("name"),
            "symbol": raw.get("symbol"),
            "creator": raw.get("creator") or raw.get("txSigner"),
            "pool_id_status": "KNOWN" if raw.get("poolId") else "UNKNOWN",
            "selection": "ALL_STREAM_CREATE_EVENTS_NO_STRATEGY_FILTER",
            "status": "CANONICAL_CREATE_OBSERVED",
        }
        launch_path = output_path.parent.parent.parent / "launches.jsonl"
        self._append_line(launch_path, launch_row)
        checkpoint["unique_launches"] += 1
        self._counters["launches"] += 1
        self._schedule_outcomes(
            launch_row=launch_row,
            output_path=launch_path,
            received_at=received_at,
            checkpoint=checkpoint,
        )
        self._commit()
        return launch_time, True

    def _schedule_outcomes(
        self,
        *,
        launch_row: dict[str, Any],
        output_path: Path,
        received_at: datetime,
        checkpoint: dict[str, Any],
    ) -> None:
        decision_time = datetime.fromisoformat(launch_row["decision_time"].replace("Z", "+00:00"))
        jobs_path = output_path.parent / "outcome-jobs.jsonl"
        for horizon, delta in TARGET_HORIZONS.items():
            target = decision_time + delta
            job_key = f"{launch_row['contract_address']}:{horizon}"
            cursor = self._db.execute(
                "INSERT OR IGNORE INTO outcome_jobs(job_key,mint,horizon,target_time,output_path) VALUES(?,?,?,?,?)",
                (job_key, launch_row["contract_address"], horizon, iso(target), str(jobs_path)),
            )
            if cursor.rowcount != 1:
                continue
            job = {
                "schema_version": "nave.memecoin.outcome-job.v1",
                "job_key": job_key,
                "chain_id": launch_row["chain_id"],
                "contract_address": launch_row["contract_address"],
                "pool_address": launch_row["pool_address"],
                "launch_time": launch_row["launch_time"],
                "decision_time": launch_row["decision_time"],
                "horizon": horizon,
                "target_time": iso(target),
                "entry_state": "SCHEDULED_AT_DECISION_PLUS_30S" if horizon == "30s" else None,
                "same_pool_required": True,
                "paper_notional_quote": 10.0,
                "status": "PENDING_RAW_STATE_COLLECTION",
                "created_at": iso(received_at),
                "analysis_status": "NOT_ANALYZED",
                "missing_evidence_rule": "UNKNOWN_NOT_ZERO",
                "fees": None,
                "estimated_spread": None,
                "estimated_slippage": None,
                "gas": None,
                "failed_exit_state": None,
                "dry_run_only": self.mode != "PROSPECTIVE",
            }
            self._append_line(jobs_path, job)
            self._queue_outcome_job(
                {
                    "job_key": job_key,
                    "contract_address": launch_row["contract_address"],
                    "horizon": horizon,
                    "target_time": iso(target),
                    "output_path": str(jobs_path),
                    "pool_address": launch_row["pool_address"],
                    "launch_time": launch_row["launch_time"],
                    "decision_time": launch_row["decision_time"],
                }
            )
            checkpoint["outcome_jobs"] += 1
            self._counters["outcome_jobs"] += 1
        self._commit()

    def _participant_path(self, event_path: Path) -> Path:
        return event_path.parent.parent.parent / "participants.jsonl"

    def _write_participants(
        self,
        *,
        raw: dict[str, Any],
        event: dict[str, Any],
        received_at: datetime,
        retrieved_at: datetime,
        decision_time: datetime | None,
        event_key: str,
        event_path: Path,
        checkpoint: dict[str, Any],
    ) -> None:
        rows = _participant_rows(raw)
        if not rows:
            return
        participant_path = self._participant_path(event_path)
        for row in rows:
            participant = {
                "schema_version": "nave.memecoin.participant-history-event.v1",
                "chain_id": CHAIN_ID,
                "participant_id": row.get("participant_id"),
                "participant_identity_status": "KNOWN" if row.get("participant_id") else "UNKNOWN",
                "activity_mint": event.get("contract_address"),
                "prior_mint": None,
                "prior_mint_assignment": "DEFERRED_UNTIL_CURRENT_MINT_EXCLUSION",
                "pool_address": event.get("pool_address"),
                "event_type": event.get("event_type"),
                "transaction_signature": event.get("tx_signature"),
                "slot": event.get("slot"),
                "participant_quote_amount": row.get("quote_amount"),
                "participant_token_amount": row.get("token_amount"),
                "event_time": event.get("event_time"),
                "observed_at": iso(received_at),
                "available_at": iso(received_at),
                "retrieved_at": iso(retrieved_at),
                "decision_time": iso(decision_time) if decision_time else None,
                "source_event_key": event_key,
                "participant_source": row.get("participant_source"),
                "information_cutoff_rule": "available_at must be <= target launch decision_time",
                "current_mint_exclusion_required": True,
                "unknown_behavior": "UNKNOWN_RETAINED",
            }
            self._append_line(participant_path, participant)
            checkpoint["participant_rows"] += 1
            self._counters["participant_rows"] += 1

    def _update_pool_state(
        self,
        *,
        event_record: dict[str, Any],
        event_key: str,
        received_at: datetime,
        retrieved_at: datetime,
    ) -> None:
        pool_address = event_record.get("pool_address")
        event_time = event_record.get("event_time")
        if not pool_address or not event_time:
            return
        candidate = {
            "source_event_key": event_key,
            "event_time": event_time,
            "available_at": event_record.get("available_at"),
            "observed_at": iso(received_at),
            "retrieved_at": iso(retrieved_at),
            "event_type": event_record.get("event_type"),
            "side": event_record.get("side"),
            "price": event_record.get("price"),
            "quote_amount": event_record.get("quote_amount"),
            "token_amount": event_record.get("token_amount"),
            "tokens_in_pool": event_record.get("tokens_in_pool"),
            "quote_in_pool": event_record.get("quote_in_pool"),
            "virtual_tokens_in_pool": event_record.get("virtual_tokens_in_pool"),
            "virtual_quote_in_pool": event_record.get("virtual_quote_in_pool"),
            "pool_fee_rate": event_record.get("pool_fee_rate"),
        }
        current = self._pool_states.get(str(pool_address))
        if current is None or str(candidate["event_time"]) >= str(current["event_time"]):
            self._pool_states[str(pool_address)] = candidate

    def _capture_due_outcomes(self, now: datetime) -> None:
        now = now.astimezone(UTC)
        while self._outcome_heap and self._outcome_heap[0][0] <= now.timestamp():
            _, _, job_key = heapq.heappop(self._outcome_heap)
            job = self._outcome_jobs.pop(job_key, None)
            if job is None:
                continue
            target = datetime.fromisoformat(str(job["target_time"]).replace("Z", "+00:00"))
            pool_address = job.get("pool_address")
            state = self._pool_states.get(str(pool_address)) if pool_address else None
            source_event_time = state.get("event_time") if state else None
            source_available_at = state.get("available_at") if state else None
            missing_fields: list[str] = []
            if not pool_address:
                missing_fields.append("pool_address")
            if state is None:
                missing_fields.append("pool_state")
            else:
                if source_event_time and source_event_time > iso(target):
                    missing_fields.append("causal_event_time")
                if source_available_at and source_available_at > iso(target):
                    missing_fields.append("causal_available_at")
            record = {
                "schema_version": "nave.memecoin.outcome-snapshot.v1",
                "job_key": job_key,
                "chain_id": CHAIN_ID,
                "contract_address": job.get("contract_address"),
                "pool_address": pool_address,
                "launch_time": job.get("launch_time"),
                "decision_time": job.get("decision_time"),
                "horizon": job.get("horizon"),
                "target_time": iso(target),
                "captured_at": iso(now),
                "available_at": source_available_at or iso(now),
                "retrieved_at": iso(self.clock()),
                "source_event_time": source_event_time,
                "source_event_key": state.get("source_event_key") if state else None,
                "status": "RAW_POOL_STATE_CAPTURED" if state and not missing_fields else "UNKNOWN",
                "missing_evidence": missing_fields,
                "same_pool_required": True,
                "paper_notional_quote": 10.0,
                "executable_price": state.get("price") if state else None,
                "quote_liquidity": (
                    state.get("quote_in_pool") or state.get("virtual_quote_in_pool") if state else None
                ),
                "pool_liquidity": {
                    "tokens_in_pool": state.get("tokens_in_pool") if state else None,
                    "quote_in_pool": state.get("quote_in_pool") if state else None,
                },
                "spread_estimate": None,
                "slippage_estimate": None,
                "fees": {"pool_fee_rate": state.get("pool_fee_rate")} if state else None,
                "gas_network_cost": None,
                "route": None,
                "failed_exit_state": None,
                "analysis_status": "NOT_ANALYZED",
                "missing_evidence_rule": "UNKNOWN_NOT_ZERO",
                "dry_run_only": self.mode != "PROSPECTIVE",
            }
            output_path = Path(str(job["output_path"])).parent / "outcome-snapshots.jsonl"
            inserted = self._db.execute(
                "INSERT OR IGNORE INTO outcome_snapshots(job_key,output_path,record_json) VALUES(?,?,?)",
                (job_key, str(output_path), canonical_json(record)),
            ).rowcount
            if inserted == 1:
                self._append_line(output_path, record)
                self._counters["outcome_snapshots"] += 1
        self._commit()

    def _normalize_record(
        self,
        *,
        raw: dict[str, Any],
        received_at: datetime,
        retrieved_at: datetime,
        event_key: str,
        launch_time: datetime | None,
    ) -> dict[str, Any]:
        event = normalize_event(raw)
        provider_timestamp = parse_provider_timestamp(raw.get("timestamp"))
        flags = list(json.loads(event.get("quality_flags_json") or "[]"))
        if raw.get("timestamp") is not None and provider_timestamp is None:
            flags.append("INVALID_EVENT_TIMESTAMP")
        if provider_timestamp is not None and received_at > provider_timestamp:
            flags.append("PROVIDER_EVENT_DELAYED_BEFORE_LOCAL_RECEIPT")
        event_time = iso(provider_timestamp) if provider_timestamp else None
        decision_time = launch_time + timedelta(minutes=5) if launch_time else None
        record = {
            "schema_version": "nave.memecoin.receiver-event.v1",
            "provider": "pumpapi",
            "stream_uri": self.stream_uri,
            "chain_id": CHAIN_ID,
            "contract_address": event.get("mint"),
            "pool_address": raw.get("poolId"),
            "launch_time": iso(launch_time) if launch_time else None,
            "event_time": event_time,
            "observed_at": iso(received_at),
            "available_at": iso(received_at),
            "retrieved_at": iso(retrieved_at),
            "decision_time": iso(decision_time) if decision_time else None,
            "provider_event_timestamp": raw.get("timestamp"),
            "provider_received_at": event.get("provider_received_at"),
            "local_received_at": iso(received_at),
            "event_key": event_key,
            "event_type": event.get("event_type"),
            "venue": raw.get("pool") or raw.get("dex"),
            "side": event.get("side"),
            "is_buy": event.get("is_buy"),
            "wallet": event.get("wallet"),
            "token_amount": event.get("token_amount"),
            "quote_amount": event.get("quote_amount"),
            "quote_mint": raw.get("quoteMint") or raw.get("quote_mint"),
            "price": event.get("price"),
            "tokens_in_pool": raw.get("tokensInPool") or raw.get("tokens_in_pool"),
            "quote_in_pool": raw.get("quoteInPool") or raw.get("quote_in_pool"),
            "virtual_tokens_in_pool": raw.get("vTokensInBondingCurve") or raw.get("virtualTokenReserves"),
            "virtual_quote_in_pool": raw.get("vQuoteInBondingCurve") or raw.get("virtualQuoteReserves"),
            "pool_fee_rate": raw.get("poolFeeRate"),
            "tx_signature": event.get("tx_signature"),
            "slot": event.get("slot"),
            "transaction_index": event.get("transaction_index"),
            "instruction_index": event.get("instruction_index"),
            "creator": raw.get("creator"),
            "name": raw.get("name"),
            "symbol": raw.get("symbol"),
            "raw_event_sha256": event_key,
            "quality_flags": sorted(set(flags)),
            "source_raw_event_retained": False,
            "analysis_status": "NOT_ANALYZED",
        }
        return record

    def process_message(self, message: str | bytes, received_at: datetime | None = None) -> None:
        received_at = (received_at or self.clock()).astimezone(UTC)
        retrieved_at = self.clock().astimezone(UTC)
        self._capture_due_outcomes(received_at)
        try:
            if isinstance(message, bytes):
                if len(message) > self.max_event_bytes:
                    self._record_error("oversized provider frame", received_at, connection=self.connection_number)
                    return
                text = message.decode("utf-8", errors="strict")
            else:
                if len(message.encode("utf-8")) > self.max_event_bytes:
                    self._record_error("oversized provider frame", received_at, connection=self.connection_number)
                    return
                text = message
        except UnicodeDecodeError as exc:
            self._record_error(f"invalid provider UTF-8: {exc}", received_at, connection=self.connection_number)
            return
        try:
            raw = json.loads(text)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self._record_error(f"invalid provider JSON: {exc}", received_at, connection=self.connection_number)
            return
        if not isinstance(raw, dict):
            self._record_error("provider frame was not an object", received_at, connection=self.connection_number)
            return

        event_key = provider_event_key(raw)
        self.last_processed_event_key = event_key
        action = str(raw.get("action") or raw.get("txType") or "").strip().lower()
        provider_event_time = parse_provider_timestamp(raw.get("timestamp"))
        partition, event_day = partition_for_event(
            provider_event_time, received_at, self.validation_days, self.holdout_days
        )
        checkpoint = self._checkpoint(partition, event_day)
        if provider_event_time is None:
            checkpoint["invalid_timestamp_rows"] += 1
            self._counters["invalid_timestamp_rows"] += 1
        elif received_at > provider_event_time:
            self._counters["delayed_event_rows"] += 1

        segment = self._segment_path(partition, event_day, received_at)
        inserted = self._db.execute(
            "INSERT OR IGNORE INTO events(event_key,event_time,available_at,mint,pool_address,action,output_path) VALUES(?,?,?,?,?,?,?)",
            (
                event_key,
                iso(provider_event_time) if provider_event_time else None,
                iso(received_at),
                raw.get("mint") or raw.get("tokenMint") or raw.get("token_mint"),
                raw.get("poolId"),
                action,
                str(segment),
            ),
        )
        if inserted.rowcount != 1:
            checkpoint["duplicate_events"] += 1
            self._counters["duplicate_events"] += 1
            self._flush_checkpoints()
            self._commit()
            return

        mint = raw.get("mint") or raw.get("tokenMint") or raw.get("token_mint")
        previous = self._db.execute(
            "SELECT launch_time FROM launches WHERE mint=?", (str(mint),)
        ).fetchone() if mint else None
        is_create = action in {"create", "createtoken"}
        launch_time = (
            provider_event_time
            if is_create and provider_event_time is not None
            else datetime.fromisoformat(previous[0].replace("Z", "+00:00")) if previous else None
        )
        event_record = self._normalize_record(
            raw=raw,
            received_at=received_at,
            retrieved_at=retrieved_at,
            event_key=event_key,
            launch_time=launch_time,
        )
        self._append_line(segment, event_record)
        self._update_pool_state(
            event_record=event_record,
            event_key=event_key,
            received_at=received_at,
            retrieved_at=retrieved_at,
        )
        checkpoint["event_rows"] += 1
        self._counters["event_rows"] += 1
        if checkpoint["hours"].get(f"{received_at.hour:02d}", {}).get("status") == "COMPLETE":
            checkpoint["late_appends"] += 1
            self._counters["late_appends"] += 1
        checkpoint["hours"][f"{received_at.hour:02d}"] = {
            "status": "OPEN",
            "capture_date": received_at.date().isoformat(),
            "event_rows": checkpoint["hours"].get(f"{received_at.hour:02d}", {}).get("event_rows", 0) + 1,
            "path": str(segment),
        }
        launch_time, _ = self._upsert_launch(
            raw=raw,
            event=event_record,
            event_key=event_key,
            received_at=received_at,
            retrieved_at=retrieved_at,
            output_path=segment,
            checkpoint=checkpoint,
        )
        # If this create row registered the launch, its own event row gets the
        # launch clock in the launch snapshot; the raw receiver row remains an
        # immutable first-receipt record with no hindsight fields.
        self._write_participants(
            raw=raw,
            event=event_record,
            received_at=received_at,
            retrieved_at=retrieved_at,
            decision_time=launch_time + timedelta(minutes=5) if launch_time else None,
            event_key=event_key,
            event_path=segment,
            checkpoint=checkpoint,
        )
        self._flush_checkpoints()
        self._commit()
        if self._counters["event_rows"] % 100 == 0:
            self._write_manifest()

    def _rotate_segments(self, current: datetime) -> None:
        capture_hour = f"{current.date().isoformat()}T{current.hour:02d}"
        if self._active_capture_hour is None:
            self._active_capture_hour = capture_hour
        elif self._active_capture_hour != capture_hour:
            self._close_all_segments()
            self._active_capture_hour = capture_hour

    def _close_all_segments(self) -> None:
        for handle in self._handles.values():
            handle.flush()
            os.fsync(handle.fileno())
            handle.close()
        self._handles.clear()

    def flush(self) -> None:
        """Durably publish buffered checkpoints for tests and operator tools."""
        self._flush_checkpoints(force=True)
        self._db.commit()
        self._write_manifest()

    def _mark_finished(self, status: str) -> None:
        self._flush_checkpoints(force=True)
        self._close_all_segments()
        for checkpoint_path in self.data_root.glob("*/date=*/checkpoint.json"):
            payload = json.loads(checkpoint_path.read_text())
            for hour_key, hour_payload in payload.get("hours", {}).items():
                if hour_payload.get("status") == "OPEN":
                    segment_path = Path(hour_payload.get("path", ""))
                    if segment_path.exists():
                        hour_payload.update(
                            {
                                "status": "CLOSED_PENDING_RECONCILIATION",
                                "file_size_bytes": segment_path.stat().st_size,
                                "sha256": sha256_file(segment_path),
                            }
                        )
            event_day = payload.get("event_date")
            partition = payload.get("partition")
            if payload.get("provider_failures", 0) > 0:
                payload["status"] = "INCOMPLETE"
            elif payload.get("event_rows", 0) == 0 and payload.get("unique_launches", 0) == 0:
                payload["status"] = "NOT_STARTED"
            elif status == "STOPPED_BEFORE_WINDOW_END":
                payload["status"] = "INCOMPLETE"
            elif payload.get("provider_failures", 0) > 0:
                payload["status"] = "INCOMPLETE"
            elif partition == "quarantine":
                payload["status"] = "QUARANTINE"
            else:
                payload["status"] = "COLLECTED_PENDING_RECONCILIATION"
            payload["source_reconciliation"] = "REQUIRED_BEFORE_COMPLETE_CLOSED_DAY"
            self._write_checkpoint(partition, event_day, payload)
        self.manifest["status"] = status
        self.manifest["stopped_at"] = iso(self.clock())
        self._write_manifest()

    def request_stop(self, *_args: Any) -> None:
        self.stop_requested = True

    async def run(self, *, stop_at: datetime, reconnect_max_seconds: int = 60) -> int:
        from research.nave.prospective_runtime import run_pipeline
        return await run_pipeline(self, stop_at, reconnect_max_seconds)


def operational_status(data_root: Path) -> dict[str, Any]:
    """Operational files only: never scan event or outcome tapes."""
    from research.nave.prospective_runtime import CONTRACT_PATH, health_reasons
    runtime_path = data_root / "runtime-health.json"
    runtime = json.loads(runtime_path.read_text()) if runtime_path.exists() else {}
    lock_path = holdout_lock_path(data_root)
    lock = json.loads(lock_path.read_text()) if lock_path.exists() else {}
    reasons = health_reasons(runtime, json.loads(CONTRACT_PATH.read_text()))
    state = runtime.get("state", "RECOVERING")
    if reasons and state == "HEALTHY":
        state = "DEGRADED_BACKLOG"
    return {
        "schema_version": "nave.memecoin.collection-status.v2",
        "collector_state": state,
        "reasons": reasons,
        "runtime": runtime,
        "validation_holdout_analysis": lock.get("status", "LOCK_MISSING"),
        "holdout_lock_path": str(lock_path),
        "days": [
            {key: row.get(key) for key in
             ("partition", "event_date", "status", "last_updated_at", "event_rows",
              "provider_failures", "source_reconciliation")}
            for path in sorted(data_root.glob("*/date=*/checkpoint.json"))
            for row in [json.loads(path.read_text())]
        ],
    }
