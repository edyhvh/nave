"""Macro regime phases for COT-led trends (bear and bull, BTC/ETH)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from trading.crypto.analysis.regime_config import RegimeConfig, load_regime_config
from trading.crypto.cot.cot_analyzer import COTBias
from trading.crypto.cot.context import cot_side_from_bias


@dataclass(frozen=True)
class RegimeAssessment:
    phase: str
    bias: str
    confidence: float
    playbook: str
    supply_zone: list[float] | None
    continuation_trigger: str | None
    metrics: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "bias": self.bias,
            "confidence": round(self.confidence, 3),
            "playbook": self.playbook,
            "supply_zone": self.supply_zone,
            "continuation_trigger": self.continuation_trigger,
            "metrics": {k: round(v, 4) for k, v in self.metrics.items()},
        }


def _ema(frame: pd.DataFrame, span: int) -> float:
    return float(frame["close"].ewm(span=span, adjust=False).mean().iloc[-1])


def _bear_assessment(
    *,
    cfg: RegimeConfig,
    cot_conf: float,
    cot_pct: float,
    close_d: float,
    close_s: float,
    ema_fast_d: float,
    ema_slow_d: float,
    ema_fast_s: float,
    high_28d: float,
    low_14d: float,
    drawdown_from_high: float,
    bounce_from_low: float,
    daily_bear: bool,
    setup_bounce: bool,
    plan_side: str,
    plan_status: str,
    plan_tradeable: bool,
    metrics: dict[str, float],
) -> RegimeAssessment:
    supply_hi = max(high_28d * 0.98, ema_fast_s * 1.01, close_s)
    supply_lo = min(ema_fast_s * 0.99, close_s * 0.995)
    supply = [float(supply_lo), float(supply_hi)]

    if plan_tradeable and plan_side == "short":
        return RegimeAssessment(
            phase="continuation_short",
            bias="bearish",
            confidence=max(cot_conf, 0.75),
            playbook="COT bearish + confirmed 4H/1H short — trend continuation entry.",
            supply_zone=supply,
            continuation_trigger="4H breakdown retest confirmed on 1H",
            metrics=metrics,
        )
    if plan_status == "confirmed" and plan_side == "short":
        return RegimeAssessment(
            phase="breakdown_retest",
            bias="bearish",
            confidence=max(cot_conf, 0.65),
            playbook="Breakdown confirmed — add on retest reject or when score clears threshold.",
            supply_zone=supply,
            continuation_trigger="1H close below breakdown after retest",
            metrics=metrics,
        )
    if setup_bounce and cfg.relief_bounce_min <= bounce_from_low <= cfg.relief_bounce_max:
        return RegimeAssessment(
            phase="relief_rally_fade",
            bias="bearish",
            confidence=max(cot_conf, 0.72),
            playbook=(
                "Crowded spec long (COT bearish): relief rally into supply — "
                "fade the bounce; perps on reject, options bear put spreads."
            ),
            supply_zone=supply,
            continuation_trigger="1H rejection in supply + 4H breakdown hold",
            metrics=metrics,
        )
    if daily_bear or drawdown_from_high >= cfg.leg_down_drawdown:
        return RegimeAssessment(
            phase="leg_down",
            bias="bearish",
            confidence=max(cot_conf, 0.6),
            playbook="COT-led bear leg — trail shorts; avoid fresh longs until COT resets.",
            supply_zone=supply,
            continuation_trigger="Fresh 4H breakdown after consolidation",
            metrics=metrics,
        )
    return RegimeAssessment(
        phase="cot_bear_bias",
        bias="bearish",
        confidence=cot_conf,
        playbook="COT bearish — stalk 4H lower-high breakdowns; options favor put structures.",
        supply_zone=None,
        continuation_trigger="4H lower-high + breakdown",
        metrics=metrics,
    )


def _bull_assessment(
    *,
    cfg: RegimeConfig,
    cot_conf: float,
    cot_pct: float,
    close_d: float,
    close_s: float,
    ema_fast_d: float,
    ema_slow_d: float,
    ema_fast_s: float,
    low_28d: float,
    high_14d: float,
    rally_from_low: float,
    pullback_from_high: float,
    daily_bull: bool,
    setup_pullback: bool,
    plan_side: str,
    plan_status: str,
    plan_tradeable: bool,
    metrics: dict[str, float],
) -> RegimeAssessment:
    demand_lo = min(low_28d * 1.02, ema_fast_s * 0.99, close_s)
    demand_hi = max(ema_fast_s * 1.01, close_s * 1.005)
    demand = [float(demand_lo), float(demand_hi)]

    if plan_tradeable and plan_side == "long":
        return RegimeAssessment(
            phase="continuation_long",
            bias="bullish",
            confidence=max(cot_conf, 0.75),
            playbook="COT bullish + confirmed 4H/1H long — trend continuation entry.",
            supply_zone=demand,
            continuation_trigger="4H breakout retest confirmed on 1H",
            metrics=metrics,
        )
    if plan_status == "confirmed" and plan_side == "long":
        return RegimeAssessment(
            phase="breakout_retest_long",
            bias="bullish",
            confidence=max(cot_conf, 0.65),
            playbook="Breakout confirmed — add on retest hold or when score clears threshold.",
            supply_zone=demand,
            continuation_trigger="1H close above breakout after retest",
            metrics=metrics,
        )
    if setup_pullback and cfg.relief_bounce_min <= pullback_from_high <= cfg.relief_bounce_max:
        return RegimeAssessment(
            phase="pullback_buy",
            bias="bullish",
            confidence=max(cot_conf, 0.72),
            playbook=(
                "Crowded spec short (COT bullish): pullback into demand — "
                "buy the dip; perps on hold, options bull call spreads."
            ),
            supply_zone=demand,
            continuation_trigger="1H hold in demand + 4H breakout support",
            metrics=metrics,
        )
    if daily_bull or rally_from_low >= cfg.leg_down_drawdown:
        return RegimeAssessment(
            phase="leg_up",
            bias="bullish",
            confidence=max(cot_conf, 0.6),
            playbook="COT-led bull leg — trail longs; avoid fresh shorts until COT resets.",
            supply_zone=demand,
            continuation_trigger="Fresh 4H breakout after consolidation",
            metrics=metrics,
        )
    return RegimeAssessment(
        phase="cot_bull_bias",
        bias="bullish",
        confidence=cot_conf,
        playbook="COT bullish — stalk 4H higher-low breakouts; options favor call structures.",
        supply_zone=None,
        continuation_trigger="4H higher-low + breakout",
        metrics=metrics,
    )


def assess_regime(
    *,
    daily: pd.DataFrame,
    setup: pd.DataFrame,
    cot_bias: COTBias | None,
    best_plan: dict[str, Any] | None,
    config: RegimeConfig | None = None,
) -> RegimeAssessment:
    """Classify COT-led bear or bull phase for BTC/ETH."""
    cfg = config or load_regime_config()
    cot_side = cot_side_from_bias(cot_bias)
    cot_conf = float(cot_bias.confidence) if cot_bias else 0.0
    cot_pct = float(cot_bias.historical_percentile or 0) if cot_bias else 0.0

    if daily.empty or setup.empty:
        return RegimeAssessment(
            phase="unknown",
            bias="neutral",
            confidence=0.0,
            playbook="Insufficient price history.",
            supply_zone=None,
            continuation_trigger=None,
            metrics={},
        )

    close_d = float(daily["close"].iloc[-1])
    close_s = float(setup["close"].iloc[-1])
    ema_fast_d = _ema(daily, cfg.ema_fast)
    ema_slow_d = _ema(daily, cfg.ema_slow)
    ema_fast_s = _ema(setup, cfg.ema_fast)

    high_28d = float(daily["high"].tail(28).max())
    low_28d = float(daily["low"].tail(28).min())
    low_14d = float(setup["low"].tail(42).min())
    high_14d = float(setup["high"].tail(42).max())
    low_10d_d = float(daily["low"].tail(10).min())

    drawdown_from_high = (high_28d - close_d) / high_28d if high_28d else 0.0
    rally_from_low = (close_d - low_28d) / low_28d if low_28d else 0.0
    bounce_from_low = (close_s - low_14d) / low_14d if low_14d else 0.0
    pullback_from_high = (high_14d - close_s) / high_14d if high_14d else 0.0
    bounce_daily = (close_d - low_10d_d) / low_10d_d if low_10d_d else 0.0

    daily_bear = close_d < ema_slow_d and ema_fast_d < ema_slow_d
    daily_bull = close_d > ema_slow_d and ema_fast_d > ema_slow_d
    setup_bounce = close_s >= ema_fast_s * cfg.supply_ema_proximity and close_d < ema_slow_d
    setup_pullback = close_s <= ema_fast_s / cfg.supply_ema_proximity and close_d > ema_slow_d

    crowded_cot = cot_pct >= cfg.cot_crowded_percentile_min

    metrics = {
        "drawdown_from_28d_high_pct": drawdown_from_high * 100,
        "rally_from_28d_low_pct": rally_from_low * 100,
        "bounce_from_14d_low_pct": bounce_from_low * 100,
        "pullback_from_14d_high_pct": pullback_from_high * 100,
        "daily_bounce_pct": bounce_daily * 100,
        "cot_percentile": cot_pct,
    }

    plan_side = str((best_plan or {}).get("side") or "").lower()
    plan_status = str((best_plan or {}).get("setup_status") or "")
    plan_tradeable = bool((best_plan or {}).get("tradeable"))
    mf_watch = bool(((best_plan or {}).get("diagnostics") or {}).get("momentum_failure_watch"))

    if cot_side == "short" and crowded_cot and drawdown_from_high >= cfg.min_drawdown_from_high:
        return _bear_assessment(
            cfg=cfg,
            cot_conf=cot_conf,
            cot_pct=cot_pct,
            close_d=close_d,
            close_s=close_s,
            ema_fast_d=ema_fast_d,
            ema_slow_d=ema_slow_d,
            ema_fast_s=ema_fast_s,
            high_28d=high_28d,
            low_14d=low_14d,
            drawdown_from_high=drawdown_from_high,
            bounce_from_low=bounce_from_low,
            daily_bear=daily_bear,
            setup_bounce=setup_bounce,
            plan_side=plan_side,
            plan_status=plan_status,
            plan_tradeable=plan_tradeable,
            metrics=metrics,
        )

    if cot_side == "long" and crowded_cot and rally_from_low >= cfg.min_drawdown_from_high:
        return _bull_assessment(
            cfg=cfg,
            cot_conf=cot_conf,
            cot_pct=cot_pct,
            close_d=close_d,
            close_s=close_s,
            ema_fast_d=ema_fast_d,
            ema_slow_d=ema_slow_d,
            ema_fast_s=ema_fast_s,
            low_28d=low_28d,
            high_14d=high_14d,
            rally_from_low=rally_from_low,
            pullback_from_high=pullback_from_high,
            daily_bull=daily_bull,
            setup_pullback=setup_pullback,
            plan_side=plan_side,
            plan_status=plan_status,
            plan_tradeable=plan_tradeable,
            metrics=metrics,
        )

    if mf_watch and plan_side == "short":
        return RegimeAssessment(
            phase="failed_impulse_short",
            bias="bearish",
            confidence=0.55,
            playbook="Failed bullish impulse — momentum failure watch favors shorts.",
            supply_zone=None,
            continuation_trigger="Daily fast EMA loss + 4H breakdown",
            metrics=metrics,
        )

    return RegimeAssessment(
        phase="neutral",
        bias="neutral",
        confidence=0.0,
        playbook="No COT-led regime — use standard momentum confirmation on 4H/1H.",
        supply_zone=None,
        continuation_trigger=None,
        metrics=metrics,
    )