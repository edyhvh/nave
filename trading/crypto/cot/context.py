"""Shared COT context helpers for analysis and momentum."""

from __future__ import annotations

from typing import Any, Literal

import pandas as pd

from trading.crypto.cot.cot_analyzer import COTAnalyzer, COTBias
from trading.crypto.cot.cot_fetcher import fetch_latest_cot
from trading.crypto.cot.cot_gate import (
    evaluate_cot_permission,
    load_cached_cot_history,
)


OverlayMode = Literal["live", "historical"]


def cot_history_for_coin(coin: str) -> pd.DataFrame:
    if coin in {"BTC", "ETH"}:
        return load_cached_cot_history("BTC")
    return load_cached_cot_history(coin)


def fetch_cot_biases(*, cot_data: dict[str, Any] | None = None) -> dict[str, COTBias]:
    payload = cot_data
    if payload is None:
        try:
            payload = fetch_latest_cot(debug=False)
        except Exception:
            payload = {}
    return COTAnalyzer().analyze(payload or {})


def cot_side_from_bias(bias: COTBias | None) -> str | None:
    if bias is None:
        return None
    if bias.bias == "bullish":
        return "long"
    if bias.bias == "bearish":
        return "short"
    return None


def permission_for_side(
    side: str,
    coin: str,
    as_of: pd.Timestamp,
) -> tuple[Any, int | None]:
    """Return (CotPermission, historical_percentile 0-100)."""
    ts = as_of.tz_convert("UTC") if getattr(as_of, "tzinfo", None) else pd.Timestamp(as_of, tz="UTC")
    perm = evaluate_cot_permission(side, cot_history_for_coin(coin), ts)
    pct = int(perm.abs_percentile * 100) if perm.abs_percentile is not None else None
    return perm, pct