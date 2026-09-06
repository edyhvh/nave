"""Bounded Dune query materialization with reusable local cache."""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
import fcntl
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

from research.core.store import ResearchStore
from research.nave import resource_guard


def _find_number(value: Any, names: tuple[str, ...]) -> float | None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key).lower() in names:
                try:
                    number = float(item)
                    if math.isfinite(number) and number >= 0:
                        return number
                except (TypeError, ValueError):
                    pass
            found = _find_number(item, names)
            if found is not None:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_number(item, names)
            if found is not None:
                return found
    return None


def _rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, Mapping):
        for key in ("rows", "data", "result"):
            if key in payload:
                return _rows(payload[key])
        raise ValueError("Dune response has no result rows")
    if isinstance(payload, list):
        if any(not isinstance(row, Mapping) for row in payload):
            raise ValueError("Dune result contains malformed rows")
        return [dict(row) for row in payload]
    raise ValueError("Dune result rows must be an array")


class DuneMaterializer:
    """Run at most one bounded Dune CLI query and persist its envelope."""

    def __init__(self, *, executable: str = "dune", timeout_seconds: int = 120) -> None:
        self.executable = executable
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def query_identity(query_id: str, query_text: str | None = None, *, limit: int = 10_000) -> str:
        if not query_text or not query_text.strip():
            raise ValueError("frozen query_text is required for meaningful cache identity")
        digest = hashlib.sha256(query_text.encode("utf-8")).hexdigest()
        return f"{query_id}:{digest}:limit={limit}"

    def materialize(
        self,
        *,
        query_id: str,
        output: Path,
        limit: int = 10_000,
        force: bool = False,
        query_text: str | None = None,
        max_age_seconds: float = 86400,
        budget: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not query_id.strip():
            raise ValueError("query_id is required")
        if limit < 1 or limit > 100_000:
            raise ValueError("limit must be between 1 and 100000")
        if not math.isfinite(max_age_seconds) or max_age_seconds <= 0:
            raise ValueError("max_age_seconds must be finite and positive")
        output = output.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        # The Quant runtime is POSIX. Lock the whole check/run/write transaction,
        # including distinct processes, so concurrent callers cannot double-spend.
        with output.with_suffix(output.suffix + ".lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            return self._materialize_locked(query_id=query_id, output=output, limit=limit,
                                            force=force, query_text=query_text,
                                            max_age_seconds=max_age_seconds, budget=budget)

    def _materialize_locked(self, *, query_id: str, output: Path, limit: int,
                            force: bool, query_text: str | None,
                            max_age_seconds: float, budget: Mapping[str, Any] | None) -> dict[str, Any]:
        identity = self.query_identity(query_id, query_text, limit=limit)
        if output.exists() and not force:
            cached = json.loads(output.read_text(encoding="utf-8"))
            try:
                fetched = datetime.fromisoformat(str(cached.get("fetched_at")).replace("Z", "+00:00"))
                age = (datetime.now(UTC) - fetched).total_seconds()
            except (AttributeError, TypeError, ValueError):
                age = -1
            if (isinstance(cached, Mapping) and cached.get("provider") == "dune" and cached.get("query_identity") == identity
                    and isinstance(cached.get("rows"), list)
                    and cached.get("row_count") == len(cached["rows"])
                    and 0 <= age <= max_age_seconds):
                return {**dict(cached), "cache_hit": True, "query_executed": False}
            raise ValueError("cache is stale, incompatible or incomplete; inspect it and use --force to refresh")

        # Execute the exact frozen SQL whose hash identifies this cache, so a
        # mutable saved-query ID cannot silently change the operation.
        command = [self.executable, "query", "run-sql", "--sql", query_text, "--limit", str(limit), "-o", "json"]
        if not budget or budget.get("approved") is not True or budget.get("query_identity") != identity:
            raise ValueError("explicit query-scoped budget approval is required")
        try:
            observed = datetime.fromisoformat(str(budget["observed_at"]).replace("Z", "+00:00"))
            if observed.tzinfo is None or not 0 <= (datetime.now(UTC) - observed).total_seconds() <= 300:
                raise ValueError("budget snapshot must be fresh")
            guard = resource_guard.check(**{key: float(budget[key]) for key in
                ("credits_used", "credits_included", "checkpoint_used", "estimate", "free_disk_gb")})
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("missing or invalid budget snapshot") from exc
        if not guard.allowed or guard.level == "HARD_STOP":
            raise ValueError("Dune budget HARD_STOP: " + "; ".join(guard.reasons))
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=self.timeout_seconds,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or f"Dune query exited {completed.returncode}")
        try:
            raw = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Dune CLI returned non-JSON output") from exc
        rows = _rows(raw)
        envelope = {
            "schema_version": 2,
            "provider": "dune",
            "mode": "remote_materialized",
            "query_id": query_id,
            "query_identity": identity,
            "query_sha256": hashlib.sha256(query_text.encode("utf-8")).hexdigest(),
            "execution_id": raw.get("execution_id") if isinstance(raw, Mapping) else None,
            "fetched_at": datetime.now(UTC).isoformat(),
            "requested_limit": limit,
            "max_age_seconds": max_age_seconds,
            "rows": rows,
            "row_count": len(rows),
            "coverage": "UNKNOWN" if len(rows) >= limit else "RETURNED_ROWS_ONLY",
            "query_executed": True,
            "cache_hit": False,
            "credit_usage": {
                "actual": _find_number(raw, ("credits", "credits_used", "compute_credits", "credit_usage")),
                "estimated": _find_number(raw, ("estimated_credits", "estimated_credit_usage")),
                "source": "Dune CLI response; null means the response did not report usage",
            },
        }
        ResearchStore._atomic_write(output, envelope)
        return envelope


__all__ = ["DuneMaterializer"]
