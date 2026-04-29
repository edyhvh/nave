"""Persistent dedup cache for seen politician disclosures.

A flat JSON file under ``var/politicians_cache/seen.json`` stores the set
of disclosure ``link`` URLs we've already surfaced, plus the timestamp of
the last successful scan. The scan diffs the latest FMP feed against this
set to identify newly-published trades.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)


def default_store_path() -> Path:
    project_root = Path(__file__).resolve().parents[3]
    base = Path(
        os.getenv("POLITICIANS_CACHE_DIR")
        or project_root / "var" / "politicians_cache"
    )
    return base / "seen.json"


class SeenStore:
    """JSON-backed set of disclosure unique IDs."""

    def __init__(self, path: Path | None = None):
        self.path = path or default_store_path()
        self._loaded: set[str] | None = None
        self._last_scan_at: str | None = None

    def _load(self) -> None:
        if self._loaded is not None:
            return
        if not self.path.exists():
            self._loaded = set()
            return
        try:
            payload = json.loads(self.path.read_text())
        except Exception:
            logger.warning(
                "Failed to parse %s — starting from empty seen set.", self.path
            )
            self._loaded = set()
            return
        if isinstance(payload, dict):
            seen = payload.get("seen") or []
            last = payload.get("last_scan_at")
            self._last_scan_at = str(last) if last else None
        elif isinstance(payload, list):
            seen = payload
        else:
            seen = []
        self._loaded = {str(item) for item in seen if item}

    def contains(self, unique_id: str) -> bool:
        self._load()
        assert self._loaded is not None
        return unique_id in self._loaded

    def add_many(self, unique_ids: Iterable[str]) -> None:
        self._load()
        assert self._loaded is not None
        self._loaded.update(uid for uid in unique_ids if uid)

    @property
    def last_scan_at(self) -> str | None:
        self._load()
        return self._last_scan_at

    def size(self) -> int:
        self._load()
        assert self._loaded is not None
        return len(self._loaded)

    def save(self) -> None:
        self._load()
        assert self._loaded is not None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._last_scan_at = datetime.now(timezone.utc).isoformat()
        payload = {
            "last_scan_at": self._last_scan_at,
            "seen": sorted(self._loaded),
        }
        self.path.write_text(json.dumps(payload, indent=2))
