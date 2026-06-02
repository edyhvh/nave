"""Persist active momentum theses so live scans cannot drift entry geometry."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def default_momentum_thesis_state_path() -> Path:
    return Path(__file__).resolve().parents[3] / "var" / "state" / "momentum_theses.json"


@dataclass
class MomentumThesisStore:
    path: Path | None = None

    def __post_init__(self) -> None:
        self.path = self.path or default_momentum_thesis_state_path()
        self._payload = self._load()

    @property
    def payload(self) -> dict[str, Any]:
        return self._payload

    def get(self, key: str) -> dict[str, Any] | None:
        theses = self._payload.get("theses")
        if not isinstance(theses, dict):
            return None
        value = theses.get(key)
        return value if isinstance(value, dict) else None

    def upsert(self, key: str, value: dict[str, Any]) -> None:
        theses = self._payload.setdefault("theses", {})
        if not isinstance(theses, dict):
            self._payload["theses"] = {}
            theses = self._payload["theses"]
        theses[key] = value

    def save(self) -> None:
        assert self.path is not None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._payload, indent=2, default=_json_default),
            encoding="utf-8",
        )

    def _load(self) -> dict[str, Any]:
        assert self.path is not None
        if not self.path.exists():
            return _empty_payload()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return _empty_payload()
        if not isinstance(payload, dict):
            return _empty_payload()
        if not isinstance(payload.get("theses"), dict):
            payload["theses"] = {}
        return payload


def _json_default(value: Any) -> Any:
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return item()
        except Exception:
            pass
    return str(value)


def reconcile_momentum_theses(
    results: dict[str, dict[str, Any]],
    *,
    current_prices: dict[str, float],
    store: MomentumThesisStore,
    now: datetime | None = None,
    max_age_hours: int = 120,
) -> dict[str, Any]:
    """Freeze active tradeable plans across scans until the thesis resolves."""

    now = now or datetime.now(timezone.utc)
    now_iso = now.isoformat()
    max_age = timedelta(hours=max_age_hours)
    active_keys: set[str] = set()

    for symbol, entry in results.items():
        price = current_prices.get(symbol)
        plans = entry.get("plans") if isinstance(entry, dict) else None
        if not isinstance(plans, list):
            continue

        reconciled_plans: list[dict[str, Any]] = []
        seen_keys: set[str] = set()
        for plan in plans:
            if not isinstance(plan, dict):
                continue
            side = str(plan.get("side") or "").lower()
            if side not in {"long", "short"}:
                reconciled_plans.append(plan)
                continue
            key = f"{symbol}:{side}"
            if key in seen_keys:
                duplicate = dict(plan)
                duplicate["tradeable"] = False
                duplicate["thesis_state"] = "suppressed"
                duplicate["thesis_status"] = "duplicate_symbol_side"
                reconciled_plans.append(duplicate)
                continue
            seen_keys.add(key)
            active_keys.add(key)
            stored = store.get(key) or {}
            stored_plan = stored.get("plan") if isinstance(stored.get("plan"), dict) else None
            stored_state = str(stored.get("state") or "")
            stored_created = _parse_datetime(stored.get("created_at"))
            is_active = (
                stored_plan is not None
                and stored_state == "active"
                and not _is_expired(stored_created, now, max_age)
            )

            if is_active:
                assert stored_plan is not None
                resolution = _resolution_status(stored_plan, price)
                if resolution is None:
                    frozen = dict(stored_plan)
                    frozen["scan_plan"] = plan
                    frozen["thesis_state"] = "active"
                    frozen["thesis_status"] = (
                        "holding_previous"
                        if _plan_geometry_changed(stored_plan, plan)
                        else "active"
                    )
                    frozen["thesis_created_at"] = stored.get("created_at")
                    frozen["thesis_last_checked_at"] = now_iso
                    reconciled_plans.append(frozen)
                    store.upsert(key, {
                        **stored,
                        "last_checked_at": now_iso,
                        "latest_scan_plan": plan,
                    })
                    continue

                closed_state = {
                    **stored,
                    "state": resolution,
                    "resolved_at": now_iso,
                    "resolved_price": price,
                    "latest_scan_plan": plan,
                }
                store.upsert(key, closed_state)

            new_plan = dict(plan)
            if bool(new_plan.get("tradeable")):
                new_plan["thesis_state"] = "active"
                new_plan["thesis_status"] = "armed"
                new_plan["thesis_created_at"] = now_iso
                new_plan["thesis_last_checked_at"] = now_iso
                store.upsert(key, {
                    "symbol": symbol,
                    "side": side,
                    "state": "active",
                    "created_at": now_iso,
                    "last_checked_at": now_iso,
                    "plan": new_plan,
                    "latest_scan_plan": plan,
                })
            reconciled_plans.append(new_plan)
        entry["plans"] = reconciled_plans

    _expire_missing_theses(store, active_keys, now_iso=now_iso)
    store.payload["generated_at"] = now_iso
    store.save()
    return store.payload


def _empty_payload() -> dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "theses": {},
    }


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _is_expired(created_at: datetime | None, now: datetime, max_age: timedelta) -> bool:
    if created_at is None:
        return False
    return now - created_at > max_age


def _resolution_status(plan: dict[str, Any], price: float | None) -> str | None:
    if price is None:
        return None
    side = str(plan.get("side") or "").lower()
    invalidation = _safe_float(plan.get("invalidation"))
    target = _safe_float(plan.get("tp2"))
    if side == "long":
        if invalidation is not None and price <= invalidation:
            return "invalidated"
        if target is not None and price >= target:
            return "target_hit"
    if side == "short":
        if invalidation is not None and price >= invalidation:
            return "invalidated"
        if target is not None and price <= target:
            return "target_hit"
    return None


def _plan_geometry_changed(stored: dict[str, Any], latest: dict[str, Any]) -> bool:
    keys = ("entry_zone", "invalidation", "tp1", "tp2", "tp3")
    return any(stored.get(key) != latest.get(key) for key in keys)


def _safe_float(value: object) -> float | None:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _expire_missing_theses(
    store: MomentumThesisStore,
    active_keys: set[str],
    *,
    now_iso: str,
) -> None:
    theses = store.payload.get("theses")
    if not isinstance(theses, dict):
        return
    for key, value in theses.items():
        if key in active_keys:
            continue
        if not isinstance(value, dict):
            continue
        if value.get("state") != "active":
            continue
        value["state"] = "expired_missing_from_scan"
        value["resolved_at"] = now_iso
