"""
Transparent scoring rubric for Solana memecoins.

Inspired by the fdv.lol explainable rubric. Every score band is visible
in the resulting :class:`ScoreBreakdown` so a human (or Hermes) can
override a single sub-score without recomputing the rest.

Inputs (all optional; missing inputs simply zero-out their band):

    * FDV band            — penalize too-low (rug-bait) and too-high (no upside).
    * Volume / FDV ratio  — turnover; >0.5 is hot.
    * Liquidity depth     — slippage proxy at our intended position size.
    * Momentum            — short-window price change (5m + 1h, weighted).
    * Age                 — newest pumps are riskiest; bias slightly older.

Output:

    * 0-100 ``total`` score.
    * One of ``GOOD`` (≥70) / ``WATCH`` (40-69) / ``SHILL`` (<40).
    * Per-band sub-scores + numeric rationale.

Scoring is pure: no I/O, no provider dependency. Pass a
:class:`TokenMarket` (and optionally the matching
:class:`SafetyReport` so a failing safety check can short-circuit the
score to ``SHILL``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from trading.memecoin.data_provider import TokenMarket
from trading.memecoin.safety_check import SafetyReport, SafetyVerdict

# ── Tunables ──────────────────────────────────────────────────────────────────

LIQUIDITY_FLOOR_USD = 25_000.0  # universe gate — locked in plan.md

# FDV bands in USD. Below LOW = rug-bait; above HIGH = no realistic upside.
_FDV_BAND_LOW = 50_000.0
_FDV_BAND_SWEET_LOW = 250_000.0
_FDV_BAND_SWEET_HIGH = 5_000_000.0
_FDV_BAND_HIGH = 50_000_000.0

# Sub-band caps (sum to 100).
_W_FDV = 20
_W_TURNOVER = 25
_W_LIQUIDITY = 25
_W_MOMENTUM = 20
_W_AGE = 10

GOOD_THRESHOLD = 70
WATCH_THRESHOLD = 40


class Label(str, Enum):
    GOOD = "GOOD"
    WATCH = "WATCH"
    SHILL = "SHILL"


@dataclass
class ScoreBreakdown:
    mint: str
    total: int
    label: Label
    bands: dict[str, dict[str, Any]] = field(default_factory=dict)
    rationale: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mint": self.mint,
            "total": self.total,
            "label": self.label.value,
            "bands": self.bands,
            "rationale": self.rationale,
        }


# ── Public entry point ────────────────────────────────────────────────────────


def score_candidate(
    mint: str,
    market: TokenMarket | None,
    *,
    safety: SafetyReport | None = None,
) -> ScoreBreakdown:
    """Compute the transparent rubric score for ``mint``.

    If a ``SafetyReport`` with verdict=FAIL is passed, the rubric still
    runs but the total is clamped to ``SHILL`` — the safety failure is
    the dominant signal.
    """
    bands: dict[str, dict[str, Any]] = {}
    rationale: list[str] = []

    fdv_pts = _band_fdv(market, bands, rationale)
    turn_pts = _band_turnover(market, bands, rationale)
    liq_pts = _band_liquidity(market, bands, rationale)
    mom_pts = _band_momentum(market, bands, rationale)
    age_pts = _band_age(market, bands, rationale)

    total = fdv_pts + turn_pts + liq_pts + mom_pts + age_pts

    # Safety override: a failing safety check can never produce GOOD/WATCH.
    if safety is not None and safety.verdict == SafetyVerdict.FAIL:
        rationale.append(
            f"safety verdict=FAIL (rug_score={safety.rug_score}); clamping to SHILL"
        )
        return ScoreBreakdown(
            mint=mint,
            total=min(total, WATCH_THRESHOLD - 1),
            label=Label.SHILL,
            bands=bands,
            rationale=rationale,
        )

    label = (
        Label.GOOD if total >= GOOD_THRESHOLD
        else Label.WATCH if total >= WATCH_THRESHOLD
        else Label.SHILL
    )
    return ScoreBreakdown(
        mint=mint,
        total=int(total),
        label=label,
        bands=bands,
        rationale=rationale,
    )


# ── Band scorers ──────────────────────────────────────────────────────────────


def _band_fdv(
    market: TokenMarket | None,
    bands: dict[str, dict[str, Any]],
    rationale: list[str],
) -> int:
    fdv = (market.fdv_usd if market else None) or (market.market_cap_usd if market else None)
    if fdv is None or fdv <= 0:
        bands["fdv"] = {"value_usd": None, "points": 0, "max": _W_FDV}
        rationale.append("fdv unknown → 0 pts")
        return 0
    if fdv < _FDV_BAND_LOW:
        pts = 4
        note = "fdv too low (rug-bait band)"
    elif fdv < _FDV_BAND_SWEET_LOW:
        pts = 12
        note = "fdv emerging (below sweet spot)"
    elif fdv <= _FDV_BAND_SWEET_HIGH:
        pts = _W_FDV
        note = "fdv in sweet spot"
    elif fdv <= _FDV_BAND_HIGH:
        pts = 10
        note = "fdv elevated (less upside)"
    else:
        pts = 2
        note = "fdv too high (no realistic upside)"
    bands["fdv"] = {"value_usd": round(fdv, 2), "points": pts, "max": _W_FDV}
    rationale.append(f"fdv ${fdv:,.0f} → {pts}/{_W_FDV} ({note})")
    return pts


def _band_turnover(
    market: TokenMarket | None,
    bands: dict[str, dict[str, Any]],
    rationale: list[str],
) -> int:
    if market is None:
        bands["turnover"] = {"ratio": None, "points": 0, "max": _W_TURNOVER}
        return 0
    fdv = market.fdv_usd or market.market_cap_usd
    vol = market.volume_24h_usd
    if not fdv or not vol or fdv <= 0:
        bands["turnover"] = {"ratio": None, "points": 0, "max": _W_TURNOVER}
        rationale.append("turnover unknown → 0 pts")
        return 0
    ratio = vol / fdv
    if ratio >= 1.0:
        pts = _W_TURNOVER
    elif ratio >= 0.5:
        pts = int(_W_TURNOVER * 0.85)
    elif ratio >= 0.2:
        pts = int(_W_TURNOVER * 0.6)
    elif ratio >= 0.05:
        pts = int(_W_TURNOVER * 0.3)
    else:
        pts = 0
    bands["turnover"] = {
        "ratio": round(ratio, 4),
        "points": pts,
        "max": _W_TURNOVER,
    }
    rationale.append(f"turnover {ratio:.2f} → {pts}/{_W_TURNOVER}")
    return pts


def _band_liquidity(
    market: TokenMarket | None,
    bands: dict[str, dict[str, Any]],
    rationale: list[str],
) -> int:
    liq = (market.liquidity_usd if market else None) or 0.0
    if liq < LIQUIDITY_FLOOR_USD:
        # Sub-floor liquidity should not have made it into the scorer at
        # all (the scanner gates on this), but if it did, score it 0.
        bands["liquidity"] = {
            "usd": round(liq, 2),
            "points": 0,
            "max": _W_LIQUIDITY,
        }
        rationale.append(f"liquidity ${liq:,.0f} below floor → 0 pts")
        return 0
    if liq >= 500_000:
        pts = _W_LIQUIDITY
    elif liq >= 150_000:
        pts = int(_W_LIQUIDITY * 0.8)
    elif liq >= 50_000:
        pts = int(_W_LIQUIDITY * 0.6)
    else:
        pts = int(_W_LIQUIDITY * 0.4)
    bands["liquidity"] = {"usd": round(liq, 2), "points": pts, "max": _W_LIQUIDITY}
    rationale.append(f"liquidity ${liq:,.0f} → {pts}/{_W_LIQUIDITY}")
    return pts


def _band_momentum(
    market: TokenMarket | None,
    bands: dict[str, dict[str, Any]],
    rationale: list[str],
) -> int:
    if market is None:
        bands["momentum"] = {"5m_pct": None, "1h_pct": None, "points": 0, "max": _W_MOMENTUM}
        return 0
    m5 = market.price_change_5m_pct or 0.0
    h1 = market.price_change_1h_pct or 0.0
    # Reward positive but not parabolic moves (parabolic = exhaustion risk).
    score = 0.0
    if 1 <= m5 <= 30:
        score += 0.5 * _W_MOMENTUM
    elif 30 < m5 <= 80:
        score += 0.4 * _W_MOMENTUM  # discount: getting frothy
    elif m5 > 80:
        score += 0.15 * _W_MOMENTUM  # likely top-tick
    elif m5 < -10:
        score -= 0.3 * _W_MOMENTUM
    if 2 <= h1 <= 50:
        score += 0.5 * _W_MOMENTUM
    elif 50 < h1 <= 150:
        score += 0.35 * _W_MOMENTUM
    elif h1 > 150:
        score += 0.1 * _W_MOMENTUM
    elif h1 < -20:
        score -= 0.3 * _W_MOMENTUM
    pts = max(0, min(_W_MOMENTUM, int(score)))
    bands["momentum"] = {
        "5m_pct": m5,
        "1h_pct": h1,
        "points": pts,
        "max": _W_MOMENTUM,
    }
    rationale.append(f"momentum 5m={m5:+.1f}% 1h={h1:+.1f}% → {pts}/{_W_MOMENTUM}")
    return pts


def _band_age(
    market: TokenMarket | None,
    bands: dict[str, dict[str, Any]],
    rationale: list[str],
) -> int:
    age = market.age_minutes if market else None
    if age is None:
        bands["age"] = {"minutes": None, "points": 0, "max": _W_AGE}
        return 0
    # Under 5 min = effectively launch block; under 1 hour still nascent;
    # 1-24 hour window is the sweet spot; >7d is "old news" but not zero.
    if age < 5:
        pts = 1
    elif age < 60:
        pts = 4
    elif age < 60 * 24:
        pts = _W_AGE
    elif age < 60 * 24 * 7:
        pts = 7
    else:
        pts = 4
    bands["age"] = {"minutes": age, "points": pts, "max": _W_AGE}
    rationale.append(f"age {age} min → {pts}/{_W_AGE}")
    return pts
