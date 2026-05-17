from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TrendConfig:
    ema_fast: int
    ema_slow: int
    min_slope_bps: float
    max_setup_ema_gap_intraday: float
    min_daily_ema_gap_intraday: float
    min_daily_ema_gap_intraday_underextended: float
    max_daily_ema_gap_swing_short: float
    min_daily_ema_gap_intraday_late_long: float
    max_setup_ema_gap_intraday_late_long: float


@dataclass(frozen=True)
class BreakoutConfig:
    lookback_bars: int
    recent_breakout_bars: int
    buffer_atr: float
    retest_tolerance: float
    pending_distance_atr: float
    extended_range_fraction: float
    min_retest_hours: int
    max_retest_hours: int


@dataclass(frozen=True)
class VolatilityConfig:
    atr_fast: int
    atr_slow: int
    min_atr_ratio: float
    min_range_expansion: float
    expansion_atr_floor: float
    min_atr_ratio_swing: float
    min_atr_ratio_intraday_underextended: float
    min_range_expansion_swing_short: float


@dataclass(frozen=True)
class StructureConfig:
    swing_bars: int
    lookback_bars: int


@dataclass(frozen=True)
class ParticipationConfig:
    min_volume_ratio: float
    min_volume_ratio_swing: float
    min_oi_change_pct: float
    max_funding_long: float
    min_funding_short: float
    squeeze_abs_funding: float
    squeeze_oi_change_pct: float


@dataclass(frozen=True)
class ExecutionConfig:
    stop_atr_buffer: float
    invalidation_fallback_pct: float
    target_atr_multiple: float
    min_expected_move_pct: float
    max_expected_move_pct: float
    max_holding_bars: int


@dataclass(frozen=True)
class CadenceConfig:
    baseline_trades_per_month: int
    expansion_trades_per_month: int
    quiet_threshold_buffer: int
    expansion_threshold_buffer: int
    min_score_floor: int
    expansion_min_confirmed: int
    expansion_min_tradeable: int
    expansion_min_symbols: int


@dataclass(frozen=True)
class RiskConfig:
    default_risk_pct: float
    min_risk_pct: float
    max_risk_pct: float
    btc_default_leverage: float
    btc_max_leverage: float
    eth_default_leverage: float
    eth_max_leverage: float
    fallback_default_leverage: float
    fallback_max_leverage: float

    def leverage_profile(self, symbol: str) -> tuple[float, float]:
        normalized = symbol.upper().replace("USDT", "")
        if normalized == "BTC":
            return self.btc_default_leverage, self.btc_max_leverage
        if normalized == "ETH":
            return self.eth_default_leverage, self.eth_max_leverage
        return self.fallback_default_leverage, self.fallback_max_leverage


@dataclass(frozen=True)
class ScoreWeights:
    trend_alignment: int
    breakout_quality: int
    volatility_regime: int
    participation: int
    risk_efficiency: int


@dataclass(frozen=True)
class TheoryOverlayConfig:
    enabled: bool = True
    min_weekly_velocity: float = 1.2
    allow_range_breakout_bias: bool = True
    block_weekly_neutral_swing: bool = True
    weekly_neutral_swing_min_expected_move_pct: float = 0.10
    require_daily_confirmation: bool = True
    block_climax_cooldown: bool = True
    climax_atr_window: int = 14
    climax_mult: float = 3.0
    climax_cooldown_bars: int = 5
    block_chase_on_swing: bool = True
    chase_min_expected_move_pct: float = 0.10
    chase_min_retrace: float = 0.50
    chase_max_retrace: float = 0.95


@dataclass(frozen=True)
class MomentumConfig:
    score_tradeable_threshold: int
    min_rr: float
    trend: TrendConfig
    breakout: BreakoutConfig
    volatility: VolatilityConfig
    structure: StructureConfig
    participation: ParticipationConfig
    execution: ExecutionConfig
    theory_overlay: TheoryOverlayConfig
    cadence: CadenceConfig
    risk: RiskConfig
    weights: ScoreWeights


def _config_path(config_path: str | Path | None = None) -> Path:
    if config_path is not None:
        return Path(config_path)
    return Path(__file__).with_name("defaults.json")


def _read_payload(config_path: str | Path | None = None) -> dict[str, Any]:
    path = _config_path(config_path)
    return json.loads(path.read_text())


def _build_theory_overlay_config(payload: dict[str, Any]) -> TheoryOverlayConfig:
    defaults = TheoryOverlayConfig()
    values = {
        "enabled": payload.get("enabled", defaults.enabled),
        "min_weekly_velocity": payload.get("min_weekly_velocity", defaults.min_weekly_velocity),
        "allow_range_breakout_bias": payload.get("allow_range_breakout_bias", defaults.allow_range_breakout_bias),
        "block_weekly_neutral_swing": payload.get("block_weekly_neutral_swing", defaults.block_weekly_neutral_swing),
        "weekly_neutral_swing_min_expected_move_pct": payload.get(
            "weekly_neutral_swing_min_expected_move_pct",
            defaults.weekly_neutral_swing_min_expected_move_pct,
        ),
        "require_daily_confirmation": payload.get("require_daily_confirmation", defaults.require_daily_confirmation),
        "block_climax_cooldown": payload.get("block_climax_cooldown", defaults.block_climax_cooldown),
        "climax_atr_window": payload.get("climax_atr_window", defaults.climax_atr_window),
        "climax_mult": payload.get("climax_mult", defaults.climax_mult),
        "climax_cooldown_bars": payload.get("climax_cooldown_bars", defaults.climax_cooldown_bars),
        "block_chase_on_swing": payload.get("block_chase_on_swing", defaults.block_chase_on_swing),
        "chase_min_expected_move_pct": payload.get(
            "chase_min_expected_move_pct",
            defaults.chase_min_expected_move_pct,
        ),
        "chase_min_retrace": payload.get("chase_min_retrace", defaults.chase_min_retrace),
        "chase_max_retrace": payload.get("chase_max_retrace", defaults.chase_max_retrace),
    }
    return TheoryOverlayConfig(**values)


def load_momentum_config(config_path: str | Path | None = None) -> MomentumConfig:
    payload = _read_payload(config_path)
    return MomentumConfig(
        score_tradeable_threshold=int(payload["score_tradeable_threshold"]),
        min_rr=float(payload["min_rr"]),
        trend=TrendConfig(**payload["trend"]),
        breakout=BreakoutConfig(**payload["breakout"]),
        volatility=VolatilityConfig(**payload["volatility"]),
        structure=StructureConfig(**payload["structure"]),
        participation=ParticipationConfig(**payload["participation"]),
        execution=ExecutionConfig(**payload["execution"]),
        cadence=CadenceConfig(**payload["cadence"]),
        risk=RiskConfig(**payload["risk"]),
        weights=ScoreWeights(**payload["weights"]),
        theory_overlay=_build_theory_overlay_config(
            payload.get("theory_overlay") or {}),
    )
