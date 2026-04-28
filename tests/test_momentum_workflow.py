from __future__ import annotations

from pathlib import Path

import pandas as pd

from trading.crypto.momentum.review import build_review_summary
from trading.crypto.momentum.workflow import (
    build_automation_guardrails,
    completed_periods,
    next_period,
    render_period_summary,
    resolve_period,
    summarize_period_result,
    write_iteration_report,
)


def test_completed_periods_parses_iteration_markdown(tmp_path: Path) -> None:
    file_path = tmp_path / "iter_1.md"
    file_path.write_text(
        "> **Command:** `python scripts/momentum_backtest.py --period 2022-bear --symbols BTC ETH`\n"
    )

    assert completed_periods(tmp_path) == ["2022-bear"]
    assert next_period(tmp_path) == "2017-bull+2018-bear"


def test_next_period_skips_completed(tmp_path: Path) -> None:
    (tmp_path / "iter_1.md").write_text(
        "> **Backtest command:** `python scripts/momentum_backtest.py --period 2017-bull+2018-bear --symbols BTC ETH`\n"
    )
    (tmp_path / "iter_2.md").write_text(
        "> **Backtest command:** `python scripts/momentum_backtest.py --period 2019-recovery --symbols BTC ETH`\n"
    )

    assert next_period(tmp_path) == "2020-covid-crash"


def test_resolve_today_period_is_recent() -> None:
    start, end = resolve_period("TODAY")

    assert start.tz is not None
    assert end.tz is not None
    assert (end - start) == pd.Timedelta(days=90)


def test_summarize_period_result_emits_threshold_hint() -> None:
    payload = {
        "metrics": {
            "pct_reaching_8": 0.25,
            "max_drawdown": 6.0,
        },
        "baseline": {
            "delta": {
                "expectancy": -0.3,
            }
        },
        "trades": [
            {"side": "long", "r_multiple": -1.0, "confidence_score": 76},
            {"side": "short", "r_multiple": -0.5, "confidence_score": 77},
            {"side": "long", "r_multiple": 1.2, "confidence_score": 92},
        ],
    }

    review = summarize_period_result(payload)

    assert "75-79" in review["confidence_bands"]
    assert any("baseline" in hint.lower() for hint in review["improvement_hints"])
    assert any("score threshold" in hint.lower() for hint in review["improvement_hints"])


def test_render_period_summary_contains_symbol_and_pooled_lines() -> None:
    payload = {
        "period": "2022-bear",
        "requested_window": {
            "start": "2022-01-01T00:00:00+00:00",
            "end": "2022-12-31T00:00:00+00:00",
        },
        "effective_window": {
            "start": "2022-02-01T00:00:00+00:00",
            "end": "2022-12-31T00:00:00+00:00",
        },
        "trigger_timeframe": "1H",
        "window": {
            "start": "2022-02-01T00:00:00+00:00",
            "end": "2022-12-31T00:00:00+00:00",
        },
        "coverage": {"complete": False},
        "automation": {
            "ready": False,
            "warnings": [
                {"severity": "error", "message": "Coverage is partial for at least one symbol or timeframe; do not promote this artifact into unattended automation."}
            ],
        },
        "results": {
            "BTC": {
                "trade_count": 4,
                "metrics": {
                    "win_rate": 0.5,
                    "expectancy": 0.25,
                    "max_drawdown": 1.5,
                    "pct_reaching_8": 0.5,
                },
                "coverage": {"complete": False},
                "review": {"improvement_hints": ["Inspect short-side late entries."]},
            }
        },
        "pooled": {
            "trade_count": 4,
            "metrics": {"win_rate": 0.5, "expectancy": 0.25},
        },
        "skipped": {},
    }

    summary = render_period_summary(payload)

    assert "[BTC]" in summary
    assert "[pooled]" in summary
    assert "Inspect short-side late entries." in summary
    assert "requested window:" in summary
    assert "coverage: partial" in summary
    assert "automation: blocked" in summary


def test_build_automation_guardrails_flags_today_low_sample() -> None:
    payload = {
        "period": "TODAY",
        "coverage": {"complete": True},
        "pooled": {
            "trade_count": 4,
            "metrics": {
                "expectancy": 1.2,
                "pct_reaching_8": 0.5,
            },
        },
        "skipped": {},
    }

    guardrails = build_automation_guardrails(payload)

    assert guardrails["ready"] is True
    codes = {warning["code"] for warning in guardrails["warnings"]}
    assert "low_sample" in codes
    assert "live_window" in codes


def test_summarize_period_result_flags_partial_coverage() -> None:
    payload = {
        "metrics": {"pct_reaching_8": 0.0, "max_drawdown": 0.0},
        "coverage": {
            "complete": False,
            "effective_window": {
                "start": "2022-02-01T00:00:00+00:00",
                "end": "2022-12-31T00:00:00+00:00",
            },
        },
        "trades": [
            {"side": "long", "r_multiple": 1.0, "confidence_score": 90},
        ],
    }

    review = summarize_period_result(payload)

    assert any("partial" in hint.lower() for hint in review["improvement_hints"])


def test_write_iteration_report_creates_progress_file(tmp_path: Path) -> None:
    artifact_path = tmp_path / "artifact.json"
    artifact_path.write_text("{}", encoding="utf-8")
    payload = {
        "period": "2022-bear",
        "symbols": ["BTC", "ETH"],
        "trigger_timeframe": "1H",
        "requested_window": {
            "start": "2022-01-01T00:00:00+00:00",
            "end": "2022-12-31T00:00:00+00:00",
        },
        "effective_window": {
            "start": "2022-02-01T00:00:00+00:00",
            "end": "2022-12-31T00:00:00+00:00",
        },
        "coverage": {"complete": False},
        "results": {
            "BTC": {
                "trade_count": 3,
                "metrics": {"win_rate": 0.5, "expectancy": 0.2},
                "coverage": {
                    "complete": False,
                    "effective_window": {
                        "start": "2022-02-01T00:00:00+00:00",
                        "end": "2022-12-31T00:00:00+00:00",
                    },
                },
                "review": {"improvement_hints": ["Cobertura parcial."]},
            }
        },
        "pooled": {
            "trade_count": 3,
            "metrics": {"win_rate": 0.5, "expectancy": 0.2},
        },
    }

    report_path = write_iteration_report(payload, artifact_path, iterations_dir=tmp_path / "iterations")

    content = report_path.read_text(encoding="utf-8")
    assert report_path.name == "iter_1.md"
    assert "python scripts/momentum_backtest.py --period 2022-bear --symbols BTC ETH --trigger-timeframe 1H" in content
    assert completed_periods(tmp_path / "iterations") == ["2022-bear"]


def test_build_review_summary_uses_latest_artifact_per_period(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    old = {
        "period": "2022-bear",
        "coverage": {"complete": True},
        "pooled": {"trade_count": 3, "metrics": {"win_rate": 0.4, "expectancy": 0.1, "max_drawdown": 1.0, "pct_reaching_8": 0.0}},
        "results": {"BTC": {"trades": [{"confidence_score": 80, "r_multiple": -1.0, "reached_8_pct": False}]}}
    }
    new = {
        "period": "2022-bear",
        "coverage": {"complete": True},
        "pooled": {"trade_count": 2, "metrics": {"win_rate": 1.0, "expectancy": 2.0, "max_drawdown": 0.0, "pct_reaching_8": 1.0}},
        "results": {"BTC": {"trades": [{"confidence_score": 92, "r_multiple": 2.0, "reached_8_pct": True}]}}
    }
    (raw_dir / "momentum_backtest_2022-bear_20260428T100000Z.json").write_text(__import__("json").dumps(old), encoding="utf-8")
    (raw_dir / "momentum_backtest_2022-bear_20260428T110000Z.json").write_text(__import__("json").dumps(new), encoding="utf-8")

    summary = build_review_summary(raw_dir)

    assert summary["periods"][0]["trade_count"] == 2
    assert summary["confidence_bands"][0]["band"] == "90-100"


def test_build_review_summary_reports_shadow_ready_and_focus_periods(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()

    fixtures = {
        "2017-bull+2018-bear": (True, 25, 0.8, 1.9, 0.8),
        "2019-recovery": (True, 25, 0.82, 1.8, 0.82),
        "2020-covid-crash": (True, 25, 0.78, 2.0, 0.76),
        "2020-recovery+2021-ATH": (True, 25, 0.77, 1.9, 0.75),
        "2022-bear": (True, 25, 0.74, 1.7, 0.7),
        "2023-recovery": (True, 10, 0.72, 1.6, 0.4),
        "2024-ETF-approval": (True, 10, 0.76, 1.55, 0.41),
        "2024-2025-bull": (True, 10, 0.71, 1.51, 0.55),
        "TODAY": (False, 5, 0.75, 1.85, 0.75),
    }

    for index, (period, metrics) in enumerate(fixtures.items(), start=1):
        complete, trade_count, win_rate, expectancy, pct_reaching_8 = metrics
        payload = {
            "period": period,
            "coverage": {"complete": complete},
            "pooled": {
                "trade_count": trade_count,
                "metrics": {
                    "win_rate": win_rate,
                    "expectancy": expectancy,
                    "max_drawdown": 1.0,
                    "pct_reaching_8": pct_reaching_8,
                },
            },
            "results": {
                "BTC": {
                    "trades": [
                        {"confidence_score": 92, "r_multiple": 2.0, "reached_8_pct": True}
                        for _ in range(trade_count)
                    ]
                }
            },
        }
        (raw_dir / f"momentum_backtest_{period}_20260428T10{index:04d}Z.json").write_text(
            __import__("json").dumps(payload),
            encoding="utf-8",
        )

    summary = build_review_summary(raw_dir)

    assert summary["readiness"]["status"] == "shadow-ready"
    assert summary["readiness"]["focus_periods"] == ["2023-recovery", "2024-ETF-approval", "TODAY"]
    assert "shadow deployment" in summary["recommendation"]
    assert summary["automation"]["ready"] is True
    warning_codes = {warning["code"] for warning in summary["automation"]["warnings"]}
    assert "partial_regimes" in warning_codes
    assert "focus_periods" in warning_codes
    assert "today_low_sample" in warning_codes