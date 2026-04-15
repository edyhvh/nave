"""Tests for the weekly COT filter."""

from __future__ import annotations

import pandas as pd

from trading.cot_gate import (
    compute_cot_state,
    load_cot_history_frame,
    parse_report_week,
    weekly_cot_filter,
)


def _history(net_values: list[float], start: str = "2024-01-02") -> pd.DataFrame:
    dates = pd.date_range(start=start, periods=len(net_values), freq="W-TUE", tz="UTC")
    return pd.DataFrame({"report_date": dates, "net_non_commercial": net_values})


def test_parse_report_week_standard():
    ts = parse_report_week("2025 Report Week 14")
    assert ts is not None
    assert ts.year == 2025
    # ISO week 14 Tuesday of 2025 is 2025-04-01
    assert ts.month == 4 and ts.day == 1


def test_parse_report_week_invalid():
    assert parse_report_week("") is None
    assert parse_report_week("garbage") is None


def test_load_cot_history_frame_drops_malformed():
    rows = [
        {"report_week": "2025 Report Week 10", "noncomm_positions_long_all": 15000,
         "noncomm_positions_short_all": 10000},
        {"report_week": "not a week", "noncomm_positions_long_all": 1, "noncomm_positions_short_all": 2},
        {"report_week": "2025 Report Week 11", "noncomm_positions_long_all": None,
         "noncomm_positions_short_all": 100},
    ]
    frame = load_cot_history_frame(rows)
    assert len(frame) == 1
    assert frame["net_non_commercial"].iloc[0] == 5000


def test_compute_cot_state_percentile_at_extreme():
    # Most values small, one big positive — latest week reads as extreme.
    nets = [500] * 20 + [10_000]
    hist = _history(nets)
    state = compute_cot_state(hist, hist["report_date"].iloc[-1])
    assert state is not None
    bias, _net, pct = state
    assert bias == "long"
    assert pct == 1.0


def test_compute_cot_state_returns_none_when_thin():
    hist = _history([1, 2, 3])
    state = compute_cot_state(hist, hist["report_date"].iloc[-1])
    assert state is None


def test_filter_permissive_when_no_history():
    passes, bias, reason = weekly_cot_filter("long", None, pd.Timestamp.now(tz="UTC"))
    assert passes is True
    assert bias == "long"
    assert "unavailable" in reason.lower() or "permissive" in reason.lower()


def test_filter_agreement_passes():
    nets = list(range(100, 1100, 100))  # monotonically rising, latest is mid-high
    hist = _history(nets)
    passes, bias, _ = weekly_cot_filter("long", hist, hist["report_date"].iloc[-1])
    assert passes is True
    assert bias == "long"


def test_filter_agreement_but_extreme_neutralizes():
    nets = [300] * 20 + [9_999]  # latest is the extreme of the window
    hist = _history(nets)
    passes, bias, reason = weekly_cot_filter("long", hist, hist["report_date"].iloc[-1])
    assert passes is False
    assert bias == "neutral"
    assert "extreme" in reason.lower()


def test_filter_disagreement_material_neutralizes():
    # SMA bias is long, COT net is deeply negative and percentile is high.
    nets = [-300] * 15 + [-9_999]
    hist = _history(nets)
    passes, bias, reason = weekly_cot_filter("long", hist, hist["report_date"].iloc[-1])
    assert passes is False
    assert bias == "neutral"
    assert "contradicts" in reason.lower()


def test_filter_disagreement_immaterial_passes():
    # COT points short but with shallow positioning — don't veto SMA long.
    nets = [-5000, -5200, -4800, -5100] * 5 + [-50]  # latest is lowest |net|
    hist = _history(nets)
    passes, bias, reason = weekly_cot_filter("long", hist, hist["report_date"].iloc[-1])
    assert passes is True
    assert bias == "long"
    assert "immaterial" in reason.lower()


def test_filter_neutral_sma_short_circuits():
    passes, bias, reason = weekly_cot_filter("neutral", None, pd.Timestamp.now(tz="UTC"))
    assert passes is False
    assert bias == "neutral"
    assert "sma" in reason.lower()


def test_filter_slices_by_as_of():
    # Recent rows should not leak into an earlier as_of evaluation.
    nets = [100] * 20 + [9_999]  # the spike is in the last week
    hist = _history(nets, start="2024-01-02")
    early = hist["report_date"].iloc[10]
    passes, _, _ = weekly_cot_filter("long", hist, early)
    # At the early as_of, the spike hasn't happened, so no extreme veto.
    assert passes is True
