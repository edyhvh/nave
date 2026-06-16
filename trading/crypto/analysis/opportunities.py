"""Secondary crypto opportunities — notrend, relief rally, forming setups.

Primary review (``review_positions``) resolves enter/watch/stand_aside from
COT + regime + momentum.  This module surfaces *additional* lanes when the
primary stack is blocked but structure still offers a solid, defined-risk play.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from trading.crypto.analysis.regime import RegimeAssessment
from trading.crypto.analysis.regime_config import RegimeConfig, load_regime_config
from trading.crypto.cot.cot_analyzer import COTBias
from trading.crypto.cot.context import cot_side_from_bias


@dataclass(frozen=True)
class SecondaryOpportunity:
    """A non-primary trade lane with explicit playbook and invalidation."""

    kind: str
    direction: str
    action: str
    confidence: float
    playbook: str
    entry_zone: list[float] | None
    invalidation: float | None
    targets: list[float]
    reasons: list[str]
    blockers: list[str]
    size_fraction: float | None = None

    def to_dict(self) -> dict[str, Any]:
        out = {
            "kind": self.kind,
            "direction": self.direction,
            "action": self.action,
            "confidence": round(self.confidence, 3),
            "playbook": self.playbook,
            "entry_zone": self.entry_zone,
            "invalidation": self.invalidation,
            "targets": self.targets,
            "reasons": self.reasons,
            "blockers": self.blockers,
        }
        if self.size_fraction is not None:
            out["size_fraction"] = self.size_fraction
        return out


def _ema(frame: pd.DataFrame, span: int) -> float:
    return float(frame["close"].ewm(span=span, adjust=False).mean().iloc[-1])


def _supply_zone(
    *,
    high_28d: float,
    ema_fast_s: float,
    close_s: float,
) -> list[float]:
    supply_hi = max(high_28d * 0.98, ema_fast_s * 1.01, close_s)
    supply_lo = min(ema_fast_s * 0.99, close_s * 0.995)
    return [float(supply_lo), float(supply_hi)]


def _demand_zone(
    *,
    low_28d: float,
    ema_fast_s: float,
    close_s: float,
) -> list[float]:
    demand_lo = min(low_28d * 1.02, ema_fast_s * 0.99, close_s)
    demand_hi = max(ema_fast_s * 1.01, close_s * 1.005)
    return [float(demand_lo), float(demand_hi)]


def _relief_rally_fade(
    *,
    daily: pd.DataFrame,
    setup: pd.DataFrame,
    cot_side: str | None,
    cot_conf: float,
    metrics: dict[str, float],
    cfg: RegimeConfig,
    supply: list[float],
) -> SecondaryOpportunity | None:
    """Detect a short setup forming as price rallies into supply under bearish COT."""
    if cot_side != "short" or cot_conf < cfg.cot_confidence_min:
        return None

    close_s = float(setup["close"].iloc[-1])
    ema_fast_s = _ema(setup, cfg.ema_fast)
    ema_slow_d = _ema(daily, cfg.ema_slow)
    close_d = float(daily["close"].iloc[-1])
    bounce_pct = metrics.get("bounce_from_14d_low_pct", 0.0)
    drawdown = metrics.get("drawdown_from_28d_high_pct", 0.0)
    bounce_min_pct = cfg.relief_bounce_min * 100
    bounce_max_pct = cfg.relief_bounce_max * 100

    # Rally into supply while daily structure still bearish.
    in_supply = close_s >= ema_fast_s * cfg.supply_ema_proximity
    daily_bear = close_d < ema_slow_d
    if not (in_supply and daily_bear and bounce_min_pct <= bounce_pct <= bounce_max_pct):
        return None

    # 4H slope positive = counter-trend bounce (classic fade setup).
    if len(setup) >= 6:
        slope_bps = (float(setup["close"].iloc[-1]) - float(setup["close"].iloc[-6])) / float(
            setup["close"].iloc[-6]
        ) * 10_000
    else:
        slope_bps = 0.0

    inv = float(max(supply)) * 1.02
    tp1 = close_s * 0.97
    tp2 = close_s * 0.94

    if slope_bps > 0:
        slope_note = "counter-trend bounce"
    elif slope_bps < 0:
        slope_note = "bounce stalling"
    else:
        slope_note = "flat 4H"
    reasons = [
        f"Bearish COT ({cot_conf:.0%}) + {bounce_pct:.1f}% relief rally into supply",
        f"Daily below slow EMA; 4H slope {slope_bps:.0f} bps ({slope_note})",
    ]
    if drawdown >= cfg.min_drawdown_from_high * 100:
        reasons.append(f"Still {drawdown:.1f}% below 28d high — macro bear leg intact")

    return SecondaryOpportunity(
        kind="relief_rally_fade",
        direction="short",
        action="watch",
        confidence=max(cot_conf, 0.62),
        playbook=(
            "Fade relief rally into supply — wait for 1H rejection + 4H lower-high; "
            "half size vs trend continuation."
        ),
        entry_zone=supply,
        invalidation=inv,
        targets=[tp1, tp2],
        reasons=reasons,
        blockers=["Requires 1H rejection trigger — not a blind short"],
        size_fraction=0.5,
    )


def _notrend_range_long(
    *,
    daily: pd.DataFrame,
    setup: pd.DataFrame,
    cot_side: str | None,
    metrics: dict[str, float],
    cfg: RegimeConfig,
    regime: RegimeAssessment,
) -> SecondaryOpportunity | None:
    """Scalp long inside a range when macro is bearish but local bounce has momentum."""
    if regime.phase not in {"neutral", "cot_bear_bias", "leg_down", "relief_rally_fade"}:
        return None
    if cot_side != "short":
        return None

    bounce_pct = metrics.get("bounce_from_14d_low_pct", 0.0)
    bounce_min_pct = cfg.relief_bounce_min * 100
    if bounce_pct < bounce_min_pct or bounce_pct > cfg.notrend_bounce_max:
        return None

    close_s = float(setup["close"].iloc[-1])
    low_14d = float(setup["low"].tail(42).min())
    high_14d = float(setup["high"].tail(42).max())
    range_pct = (high_14d - low_14d) / low_14d * 100 if low_14d else 0.0

    if range_pct < cfg.notrend_min_range_pct or range_pct > cfg.notrend_max_range_pct:
        return None

    # Price in lower half of range with bounce underway.
    range_pos = (close_s - low_14d) / (high_14d - low_14d) if high_14d > low_14d else 0.5
    if range_pos > 0.55:
        return None

    ema_fast_s = _ema(setup, cfg.ema_fast)
    if len(setup) >= 4:
        recent_up = float(setup["close"].iloc[-1]) > float(setup["close"].iloc[-4])
    else:
        recent_up = False
    if not recent_up:
        return None

    demand = _demand_zone(
        low_28d=float(daily["low"].tail(28).min()),
        ema_fast_s=ema_fast_s,
        close_s=close_s,
    )
    inv = float(min(demand)) * 0.985
    mid = (high_14d + low_14d) / 2
    supply = _supply_zone(
        high_28d=float(daily["high"].tail(28).max()),
        ema_fast_s=ema_fast_s,
        close_s=close_s,
    )

    return SecondaryOpportunity(
        kind="notrend_range_long",
        direction="long",
        action="watch",
        confidence=0.55,
        playbook=(
            "Notrend scalp — buy demand in lower range, exit into mid/supply; "
            "tight stop, no swing hold. Counter to COT macro."
        ),
        entry_zone=demand,
        invalidation=inv,
        targets=[mid, float(max(supply))],
        reasons=[
            f"Range {range_pct:.1f}% wide; price at {range_pos:.0%} of 14d range",
            f"Bounce {bounce_pct:.1f}% underway while COT still bearish — local mean-revert lane",
        ],
        blockers=[
            "Counter-trend to COT — quarter size max",
            "Exit at range mid; do not hold through supply",
        ],
        size_fraction=0.25,
    )


def _forming_breakdown_short(
    *,
    plans: list[dict[str, Any]],
    cot_side: str | None,
    cot_conf: float,
    cfg: RegimeConfig,
) -> SecondaryOpportunity | None:
    """Surface a short when momentum has a pending/confirmed plan blocked only by theory."""
    if cot_side != "short" or cot_conf < cfg.cot_confidence_min:
        return None

    short_plans = [p for p in plans if p.get("side") == "short"]
    if not short_plans:
        return None

    best = max(short_plans, key=lambda p: int(p.get("confidence_score", 0) or 0))
    score = int(best.get("confidence_score", 0) or 0)
    if score < cfg.forming_short_min_score:
        return None

    overlay = (best.get("diagnostics") or {}).get("theory_overlay") or {}
    if overlay.get("passed"):
        return None

    reason = str(overlay.get("reason") or "")
    blocked_by_daily = "daily" in reason.lower()
    if not blocked_by_daily:
        return None

    entry = list(best.get("entry_zone") or [])
    inv = best.get("invalidation")
    targets = [v for v in (best.get("tp1"), best.get("tp2")) if v is not None]

    return SecondaryOpportunity(
        kind="forming_short",
        direction="short",
        action="watch",
        confidence=max(cot_conf, score / 100.0 * 0.85),
        playbook=(
            "Short structure forming — momentum score rising but daily gate open; "
            "stalk breakdown retest when daily confirms."
        ),
        entry_zone=entry or None,
        invalidation=float(inv) if inv is not None else None,
        targets=targets,
        reasons=[
            f"Momentum short score {score} ({best.get('setup_status')})",
            f"Theory blocker: {reason}",
        ],
        blockers=["Wait for daily confirmation or 4H breakdown retest"],
        size_fraction=0.5,
    )


def detect_secondary_opportunities(
    *,
    daily: pd.DataFrame,
    setup: pd.DataFrame,
    cot_bias: COTBias | None,
    regime: RegimeAssessment,
    plans: list[dict[str, Any]],
    primary_action: str,
    config: RegimeConfig | None = None,
) -> list[dict[str, Any]]:
    """Return ranked secondary opportunities when primary action is not enter."""
    if primary_action == "enter":
        return []

    cfg = config or load_regime_config()
    cot_side = cot_side_from_bias(cot_bias)
    cot_conf = float(cot_bias.confidence) if cot_bias else 0.0
    metrics = regime.metrics

    if daily.empty or setup.empty:
        return []

    supply = _supply_zone(
        high_28d=float(daily["high"].tail(28).max()),
        ema_fast_s=_ema(setup, cfg.ema_fast),
        close_s=float(setup["close"].iloc[-1]),
    )

    candidates: list[SecondaryOpportunity] = []

    fade = _relief_rally_fade(
        daily=daily,
        setup=setup,
        cot_side=cot_side,
        cot_conf=cot_conf,
        metrics=metrics,
        cfg=cfg,
        supply=supply,
    )
    if fade:
        candidates.append(fade)

    forming = _forming_breakdown_short(
        plans=plans,
        cot_side=cot_side,
        cot_conf=cot_conf,
        cfg=cfg,
    )
    if forming:
        candidates.append(forming)

    notrend = _notrend_range_long(
        daily=daily,
        setup=setup,
        cot_side=cot_side,
        metrics=metrics,
        cfg=cfg,
        regime=regime,
    )
    if notrend:
        candidates.append(notrend)

    # De-duplicate by kind; keep highest confidence per kind.
    by_kind: dict[str, SecondaryOpportunity] = {}
    for opp in candidates:
        prev = by_kind.get(opp.kind)
        if prev is None or opp.confidence > prev.confidence:
            by_kind[opp.kind] = opp

    ranked = sorted(by_kind.values(), key=lambda o: o.confidence, reverse=True)
    return [o.to_dict() for o in ranked[: cfg.max_secondary_opportunities]]