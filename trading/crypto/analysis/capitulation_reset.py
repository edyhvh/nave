"""Crowded-long liquidation reset assessment.

These are secondary lanes only. They never override the primary COT
anti-chase guard for normal fresh longs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from trading.crypto.cot.cot_analyzer import COTBias


@dataclass(frozen=True)
class CapitulationResetAssessment:
    kind: str
    direction: str
    action: str
    confidence: float
    size_fraction: float
    entry_zone: list[float] | None
    invalidation: float | None
    targets: list[float]
    reclaim_levels: list[float]
    reset_evidence: list[str]
    blockers: list[str]
    reasons: list[str]
    context: list[str] | None = None
    trigger: list[str] | None = None
    confirmation: list[str] | None = None
    invalidation_detail: list[str] | None = None

    def to_opportunity(self) -> dict[str, Any]:
        playbook = _playbook_for_kind(self.kind)
        out = {
            "kind": self.kind,
            "direction": self.direction,
            "action": self.action,
            "confidence": round(self.confidence, 3),
            "playbook": playbook,
            "entry_zone": self.entry_zone,
            "invalidation": self.invalidation,
            "targets": self.targets,
            "reasons": self.reasons,
            "blockers": self.blockers,
            "size_fraction": self.size_fraction,
            "reclaim_levels": self.reclaim_levels,
            "reset_evidence": self.reset_evidence,
        }
        if self.context is not None:
            out["context"] = self.context
        if self.trigger is not None:
            out["trigger"] = self.trigger
        if self.confirmation is not None:
            out["confirmation"] = self.confirmation
        if self.invalidation_detail is not None:
            out["invalidation_detail"] = self.invalidation_detail
        return out


def assess_crowded_long_reset(
    *,
    daily: pd.DataFrame,
    setup: pd.DataFrame,
    trigger: pd.DataFrame | None,
    cot_bias: COTBias | None,
    funding_rate: float | None,
    open_interest: pd.DataFrame | pd.Series | None = None,
    oi_change_pct: float | None = None,
    min_cot_percentile: int = 85,
    min_drawdown_pct: float = 15.0,
    min_oi_contraction_pct: float = 0.05,
    max_reset_funding_rate: float = 0.0,
) -> CapitulationResetAssessment | None:
    """Assess a liquidation-reset long candidate under crowded-long COT.

    Returns a watch/starter/confirmed secondary opportunity when COT is crowded
    long and liquidation evidence exists. Positive funding plus rising OI blocks
    starter/confirmed actions even if price bounced.
    """
    if daily.empty or setup.empty or cot_bias is None:
        return None
    cot_pct = int(cot_bias.historical_percentile or 0)
    if cot_bias.bias != "bearish" or cot_pct < min_cot_percentile:
        return None

    drawdown = _drawdown_from_high_pct(daily, lookback=28)
    if drawdown < min_drawdown_pct:
        return None

    oi_delta = oi_change_pct if oi_change_pct is not None else _oi_change_pct(open_interest)
    setup_level = _prior_breakdown_level(setup)
    h4_reclaim = _has_4h_reclaim(setup, setup_level)
    h4_retest = _has_4h_reclaim_retest_hold(setup, setup_level)
    h1_reclaim = _has_1h_reclaim(trigger, setup_level)
    new_low_after_reclaim = _new_low_after_reclaim(setup, setup_level)

    funding_reset = funding_rate is not None and funding_rate <= max_reset_funding_rate
    oi_reset = oi_delta is not None and oi_delta <= -abs(min_oi_contraction_pct)
    lows_stabilizing = _stops_making_fresh_lows(setup)

    reset_evidence: list[str] = [
        f"COT crowded long P{cot_pct}; weekly/stale positioning may describe trapped longs",
        f"Drawdown from 28d high {drawdown:.1f}% meets liquidation threshold",
    ]
    blockers: list[str] = []

    if funding_reset:
        reset_evidence.append(f"Funding cooled/negative ({funding_rate:.6f})")
    else:
        blockers.append("Funding is not cooled/negative")

    if oi_reset:
        reset_evidence.append(
            "Perp OI contracted materially "
            f"({oi_delta:.2%}, threshold {-abs(min_oi_contraction_pct):.2%})"
        )
    else:
        blockers.append(
            f"Open interest contraction is below reset threshold ({min_oi_contraction_pct:.0%})"
        )

    if lows_stabilizing:
        reset_evidence.append("4H stopped making fresh lows")
    else:
        blockers.append("Price has not stopped making fresh lows")

    if h4_reclaim:
        reset_evidence.append(f"4H close reclaimed breakdown level {setup_level:,.2f}")
    else:
        blockers.append("No 4H reclaim of prior breakdown level")

    if h1_reclaim:
        reset_evidence.append("1H higher-low/reclaim trigger present")
    else:
        blockers.append("No 1H higher-low trigger after reclaim")

    if h4_retest:
        reset_evidence.append("4H reclaim retest held")

    if new_low_after_reclaim:
        blockers.append("New low after reclaim invalidates reset setup")

    hard_blocked = (funding_rate is not None and funding_rate > max_reset_funding_rate) and (
        oi_delta is not None and oi_delta > -abs(min_oi_contraction_pct)
    )
    if hard_blocked:
        blockers.append("Positive funding with rising/flat OI blocks reset long")

    action = "watch"
    size_fraction = 0.0
    daily_confirmed = _daily_structure_bullish(daily)
    if not hard_blocked and not new_low_after_reclaim and funding_reset and oi_reset:
        if h4_retest and h1_reclaim:
            action = "confirmed_long"
            size_fraction = 1.0 if daily_confirmed else 0.5
        elif h1_reclaim:
            action = "starter_long"
            size_fraction = 0.25

    close_s = float(setup["close"].iloc[-1])
    recent_low = float(setup["low"].tail(min(len(setup), 20)).min())
    entry_zone = (
        _ordered_zone(setup_level, close_s)
        if action != "watch"
        else _ordered_zone(setup_level * 0.995, setup_level * 1.01)
    )
    invalidation = min(recent_low, setup_level * 0.985)
    targets = [close_s * 1.04, close_s * 1.08] if action != "watch" else [setup_level * 1.04]
    confidence = 0.58
    if action == "starter_long":
        confidence = 0.64
    elif action == "confirmed_long":
        confidence = 0.74

    reasons = [
        "Crowded-long COT remains an anti-chase warning; this is a reset-only secondary lane",
        "Long exposure may only scale upward after reclaim confirmation, never by averaging down",
    ]
    return CapitulationResetAssessment(
        kind="capitulation_reclaim_long",
        direction="long",
        action=action,
        confidence=confidence,
        size_fraction=size_fraction,
        entry_zone=entry_zone,
        invalidation=invalidation,
        targets=targets,
        reclaim_levels=[setup_level],
        reset_evidence=reset_evidence,
        blockers=blockers,
        reasons=reasons,
        context=[
            f"Weekly COT is crowded long/bearish at P{cot_pct}",
            f"Recent drawdown from 28d high is {drawdown:.1f}%",
        ],
        trigger=[
            "1H higher-low/reclaim after liquidation sweep"
            if h1_reclaim
            else "Waiting for 1H higher-low/reclaim after liquidation sweep"
        ],
        confirmation=[
            "4H reclaim retest held" if h4_retest else "Waiting for 4H reclaim retest hold",
            "Daily structure supports full size" if daily_confirmed else "Daily structure does not yet allow full size",
        ],
        invalidation_detail=[
            "New low after reclaim invalidates the setup",
            "Failure back below reclaimed level invalidates long exposure",
        ],
    )


def assess_crowded_long_failed_reset_short(
    *,
    daily: pd.DataFrame,
    setup: pd.DataFrame,
    trigger: pd.DataFrame | None,
    cot_bias: COTBias | None,
    funding_rate: float | None,
    open_interest: pd.DataFrame | pd.Series | None = None,
    oi_change_pct: float | None = None,
    min_cot_percentile: int = 85,
    min_drawdown_pct: float = 15.0,
    min_oi_contraction_pct: float = 0.05,
    max_reset_funding_rate: float = 0.0,
) -> CapitulationResetAssessment | None:
    """Assess short/fade priority when a crowded-long reset has not confirmed."""
    if daily.empty or setup.empty or cot_bias is None:
        return None
    cot_pct = int(cot_bias.historical_percentile or 0)
    if cot_bias.bias != "bearish" or cot_pct < min_cot_percentile:
        return None

    drawdown = _drawdown_from_high_pct(daily, lookback=28)
    if drawdown < min_drawdown_pct:
        return None

    oi_delta = oi_change_pct if oi_change_pct is not None else _oi_change_pct(open_interest)
    setup_level = _prior_breakdown_level(setup)
    h4_reclaim = _has_4h_reclaim(setup, setup_level)
    h1_reclaim = _has_1h_reclaim(trigger, setup_level)
    h4_retest = _has_4h_reclaim_retest_hold(setup, setup_level)
    new_low_after_reclaim = _new_low_after_reclaim(setup, setup_level)
    lows_stabilizing = _stops_making_fresh_lows(setup)

    funding_hot = funding_rate is not None and funding_rate > max_reset_funding_rate
    oi_not_reset = oi_delta is None or oi_delta > -abs(min_oi_contraction_pct)
    derivative_pressure = funding_hot and oi_not_reset
    failed_or_absent_reclaim = (
        new_low_after_reclaim or not h4_reclaim or (h4_reclaim and not h1_reclaim)
    )
    short_priority = derivative_pressure or failed_or_absent_reclaim
    if not short_priority:
        return None

    close_s = float(setup["close"].iloc[-1])
    recent_low = float(setup["low"].tail(min(len(setup), 20)).min())
    recent_high = float(setup["high"].tail(min(len(setup), 12)).max())
    entry_zone = _ordered_zone(min(close_s, setup_level * 0.995), max(close_s, setup_level * 1.01))
    invalidation = max(recent_high, setup_level * 1.025)
    targets = [recent_low, recent_low * 0.96]

    reset_evidence = [
        f"COT crowded long P{cot_pct}; liquidation risk remains active",
        f"Drawdown from 28d high {drawdown:.1f}% confirms trapped-long stress",
    ]
    reasons = [
        "Failed or unconfirmed reset keeps short/fade priority; "
        "do not chase long while COT is crowded",
        "Treat bounces into the 4H breakdown/reclaim level as supply until reclaim is proven",
    ]
    blockers = ["Requires 1H rejection or 4H lower-high trigger; not a blind short"]

    if derivative_pressure:
        funding_note = "unknown" if funding_rate is None else f"{funding_rate:.6f}"
        oi_note = "unknown" if oi_delta is None else f"{oi_delta:.2%}"
        reset_evidence.append(
            f"Funding/OI did not reset (funding {funding_note}, OI change {oi_note})"
        )
    if not h4_reclaim:
        reset_evidence.append(f"4H has not reclaimed breakdown level {setup_level:,.2f}")
    if h4_reclaim and not h1_reclaim:
        reset_evidence.append("4H reclaim lacks 1H higher-low confirmation")
    if new_low_after_reclaim:
        reset_evidence.append("New low after reclaim marks a failed reset")
    if not lows_stabilizing:
        reset_evidence.append("4H lows remain unstable")
    if h4_retest and h1_reclaim and not derivative_pressure and not new_low_after_reclaim:
        blockers.append(
            "4H/1H reclaim evidence is improving; downgrade short if retest continues to hold"
        )

    confidence = 0.66
    if derivative_pressure and failed_or_absent_reclaim:
        confidence = 0.72
    if new_low_after_reclaim:
        confidence = max(confidence, 0.74)

    return CapitulationResetAssessment(
        kind="failed_reset_continuation_short",
        direction="short",
        action="watch",
        confidence=confidence,
        size_fraction=0.5,
        entry_zone=entry_zone,
        invalidation=invalidation,
        targets=targets,
        reclaim_levels=[setup_level],
        reset_evidence=reset_evidence,
        blockers=blockers,
        reasons=reasons,
        context=[
            f"Weekly COT remains crowded long/bearish at P{cot_pct}",
            f"Drawdown from 28d high is {drawdown:.1f}%",
        ],
        trigger=["1H rejection or 4H lower-high is required before entry"],
        confirmation=[
            "4H reclaim has failed" if not h4_reclaim else "4H reclaim is unconfirmed",
            "Derivative reset is absent" if derivative_pressure else "Derivative pressure is not the main short driver",
        ],
        invalidation_detail=[
            "4H reclaim retest hold plus 1H higher-low downgrades the short",
            "Daily bullish structure flip invalidates continuation-fade priority",
        ],
    )


def assess_cot_early_trend_entry(
    *,
    daily: pd.DataFrame,
    setup: pd.DataFrame,
    trigger: pd.DataFrame | None,
    cot_bias: COTBias | None,
    funding_rate: float | None,
    open_interest: pd.DataFrame | pd.Series | None = None,
    oi_change_pct: float | None = None,
    min_cot_percentile: int = 85,
    max_hot_funding_rate: float = 0.0005,
) -> list[CapitulationResetAssessment]:
    """Assess early 4H/1H trend-entry lanes with COT as context, not trigger.

    COT is weekly and stale, so this function never creates a trade from COT
    alone. It requires 4H structure, 1H execution trigger, and derivatives
    behavior that does not contradict the trend.
    """
    if daily.empty or setup.empty:
        return []

    oi_delta = oi_change_pct if oi_change_pct is not None else _oi_change_pct(open_interest)
    setup_level = _prior_breakdown_level(setup)
    cot_pct = int(cot_bias.historical_percentile or 0) if cot_bias else 0
    crowded_bearish = bool(
        cot_bias and cot_bias.bias == "bearish" and cot_pct >= min_cot_percentile
    )
    daily_bull = _daily_structure_bullish(daily)
    daily_bear = _daily_structure_bearish(daily)
    h4_reclaim = _has_4h_reclaim(setup, setup_level)
    h4_retest = _has_4h_reclaim_retest_hold(setup, setup_level)
    h1_reclaim = _has_1h_reclaim(trigger, setup_level)
    h4_lower_high = _has_4h_lower_high(setup)
    h1_breakdown = _has_1h_breakdown(trigger, setup_level)
    trend_oi_expansion = oi_delta is not None and oi_delta > 0
    funding_not_hot = funding_rate is None or funding_rate <= max_hot_funding_rate
    funding_short_supportive = funding_rate is not None and funding_rate >= 0
    funding_not_too_negative = funding_rate is None or funding_rate >= 0
    short_derivative_confirmed = trend_oi_expansion or funding_short_supportive

    opportunities: list[CapitulationResetAssessment] = []

    long_blockers: list[str] = []
    if crowded_bearish and not h4_retest:
        long_blockers.append("Crowded-long COT requires completed 4H reset/retest before early long")
    if not h4_reclaim:
        long_blockers.append("No 4H reclaim structure")
    if not h1_reclaim:
        long_blockers.append("No 1H higher-low/reclaim trigger")
    if not funding_not_hot:
        long_blockers.append("Funding is already hot for an early long")
    if not trend_oi_expansion:
        long_blockers.append("OI is not expanding after reclaim")

    if h4_reclaim and h1_reclaim and funding_not_hot and trend_oi_expansion:
        if not crowded_bearish or h4_retest:
            close_s = float(setup["close"].iloc[-1])
            recent_low = float(setup["low"].tail(min(len(setup), 12)).min())
            action = "confirmed_trend_long" if daily_bull and h4_retest else "starter_trend_long"
            size_fraction = 0.75 if action == "confirmed_trend_long" else 0.25
            opportunities.append(
                CapitulationResetAssessment(
                    kind="early_trend_long",
                    direction="long",
                    action=action,
                    confidence=0.72 if action == "confirmed_trend_long" else 0.62,
                    size_fraction=size_fraction,
                    entry_zone=_ordered_zone(setup_level, close_s),
                    invalidation=min(recent_low, setup_level * 0.99),
                    targets=[close_s * 1.04, close_s * 1.08],
                    reclaim_levels=[setup_level],
                    reset_evidence=[
                        "4H reclaim plus 1H higher-low creates early trend ignition",
                        f"OI expansion after reclaim is {oi_delta:.2%}",
                    ],
                    blockers=[],
                    reasons=[
                        "COT is treated as context; entry requires 4H/1H trend structure",
                        "Starter size until daily structure confirms trend continuation",
                    ],
                    context=[
                        _cot_context_label(cot_bias),
                        "Derivative flow supports continuation after reclaim",
                    ],
                    trigger=["1H higher-low/reclaim fired inside the 4H reclaim zone"],
                    confirmation=[
                        "Daily bullish structure confirmed" if daily_bull else "Daily bullish structure still pending",
                        "4H reclaim retest held" if h4_retest else "4H reclaim retest still pending",
                    ],
                    invalidation_detail=[
                        "Lose reclaimed 4H level",
                        "New low below post-reclaim base",
                    ],
                )
            )

    short_blockers: list[str] = []
    if not crowded_bearish:
        short_blockers.append("COT is not crowded-long/bearish enough for trend short context")
    if not h4_lower_high:
        short_blockers.append("No 4H lower-high / failed-reclaim structure")
    if not h1_breakdown:
        short_blockers.append("No 1H breakdown/retest trigger")
    if not funding_not_too_negative:
        short_blockers.append("Funding is too negative; short may be crowded")
    if not short_derivative_confirmed:
        short_blockers.append("No OI/funding confirmation for short continuation")

    if (
        crowded_bearish
        and h4_lower_high
        and h1_breakdown
        and funding_not_too_negative
        and short_derivative_confirmed
    ):
        close_s = float(setup["close"].iloc[-1])
        recent_high = float(setup["high"].tail(min(len(setup), 12)).max())
        recent_low = float(setup["low"].tail(min(len(setup), 20)).min())
        action = "confirmed_trend_short" if daily_bear else "starter_trend_short"
        opportunities.append(
            CapitulationResetAssessment(
                kind="early_trend_short",
                direction="short",
                action=action,
                confidence=0.74 if action == "confirmed_trend_short" else 0.64,
                size_fraction=0.75 if action == "confirmed_trend_short" else 0.25,
                entry_zone=_ordered_zone(close_s, setup_level * 1.01),
                invalidation=max(recent_high, setup_level * 1.02),
                targets=[recent_low, recent_low * 0.96],
                reclaim_levels=[setup_level],
                reset_evidence=[
                    f"COT crowded long P{cot_pct}; trapped-long pressure can fuel trend short",
                    "4H lower-high / failed-reclaim structure is present",
                ],
                blockers=[],
                reasons=[
                    "Early short trend entry requires structure, not COT alone",
                    "Scale only after breakdown retest holds; do not short blind into lows",
                ],
                context=[
                    _cot_context_label(cot_bias),
                    "Failed reset can convert liquidation into trend continuation",
                ],
                trigger=["1H breakdown/retest trigger fired"],
                confirmation=[
                    "Daily bearish structure confirmed" if daily_bear else "Daily bearish structure still pending",
                    "OI expanding with trend" if trend_oi_expansion else "OI expansion not available",
                ],
                invalidation_detail=[
                    "4H reclaim above breakdown level",
                    "1H higher-low after reclaim",
                ],
            )
        )

    if not opportunities and (crowded_bearish or h4_reclaim):
        # Return watch rows only when the COT/structure context is close enough
        # to be useful in daily monitoring.
        direction = "short" if crowded_bearish and not h4_reclaim else "long"
        blockers = short_blockers if direction == "short" else long_blockers
        kind = "early_trend_short" if direction == "short" else "early_trend_long"
        opportunities.append(
            CapitulationResetAssessment(
                kind=kind,
                direction=direction,
                action="watch",
                confidence=0.56,
                size_fraction=0.0,
                entry_zone=_ordered_zone(setup_level * 0.995, setup_level * 1.01),
                invalidation=None,
                targets=[],
                reclaim_levels=[setup_level],
                reset_evidence=[],
                blockers=blockers,
                reasons=["Early trend entry is close enough to monitor, but trigger stack is incomplete"],
                context=[_cot_context_label(cot_bias)],
                trigger=["Waiting for 4H/1H trend trigger stack"],
                confirmation=["No trend confirmation yet"],
                invalidation_detail=["No trade while trigger stack is incomplete"],
            )
        )

    return opportunities


def _playbook_for_kind(kind: str) -> str:
    if kind == "early_trend_long":
        return (
            "Early trend long — COT is context only; require 4H reclaim, 1H higher-low, "
            "OI expansion after reset, and daily confirmation before full size."
        )
    if kind == "early_trend_short":
        return (
            "Early trend short — use crowded-long/failed-reset context only with 4H lower-high "
            "or failed reclaim plus 1H breakdown/retest."
        )
    if kind == "failed_reset_continuation_short":
        return (
            "Crowded-long failed reset — keep short/fade priority while reclaim fails "
            "or funding/OI remain crowded; wait for 1H rejection + 4H lower-high."
        )
    return (
        "Crowded-long liquidation reset — no normal long chase; "
        "probe only after 1H reclaim, add only after 4H reclaim retest holds."
    )


def _ema(frame: pd.DataFrame, span: int) -> float:
    return float(frame["close"].ewm(span=span, adjust=False).mean().iloc[-1])


def _daily_structure_bullish(daily: pd.DataFrame, *, ema_span: int = 20) -> bool:
    """Daily close above fast EMA — stage-4 full sizing gate per theory."""
    if daily.empty or len(daily) < ema_span:
        return False
    close = float(daily["close"].iloc[-1])
    ema = _ema(daily, ema_span)
    return close > ema


def _daily_structure_bearish(daily: pd.DataFrame, *, ema_span: int = 20) -> bool:
    if daily.empty or len(daily) < ema_span:
        return False
    close = float(daily["close"].iloc[-1])
    ema = _ema(daily, ema_span)
    return close < ema


def _drawdown_from_high_pct(frame: pd.DataFrame, *, lookback: int) -> float:
    window = frame.tail(min(len(frame), lookback))
    high = float(window["high"].max())
    close = float(frame["close"].iloc[-1])
    return ((high - close) / high * 100.0) if high else 0.0


def _prior_breakdown_level(setup: pd.DataFrame) -> float:
    if len(setup) < 12:
        return float(setup["close"].iloc[-1])
    prior = setup.iloc[:-2] if len(setup) > 8 else setup
    window = prior.tail(min(len(prior), 24))
    low_idx = int(window["low"].astype(float).reset_index(drop=True).idxmin())
    if low_idx > 0:
        pre_liquidation = window["close"].iloc[max(0, low_idx - 6) : low_idx]
        if not pre_liquidation.empty:
            return float(pre_liquidation.min())
    return float(window["close"].min())


def _has_4h_reclaim(setup: pd.DataFrame, level: float) -> bool:
    if len(setup) < 5:
        return False
    recent = setup.tail(min(len(setup), 10))
    swept = bool((recent["low"] < level).any())
    return swept and float(setup["close"].iloc[-1]) > level


def _has_4h_reclaim_retest_hold(setup: pd.DataFrame, level: float) -> bool:
    if not _has_4h_reclaim(setup, level) or len(setup) < 8:
        return False
    recent = setup.tail(3)
    retested = bool((recent["low"] <= level * 1.01).any())
    held = bool((recent["low"] >= level * 0.995).all() and recent["close"].iloc[-1] > level)
    return retested and held


def _has_1h_reclaim(trigger: pd.DataFrame | None, level: float) -> bool:
    if trigger is None or trigger.empty or len(trigger) < 5:
        return False
    recent = trigger.tail(min(len(trigger), 8))
    close_above = float(recent["close"].iloc[-1]) > level
    higher_low = float(recent["low"].iloc[-1]) > float(recent["low"].iloc[:-1].min())
    swept = bool((recent["low"].iloc[:-1] < level).any())
    return close_above and higher_low and swept


def _has_4h_lower_high(setup: pd.DataFrame) -> bool:
    if len(setup) < 8:
        return False
    highs = setup["high"].tail(8).astype(float).reset_index(drop=True)
    closes = setup["close"].tail(8).astype(float).reset_index(drop=True)
    first_half_high = float(highs.iloc[:4].max())
    second_half_high = float(highs.iloc[4:].max())
    lower_high = second_half_high < first_half_high * 1.002
    closing_weak = float(closes.iloc[-1]) < float(closes.iloc[3])
    return lower_high and closing_weak


def _has_1h_breakdown(trigger: pd.DataFrame | None, level: float) -> bool:
    if trigger is None or trigger.empty or len(trigger) < 5:
        return False
    recent = trigger.tail(min(len(trigger), 8))
    close_below = float(recent["close"].iloc[-1]) < level
    lower_high = float(recent["high"].iloc[-1]) < float(recent["high"].iloc[:-1].max())
    tested_level = bool((recent["high"].iloc[:-1] >= level * 0.995).any())
    return close_below and lower_high and tested_level


def _cot_context_label(cot_bias: COTBias | None) -> str:
    if cot_bias is None:
        return "COT unavailable; structure must carry the setup"
    pct = int(cot_bias.historical_percentile or 0)
    return f"COT {cot_bias.bias} P{pct} confidence {cot_bias.confidence:.0%}"


def _new_low_after_reclaim(setup: pd.DataFrame, level: float) -> bool:
    if len(setup) < 6:
        return False
    closes = setup["close"].tail(min(len(setup), 12)).reset_index(drop=True)
    lows = setup["low"].tail(min(len(setup), 12)).reset_index(drop=True)
    swept_indices = [idx for idx, low in enumerate(lows) if float(low) < level]
    if not swept_indices:
        return False
    sweep_idx = swept_indices[0]
    reclaim_idx = None
    for idx in range(sweep_idx + 1, len(closes)):
        close = closes.iloc[idx]
        if float(close) > level:
            reclaim_idx = idx
            break
    if reclaim_idx is None or reclaim_idx >= len(lows) - 1:
        return False
    if bool((closes.iloc[reclaim_idx + 1 :] < level).any()):
        return True
    pre_low = float(lows.iloc[: reclaim_idx + 1].min())
    post_low = float(lows.iloc[reclaim_idx + 1 :].min())
    return post_low < pre_low


def _stops_making_fresh_lows(setup: pd.DataFrame) -> bool:
    if len(setup) < 6:
        return False
    recent = setup["low"].tail(4)
    prior_low = float(setup["low"].iloc[:-4].tail(min(len(setup) - 4, 20)).min())
    return float(recent.min()) >= prior_low


def _oi_change_pct(open_interest: pd.DataFrame | pd.Series | None) -> float | None:
    if open_interest is None:
        return None
    if isinstance(open_interest, pd.Series):
        series = open_interest.astype(float)
    else:
        normalized = open_interest.copy()
        normalized.columns = [str(column).lower() for column in normalized.columns]
        column = (
            "open_interest" if "open_interest" in normalized.columns else normalized.columns[-1]
        )
        series = normalized[column].astype(float)
    if len(series) < 2:
        return None
    latest = float(series.iloc[-1])
    baseline = (
        float(series.iloc[-min(len(series), 20) : -1].mean())
        if len(series) > 2
        else float(series.iloc[0])
    )
    if baseline == 0:
        return None
    return (latest - baseline) / baseline


def _ordered_zone(a: float, b: float) -> list[float] | None:
    lo, hi = sorted((float(a), float(b)))
    if hi <= lo:
        return None
    return [lo, hi]
