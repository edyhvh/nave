"""Persist COT-led regime theses across scans until invalidation or expiry."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from trading.crypto.analysis.constants import (
    BEARISH_REGIME_PHASES,
    BULLISH_REGIME_PHASES,
)
from trading.crypto.analysis.regime import RegimeAssessment


ARM_PHASES_BY_BIAS = {
    "bearish": BEARISH_REGIME_PHASES,
    "bullish": BULLISH_REGIME_PHASES,
}


def default_regime_thesis_path() -> Path:
    return Path(__file__).resolve().parents[3] / "var" / "state" / "regime_theses.json"


@dataclass
class RegimeThesisStore:
    path: Path | None = None

    def __post_init__(self) -> None:
        self.path = self.path or default_regime_thesis_path()
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
        self.path.write_text(json.dumps(self._payload, indent=2, default=str), encoding="utf-8")

    def _load(self) -> dict[str, Any]:
        assert self.path is not None
        if not self.path.exists():
            return {"generated_at": datetime.now(timezone.utc).isoformat(), "theses": {}}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"generated_at": datetime.now(timezone.utc).isoformat(), "theses": {}}
        if not isinstance(payload.get("theses"), dict):
            payload["theses"] = {}
        return payload


def _thesis_key(coin: str, bias: str) -> str:
    return f"{coin.upper()}:{bias}"


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _regime_invalidation(
    thesis: dict[str, Any],
    *,
    price: float | None,
    cot_bias_label: str | None,
    current_phase: str,
) -> str | None:
    if price is None:
        return None
    inv = thesis.get("invalidation")
    if isinstance(inv, (int, float)) and thesis.get("direction") == "short" and price >= float(inv):
        return "invalidated"
    if isinstance(inv, (int, float)) and thesis.get("direction") == "long" and price <= float(inv):
        return "invalidated"
    if cot_bias_label == "bullish" and thesis.get("bias") == "bearish":
        return "cot_flip"
    if current_phase in {"neutral", "cot_bull_bias"} and thesis.get("bias") == "bearish":
        return "regime_cleared"
    return None


def reconcile_regime_thesis(
    *,
    coin: str,
    regime: RegimeAssessment,
    cot_bias_label: str | None,
    price: float | None,
    invalidation: float | None,
    store: RegimeThesisStore,
    max_age_hours: int = 336,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return active thesis overlay for recommendations."""
    now = now or datetime.now(timezone.utc)
    now_iso = now.isoformat()
    key = _thesis_key(coin, regime.bias)
    stored = store.get(key) or {}
    created = _parse_dt(stored.get("created_at"))
    expired = created is not None and (now - created) > timedelta(hours=max_age_hours)

    arm_phases = ARM_PHASES_BY_BIAS.get(regime.bias, frozenset())
    arm = regime.phase in arm_phases
    resolution = _regime_invalidation(
        stored, price=price, cot_bias_label=cot_bias_label, current_phase=regime.phase
    ) if stored.get("state") == "active" else None

    if stored.get("state") == "active" and not expired and resolution is None:
        store.upsert(
            key,
            {
                **stored,
                "last_checked_at": now_iso,
                "latest_phase": regime.phase,
                "latest_metrics": regime.metrics,
            },
        )
        return {
            "thesis_state": "active",
            "thesis_status": "holding",
            "thesis_phase": stored.get("phase") or regime.phase,
            "thesis_created_at": stored.get("created_at"),
            "thesis_playbook": stored.get("playbook"),
            "thesis_supply_zone": stored.get("supply_zone"),
            "thesis_direction": stored.get("direction"),
        }

    if stored.get("state") == "active" and (resolution or expired):
        store.upsert(
            key,
            {
                **stored,
                "state": resolution or "expired",
                "resolved_at": now_iso,
                "resolved_price": price,
            },
        )

    if not arm:
        store.payload["generated_at"] = now_iso
        store.save()
        return {"thesis_state": "none", "thesis_status": "idle"}

    supply = regime.supply_zone
    thesis_inv = invalidation
    if thesis_inv is None and supply and len(supply) >= 2:
        if regime.bias == "bearish":
            thesis_inv = float(max(supply)) * 1.015
        elif regime.bias == "bullish":
            thesis_inv = float(min(supply)) * 0.985

    store.upsert(
        key,
        {
            "coin": coin.upper(),
            "bias": regime.bias,
            "direction": "short" if regime.bias == "bearish" else ("long" if regime.bias == "bullish" else None),
            "phase": regime.phase,
            "playbook": regime.playbook,
            "supply_zone": supply,
            "invalidation": thesis_inv,
            "state": "active",
            "created_at": now_iso,
            "last_checked_at": now_iso,
            "latest_phase": regime.phase,
            "latest_metrics": regime.metrics,
        },
    )
    store.payload["generated_at"] = now_iso
    store.save()
    return {
        "thesis_state": "active",
        "thesis_status": "armed",
        "thesis_phase": regime.phase,
        "thesis_created_at": now_iso,
        "thesis_playbook": regime.playbook,
        "thesis_supply_zone": supply,
        "thesis_direction": "short" if regime.bias == "bearish" else "long",
    }


def apply_thesis_to_recommendation(
    rec: dict[str, Any],
    thesis_overlay: dict[str, Any],
) -> dict[str, Any]:
    """Elevate watch/enter when an active regime thesis is armed."""
    if thesis_overlay.get("thesis_state") != "active":
        rec["thesis"] = thesis_overlay
        return rec

    direction = thesis_overlay.get("thesis_direction")
    if rec.get("action") == "stand_aside" and direction in {"long", "short"}:
        rec["action"] = "watch"
        rec["direction"] = direction
        rec["primary_source"] = "regime_thesis"
        rec["confidence"] = max(float(rec.get("confidence") or 0), 0.68)
        rec["regime_phase"] = thesis_overlay.get("thesis_phase") or rec.get("regime_phase")
        rec["playbook"] = thesis_overlay.get("thesis_playbook") or rec.get("playbook")
        supply = thesis_overlay.get("thesis_supply_zone")
        if supply and not rec.get("entry_zone"):
            rec["entry_zone"] = list(supply)
        rec["reasons"] = list(rec.get("reasons") or []) + [
            f"Active regime thesis ({thesis_overlay.get('thesis_status')}) — {thesis_overlay.get('thesis_playbook', '')[:80]}"
        ]
    elif rec.get("action") == "watch" and thesis_overlay.get("thesis_status") == "holding":
        rec["reasons"] = list(rec.get("reasons") or []) + [
            "Regime thesis holding — prior COT-led leg still valid on structure"
        ]

    rec["thesis"] = thesis_overlay
    return rec