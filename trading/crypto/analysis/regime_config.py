"""Load regime detection thresholds."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RegimeConfig:
    ema_fast: int
    ema_slow: int
    cot_crowded_percentile_min: float
    min_drawdown_from_high: float
    leg_down_drawdown: float
    relief_bounce_min: float
    relief_bounce_max: float
    supply_ema_proximity: float
    thesis_max_age_hours: int


def load_regime_config(path: str | Path | None = None) -> RegimeConfig:
    config_path = Path(path) if path else Path(__file__).with_name("regime_defaults.json")
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    return RegimeConfig(
        ema_fast=int(payload["ema_fast"]),
        ema_slow=int(payload["ema_slow"]),
        cot_crowded_percentile_min=float(payload["cot_crowded_percentile_min"]),
        min_drawdown_from_high=float(payload["min_drawdown_from_high"]),
        leg_down_drawdown=float(payload["leg_down_drawdown"]),
        relief_bounce_min=float(payload["relief_bounce_min"]),
        relief_bounce_max=float(payload["relief_bounce_max"]),
        supply_ema_proximity=float(payload["supply_ema_proximity"]),
        thesis_max_age_hours=int(payload["thesis_max_age_hours"]),
    )