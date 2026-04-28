"""
Persistent archive for memecoin scan snapshots.

Each scan writes one JSON file under ``var/memecoin_scans/`` named by UTC
second timestamp (``YYYYMMDDTHHMMSSZ.json``). The archive is used as a
lightweight state source for entry timing (first-seen vs repeated).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_DEFAULT_SCAN_ARCHIVE_DIR = (
    Path(__file__).resolve().parents[2] / "var" / "memecoin_scans"
)


@dataclass(frozen=True)
class MintHistory:
    mint: str
    seen_count: int
    first_seen_at: str
    last_seen_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "mint": self.mint,
            "seen_count": self.seen_count,
            "first_seen_at": self.first_seen_at,
            "last_seen_at": self.last_seen_at,
        }



def _utc_now() -> datetime:
    return datetime.now(timezone.utc)



def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()



def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
            timezone.utc
        )
    except ValueError:
        return None



def _archive_dir(scan_dir: str | Path | None = None) -> Path:
    return Path(scan_dir) if scan_dir else _DEFAULT_SCAN_ARCHIVE_DIR



def _iter_scan_files(scan_dir: Path) -> list[Path]:
    if not scan_dir.exists():
        return []
    return sorted(p for p in scan_dir.glob("*.json") if p.is_file())



def persist_scan_snapshot(
    *,
    candidates: list[dict[str, Any]],
    params: dict[str, Any],
    scan_dir: str | Path | None = None,
    scanned_at: datetime | None = None,
) -> Path:
    """Persist one scan snapshot to disk and return the file path."""
    now = scanned_at or _utc_now()
    archive_dir = _archive_dir(scan_dir)
    archive_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "schema_version": 1,
        "scanned_at": _iso(now),
        "params": params,
        "count": len(candidates),
        "candidates": candidates,
    }
    file_name = f"{now.strftime('%Y%m%dT%H%M%SZ')}.json"
    path = archive_dir / file_name
    path.write_text(json.dumps(payload, default=str, indent=2), encoding="utf-8")
    return path



def mint_history(
    *,
    hours: int = 24,
    scan_dir: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, MintHistory]:
    """Return per-mint appearance history in the trailing ``hours`` window."""
    if hours < 1:
        raise ValueError("hours must be >= 1")

    now_dt = now or _utc_now()
    cutoff = now_dt - timedelta(hours=hours)
    archive_dir = _archive_dir(scan_dir)

    acc: dict[str, dict[str, Any]] = {}
    for path in _iter_scan_files(archive_dir):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        scanned_at = _parse_iso(payload.get("scanned_at"))
        if scanned_at is None or scanned_at < cutoff:
            continue

        candidates = payload.get("candidates") or []
        if not isinstance(candidates, list):
            continue

        seen_mints_this_scan = {
            str(item.get("mint"))
            for item in candidates
            if isinstance(item, dict) and item.get("mint")
        }
        iso = _iso(scanned_at)
        for mint in seen_mints_this_scan:
            current = acc.get(mint)
            if current is None:
                acc[mint] = {
                    "mint": mint,
                    "seen_count": 1,
                    "first_seen_at": iso,
                    "last_seen_at": iso,
                }
                continue

            current["seen_count"] += 1
            if iso < current["first_seen_at"]:
                current["first_seen_at"] = iso
            if iso > current["last_seen_at"]:
                current["last_seen_at"] = iso

    return {k: MintHistory(**v) for k, v in acc.items()}



def scan_history_payload(
    *,
    hours: int = 24,
    scan_dir: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """JSON-ready payload for MCP ``memecoin_scan_history``."""
    now_dt = now or _utc_now()
    hist = mint_history(hours=hours, scan_dir=scan_dir, now=now_dt)
    rows = sorted(
        (item.to_dict() for item in hist.values()),
        key=lambda row: (-int(row["seen_count"]), str(row["last_seen_at"])),
    )
    return {
        "tool": "memecoin_scan_history",
        "generated_at": _iso(now_dt),
        "hours": hours,
        "count": len(rows),
        "tokens": rows,
    }
