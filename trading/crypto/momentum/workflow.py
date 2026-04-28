from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from trading.crypto.momentum import MomentumBacktester, load_momentum_config


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import data_loader  # noqa: E402
from data_loader import DataNotFoundError  # noqa: E402


MOMENTUM_PERIOD_ORDER = [
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

MOMENTUM_PERIODS: dict[str, tuple[str, str]] = {
    "2017-bull+2018-bear": ("2017-01-01", "2018-12-31"),
    "2019-recovery": ("2019-01-01", "2019-12-31"),
    "2020-covid-crash": ("2020-01-01", "2020-06-30"),
    "2020-recovery+2021-ATH": ("2020-07-01", "2021-12-31"),
    "2022-bear": ("2022-01-01", "2022-12-31"),
    "2023-recovery": ("2023-01-01", "2023-12-31"),
    "2024-ETF-approval": ("2024-01-01", "2024-06-30"),
    "2024-2025-bull": ("2024-07-01", "2025-03-31"),
}

DEFAULT_TRIGGER_TF = "1H"
RAW_OUTPUT_DIR = PROJECT_ROOT / "docs" / "analysis" / "raw"
ITERATIONS_DIR = PROJECT_ROOT / "docs" / "analysis" / "momentum_iterations"
ITERATION_PATTERNS = [
    re.compile(r"^> \*\*Command:\*\* `python scripts/momentum_backtest\.py --period (?P<period>[^ ]+) "),
    re.compile(r"^> \*\*Backtest command:\*\* `python scripts/momentum_backtest\.py --period (?P<period>[^ ]+) "),
]


@dataclass(frozen=True)
class MomentumWorkflowConfig:
    symbols: tuple[str, ...] = ("BTC", "ETH")
    trigger_timeframe: str = DEFAULT_TRIGGER_TF


@dataclass(frozen=True)
class FrameCoverage:
    timeframe: str
    requested_start: pd.Timestamp
    requested_end: pd.Timestamp
    actual_start: pd.Timestamp | None
    actual_end: pd.Timestamp | None

    @property
    def complete(self) -> bool:
        return (
            self.actual_start is not None
            and self.actual_end is not None
            and self.actual_start <= self.requested_start
            and self.actual_end >= self.requested_end
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "timeframe": self.timeframe,
            "requested_start": self.requested_start.isoformat(),
            "requested_end": self.requested_end.isoformat(),
            "actual_start": self.actual_start.isoformat() if self.actual_start is not None else None,
            "actual_end": self.actual_end.isoformat() if self.actual_end is not None else None,
            "complete": self.complete,
        }


def resolve_period(name: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    if name == "TODAY":
        end = pd.Timestamp.now(tz="UTC").normalize()
        return end - pd.Timedelta(days=90), end
    if name not in MOMENTUM_PERIODS:
        raise ValueError(
            f"unknown period: {name}; available: {', '.join(list(MOMENTUM_PERIODS) + ['TODAY'])}"
        )
    start_s, end_s = MOMENTUM_PERIODS[name]
    return pd.Timestamp(start_s, tz="UTC"), pd.Timestamp(end_s, tz="UTC")


def completed_periods(iterations_dir: Path = ITERATIONS_DIR) -> list[str]:
    periods: list[str] = []
    if not iterations_dir.exists():
        return periods
    for path in sorted(iterations_dir.glob("iter_*.md")):
        for line in path.read_text(encoding="utf-8").splitlines():
            for pattern in ITERATION_PATTERNS:
                match = pattern.match(line)
                if match:
                    periods.append(match.group("period"))
                    break
            else:
                continue
            break
    return periods


def next_period(iterations_dir: Path = ITERATIONS_DIR) -> str | None:
    done = set(completed_periods(iterations_dir))
    for period in MOMENTUM_PERIOD_ORDER:
        if period not in done:
            return period
    return None


def _load_frame(coin: str, timeframe: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    return data_loader.load(coin, timeframe, start, end)


def _frame_coverage(
    timeframe: str,
    frame: pd.DataFrame,
    requested_start: pd.Timestamp,
    requested_end: pd.Timestamp,
) -> FrameCoverage:
    if frame.empty:
        return FrameCoverage(timeframe, requested_start, requested_end, None, None)
    first = pd.Timestamp(frame["timestamp"].iloc[0]).tz_convert("UTC")
    last = pd.Timestamp(frame["timestamp"].iloc[-1]).tz_convert("UTC")
    return FrameCoverage(timeframe, requested_start, requested_end, first, last)


def _effective_coverage_window(coverages: dict[str, FrameCoverage]) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    starts = [coverage.actual_start for coverage in coverages.values() if coverage.actual_start is not None]
    ends = [coverage.actual_end for coverage in coverages.values() if coverage.actual_end is not None]
    if not starts or not ends:
        return None, None
    return max(starts), min(ends)


def load_symbol_frames(
    symbol: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    trigger_timeframe: str = DEFAULT_TRIGGER_TF,
    trigger_forward_buffer: pd.Timedelta = pd.Timedelta(days=14),
) -> dict[str, pd.DataFrame]:
    daily = _load_frame(symbol, "1D", start - pd.Timedelta(days=120), end)
    setup = _load_frame(symbol, "4H", start - pd.Timedelta(days=60), end)
    trigger = _load_frame(
        symbol,
        trigger_timeframe,
        start - pd.Timedelta(days=60),
        end + trigger_forward_buffer,
    )
    return {
        "daily": daily,
        "setup": setup,
        "trigger": trigger,
    }


def _confidence_band(score: int) -> str:
    if score >= 90:
        return "90-100"
    if score >= 80:
        return "80-89"
    if score >= 75:
        return "75-79"
    return "<75"


def summarize_period_result(symbol_payload: dict[str, Any]) -> dict[str, Any]:
    trades = symbol_payload.get("trades", [])
    coverage = symbol_payload.get("coverage", {})
    if not trades:
        hints = ["No trades fired. Loosen nothing yet; first verify data coverage and trigger timeframe."]
        if not coverage.get("complete", True):
            hints.insert(0, "Coverage is partial for this regime; do not tune thresholds from this artifact until missing history is addressed.")
        return {
            "sides": {},
            "confidence_bands": {},
            "improvement_hints": hints,
        }

    side_summary: dict[str, dict[str, float]] = {}
    band_summary: dict[str, dict[str, float]] = {}
    for trade in trades:
        side = str(trade.get("side", "unknown"))
        side_bucket = side_summary.setdefault(side, {"count": 0, "win_rate_sum": 0.0, "total_r": 0.0})
        side_bucket["count"] += 1
        side_bucket["win_rate_sum"] += 1.0 if float(trade.get("r_multiple", 0.0)) > 0 else 0.0
        side_bucket["total_r"] += float(trade.get("r_multiple", 0.0))

        band = _confidence_band(int(trade.get("confidence_score", 0) or 0))
        band_bucket = band_summary.setdefault(band, {"count": 0, "wins": 0.0, "total_r": 0.0})
        band_bucket["count"] += 1
        band_bucket["wins"] += 1.0 if float(trade.get("r_multiple", 0.0)) > 0 else 0.0
        band_bucket["total_r"] += float(trade.get("r_multiple", 0.0))

    sides_out = {
        side: {
            "count": int(values["count"]),
            "win_rate": round(values["win_rate_sum"] / values["count"], 4) if values["count"] else 0.0,
            "avg_r": round(values["total_r"] / values["count"], 4) if values["count"] else 0.0,
        }
        for side, values in side_summary.items()
    }
    bands_out = {
        band: {
            "count": int(values["count"]),
            "win_rate": round(values["wins"] / values["count"], 4) if values["count"] else 0.0,
            "avg_r": round(values["total_r"] / values["count"], 4) if values["count"] else 0.0,
        }
        for band, values in band_summary.items()
    }
    hints = build_improvement_hints(symbol_payload, sides_out, bands_out)
    return {
        "sides": sides_out,
        "confidence_bands": bands_out,
        "improvement_hints": hints,
    }


def build_improvement_hints(
    symbol_payload: dict[str, Any],
    sides_out: dict[str, dict[str, float]],
    bands_out: dict[str, dict[str, float]],
) -> list[str]:
    metrics = symbol_payload.get("metrics", {})
    baseline = symbol_payload.get("baseline", {}).get("delta", {})
    coverage = symbol_payload.get("coverage", {})
    hints: list[str] = []
    if not coverage.get("complete", True):
        effective = coverage.get("effective_window", {})
        hints.append(
            "Coverage is partial; treat this as a partial validation window"
            f" ({effective.get('start', 'unknown')} -> {effective.get('end', 'unknown')})."
        )
    expectancy_delta = float(baseline.get("expectancy", 0.0) or 0.0)
    if expectancy_delta < 0:
        hints.append("Expectancy is below the simple breakout baseline; tighten confirmation before relaxing thresholds.")
    if float(metrics.get("pct_reaching_8", 0.0) or 0.0) < 0.35:
        hints.append("Too few trades are reaching 8%; inspect whether entries are late and whether retest tolerance is too loose.")
    if float(metrics.get("max_drawdown", 0.0) or 0.0) > 5.0:
        hints.append("Drawdown is elevated in R terms; consider raising the score threshold or tightening the funding/participation filter.")
    low_band = bands_out.get("75-79")
    high_band = bands_out.get("90-100")
    if low_band and high_band and low_band.get("avg_r", 0.0) < 0 < high_band.get("avg_r", 0.0):
        hints.append("Low-score trades underperform high-score trades; raising the tradeable threshold is a good first candidate.")
    if sides_out.get("short", {}).get("avg_r", 0.0) < -0.25:
        hints.append("Shorts are dragging performance in this regime; review breakout freshness and funding crowding on short setups.")
    if not hints:
        hints.append("No obvious structural defect from aggregate stats; inspect individual losing trades before changing thresholds.")
    return hints


def _with_trade_diagnostics(payload: dict[str, Any]) -> dict[str, Any]:
    trades = payload.get("trades", [])
    for trade in trades:
        trade.setdefault("confidence_score", 0)
        trade.setdefault("expected_move_pct", 0.0)
        trade.setdefault("rr_estimated", 0.0)
        trade.setdefault("holding_horizon_estimate", "unknown")
    return payload


def _metrics_from_trade_dicts(trades: list[dict[str, Any]]) -> dict[str, Any]:
    if not trades:
        return {
            "win_rate": 0.0,
            "expectancy": 0.0,
            "max_drawdown": 0.0,
            "average_realized_move": 0.0,
            "pct_reaching_8": 0.0,
            "pct_reaching_12": 0.0,
            "pct_reaching_20": 0.0,
        }

    ordered = sorted(trades, key=lambda trade: (trade.get("exit_time", ""), trade.get("entry_time", "")))
    count = len(ordered)
    winners = [trade for trade in ordered if float(trade.get("r_multiple", 0.0)) > 0.0]
    cumulative_r = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for trade in ordered:
        cumulative_r += float(trade.get("r_multiple", 0.0))
        peak = max(peak, cumulative_r)
        max_drawdown = min(max_drawdown, cumulative_r - peak)
    return {
        "win_rate": round(len(winners) / count, 4),
        "expectancy": round(sum(float(trade.get("r_multiple", 0.0)) for trade in ordered) / count, 4),
        "max_drawdown": round(abs(max_drawdown), 4),
        "average_realized_move": round(sum(float(trade.get("realized_move_pct", 0.0)) for trade in ordered) / count, 4),
        "pct_reaching_8": round(sum(1 for trade in ordered if bool(trade.get("reached_8_pct", False))) / count, 4),
        "pct_reaching_12": round(sum(1 for trade in ordered if bool(trade.get("reached_12_pct", False))) / count, 4),
        "pct_reaching_20": round(sum(1 for trade in ordered if bool(trade.get("reached_20_pct", False))) / count, 4),
    }


def _warning(code: str, severity: str, message: str) -> dict[str, str]:
    return {
        "code": code,
        "severity": severity,
        "message": message,
    }


def build_automation_guardrails(payload: dict[str, Any]) -> dict[str, Any]:
    warnings: list[dict[str, str]] = []
    coverage = payload.get("coverage", {})
    pooled = payload.get("pooled", {})
    pooled_metrics = pooled.get("metrics", {})
    trade_count = int(pooled.get("trade_count", 0) or 0)
    period = str(payload.get("period", "unknown"))

    if not coverage.get("complete", True):
        warnings.append(
            _warning(
                "partial_coverage",
                "error",
                "Coverage is partial for at least one symbol or timeframe; do not promote this artifact into unattended automation.",
            )
        )

    if payload.get("skipped"):
        warnings.append(
            _warning(
                "skipped_symbols",
                "error",
                "One or more requested symbols were skipped because the required historical data was missing.",
            )
        )

    if trade_count < 10:
        warnings.append(
            _warning(
                "low_sample",
                "warning",
                f"Only {trade_count} pooled trades were available; treat win rate and expectancy as unstable until sample size improves.",
            )
        )

    if period == "TODAY":
        warnings.append(
            _warning(
                "live_window",
                "warning",
                "TODAY is a live rolling window; use it as a provisional operator check rather than as standalone production validation.",
            )
        )

    if float(pooled_metrics.get("pct_reaching_8", 0.0) or 0.0) < 0.35:
        warnings.append(
            _warning(
                "extension_quality",
                "warning",
                "Too few trades are extending to 8%; monitor entry quality before scheduling this configuration unattended.",
            )
        )

    if float(pooled_metrics.get("expectancy", 0.0) or 0.0) <= 0:
        warnings.append(
            _warning(
                "non_positive_expectancy",
                "error",
                "Expectancy is non-positive for this slice; keep this configuration out of automation until the edge is restored.",
            )
        )

    return {
        "ready": not any(warning["severity"] == "error" for warning in warnings),
        "warnings": warnings,
    }


def _next_iteration_number(iterations_dir: Path) -> int:
    existing = []
    if iterations_dir.exists():
        for path in iterations_dir.glob("iter_*.md"):
            match = re.match(r"iter_(\d+)\.md$", path.name)
            if match:
                existing.append(int(match.group(1)))
    return (max(existing) + 1) if existing else 1


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def write_iteration_report(
    payload: dict[str, Any],
    artifact_path: Path,
    *,
    iterations_dir: Path = ITERATIONS_DIR,
) -> Path:
    iterations_dir.mkdir(parents=True, exist_ok=True)
    iteration_number = _next_iteration_number(iterations_dir)
    requested = payload.get("requested_window", payload.get("window", {}))
    effective = payload.get("effective_window", payload.get("window", {}))
    lines = [
        f"# Iteracion {iteration_number}",
        "",
        f"> **Backtest command:** `python scripts/momentum_backtest.py --period {payload['period']} --symbols {' '.join(payload.get('symbols', []))} --trigger-timeframe {payload['trigger_timeframe']}`",
        f"> **Artifact:** `{_display_path(artifact_path)}`",
        "",
        "## Resumen",
        "",
        f"- Periodo: `{payload['period']}`",
        f"- Ventana solicitada: `{requested.get('start', 'unknown')}` -> `{requested.get('end', 'unknown')}`",
        f"- Ventana efectiva: `{effective.get('start', 'unknown')}` -> `{effective.get('end', 'unknown')}`",
        f"- Cobertura completa: `{payload.get('coverage', {}).get('complete', False)}`",
        f"- Trades totales: `{payload.get('pooled', {}).get('trade_count', 0)}`",
        f"- Win rate pool: `{payload.get('pooled', {}).get('metrics', {}).get('win_rate', 0.0)}`",
        f"- Expectancy pool: `{payload.get('pooled', {}).get('metrics', {}).get('expectancy', 0.0)}`",
        "",
        "## Observaciones",
        "",
    ]
    for symbol, result in payload.get("results", {}).items():
        review = result.get("review", {})
        lines.append(f"### {symbol}")
        lines.append("")
        coverage = result.get("coverage", {})
        lines.append(
            f"- Cobertura: `{coverage.get('effective_window', {}).get('start', 'unknown')}` -> `{coverage.get('effective_window', {}).get('end', 'unknown')}` (completa=`{coverage.get('complete', False)}`)"
        )
        lines.append(f"- Trades: `{result.get('trade_count', 0)}`")
        lines.append(f"- Win rate: `{result.get('metrics', {}).get('win_rate', 0.0)}`")
        lines.append(f"- Expectancy: `{result.get('metrics', {}).get('expectancy', 0.0)}`")
        for hint in review.get("improvement_hints", [])[:3]:
            lines.append(f"- Nota: {hint}")
        lines.append("")
    path = iterations_dir / f"iter_{iteration_number}.md"
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def run_period_backtest(
    period: str,
    *,
    symbols: list[str] | None = None,
    trigger_timeframe: str = DEFAULT_TRIGGER_TF,
) -> dict[str, Any]:
    selected_symbols = [symbol.upper() for symbol in (symbols or ["BTC", "ETH"])]
    start, end = resolve_period(period)
    trigger_forward_buffer = pd.Timedelta(0) if period == "TODAY" else pd.Timedelta(days=14)
    config = load_momentum_config()
    backtester = MomentumBacktester(config)

    results: dict[str, Any] = {}
    pooled_trade_count = 0
    pooled_trades: list[dict[str, Any]] = []
    skipped: dict[str, str] = {}
    symbol_coverages: dict[str, dict[str, Any]] = {}

    for symbol in selected_symbols:
        try:
            frames = load_symbol_frames(
                symbol,
                start,
                end,
                trigger_timeframe,
                trigger_forward_buffer=trigger_forward_buffer,
            )
        except DataNotFoundError as exc:
            skipped[symbol] = str(exc)
            continue
        daily_coverage = _frame_coverage("1D", frames["daily"], start - pd.Timedelta(days=120), end)
        setup_coverage = _frame_coverage("4H", frames["setup"], start - pd.Timedelta(days=60), end)
        trigger_coverage = _frame_coverage(
            trigger_timeframe,
            frames["trigger"],
            start - pd.Timedelta(days=60),
            end + trigger_forward_buffer,
        )
        coverages = {
            "daily": daily_coverage,
            "setup": setup_coverage,
            "trigger": trigger_coverage,
        }
        effective_start, effective_end = _effective_coverage_window(coverages)
        symbol_coverage = {
            "complete": all(coverage.complete for coverage in coverages.values()),
            "frames": {name: coverage.to_dict() for name, coverage in coverages.items()},
            "effective_window": {
                "start": effective_start.isoformat() if effective_start is not None else None,
                "end": effective_end.isoformat() if effective_end is not None else None,
            },
        }
        symbol_payload = backtester.evaluate(
            symbol=f"{symbol}USDT",
            daily_frame=frames["daily"],
            setup_frame=frames["setup"],
            trigger_frame=frames["trigger"],
        )
        symbol_payload = _with_trade_diagnostics(symbol_payload)
        symbol_payload["coverage"] = symbol_coverage
        symbol_payload["review"] = summarize_period_result(symbol_payload)
        results[symbol] = symbol_payload
        symbol_coverages[symbol] = symbol_coverage
        pooled_trade_count += int(symbol_payload.get("trade_count", 0))
        pooled_trades.extend(symbol_payload.get("trades", []))

    effective_starts = [
        pd.Timestamp(coverage["effective_window"]["start"])
        for coverage in symbol_coverages.values()
        if coverage.get("effective_window", {}).get("start")
    ]
    effective_ends = [
        pd.Timestamp(coverage["effective_window"]["end"])
        for coverage in symbol_coverages.values()
        if coverage.get("effective_window", {}).get("end")
    ]
    requested_window = {
        "start": start.isoformat(),
        "end": end.isoformat(),
    }
    effective_window = {
        "start": max(effective_starts).isoformat() if effective_starts else None,
        "end": min(effective_ends).isoformat() if effective_ends else None,
    }
    pooled = {
        "trade_count": pooled_trade_count,
        "metrics": _metrics_from_trade_dicts(pooled_trades),
    }

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "period": period,
        "window": effective_window,
        "requested_window": requested_window,
        "effective_window": effective_window,
        "symbols": selected_symbols,
        "trigger_timeframe": trigger_timeframe,
        "coverage": {
            "complete": bool(symbol_coverages) and all(coverage.get("complete", False) for coverage in symbol_coverages.values()),
            "symbols": symbol_coverages,
        },
        "results": results,
        "pooled": pooled,
        "skipped": skipped,
    }
    payload["automation"] = build_automation_guardrails(payload)
    return payload


def write_period_artifact(payload: dict[str, Any], output_dir: Path = RAW_OUTPUT_DIR) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    period = str(payload.get("period", "unknown"))
    path = output_dir / f"momentum_backtest_{period}_{ts}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def render_period_summary(payload: dict[str, Any]) -> str:
    requested_window = payload.get("requested_window", payload["window"])
    effective_window = payload.get("effective_window", payload["window"])
    lines = [
        f"momentum backtest — period={payload['period']} trigger={payload['trigger_timeframe']}",
        f"requested window: {requested_window['start']} -> {requested_window['end']}",
        f"effective window: {effective_window['start']} -> {effective_window['end']}",
    ]
    if not payload.get("coverage", {}).get("complete", True):
        lines.append("coverage: partial")
    automation = payload.get("automation", {})
    if automation:
        readiness = "ready" if automation.get("ready", False) else "blocked"
        lines.append(f"automation: {readiness}")
        for warning in automation.get("warnings", [])[:2]:
            lines.append(f"  guardrail[{warning.get('severity', 'warning')}]: {warning.get('message', '')}")
    for symbol, result in payload.get("results", {}).items():
        metrics = result.get("metrics", {})
        coverage = result.get("coverage", {})
        coverage_label = "complete" if coverage.get("complete", False) else "partial"
        lines.append(
            f"[{symbol}] trades={result.get('trade_count', 0)} "
            f"wr={metrics.get('win_rate', 0.0):.2%} exp={metrics.get('expectancy', 0.0):+.2f} "
            f"mdd={metrics.get('max_drawdown', 0.0):.2f} "
            f">=8%={metrics.get('pct_reaching_8', 0.0):.2%} coverage={coverage_label}"
        )
        review = result.get("review", {})
        for hint in review.get("improvement_hints", [])[:2]:
            lines.append(f"  hint: {hint}")
    if payload.get("skipped"):
        for symbol, reason in payload["skipped"].items():
            lines.append(f"[{symbol}] skipped: {reason[:120]}")
    pooled = payload.get("pooled", {}).get("metrics", {})
    lines.append(
        f"[pooled] trades={payload.get('pooled', {}).get('trade_count', 0)} "
        f"wr={pooled.get('win_rate', 0.0):.2%} exp={pooled.get('expectancy', 0.0):+.2f}"
    )
    return "\n".join(lines)