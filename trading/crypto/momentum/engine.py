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
        open_interest: pd.DataFrame | pd.Series | None = None,
        funding_rate: float | None = None,
        account_equity: float = 10000.0,
        risk_pct: float | None = None,
        side: str | None = None,
    ) -> list[TradePlan]:
        daily = normalize_frame(daily_frame)
        setup = normalize_frame(setup_frame)
        trigger = normalize_frame(trigger_frame)
        sides = [side.lower()] if side else ["long", "short"]
        plans: list[TradePlan] = []
        for requested_side in sides:
            evaluation = self._evaluate_side(
                symbol=symbol,
                side=requested_side,
                daily=daily,
                setup=setup,
                trigger=trigger,
                open_interest=open_interest,
                funding_rate=funding_rate,
                account_equity=account_equity,
                risk_pct=risk_pct or self.config.risk.default_risk_pct,
            )
            plans.append(evaluation.plan)
        return plans

    def _evaluate_side(
        self,
        *,
        symbol: str,
        side: str,
        daily: pd.DataFrame,
        setup: pd.DataFrame,
        trigger: pd.DataFrame,
        open_interest: pd.DataFrame | pd.Series | None,
        funding_rate: float | None,
        account_equity: float,
        risk_pct: float,
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
        invalidation = self._invalidation(
            trigger, side, breakout, retest, entry_price)
        expected_move_pct, stop_pct, rr_estimated = self._reward_profile(
            entry_price=entry_price,
            invalidation=invalidation,
            breakout=breakout,
            volatility=volatility,
        )
        score_breakdown = build_score_breakdown(
            trend_score=(
                (daily_trend.score + setup_trend.score + structure.score) / 3.0),
            breakout_score=self._breakout_score(breakout, retest),
            volatility_score=volatility.score,
            participation_score=participation.score,
            rr_estimated=rr_estimated,
            expected_move_pct=expected_move_pct,
            stop_pct=stop_pct,
            config=self.config,
        )
        tradeable = self._is_tradeable(
            setup_status=setup_status,
            rr_estimated=rr_estimated,
            expected_move_pct=expected_move_pct,
            score=score_breakdown.total,
            volatility=volatility,
            participation=participation,
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
            confidence_score=score_breakdown.total,
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
                breakout_level=round(
                    breakout.breakout_level, 6) if breakout.breakout_level is not None else None,
                breakout_volume_ratio=round(participation.volume_ratio, 3),
                atr_ratio=round(volatility.atr_ratio, 3),
                range_expansion=round(volatility.range_expansion, 3),
                funding_rate=participation.funding_rate,
                oi_change_pct=round(participation.oi_change_pct, 4)
                if participation.oi_change_pct is not None
                else None,
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
        return assess_retest(trigger, side, breakout.breakout_level, breakout.breakout_index, self.config)

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
    ) -> float:
        level = breakout.breakout_level if breakout.breakout_level is not None else entry_price
        invalidation = build_invalidation(
            trigger, side, level, retest, self.config)
        if side == "long" and invalidation >= entry_price:
            invalidation = entry_price * (1 - 0.02)
        if side == "short" and invalidation <= entry_price:
            invalidation = entry_price * (1 + 0.02)
        return float(invalidation)

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
        if retest.confirmed:
            base = min(base + 0.2, 1.0)
        if retest.status == "invalid":
            base *= 0.2
        return base

    def _is_tradeable(
        self,
        *,
        setup_status: str,
        rr_estimated: float,
        expected_move_pct: float,
        score: int,
        volatility: VolatilityAssessment,
        participation: ParticipationAssessment,
        daily_ema_gap_pct: float | None,
        setup_ema_gap_pct: float | None,
    ) -> bool:
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
        return (
            setup_status == "confirmed"
            and rr_estimated >= self.config.min_rr
            and expected_move_pct >= self.config.execution.min_expected_move_pct
            and score >= self.config.score_tradeable_threshold
            and volatility.passed
            and volume_ok
            and atr_ok
            and intraday_gap_ok
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
                "passed": structure.passed,
                "value": {
                    "highs": [round(value, 4) for value in structure.last_highs],
                    "lows": [round(value, 4) for value in structure.last_lows],
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
                "code": "risk_efficiency",
                "passed": rr_estimated >= self.config.min_rr,
                "value": {
                    "rr_estimated": round(rr_estimated, 3),
                    "expected_move_pct": round(expected_move_pct, 4),
                },
                "detail": "expected move vs stop distance",
            },
        ]
        human = [
            f"{side.upper()} setup is {setup_status}; 1D/4H trend alignment={'yes' if daily_trend.passed and setup_trend.passed else 'no'}.",
            f"Breakout={'yes' if breakout.detected else 'no'} and retest={'confirmed' if retest.confirmed else retest.status} around {round(breakout.breakout_level, 2) if breakout.breakout_level is not None else 'n/a'}.",
            f"Volatility regime atr_ratio={volatility.atr_ratio:.2f}, range_expansion={volatility.range_expansion:.2f}; expected move {expected_move_pct*100:.1f}%.",
            f"Participation volume_ratio={participation.volume_ratio:.2f}, funding={participation.funding_rate if participation.funding_rate is not None else 'n/a'}, crowded={participation.crowded}.",
            f"Estimated R:R {rr_estimated:.2f} vs minimum {self.config.min_rr:.2f}.",
        ]
        return {"machine": machine, "human": human}
