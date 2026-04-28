from __future__ import annotations

from dataclasses import dataclass

from trading.crypto.momentum.config import MomentumConfig


@dataclass(frozen=True)
class ScoreBreakdown:
    trend_alignment: int
    breakout_quality: int
    volatility_regime: int
    participation: int
    risk_efficiency: int

    @property
    def total(self) -> int:
        return (
            self.trend_alignment
            + self.breakout_quality
            + self.volatility_regime
            + self.participation
            + self.risk_efficiency
        )

    def to_dict(self) -> dict[str, int]:
        return {
            "trend_alignment": self.trend_alignment,
            "breakout_quality": self.breakout_quality,
            "volatility_regime": self.volatility_regime,
            "participation": self.participation,
            "risk_efficiency": self.risk_efficiency,
            "total": self.total,
        }


def _bucket(weight: int, value: float) -> int:
    clamped = max(0.0, min(value, 1.0))
    return int(round(weight * clamped))


def risk_efficiency_score(rr_estimated: float, expected_move_pct: float, stop_pct: float, config: MomentumConfig) -> float:
    rr_component = min(rr_estimated / max(config.min_rr, 0.1), 1.5) / 1.5
    move_component = min(
        expected_move_pct / max(config.execution.min_expected_move_pct, 0.001),
        1.4,
    ) / 1.4
    stop_component = 1.0 if stop_pct <= expected_move_pct / max(config.min_rr, 0.1) else 0.45
    return max(0.0, min((0.5 * rr_component) + (0.3 * move_component) + (0.2 * stop_component), 1.0))


def build_score_breakdown(
    *,
    trend_score: float,
    breakout_score: float,
    volatility_score: float,
    participation_score: float,
    rr_estimated: float,
    expected_move_pct: float,
    stop_pct: float,
    config: MomentumConfig,
) -> ScoreBreakdown:
    weights = config.weights
    return ScoreBreakdown(
        trend_alignment=_bucket(weights.trend_alignment, trend_score),
        breakout_quality=_bucket(weights.breakout_quality, breakout_score),
        volatility_regime=_bucket(weights.volatility_regime, volatility_score),
        participation=_bucket(weights.participation, participation_score),
        risk_efficiency=_bucket(
            weights.risk_efficiency,
            risk_efficiency_score(rr_estimated, expected_move_pct, stop_pct, config),
        ),
    )