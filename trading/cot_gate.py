"""Weekly COT filter for the theory_v2 engine.

The engine's SMA-only weekly bias is blind to institutional positioning.
``cot_integration.yaml`` places COT fourth in the weekly decision order:
used to *confirm or warn*, never to *drive*. This module implements that
contract as a pure function that sits between the SMA bias and the daily
gate.

Two rules:

  1. **Disagreement rule.** If COT non-commercial net direction disagrees
     with the SMA bias and positioning is material (percentile of the
     absolute net is >= ``disagreement_pct_threshold``), neutralize the
     bias. Below that threshold the COT is noise and the SMA wins.

  2. **Reversal warning.** If COT agrees with the SMA bias but positioning
     is at an extreme (percentile >= ``extreme_pct_threshold``), neutralize.
     This follows ``cot_integration.yaml`` §contrarian_usage — do not chase
     fresh entries when non-commercials are already crowded.

If no COT data is available for ``as_of`` (pre-2022 for BTC, always for
ETH) the gate is permissive.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


_REPORT_WEEK_RE = re.compile(r"(\d{4})\s+Report Week\s+(\d{1,2})")


def parse_report_week(value: str) -> pd.Timestamp | None:
    """Convert a CFTC ``report_week`` string to the Tuesday timestamp."""
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
    """Build a sorted ``(report_date, net_non_commercial)`` frame.

    Accepts the raw row list shipped by ``trading.cot.cot_fetcher``
    (e.g. ``~/.cache/nave/cot/history_cot.json``). Unparseable rows are
    dropped silently.
    """
    records: list[tuple[pd.Timestamp, float]] = []
    for row in rows:
        ts = parse_report_week(str(row.get("report_week", "")))
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
    """Return ``(bias, net, abs_percentile)`` at ``as_of`` or ``None``.

    ``abs_percentile`` is the rank of the latest absolute net within the
    trailing ``history_window`` weeks, normalized to [0, 1]. A fresh
    extreme reads 1.0; a middling reading reads 0.5.
    """
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


def weekly_cot_filter(
    sma_bias: str,
    cot_history: pd.DataFrame | None,
    as_of: pd.Timestamp,
    *,
    disagreement_pct_threshold: float = 0.60,
    extreme_pct_threshold: float = 0.85,
) -> tuple[bool, str, str]:
    """Apply the COT weekly filter on top of the SMA bias.

    Returns ``(passes, effective_bias, reason)``. When ``passes`` is
    ``False`` the caller should stop evaluating (stage ``weekly_cot``).
    """
    if sma_bias == "neutral":
        return False, "neutral", "SMA bias is neutral"

    state = compute_cot_state(cot_history, as_of)
    if state is None:
        return True, sma_bias, "COT unavailable — permissive pass"

    cot_bias, _net, pct = state

    if cot_bias != sma_bias:
        if pct >= disagreement_pct_threshold:
            return False, "neutral", (
                f"COT {cot_bias} (pct {pct:.0%}) contradicts SMA {sma_bias}"
            )
        return True, sma_bias, f"COT {cot_bias} pct {pct:.0%} — immaterial"

    if pct >= extreme_pct_threshold:
        return False, "neutral", (
            f"COT agrees with {sma_bias} but extreme (pct {pct:.0%}) — reversal risk"
        )
    return True, sma_bias, f"COT confirms {sma_bias} (pct {pct:.0%})"


def load_cached_cot_history(
    asset: str,
    report_type: str = "futures_and_options",
    include_micro: bool = False,
    cache_path: Path | None = None,
) -> pd.DataFrame:
    """Load the persisted COT history cache and return a frame for ``asset``.

    Returns an empty frame when the cache is missing or has no rows for
    the requested asset. This is the path used by the backtest loop.
    """
    path = cache_path or (Path.home() / ".cache" / "nave" / "cot" / "history_cot.json")
    if not path.exists():
        return pd.DataFrame(columns=["report_date", "net_non_commercial"])
    import json
    try:
        blob = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return pd.DataFrame(columns=["report_date", "net_non_commercial"])
    key = f"{asset}|{report_type}|micro={int(include_micro)}"
    rows = blob.get(key, [])
    return load_cot_history_frame(rows)
