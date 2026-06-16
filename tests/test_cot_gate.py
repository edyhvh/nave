"""Tests for the weekly COT filter (contrarian-aware)."""

from __future__ import annotations

import pandas as pd

from trading.crypto.cot_gate import (
    compute_cot_state,
    contrarian_bias_from_state,
    evaluate_cot_permission,
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
    assert ts.month == 4 and ts.day == 1


def test_load_cot_history_frame_accepts_cached_report_date_shape():
    frame = load_cot_history_frame(
        [
            {
                "report_date_as_yyyy_mm_dd": "2026-06-09",
                "noncomm_positions_long_all": 12_000,
                "noncomm_positions_short_all": 7_500,
            }
        ]
    )
    assert len(frame) == 1
    assert frame["report_date"].iloc[0] == pd.Timestamp("2026-06-09", tz="UTC")
    assert frame["net_non_commercial"].iloc[0] == 4_500


def test_filter_permissive_when_no_history():
    passes, bias, reason = weekly_cot_filter("short", None, pd.Timestamp.now(tz="UTC"))
    assert passes is True
    assert bias == "short"


def test_contrarian_supports_short_when_specs_crowded_long():
    nets = [300] * 20 + [9_999]
    hist = _history(nets)
    as_of = hist["report_date"].iloc[-1]
    perm = evaluate_cot_permission("short", hist, as_of)
    assert perm.permission == "allow"
    assert perm.effective_bias == "short"
    assert "contrarian" in perm.reason.lower()


def test_blocks_chase_long_into_crowded_specs():
    nets = [300] * 20 + [9_999]
    hist = _history(nets)
    as_of = hist["report_date"].iloc[-1]
    perm = evaluate_cot_permission("long", hist, as_of)
    assert perm.permission == "block"
    assert perm.effective_bias == "neutral"
    assert "reversal" in perm.reason.lower() or "crowded" in perm.reason.lower()


def test_blocks_chase_short_into_crowded_specs_short():
    nets = [-300] * 20 + [-9_999]
    hist = _history(nets)
    as_of = hist["report_date"].iloc[-1]
    perm = evaluate_cot_permission("short", hist, as_of)
    assert perm.permission == "block"


def test_material_conflict_blocks_long():
    # Rising spec net-long stack: contrarian bearish opposes a long price bias.
    nets = list(range(500, 6500, 500))
    hist = _history(nets)
    as_of = hist["report_date"].iloc[-1]
    perm = evaluate_cot_permission("long", hist, as_of)
    assert perm.permission == "block"
    assert "crowded" in perm.reason.lower() or "opposes" in perm.reason.lower()


def test_immaterial_conflict_caution_long():
    nets = [-5000, -5200, -4800, -5100] * 5 + [-50]
    hist = _history(nets)
    as_of = hist["report_date"].iloc[-1]
    perm = evaluate_cot_permission("long", hist, as_of)
    assert perm.permission in {"caution", "allow"}
    passes, bias, _ = weekly_cot_filter("long", hist, as_of)
    assert passes is True
    assert bias == "long"


def test_contrarian_bias_from_state():
    assert contrarian_bias_from_state(5000, 0.95) == "bearish"
    assert contrarian_bias_from_state(-5000, 0.05) == "bullish"
