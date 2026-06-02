"""COT confluence layer for the momentum engine (uses ``cot.context`` only)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import pandas as pd

from trading.crypto.cot.context import (
    OverlayMode,
    cot_side_from_bias,
    fetch_cot_biases,
    permission_for_side,
)
from trading.crypto.momentum.config import CotOverlayConfig


@dataclass(frozen=True)
class CotOverlayAssessment:
    passed: bool
    aligned: bool
    score_bonus: int
    permission: str
    contrarian_bias: str
    reason: str
    confidence: float | None = None
    historical_percentile: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "aligned": self.aligned,
            "score_bonus": self.score_bonus,
            "permission": self.permission,
            "contrarian_bias": self.contrarian_bias,
            "reason": self.reason,
            "confidence": self.confidence,
            "historical_percentile": self.historical_percentile,
        }


def _coin_from_symbol(symbol: str) -> str:
    return symbol.upper().replace("USDT", "")


def _aligned_with_side(side: str, contrarian_bias: str, effective_bias: str, permission: str) -> bool:
    if contrarian_bias == "bearish" and side == "short":
        return True
    if contrarian_bias == "bullish" and side == "long":
        return True
    return permission == "allow" and effective_bias == side


def evaluate_cot_overlay(
    *,
    side: str,
    symbol: str,
    config: CotOverlayConfig,
    as_of: pd.Timestamp | None = None,
    mode: OverlayMode = "live",
) -> CotOverlayAssessment:
    if not config.enabled:
        return CotOverlayAssessment(
            passed=True,
            aligned=False,
            score_bonus=0,
            permission="allow",
            contrarian_bias="neutral",
            reason="COT overlay disabled",
        )

    coin = _coin_from_symbol(symbol)
    ts = as_of if as_of is not None else pd.Timestamp.now(tz="UTC")
    if getattr(ts, "tzinfo", None) is None:
        ts = pd.Timestamp(ts, tz="UTC")
    else:
        ts = ts.tz_convert("UTC")

    perm, pct = permission_for_side(side, coin, ts)
    bias = fetch_cot_biases().get(coin) if mode == "live" else None
    confidence = bias.confidence if bias else None

    aligned = _aligned_with_side(side, perm.contrarian_bias, perm.effective_bias, perm.permission)
    if perm.permission == "block" and config.block_on_conflict:
        return CotOverlayAssessment(
            passed=False,
            aligned=False,
            score_bonus=0,
            permission="block",
            contrarian_bias=perm.contrarian_bias,
            reason=perm.reason,
            confidence=confidence,
            historical_percentile=pct,
        )

    bonus = config.score_bonus_aligned if aligned else (
        config.score_bonus_caution if perm.permission == "caution" else 0
    )
    passed = perm.permission != "block" or not config.block_on_conflict
    reason = perm.reason
    if bias and aligned and cot_side_from_bias(bias) == side:
        reason = f"COT {bias.bias} aligns with {side}"

    return CotOverlayAssessment(
        passed=passed,
        aligned=aligned,
        score_bonus=bonus if passed else 0,
        permission=perm.permission,
        contrarian_bias=perm.contrarian_bias,
        reason=reason,
        confidence=confidence,
        historical_percentile=pct,
    )