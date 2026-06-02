"""Tests for options position context formatting."""

from __future__ import annotations

from options.position_context import (
    format_position_digest_line,
    format_position_panel_lines,
    position_context_from_scan_row,
)


def _row() -> dict:
    return {
        "ticker": "WFC",
        "status": "trade_candidate",
        "trade_decision": {
            "status": "trade_candidate",
            "open_recommended": True,
            "entry_quality": "high_odds",
            "reason": "Income setup passed filters.",
        },
        "executable_strategy": "bull_put_credit_spread",
        "executable_setup": {
            "strategy_name": "bull_put_credit_spread",
            "bias": "bullish",
            "thesis": "Pullback support holds.",
            "rationale": "Defined-risk premium.",
            "setup_summary": "sell 1 put 70; buy 1 put 65",
        },
        "executable_metrics": {
            "composite_score": 32.5,
            "pop": 72.0,
            "expected_value": 45.0,
            "probability_of_touch": 55.0,
            "theta_per_day": 0.12,
            "max_loss": 500.0,
        },
        "top_modeled_strategy": "long_straddle",
        "top_modeled_metrics": {"composite_score": 40.0, "expected_value": 90.0},
        "warnings": ["slightly_negative_expected_value"],
    }


def test_position_context_from_scan_row() -> None:
    ctx = position_context_from_scan_row(_row(), days_to_exp=30, congress_tickers=frozenset({"WFC"}))
    assert ctx["ticker"] == "WFC"
    assert ctx["setup_summary"] == "sell 1 put 70; buy 1 put 65"
    assert ctx["congress_boost"] is True
    assert "WFC" in ctx["deep_dive_cmd"]


def test_format_position_digest_line() -> None:
    ctx = position_context_from_scan_row(_row(), days_to_exp=30)
    line = format_position_digest_line(ctx)
    assert "WFC" in line
    assert "sell 1 put 70" in line
    assert "PoP" in line


def test_format_position_panel_lines() -> None:
    ctx = position_context_from_scan_row(_row(), days_to_exp=30)
    lines = format_position_panel_lines(ctx)
    assert any("Position:" in line for line in lines)
    assert any("Deep dive:" in line for line in lines)