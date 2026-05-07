"""State persistence for entry-zone watch alerts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def default_zone_watch_state_path() -> Path:
    return Path(__file__).resolve().parents[2] / "var" / "state" / "entry_zone_watch.json"


@dataclass
class ZoneWatchStateStore:
    path: Path | None = None

    def __post_init__(self) -> None:
        self.path = self.path or default_zone_watch_state_path()
        self._payload = self._load()

    @property
    def payload(self) -> dict[str, Any]:
        return self._payload

    def get(self, key: str) -> dict[str, Any] | None:
        alerts = self._payload.get("alerts")
        if not isinstance(alerts, dict):
            return None
        value = alerts.get(key)
        return value if isinstance(value, dict) else None

    def upsert(self, key: str, value: dict[str, Any]) -> None:
        alerts = self._payload.setdefault("alerts", {})
        if not isinstance(alerts, dict):
            self._payload["alerts"] = {}
            alerts = self._payload["alerts"]
        alerts[key] = value

    def mark_missing_as_expired(self, active_keys: set[str], *, now_iso: str) -> None:
        alerts = self._payload.get("alerts")
        if not isinstance(alerts, dict):
            return
        for key, value in alerts.items():
            if key in active_keys:
                continue
            if not isinstance(value, dict):
                continue
            if value.get("expired_at"):
                continue
            value["expired_at"] = now_iso

    def save(self) -> None:
        assert self.path is not None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._payload, indent=2), encoding="utf-8")

    def _load(self) -> dict[str, Any]:
        assert self.path is not None
        if not self.path.exists():
            return {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "alerts": {},
            }

        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "alerts": {},
            }

        if not isinstance(payload, dict):
            return {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "alerts": {},
            }
        if not isinstance(payload.get("alerts"), dict):
            payload["alerts"] = {}
        return payload
