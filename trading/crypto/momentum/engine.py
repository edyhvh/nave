from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from trading.crypto.momentum.config import MomentumConfig, load_momentum_config
from trading.crypto.momentum.execution_plan import TradePlan, holding_horizon, recommend_position_sizing
from trading.crypto.momentum.filters import (
    BreakoutAssessment,
    ParticipationAssessment,
    TrendAssessment,
    VolatilityAssessment,
    assess_breakout,
    assess_participation,
    assess_trend,
    assess_volatility,
    diagnostics_payload,
    normalize_frame,
)
from trading.crypto.momentum.scoring import ScoreBreakdown, build_score_breakdown
from trading.crypto.momentum.structure import (
    RetestAssessment,
    StructureAssessment,
    assess_retest,
    assess_structure,
    build_invalidation,
)
from trading.crypto.momentum.cot_overlay import CotOverlayAssessment, evaluate_cot_overlay
from trading.crypto.momentum.theory_overlay import (
    TheoryOverlayAssessment,
    build_weekly_frame,
    evaluate_theory_overlay,
)
from trading.crypto.theory_v2 import momentum_bias


@dataclass(frozen=True)
class MomentumEvaluation:
    plan: TradePlan
    score_breakdown: ScoreBreakdown


class MomentumSetupEngine:
    def __init__(self, config: MomentumConfig | None = None):
        self.config = config or load_momentum_config()

    def evaluate_symbol(
        self,
        *,
        symbol: str,
        daily_frame: pd.DataFrame,
        setup_frame: pd.DataFrame,
        trigger_frame: pd.DataFrame,
        weekly_frame: pd.DataFrame | None = None,
        open_interest: pd.DataFrame | pd.Series | None = None,
        funding_rate: float | None = None,
        account_equity: float = 10000.0,
        risk_pct: float | None = None,
        side: str | None = None,
        as_of: pd.Timestamp | None = None,
        cot_overlay_mode: str = "neutral",
    ) -> list[TradePlan]:
        """Evaluate momentum setup geometry.

        ``cot_overlay_mode`` is ``neutral`` by default for deterministic engine
        and unit-test use. Live operator paths pass ``live`` from
        ``MomentumMarketService``; historical backtests pass ``historical``.
        """
        if cot_overlay_mode not in {"neutral", "historical", "live"}:
            raise ValueError("cot_overlay_mode must be neutral, historical, or live")
        daily = normalize_frame(daily_frame)
        setup = normalize_frame(setup_frame)
        trigger = normalize_frame(trigger_frame)
        weekly = normalize_frame(weekly_frame) if weekly_frame is not None else None
        sides = [side.lower()] if side else ["long", "short"]
        plans: list[TradePlan] = []
        for requested_side in sides:
            evaluation = self._evaluate_side(
                symbol=symbol,
                side=requested_side,
                weekly=weekly,
                daily=daily,
                setup=setup,
                trigger=trigger,
                open_interest=open_interest,
                funding_rate=funding_rate,
                account_equity=account_equity,
                risk_pct=risk_pct or self.config.risk.default_risk_pct,
                as_of=as_of,
                cot_overlay_mode=cot_overlay_mode,
            )
            plans.append(evaluation.plan)
        return plans

    def _evaluate_side(
        self,
        *,
        symbol: str,
        side: str,
        weekly: pd.DataFrame | None,
        daily: pd.DataFrame,
        setup: pd.DataFrame,
        trigger: pd.DataFrame,
        open_interest: pd.DataFrame | pd.Series | None,
        funding_rate: float | None,
        account_equity: float,
        risk_pct: float,
        as_of: pd.Timestamp | None = None,
        cot_overlay_mode: str = "neutral",
    ) -> MomentumEvaluation:
        daily_trend = assess_trend(daily, side, self.config)
        setup_trend = assess_trend(setup, side, self.config)
        structure = assess_structure(setup, side, self.config)
        breakout = assess_breakout(setup, side, self.config)
        retest = self._assess_retest(trigger, breakout, side)
        volatility = self._assess_volatility(setup, breakout)
        participation = assess_participation(
            breakout,
            side,
            self.config,
            open_interest=open_interest,
            funding_rate=funding_rate,
        )
        daily_ema_gap_pct = self._ema_gap_pct(daily)
        setup_ema_gap_pct = self._ema_gap_pct(setup)

        setup_status = self._status_from_assessments(
            daily_trend=daily_trend,
            setup_trend=setup_trend,
            structure=structure,
            breakout=breakout,
            retest=retest,
            participation=participation,
        )

        entry_price = self._entry_price(side, trigger, breakout, retest)
        invalidation, invalidation_fallback_used = self._invalidation(
            trigger, side, breakout, retest, entry_price)
        expected_move_pct, stop_pct, rr_estimated = self._reward_profile(
            entry_price=entry_price,
            invalidation=invalidation,
            breakout=breakout,
            volatility=volatility,
        )
        theory_overlay = evaluate_theory_overlay(
            side=side,
            weekly=weekly,
            daily=daily,
            setup=setup,
            expected_move_pct=expected_move_pct,
            config=self.config.theory_overlay,
        )
        if cot_overlay_mode == "neutral":
            cot_overlay = CotOverlayAssessment(
                passed=True,
                aligned=False,
                score_bonus=0,
                permission="allow",
                contrarian_bias="neutral",
                reason="COT overlay neutral for direct engine evaluation",
            )
        else:
            cot_overlay = evaluate_cot_overlay(
                side=side,
                symbol=symbol,
                config=self.config.cot_overlay,
                as_of=as_of,
                mode="historical" if cot_overlay_mode == "historical" else "live",
            )
        momentum_failure_watch = self._momentum_failure_watch_accepts(
            side=side,
            daily_trend=daily_trend,
            setup_trend=setup_trend,
            structure=structure,
            breakout=breakout,
            retest=retest,
            volatility=volatility,
            participation=participation,
            theory_overlay=theory_overlay,
            weekly=weekly,
            daily=daily,
            expected_move_pct=expected_move_pct,
        )
        if momentum_failure_watch and setup_status == "invalid":
            setup_status = "confirmed"
        daily_trend_score = daily_trend.score
        if momentum_failure_watch:
            daily_trend_score = max(daily_trend_score, 0.75)
        structure_score = structure.score
        if momentum_failure_watch:
            structure_score = max(structure_score, 0.8)
        score_breakdown = build_score_breakdown(
            trend_score=(
                (daily_trend_score + setup_trend.score + structure_score) / 3.0),
            breakout_score=self._breakout_score(breakout, retest),
            volatility_score=volatility.score,
            participation_score=participation.score,
            rr_estimated=rr_estimated,
            expected_move_pct=expected_move_pct,
            stop_pct=stop_pct,
            config=self.config,
        )
        confidence_score = min(100, score_breakdown.total + cot_overlay.score_bonus)
        tradeable = self._is_tradeable(
            side=side,
            setup_status=setup_status,
            rr_estimated=rr_estimated,
            expected_move_pct=expected_move_pct,
            score=confidence_score,
            volatility=volatility,
            participation=participation,
            theory_overlay=theory_overlay,
            cot_overlay=cot_overlay,
            momentum_failure_watch=momentum_failure_watch,
            daily_ema_gap_pct=daily_ema_gap_pct,
            setup_ema_gap_pct=setup_ema_gap_pct,
        )
        sizing = recommend_position_sizing(
            symbol=symbol,
            entry_price=entry_price,
            invalidation=invalidation,
            account_equity=account_equity,
            risk_pct=risk_pct,
            config=self.config,
        )
        tp1, tp2, tp3 = self._targets(entry_price, side, expected_move_pct)
        reasoning = self._reasoning(
            side=side,
            setup_status=setup_status,
            daily_trend=daily_trend,
            setup_trend=setup_trend,
            structure=structure,
            breakout=breakout,
            retest=retest,
            volatility=volatility,
            participation=participation,
            theory_overlay=theory_overlay,
            momentum_failure_watch=momentum_failure_watch,
            rr_estimated=rr_estimated,
            expected_move_pct=expected_move_pct,
        )
        plan = TradePlan(
            symbol=symbol,
            side=side,
            setup_status=setup_status,
            entry_zone=self._entry_zone(side, breakout, entry_price),
            invalidation=invalidation,
            tp1=tp1,
            tp2=tp2,
            tp3=tp3,
            expected_move_pct=expected_move_pct,
            rr_estimated=rr_estimated,
            holding_horizon_estimate=holding_horizon(expected_move_pct),
            confidence_score=confidence_score,
            tradeable=tradeable,
            score_breakdown=score_breakdown.to_dict(),
            reasoning=reasoning,
            sizing=sizing.to_dict(),
            leverage_constraints={
                "recommended": round(sizing.recommended_leverage, 2),
                "max": round(sizing.max_leverage, 2),
            },
            diagnostics=diagnostics_payload(
                daily_trend_slope_bps=round(daily_trend.slope_bps, 2),
                setup_trend_slope_bps=round(setup_trend.slope_bps, 2),
                daily_ema_gap_pct=round(daily_ema_gap_pct, 4) if daily_ema_gap_pct is not None else None,
                setup_ema_gap_pct=round(setup_ema_gap_pct, 4) if setup_ema_gap_pct is not None else None,
                breakout_status=breakout.status,
                breakout_level=round(
                    breakout.breakout_level, 6) if breakout.breakout_level is not None else None,
                breakout_volume_ratio=round(participation.volume_ratio, 3),
                atr_ratio=round(volatility.atr_ratio, 3),
                range_expansion=round(volatility.range_expansion, 3),
                funding_rate=participation.funding_rate,
                oi_change_pct=round(participation.oi_change_pct, 4)
                if participation.oi_change_pct is not None
                else None,
                invalidation_fallback_used=True if invalidation_fallback_used else None,
                momentum_failure_watch=True if momentum_failure_watch else None,
                theory_overlay=theory_overlay.to_dict(),
                cot_overlay=cot_overlay.to_dict(),
            ),
        )
        return MomentumEvaluation(plan=plan, score_breakdown=score_breakdown)

    def _assess_retest(
        self,
        trigger: pd.DataFrame,
        breakout: BreakoutAssessment,
        side: str,
    ) -> RetestAssessment:
        if not breakout.detected or breakout.breakout_index is None or breakout.breakout_level is None:
            return RetestAssessment(
                status="pending" if breakout.near_trigger else "invalid",
                confirmed=False,
                entry_price=None,
                retest_low=None,
                retest_high=None,
                close_above_level=False,
            )
        max_hours = (
            self.config.breakout.max_retest_hours_swing
            if side == "short"
            else self.config.breakout.max_retest_hours
        )
        return assess_retest(
            trigger,
            side,
            breakout.breakout_level,
            breakout.breakout_index,
            self.config,
            max_retest_hours=max_hours,
        )

    def _assess_volatility(
        self,
        setup: pd.DataFrame,
        breakout: BreakoutAssessment,
    ) -> VolatilityAssessment:
        if breakout.breakout_index is None:
            return assess_volatility(setup, setup.index[-1], self.config)
        return assess_volatility(setup, breakout.breakout_index, self.config)

    def _status_from_assessments(
        self,
        *,
        daily_trend: TrendAssessment,
        setup_trend: TrendAssessment,
        structure: StructureAssessment,
        breakout: BreakoutAssessment,
        retest: RetestAssessment,
        participation: ParticipationAssessment,
    ) -> str:
        if participation.crowded or retest.status == "invalid":
            return "invalid"
        if breakout.detected and retest.confirmed and daily_trend.passed and setup_trend.passed and structure.passed:
            return "confirmed"
        if breakout.status == "pending" and daily_trend.passed and setup_trend.passed:
            return "pending"
        return "invalid"

    def _momentum_failure_watch_accepts(
        self,
        *,
        side: str,
        daily_trend: TrendAssessment,
        setup_trend: TrendAssessment,
        structure: StructureAssessment,
        breakout: BreakoutAssessment,
        retest: RetestAssessment,
        volatility: VolatilityAssessment,
        participation: ParticipationAssessment,
        theory_overlay: TheoryOverlayAssessment,
        weekly: pd.DataFrame | None,
        daily: pd.DataFrame,
        expected_move_pct: float,
    ) -> bool:
        """Promote downside failed-momentum breaks before the daily stack flips.

        The normal daily gate waits for a full bearish EMA stack. After a
        failed bullish impulse, that is often too late: price first loses the
        daily fast EMA, weekly velocity decays to neutral, and a 4H breakdown
        confirms on a 1H retest. This watch is intentionally short-only because
        it models distribution after a failed long impulse, not trend chasing.
        """
        weekly_velocity = theory_overlay.weekly_velocity_atr
        prior_long_velocity = self._recent_weekly_velocity_peak(weekly, daily)
        return (
            side == "short"
            and not structure.passed
            and setup_trend.passed
            and breakout.detected
            and retest.confirmed
            and volatility.passed
            and theory_overlay.passed
            and theory_overlay.stage == "weekly_neutral"
            and weekly_velocity is not None
            and abs(weekly_velocity) <= 0.8
            and prior_long_velocity >= 1.5
            and self._daily_fast_ema_failed(daily_trend)
            and participation.volume_ratio >= 0.75
            and expected_move_pct <= self.config.theory_overlay.weekly_neutral_swing_min_expected_move_pct
        )

    def _daily_fast_ema_failed(self, daily_trend: TrendAssessment) -> bool:
        return daily_trend.slope_bps <= -self.config.trend.min_slope_bps

    def _recent_weekly_velocity_peak(self, weekly: pd.DataFrame | None, daily: pd.DataFrame) -> float:
        weekly_frame = weekly if weekly is not None else build_weekly_frame(daily)
        if weekly_frame.empty:
            return 0.0
        peaks: list[float] = []
        for offset in range(1, min(7, len(weekly_frame))):
            _bias, velocity = momentum_bias(
                weekly_frame.iloc[: -offset],
                min_velocity=self.config.theory_overlay.min_weekly_velocity,
            )
            if velocity is not None:
                peaks.append(float(velocity))
        return max(peaks) if peaks else 0.0

    def _entry_price(
        self,
        side: str,
        trigger: pd.DataFrame,
        breakout: BreakoutAssessment,
        retest: RetestAssessment,
    ) -> float:
        if retest.confirmed and breakout.breakout_level is not None:
            tolerance = breakout.breakout_level * self.config.breakout.retest_tolerance
            if side == "long":
                return float(breakout.breakout_level + tolerance)
            return float(breakout.breakout_level - tolerance)
        if retest.entry_price is not None:
            return float(retest.entry_price)
        if breakout.status == "extended" and breakout.breakout_level is not None:
            tolerance = breakout.breakout_level * self.config.breakout.retest_tolerance
            if side == "long":
                return float(breakout.breakout_level + tolerance)
            return float(breakout.breakout_level - tolerance)
        if breakout.breakout_close is not None:
            return float(breakout.breakout_close)
        return float(trigger["close"].iloc[-1])

    def _invalidation(
        self,
        trigger: pd.DataFrame,
        side: str,
        breakout: BreakoutAssessment,
        retest: RetestAssessment,
        entry_price: float,
    ) -> tuple[float, bool]:
        level = breakout.breakout_level if breakout.breakout_level is not None else entry_price
        invalidation = build_invalidation(
            trigger, side, level, retest, self.config)
        fallback_used = False
        if side == "long" and invalidation >= entry_price:
            invalidation = entry_price * (1 - self.config.execution.invalidation_fallback_pct)
            fallback_used = True
        if side == "short" and invalidation <= entry_price:
            invalidation = entry_price * (1 + self.config.execution.invalidation_fallback_pct)
            fallback_used = True
        return float(invalidation), fallback_used

    def _reward_profile(
        self,
        *,
        entry_price: float,
        invalidation: float,
        breakout: BreakoutAssessment,
        volatility: VolatilityAssessment,
    ) -> tuple[float, float, float]:
        stop_pct = abs(entry_price - invalidation) / \
            entry_price if entry_price else 0.0
        range_height = 0.0
        if breakout.range_low is not None and breakout.range_high is not None:
            range_height = abs(breakout.range_high - breakout.range_low)
        measured_move_pct = range_height / entry_price if entry_price else 0.0
        atr_move_pct = (volatility.atr_fast * self.config.execution.target_atr_multiple) / \
            entry_price if entry_price else 0.0
        expected_move_pct = max(
            measured_move_pct,
            atr_move_pct,
            self.config.execution.min_expected_move_pct if breakout.detected else 0.0,
        )
        expected_move_pct = min(
            expected_move_pct, self.config.execution.max_expected_move_pct)
        rr_estimated = expected_move_pct / stop_pct if stop_pct else 0.0
        return float(expected_move_pct), float(stop_pct), float(rr_estimated)

    def _breakout_score(self, breakout: BreakoutAssessment, retest: RetestAssessment) -> float:
        base = 1.0 if breakout.detected else 0.35 if breakout.near_trigger else 0.0
        if breakout.status == "extended":
            base = 0.0
        if retest.confirmed:
            base = min(base + 0.2, 1.0)
        if retest.status == "invalid":
            base *= 0.2
        return base

    def _volatility_allows_trade(
        self,
        *,
        volatility: VolatilityAssessment,
        participation: ParticipationAssessment,
        expected_move_pct: float,
    ) -> bool:
        if volatility.passed:
            return True
        if expected_move_pct >= self.config.execution.min_expected_move_pct and participation.passed:
            return (
                volatility.range_expansion
                >= self.config.volatility.min_range_expansion_trend_override
            )
        return False

    def _is_tradeable(
        self,
        *,
        side: str,
        setup_status: str,
        rr_estimated: float,
        expected_move_pct: float,
        score: int,
        volatility: VolatilityAssessment,
        participation: ParticipationAssessment,
        theory_overlay: TheoryOverlayAssessment,
        cot_overlay: CotOverlayAssessment | None = None,
        momentum_failure_watch: bool = False,
        daily_ema_gap_pct: float | None,
        setup_ema_gap_pct: float | None,
    ) -> bool:
        if cot_overlay is None:
            cot_overlay = CotOverlayAssessment(
                passed=True,
                aligned=False,
                score_bonus=0,
                permission="allow",
                contrarian_bias="neutral",
                reason="COT overlay not supplied",
            )
        cot_cfg = self.config.cot_overlay
        if cot_cfg.enabled:
            score_threshold = (
                cot_cfg.score_threshold_aligned
                if cot_overlay.aligned
                else cot_cfg.score_threshold_default
            )
        else:
            score_threshold = self.config.score_tradeable_threshold
        if momentum_failure_watch:
            score_threshold = min(score_threshold, 74)
        volume_ok = True
        if expected_move_pct >= 0.1:
            volume_ok = participation.volume_ratio >= self.config.participation.min_volume_ratio_swing
        atr_ok = True
        if expected_move_pct >= 0.1:
            atr_ok = volatility.atr_ratio >= self.config.volatility.min_atr_ratio_swing
        intraday_gap_ok = True
        if expected_move_pct < 0.1 and daily_ema_gap_pct is not None and setup_ema_gap_pct is not None:
            intraday_gap_ok = not (
                setup_ema_gap_pct >= self.config.trend.max_setup_ema_gap_intraday
                and daily_ema_gap_pct <= self.config.trend.min_daily_ema_gap_intraday
            )
        intraday_underextended_ok = True
        if expected_move_pct < 0.1 and daily_ema_gap_pct is not None:
            intraday_underextended_ok = not (
                daily_ema_gap_pct <= self.config.trend.min_daily_ema_gap_intraday_underextended
                and volatility.atr_ratio < self.config.volatility.min_atr_ratio_intraday_underextended
            )
        intraday_late_long_ok = True
        if side == "long" and expected_move_pct < 0.1 and daily_ema_gap_pct is not None and setup_ema_gap_pct is not None:
            intraday_late_long_ok = not (
                daily_ema_gap_pct >= self.config.trend.min_daily_ema_gap_intraday_late_long
                and setup_ema_gap_pct <= self.config.trend.max_setup_ema_gap_intraday_late_long
            )
        swing_short_exhaustion_ok = True
        if side == "short" and expected_move_pct >= 0.1 and daily_ema_gap_pct is not None:
            swing_short_exhaustion_ok = not (
                daily_ema_gap_pct >= self.config.trend.max_daily_ema_gap_swing_short
                and volatility.range_expansion < self.config.volatility.min_range_expansion_swing_short
            )
        return (
            setup_status == "confirmed"
            and rr_estimated >= self.config.min_rr
            and expected_move_pct >= self.config.execution.min_expected_move_pct
            and score >= score_threshold
            and self._volatility_allows_trade(
                volatility=volatility,
                participation=participation,
                expected_move_pct=expected_move_pct,
            )
            and volume_ok
            and atr_ok
            and intraday_gap_ok
            and intraday_underextended_ok
            and intraday_late_long_ok
            and swing_short_exhaustion_ok
            and theory_overlay.passed
            and cot_overlay.passed
            and not participation.crowded
        )

    def _ema_gap_pct(self, frame: pd.DataFrame) -> float | None:
        close = float(frame["close"].iloc[-1])
        if not close:
            return None
        fast = float(frame["close"].ewm(span=self.config.trend.ema_fast, adjust=False).mean().iloc[-1])
        return abs(close - fast) / close

    def _targets(self, entry_price: float, side: str, expected_move_pct: float) -> tuple[float, float, float]:
        tp1_pct = min(max(expected_move_pct * 0.5, 0.04), 0.08)
        tp2_pct = expected_move_pct
        tp3_pct = min(expected_move_pct * 1.6,
                      self.config.execution.max_expected_move_pct)
        if side == "long":
            return (
                entry_price * (1 + tp1_pct),
                entry_price * (1 + tp2_pct),
                entry_price * (1 + tp3_pct),
            )
        return (
            entry_price * (1 - tp1_pct),
            entry_price * (1 - tp2_pct),
            entry_price * (1 - tp3_pct),
        )

    def _entry_zone(self, side: str, breakout: BreakoutAssessment, entry_price: float) -> list[float]:
        level = breakout.breakout_level if breakout.breakout_level is not None else entry_price
        tolerance = level * self.config.breakout.retest_tolerance
        if side == "long":
            return [float(level - tolerance), float(max(level + tolerance, entry_price))]
        low = min(level - tolerance, entry_price)
        high = level + tolerance
        return [float(low), float(high)]

    def _reasoning(
        self,
        *,
        side: str,
        setup_status: str,
        daily_trend: TrendAssessment,
        setup_trend: TrendAssessment,
        structure: StructureAssessment,
        breakout: BreakoutAssessment,
        retest: RetestAssessment,
        volatility: VolatilityAssessment,
        participation: ParticipationAssessment,
        theory_overlay: TheoryOverlayAssessment,
        momentum_failure_watch: bool,
        rr_estimated: float,
        expected_move_pct: float,
    ) -> dict[str, list[Any]]:
        machine = [
            {
                "code": "daily_trend",
                "passed": daily_trend.passed,
                "value": round(daily_trend.slope_bps, 2),
                "detail": "1D trend slope in bps on fast EMA",
            },
            {
                "code": "setup_trend",
                "passed": setup_trend.passed,
                "value": round(setup_trend.slope_bps, 2),
                "detail": "4H trend slope in bps on fast EMA",
            },
            {
                "code": "structure",
                "passed": structure.passed or momentum_failure_watch,
                "value": {
                    "highs": [round(value, 4) for value in structure.last_highs],
                    "lows": [round(value, 4) for value in structure.last_lows],
                    "momentum_failure_watch": momentum_failure_watch,
                },
                "detail": "recent swing sequence",
            },
            {
                "code": "breakout_retest",
                "passed": breakout.detected and retest.confirmed,
                "value": {
                    "status": setup_status,
                    "breakout_level": round(breakout.breakout_level, 4)
                    if breakout.breakout_level is not None
                    else None,
                },
                "detail": "4H breakout with 1H retest confirmation",
            },
            {
                "code": "volatility",
                "passed": volatility.passed,
                "value": {
                    "atr_ratio": round(volatility.atr_ratio, 3),
                    "range_expansion": round(volatility.range_expansion, 3),
                },
                "detail": "ATR regime and range expansion",
            },
            {
                "code": "participation",
                "passed": participation.passed,
                "value": {
                    "volume_ratio": round(participation.volume_ratio, 3),
                    "oi_change_pct": round(participation.oi_change_pct, 4)
                    if participation.oi_change_pct is not None
                    else None,
                    "funding_rate": participation.funding_rate,
                    "crowded": participation.crowded,
                },
                "detail": "volume, OI, and funding quality",
            },
            {
                "code": "theory_overlay",
                "passed": theory_overlay.passed,
                "value": theory_overlay.to_dict(),
                "detail": "weekly theory bias plus anti-climax and anti-chase vetoes",
            },
            {
                "code": "risk_efficiency",
                "passed": rr_estimated >= self.config.min_rr,
                "value": {
                    "rr_estimated": round(rr_estimated, 3),
                    "expected_move_pct": round(expected_move_pct, 4),
                },
                "detail": "expected move vs stop distance",
            },
        ]
        if breakout.status == "extended":
            machine.append(
                {
                    "code": "no_trailing_fresh_setup",
                    "passed": False,
                    "value": {
                        "status": breakout.status,
                        "retest_anchor": round(breakout.breakout_level, 4)
                        if breakout.breakout_level is not None
                        else None,
                    },
                    "detail": "price is already extended from the 4H range; do not trail a fresh setup at the current continuation price",
                }
            )

        human = [
            f"{side.upper()} setup is {setup_status}; 1D/4H trend alignment={'yes' if daily_trend.passed and setup_trend.passed else 'no'}.",
            f"Breakout={'yes' if breakout.detected else 'no'} and retest={'confirmed' if retest.confirmed else retest.status} around {round(breakout.breakout_level, 2) if breakout.breakout_level is not None else 'n/a'}.",
            f"Volatility regime atr_ratio={volatility.atr_ratio:.2f}, range_expansion={volatility.range_expansion:.2f}; expected move {expected_move_pct*100:.1f}%.",
            f"Participation volume_ratio={participation.volume_ratio:.2f}, funding={participation.funding_rate if participation.funding_rate is not None else 'n/a'}, crowded={participation.crowded}.",
            f"Theory overlay={theory_overlay.passed}; stage={theory_overlay.stage}; reason={theory_overlay.reason}.",
            f"Estimated R:R {rr_estimated:.2f} vs minimum {self.config.min_rr:.2f}.",
        ]
        if breakout.status == "extended":
            human.append(
                "Fresh setup is extended from the 4H range; keep the prior thesis only on a pullback/retest, not by trailing a new continuation entry."
            )
        return {"machine": machine, "human": human}
