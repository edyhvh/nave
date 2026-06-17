from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.capitulation_reset_backtest import (
    build_fixture_frames,
    fixture_cot_bias,
    run_backtest,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_fixture_backtest_reports_signal_counts_and_trades() -> None:
    payload = run_backtest(
        build_fixture_frames(),
        cot_bias_fn=fixture_cot_bias,
        step_bars=1,
        warmup=15,
    )

    counts = payload["counts"]
    assert counts["watch"] >= 1
    assert counts["starter_long"] + counts["confirmed_long"] >= 1
    assert payload["trade_count"] >= 1
    assert isinstance(payload["total_sized_r"], float)
    assert payload["metrics"]["win_rate"] >= 0
    assert "max_drawdown_sized_r" in payload["metrics"]
    assert payload["trades"]
    assert all("sized_r" in trade and "exit_reason" in trade for trade in payload["trades"])


def test_fixture_backtest_does_not_duplicate_overlapping_active_trades() -> None:
    payload = run_backtest(
        build_fixture_frames(),
        cot_bias_fn=fixture_cot_bias,
        step_bars=1,
        warmup=15,
    )

    by_symbol: dict[str, list[dict[str, str]]] = {}
    for trade in payload["trades"]:
        by_symbol.setdefault(trade["symbol"], []).append(trade)

    for trades in by_symbol.values():
        ordered = sorted(trades, key=lambda trade: trade["setup_time"])
        for previous, current in zip(ordered, ordered[1:]):
            assert current["setup_time"] > previous["exit_time"]


def test_missing_derivative_reset_data_blocks_trades_but_reports_watches() -> None:
    payload = run_backtest(
        build_fixture_frames(),
        cot_bias_fn=fixture_cot_bias,
        step_bars=1,
        warmup=15,
        funding_rate=None,
        open_interest=None,
        oi_contracting=False,
    )

    assert payload["counts"]["watch"] >= 1
    assert payload["trade_count"] == 0


def test_fixture_cli_runs_offline_json() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "capitulation_reset_backtest.py"),
            "--fixture",
            "--json",
        ],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(proc.stdout[proc.stdout.index("{") :])
    assert payload["mode"] == "fixture"
    assert set(payload["counts"]) >= {"watch", "starter_long", "confirmed_long"}
    assert "total_sized_r" in payload
