from __future__ import annotations

import json
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from trading.crypto.momentum.config import TheoryOverlayConfig, load_momentum_config
from trading.crypto.momentum.review import latest_artifacts
from trading.crypto.momentum.theory_overlay import evaluate_theory_overlay
from trading.crypto.momentum.workflow import load_symbol_frames, resolve_period


def _default_period_order() -> list[str]:
    return [
        "2017-bull+2018-bear",
        "2019-recovery",
        "2020-covid-crash",
        "2020-recovery+2021-ATH",
        "2022-bear",
        "2023-recovery",
        "2024-ETF-approval",
        "2024-2025-bull",
        "TODAY",
    ]


def _resolve_periods(raw_dir: Path, periods: list[str] | None) -> list[tuple[str, dict[str, Any]]]:
    latest = latest_artifacts(raw_dir)
    ordered = _default_period_order()
    selected = periods or [period for period in ordered if period in latest]
    return [(period, latest[period][1]) for period in selected if period in latest]


def _build_trade_surfaces(
    raw_dir: Path,
    periods: list[str] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for period, payload in _resolve_periods(raw_dir, periods):
        start, end = resolve_period(period)
        trigger_forward_buffer = pd.Timedelta(0) if period == "TODAY" else pd.Timedelta(days=14)
        frame_cache: dict[str, dict[str, pd.DataFrame]] = {}
        for symbol, result in payload.get("results", {}).items():
            if symbol not in frame_cache:
                frame_cache[symbol] = load_symbol_frames(
                    symbol,
                    start,
                    end,
                    trigger_forward_buffer=trigger_forward_buffer,
                )
            daily = frame_cache[symbol]["daily"]
            setup = frame_cache[symbol]["setup"]
            for trade in result.get("trades", []):
                entry_time = pd.Timestamp(trade["entry_time"])
                rows.append(
                    {
                        "period": period,
                        "symbol": symbol,
                        "side": str(trade["side"]),
                        "entry_time": trade["entry_time"],
                        "r_multiple": float(trade["r_multiple"]),
                        "expected_move_pct": float(trade.get("expected_move_pct", 0.0)),
                        "daily": daily[daily["timestamp"] <= entry_time].set_index("timestamp"),
                        "setup": setup[setup["timestamp"] <= entry_time].set_index("timestamp"),
                    }
                )
    return rows


def _blocked_stage_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    stages = sorted({row["stage"] for row in rows})
    return {stage: sum(1 for row in rows if row["stage"] == stage) for stage in stages}


def _summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    blocked = [row for row in rows if not row["passed"]]
    kept = [row for row in rows if row["passed"]]
    kept_count = len(kept)
    return {
        "trade_count": len(rows),
        "kept_trades": kept_count,
        "kept_win_rate": round(sum(1 for row in kept if row["r_multiple"] > 0) / kept_count, 4)
        if kept_count
        else 0.0,
        "kept_expectancy": round(sum(row["r_multiple"] for row in kept) / kept_count, 4)
        if kept_count
        else 0.0,
        "blocked_trades": len(blocked),
        "blocked_winners": sum(1 for row in blocked if row["r_multiple"] > 0),
        "blocked_losers": sum(1 for row in blocked if row["r_multiple"] <= 0),
        "blocked_by_stage": _blocked_stage_counts(blocked),
    }


def evaluate_overlay_replay(
    raw_dir: Path,
    *,
    config: TheoryOverlayConfig | None = None,
    periods: list[str] | None = None,
    blocked_examples_per_period: int = 3,
) -> dict[str, Any]:
    overlay_config = config or load_momentum_config().theory_overlay
    trade_surfaces = _build_trade_surfaces(raw_dir, periods)
    evaluated_rows: list[dict[str, Any]] = []

    for row in trade_surfaces:
        overlay = evaluate_theory_overlay(
            side=row["side"],
            daily=row["daily"],
            setup=row["setup"],
            expected_move_pct=row["expected_move_pct"],
            config=overlay_config,
        )
        evaluated_rows.append(
            {
                "period": row["period"],
                "symbol": row["symbol"],
                "side": row["side"],
                "entry_time": row["entry_time"],
                "r_multiple": row["r_multiple"],
                "expected_move_pct": row["expected_move_pct"],
                "passed": overlay.passed,
                "stage": overlay.stage,
                "reason": overlay.reason,
                "retrace_fraction": overlay.retrace_fraction,
                "weekly_velocity_atr": overlay.weekly_velocity_atr,
            }
        )

    periods_out: list[dict[str, Any]] = []
    for period in periods or _default_period_order():
        period_rows = [row for row in evaluated_rows if row["period"] == period]
        if not period_rows:
            continue
        blocked = [row for row in period_rows if not row["passed"]]
        period_summary = _summarize_rows(period_rows)
        period_summary["period"] = period
        period_summary["blocked_examples"] = blocked[:blocked_examples_per_period]
        periods_out.append(period_summary)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "replay",
        "overlay_config": asdict(overlay_config),
        "pooled": _summarize_rows(evaluated_rows),
        "periods": periods_out,
    }
    return payload


def sweep_overlay_parameters(
    raw_dir: Path,
    *,
    periods: list[str] | None = None,
    chase_min_retrace_values: list[float] | None = None,
    chase_min_expected_move_pct_values: list[float] | None = None,
) -> dict[str, Any]:
    base_config = load_momentum_config().theory_overlay
    trade_surfaces = _build_trade_surfaces(raw_dir, periods)
    retrace_values = chase_min_retrace_values or [0.1, 0.12, 0.15, 0.18, 0.2]
    move_values = chase_min_expected_move_pct_values or [0.08, 0.1, 0.12]

    rows: list[dict[str, Any]] = []
    for chase_min_retrace in retrace_values:
        for chase_min_expected_move_pct in move_values:
            config = replace(
                base_config,
                chase_min_retrace=chase_min_retrace,
                chase_min_expected_move_pct=chase_min_expected_move_pct,
            )
            evaluated_rows: list[dict[str, Any]] = []
            for row in trade_surfaces:
                overlay = evaluate_theory_overlay(
                    side=row["side"],
                    daily=row["daily"],
                    setup=row["setup"],
                    expected_move_pct=row["expected_move_pct"],
                    config=config,
                )
                evaluated_rows.append(
                    {
                        "r_multiple": row["r_multiple"],
                        "passed": overlay.passed,
                        "stage": overlay.stage,
                    }
                )
            summary = _summarize_rows(evaluated_rows)
            rows.append(
                {
                    "chase_min_retrace": chase_min_retrace,
                    "chase_min_expected_move_pct": chase_min_expected_move_pct,
                    **summary,
                }
            )

    ranked = sorted(
        rows,
        key=lambda row: (row["kept_win_rate"], row["kept_expectancy"], -row["blocked_winners"]),
        reverse=True,
    )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "sweep",
        "base_overlay_config": asdict(base_config),
        "results": ranked,
        "top_candidates": ranked[:10],
    }


def write_overlay_review_markdown(payload: dict[str, Any], output_path: Path) -> Path:
    lines = ["# Momentum Theory Overlay Report", ""]
    lines.append(f"Fecha: {payload.get('generated_at', 'unknown')}")
    lines.append("")
    if payload.get("mode") == "sweep":
        lines.append("## Top candidates")
        lines.append("")
        for row in payload.get("top_candidates", []):
            lines.append(
                "- "
                f"retrace={row['chase_min_retrace']}, "
                f"expected_move_floor={row['chase_min_expected_move_pct']}, "
                f"kept_trades={row['kept_trades']}, "
                f"kept_win_rate={row['kept_win_rate']}, "
                f"kept_expectancy={row['kept_expectancy']}, "
                f"blocked_winners={row['blocked_winners']}, "
                f"blocked_losers={row['blocked_losers']}"
            )
    else:
        pooled = payload.get("pooled", {})
        lines.extend(
            [
                "## Pooled",
                "",
                f"- trade_count={pooled.get('trade_count', 0)}",
                f"- kept_trades={pooled.get('kept_trades', 0)}",
                f"- kept_win_rate={pooled.get('kept_win_rate', 0.0)}",
                f"- kept_expectancy={pooled.get('kept_expectancy', 0.0)}",
                f"- blocked_trades={pooled.get('blocked_trades', 0)}",
                f"- blocked_winners={pooled.get('blocked_winners', 0)}",
                f"- blocked_losers={pooled.get('blocked_losers', 0)}",
                "",
                "## Periods",
                "",
            ]
        )
        for period in payload.get("periods", []):
            lines.append(f"### {period['period']}")
            lines.append("")
            lines.append(f"- kept_trades={period['kept_trades']}")
            lines.append(f"- kept_win_rate={period['kept_win_rate']}")
            lines.append(f"- kept_expectancy={period['kept_expectancy']}")
            lines.append(f"- blocked_trades={period['blocked_trades']}")
            lines.append(f"- blocked_winners={period['blocked_winners']}")
            lines.append(f"- blocked_losers={period['blocked_losers']}")
            if period.get("blocked_by_stage"):
                lines.append(f"- blocked_by_stage={json.dumps(period['blocked_by_stage'], sort_keys=True)}")
            lines.append("")
    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return output_path