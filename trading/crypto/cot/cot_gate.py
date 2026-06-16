"""Weekly COT permission gate (contrarian-aware, shared by theory and momentum)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import pandas as pd


_REPORT_WEEK_RE = re.compile(r"(\d{4})\s+Report Week\s+(\d{1,2})")

Permission = Literal["allow", "caution", "block"]
ContrarianBias = Literal["bullish", "bearish", "neutral"]


@dataclass(frozen=True)
class CotPermission:
    permission: Permission
    effective_bias: str
    reason: str
    contrarian_bias: ContrarianBias
    net_non_commercial: float | None = None
    abs_percentile: float | None = None


def parse_report_week(value: str) -> pd.Timestamp | None:
    if not value:
        return None
    match = _REPORT_WEEK_RE.search(str(value))
    if not match:
        return None
    year = int(match.group(1))
    week = int(match.group(2))
    try:
        return pd.Timestamp(datetime.fromisocalendar(year, week, 2), tz="UTC")
    except ValueError:
        return None


def parse_report_date(row: dict[str, Any]) -> pd.Timestamp | None:
    """Parse either cached ISO report dates or CFTC report-week labels."""
    for key in ("report_date_as_yyyy_mm_dd", "report_date"):
        value = row.get(key)
        if not value:
            continue
        try:
            ts = pd.Timestamp(value)
            return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
        except (TypeError, ValueError):
            pass
    return parse_report_week(str(row.get("report_week", "")))


def _row_net_non_commercial(row: dict[str, Any]) -> float | None:
    long_val = row.get("noncomm_positions_long_all")
    short_val = row.get("noncomm_positions_short_all")
    if long_val is None or short_val is None:
        return None
    try:
        return float(long_val) - float(short_val)
    except (TypeError, ValueError):
        return None


def load_cot_history_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    records: list[tuple[pd.Timestamp, float]] = []
    for row in rows:
        ts = parse_report_date(row)
        if ts is None:
            continue
        net = _row_net_non_commercial(row)
        if net is None:
            continue
        records.append((ts, net))
    if not records:
        return pd.DataFrame(columns=["report_date", "net_non_commercial"])
    df = pd.DataFrame(records, columns=["report_date", "net_non_commercial"])
    df = df.drop_duplicates(subset=["report_date"], keep="last").sort_values("report_date")
    return df.reset_index(drop=True)


def compute_cot_state(
    history: pd.DataFrame | None,
    as_of: pd.Timestamp,
    min_rows: int = 12,
    history_window: int = 104,
) -> tuple[str, float, float] | None:
    if history is None or history.empty:
        return None
    sub = history[history["report_date"] <= as_of]
    if len(sub) < min_rows:
        return None
    recent = sub.tail(history_window)
    latest_net = float(recent["net_non_commercial"].iloc[-1])
    abs_series = recent["net_non_commercial"].abs()
    pct = float((abs_series <= abs(latest_net)).mean())
    if latest_net > 0:
        bias = "long"
    elif latest_net < 0:
        bias = "short"
    else:
        bias = "neutral"
    return bias, latest_net, pct


def contrarian_bias_from_state(
    net: float,
    abs_percentile: float,
    *,
    crowded_high: float = 0.70,
    crowded_low: float = 0.30,
) -> ContrarianBias:
    if net > 0 and abs_percentile >= crowded_high:
        return "bearish"
    if net < 0 and abs_percentile <= crowded_low:
        return "bullish"
    if net > 0:
        return "bearish"
    if net < 0:
        return "bullish"
    return "neutral"


def _price_bias_to_direction(price_bias: str) -> str | None:
    normalized = price_bias.lower()
    if normalized in {"long", "bullish", "up"}:
        return "long"
    if normalized in {"short", "bearish", "down"}:
        return "short"
    return None


def evaluate_cot_permission(
    price_bias: str,
    cot_history: pd.DataFrame | None,
    as_of: pd.Timestamp,
    *,
    disagreement_pct_threshold: float = 0.60,
    extreme_pct_threshold: float = 0.85,
) -> CotPermission:
    direction = _price_bias_to_direction(price_bias)
    if direction is None:
        return CotPermission(
            permission="block",
            effective_bias="neutral",
            reason="price bias is neutral",
            contrarian_bias="neutral",
        )

    state = compute_cot_state(cot_history, as_of)
    if state is None:
        return CotPermission(
            permission="allow",
            effective_bias=direction,
            reason="COT unavailable — permissive pass",
            contrarian_bias="neutral",
        )

    spec_direction, net, pct = state
    contrarian = contrarian_bias_from_state(net, pct)
    maps_to_long = contrarian == "bullish"
    maps_to_short = contrarian == "bearish"

    if direction == "long" and spec_direction == "long" and pct >= extreme_pct_threshold:
        return CotPermission(
            permission="block",
            effective_bias="neutral",
            reason=(
                f"specs crowded long (pct {pct:.0%}) — reversal risk; "
                f"do not chase fresh longs"
            ),
            contrarian_bias=contrarian,
            net_non_commercial=net,
            abs_percentile=pct,
        )
    if direction == "short" and spec_direction == "short" and pct >= extreme_pct_threshold:
        return CotPermission(
            permission="block",
            effective_bias="neutral",
            reason=(
                f"specs crowded short (pct {pct:.0%}) — reversal risk; "
                f"do not chase fresh shorts"
            ),
            contrarian_bias=contrarian,
            net_non_commercial=net,
            abs_percentile=pct,
        )

    if direction == "short" and spec_direction == "long" and pct >= extreme_pct_threshold:
        return CotPermission(
            permission="allow",
            effective_bias="short",
            reason=(
                f"specs crowded long (pct {pct:.0%}) — contrarian supports short fade"
            ),
            contrarian_bias=contrarian,
            net_non_commercial=net,
            abs_percentile=pct,
        )
    if direction == "long" and spec_direction == "short" and pct >= extreme_pct_threshold:
        return CotPermission(
            permission="allow",
            effective_bias="long",
            reason=(
                f"specs crowded short (pct {pct:.0%}) — contrarian supports long fade"
            ),
            contrarian_bias=contrarian,
            net_non_commercial=net,
            abs_percentile=pct,
        )

    if (direction == "long" and maps_to_long) or (direction == "short" and maps_to_short):
        return CotPermission(
            permission="allow",
            effective_bias=direction,
            reason=f"COT contrarian read confirms {direction} (pct {pct:.0%})",
            contrarian_bias=contrarian,
            net_non_commercial=net,
            abs_percentile=pct,
        )

    if pct >= disagreement_pct_threshold:
        if (direction == "long" and maps_to_short) or (direction == "short" and maps_to_long):
            return CotPermission(
                permission="block",
                effective_bias="neutral",
                reason=(
                    f"COT contrarian {contrarian} (pct {pct:.0%}) "
                    f"opposes price bias {direction}"
                ),
                contrarian_bias=contrarian,
                net_non_commercial=net,
                abs_percentile=pct,
            )

    return CotPermission(
        permission="caution",
        effective_bias=direction,
        reason=f"COT {contrarian} vs price {direction} — immaterial (pct {pct:.0%})",
        contrarian_bias=contrarian,
        net_non_commercial=net,
        abs_percentile=pct,
    )


def weekly_cot_filter(
    price_bias: str,
    cot_history: pd.DataFrame | None,
    as_of: pd.Timestamp,
    *,
    disagreement_pct_threshold: float = 0.60,
    extreme_pct_threshold: float = 0.85,
) -> tuple[bool, str, str]:
    result = evaluate_cot_permission(
        price_bias,
        cot_history,
        as_of,
        disagreement_pct_threshold=disagreement_pct_threshold,
        extreme_pct_threshold=extreme_pct_threshold,
    )
    passes = result.permission != "block"
    return passes, result.effective_bias, result.reason


_COT_HISTORY_CACHE: dict[tuple[str, float], dict[str, pd.DataFrame]] = {}


def load_cached_cot_history(
    asset: str,
    report_type: str = "futures_and_options",
    include_micro: bool = False,
    cache_path: Path | None = None,
) -> pd.DataFrame:
    path = cache_path or (Path.home() / ".cache" / "nave" / "cot" / "history_cot.json")
    empty = pd.DataFrame(columns=["report_date", "net_non_commercial"])
    if not path.exists():
        return empty
    import json

    # The history JSON is static within a process run but is read once per bar
    # during historical backtests (long + short). Cache parsed frames keyed by
    # (path, mtime) so a weekly COT refresh still invalidates the cache.
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return empty
    cache_key = (str(path), mtime)
    per_path = _COT_HISTORY_CACHE.get(cache_key)
    if per_path is None:
        try:
            blob = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return empty
        per_path = {
            blob_key: load_cot_history_frame(rows)
            for blob_key, rows in blob.items()
        }
        _COT_HISTORY_CACHE.clear()
        _COT_HISTORY_CACHE[cache_key] = per_path

    key = f"{asset}|{report_type}|micro={int(include_micro)}"
    frame = per_path.get(key)
    if frame is None:
        return empty
    return frame.copy()
