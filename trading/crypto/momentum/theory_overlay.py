from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from trading.crypto.momentum.config import TheoryOverlayConfig
from trading.crypto.theory_v2 import (
    chase_gate,
    daily_confirms,
    detect_climax_cooldown,
    momentum_bias,
    range_breakout_bias,
)


@dataclass(frozen=True)
class TheoryOverlayAssessment:
    passed: bool
    stage: str
    bias: str
    bias_source: str
    reason: str
    weekly_velocity_atr: float | None = None
    retrace_fraction: float | None = None
    bars_since_climax: int | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "stage": self.stage,
            "bias": self.bias,
            "bias_source": self.bias_source,
            "reason": self.reason,
            "weekly_velocity_atr": round(self.weekly_velocity_atr, 3)
            if self.weekly_velocity_atr is not None
            else None,
            "retrace_fraction": round(self.retrace_fraction, 4)
            if self.retrace_fraction is not None
            else None,
            "bars_since_climax": self.bars_since_climax,
        }


def build_weekly_frame(daily: pd.DataFrame) -> pd.DataFrame:
    if daily.empty:
        return daily.copy()
    weekly = daily.resample("W-SUN").agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
    )
    return weekly.dropna(subset=["open", "high", "low", "close"])


def evaluate_theory_overlay(
    *,
    side: str,
    daily: pd.DataFrame,
    setup: pd.DataFrame,
    expected_move_pct: float,
    config: TheoryOverlayConfig,
    weekly: pd.DataFrame | None = None,
) -> TheoryOverlayAssessment:
    if not config.enabled:
        return TheoryOverlayAssessment(
            passed=True,
            stage="disabled",
            bias=side,
            bias_source="disabled",
            reason="theory overlay disabled",
        )

    weekly_frame = weekly if weekly is not None else build_weekly_frame(daily)
    bias, velocity = momentum_bias(
        weekly_frame,
        min_velocity=config.min_weekly_velocity,
    )
    bias_source = "momentum"
    if bias == "neutral" and config.allow_range_breakout_bias:
        breakout_bias, _ = range_breakout_bias(weekly_frame)
        if breakout_bias != "neutral":
            bias = breakout_bias
            bias_source = "range_breakout"

    if bias == "neutral":
        if (
            config.block_weekly_neutral_swing
            and expected_move_pct >= config.weekly_neutral_swing_min_expected_move_pct
        ):
            return TheoryOverlayAssessment(
                passed=False,
                stage="weekly_neutral_swing",
                bias=bias,
                bias_source=bias_source,
                reason=(
                    "weekly theory bias is neutral; swing exposure requires a clear weekly tailwind"
                ),
                weekly_velocity_atr=velocity,
            )
        return TheoryOverlayAssessment(
            passed=True,
            stage="weekly_neutral",
            bias=bias,
            bias_source=bias_source,
            reason="weekly theory bias is neutral; defer to momentum model",
            weekly_velocity_atr=velocity,
        )

    if bias != side:
        return TheoryOverlayAssessment(
            passed=False,
            stage="weekly_bias",
            bias=bias,
            bias_source=bias_source,
            reason=f"weekly theory bias {bias} conflicts with {side}",
            weekly_velocity_atr=velocity,
        )

    if config.require_daily_confirmation and not daily_confirms(daily, bias):
        return TheoryOverlayAssessment(
            passed=False,
            stage="daily_confirmation",
            bias=bias,
            bias_source=bias_source,
            reason="daily theory confirmation is missing",
            weekly_velocity_atr=velocity,
        )

    if config.block_climax_cooldown:
        in_cooldown, bars_since = detect_climax_cooldown(
            daily,
            atr_window=config.climax_atr_window,
            climax_mult=config.climax_mult,
            cooldown_bars=config.climax_cooldown_bars,
        )
        if in_cooldown:
            return TheoryOverlayAssessment(
                passed=False,
                stage="climax_cooldown",
                bias=bias,
                bias_source=bias_source,
                reason=f"daily climax cooldown active ({bars_since} bars since climax)",
                weekly_velocity_atr=velocity,
                bars_since_climax=bars_since,
            )

    retrace_fraction: float | None = None
    if config.block_chase_on_swing and expected_move_pct >= config.chase_min_expected_move_pct:
        passes, retrace_fraction, reason = chase_gate(
            daily,
            bias,
            min_retrace=config.chase_min_retrace,
            max_retrace=config.chase_max_retrace,
        )
        if not passes:
            if retrace_fraction is not None and retrace_fraction < 0:
                return TheoryOverlayAssessment(
                    passed=True,
                    stage="chase_overshoot",
                    bias=bias,
                    bias_source=bias_source,
                    reason="price extended beyond the prior impulse extreme; do not map pullback chase veto onto breakout continuation",
                    weekly_velocity_atr=velocity,
                    retrace_fraction=retrace_fraction,
                )
            return TheoryOverlayAssessment(
                passed=False,
                stage="chase_gate",
                bias=bias,
                bias_source=bias_source,
                reason=reason,
                weekly_velocity_atr=velocity,
                retrace_fraction=retrace_fraction,
            )

    return TheoryOverlayAssessment(
        passed=True,
        stage="passed",
        bias=bias,
        bias_source=bias_source,
        reason="theory overlay passed",
        weekly_velocity_atr=velocity,
        retrace_fraction=retrace_fraction,
    )