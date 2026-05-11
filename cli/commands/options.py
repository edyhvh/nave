"""Options analysis command group for Nave CLI."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from cli.professional_typer import ProfessionalTyper
from options.analyzer import OptionsAnalyzer
from options.exceptions import OptionsError

options_app = ProfessionalTyper(help="Options analytics commands")


def _slug(value: str) -> str:
    keep = [ch if ch.isalnum() or ch in {
        "_", "-"} else "_" for ch in value.strip()]
    normalized = "".join(keep).strip("_")
    return normalized or "ticker"


def _default_reports_dir(analyzer: OptionsAnalyzer) -> Path:
    cfg = getattr(analyzer, "config", None)
    reports_dir = getattr(cfg, "reports_dir", None)
    if reports_dir is not None:
        return Path(reports_dir)
    return Path("data") / "options_cache" / "reports"


def _resolve_json_report_path(
    *,
    analyzer: OptionsAnalyzer,
    ticker: str,
    json_path: str | None,
) -> Path:
    if json_path:
        return Path(json_path).expanduser()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    reports_dir = _default_reports_dir(analyzer)
    return reports_dir / f"{_slug(ticker)}_options_report_{stamp}.json"


def _write_json_report(*, payload: dict, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2,
                        default=str), encoding="utf-8")
    return out_path


def _build_llm_prompt(payload: dict) -> str:
    ticker = str(payload.get("ticker") or "UNKNOWN")
    underlying = payload.get("underlying_analysis") or {}
    recs = payload.get("recommendations") or []

    top_names: list[str] = []
    for rec in recs[:3]:
        strategy = (rec.get("strategy") or {}).get("name")
        if strategy:
            top_names.append(str(strategy))
    strategy_list = ", ".join(top_names) if top_names else "none"

    payload_for_prompt = _strip_paths_for_prompt(payload)
    payload_blob = json.dumps(payload_for_prompt, indent=2, default=str)

    return "\n".join(
        [
            "You are an options strategy analyst.",
            f"Analyze ticker: {ticker}",
            f"Current price: {underlying.get('price')}",
            f"Top strategies in report: {strategy_list}",
            "Input data will be provided separately as JSON payload and llm_paths block.",
            "Tasks:",
            "1. Summarize volatility regime and market context from the report.",
            "2. Compare top strategies by PoP, expected value, max loss, and touch probability.",
            "3. Recommend one conservative and one aggressive setup with tradeoff rationale.",
            "4. Provide invalidation logic, risk guardrails, and position-sizing guidance.",
            "Output format:",
            "- Executive summary (3 bullets)",
            "- Strategy comparison table",
            "- Final recommendation",
            "- Risks and what to monitor next",
            "JSON data (paths removed):",
            "```json",
            payload_blob,
            "```",
        ]
    )


def _strip_paths_for_prompt(value: object) -> object:
    if isinstance(value, dict):
        cleaned: dict[str, object] = {}
        for key, item in value.items():
            k = str(key).lower()
            if k == "llm_paths":
                continue
            if k == "charts" and isinstance(item, dict):
                cleaned[str(key)] = {
                    str(name): "[path omitted]" for name in item.keys()}
                continue
            if "path" in k:
                continue
            cleaned[str(key)] = _strip_paths_for_prompt(item)
        return cleaned
    if isinstance(value, list):
        return [_strip_paths_for_prompt(item) for item in value]
    return value


def _build_llm_paths(payload: dict, json_report_path: Path | None) -> dict:
    return {
        "json_report_path": str(json_report_path) if json_report_path is not None else None,
        "charts": payload.get("charts") or {},
    }


@options_app.command("analyze")
def analyze(
    ticker: str = typer.Option(
        "MSFT", "--ticker", help="Underlying ticker symbol"),
    days_to_exp: int = typer.Option(
        30, "--days-to-exp", min=1, max=365, help="Target days to expiration"),
    json_out: bool = typer.Option(
        False, "--json", help="Emit machine-stable JSON output"),
    sheet: bool = typer.Option(
        True, "--sheet/--no-sheet", help="Render human output as a Rich table"),
    save_json: bool = typer.Option(
        True,
        "--save-json/--no-save-json",
        help="Persist the analysis payload to a .json report file for copy/share",
    ),
    json_path: str | None = typer.Option(
        None,
        "--json-path",
        help="Optional output path for the saved .json report",
    ),
    llm_prompt: bool = typer.Option(
        False,
        "--llm-prompt",
        help="Print a copy-ready prompt for another LLM using the saved JSON report",
    ),
) -> None:
    """Run options analysis and print recommendations."""
    analyzer = OptionsAnalyzer()
    console = Console()

    try:
        payload = analyzer.run(ticker=ticker, days_to_exp=days_to_exp)
    except OptionsError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    report_path: Path | None = None
    if save_json:
        report_path = _resolve_json_report_path(
            analyzer=analyzer,
            ticker=str(payload.get("ticker") or ticker),
            json_path=json_path,
        )

    payload_out = dict(payload)
    artifacts = dict(payload_out.get("artifacts") or {})
    artifacts["json_report_path"] = str(
        report_path) if report_path is not None else None
    payload_out["artifacts"] = artifacts

    if llm_prompt:
        prompt_source = dict(payload_out)
        payload_out["llm_prompt"] = _build_llm_prompt(prompt_source)
        payload_out["llm_paths"] = _build_llm_paths(payload_out, report_path)

    if save_json:
        report_path = _write_json_report(
            payload=payload_out,
            out_path=report_path if report_path is not None else _resolve_json_report_path(
                analyzer=analyzer,
                ticker=str(payload.get("ticker") or ticker),
                json_path=json_path,
            ),
        )

    if json_out:
        typer.echo(json.dumps(payload_out, indent=2, default=str))
        return

    underlying = payload_out.get("underlying_analysis", {})
    implied = underlying.get("implied_volatility", {}) or {}
    expected_move = underlying.get("expected_move", {}) or {}
    snapshot = underlying.get("options_market_snapshot", {}) or {}

    if sheet:
        summary = Table(
            title=f"Options Summary - {payload_out.get('ticker')}", box=box.SIMPLE_HEAVY)
        summary.add_column("Metric")
        summary.add_column("Value")
        summary.add_row("Price", str(underlying.get("price")))
        summary.add_row("IV Mean", str(implied.get("iv_mean")))
        summary.add_row("IV Rank", str(implied.get("iv_rank")))
        summary.add_row("Expected Move (1sd)", str(
            expected_move.get("one_std_move")))
        summary.add_row("Contracts", str(snapshot.get("contracts")))
        summary.add_row("Put/Call OI Ratio",
                        str(snapshot.get("put_call_oi_ratio")))
        console.print(summary)

        rec_table = Table(title="Top Strategy Ranking", box=box.SIMPLE_HEAVY)
        rec_table.add_column("Rank", justify="right")
        rec_table.add_column("Strategy")
        rec_table.add_column("Score", justify="right")
        rec_table.add_column("PoP %", justify="right")
        rec_table.add_column("EV", justify="right")
        rec_table.add_column("Touch %", justify="right")
        rec_table.add_column("Tradeoff")
        for idx, rec in enumerate(payload_out.get("recommendations", [])[:3], start=1):
            strategy = (rec.get("strategy", {}) or {}).get("name", "unknown")
            metrics = rec.get("metrics", {}) or {}
            rec_table.add_row(
                str(idx),
                str(strategy),
                str(metrics.get("composite_score")),
                str(metrics.get("pop")),
                str(metrics.get("expected_value")),
                str(metrics.get("probability_of_touch")),
                str(rec.get("tradeoff_comment") or ""),
            )
        console.print(rec_table)

        charts = payload_out.get("charts", {}) or {}
        chart_table = Table(title="Chart Artifacts", box=box.SIMPLE)
        chart_table.add_column("Chart")
        chart_table.add_column("Path")
        for key in ["strategy_ranking", "payoff", "greeks", "monte_carlo"]:
            chart_table.add_row(key, str(charts.get(key)))
        console.print(chart_table)

        if report_path is not None:
            copy_help = Text(
                f"JSON report: {report_path}\n"
                f"View: cat {report_path}\n"
                f"Copy (macOS): pbcopy < {report_path}",
            )
            console.print(
                Panel(copy_help, title="Copyable JSON", border_style="cyan"))

        if llm_prompt:
            prompt = str(payload_out.get("llm_prompt") or "")
            console.print(
                Panel(prompt, title="LLM Prompt (Copy/Paste)", border_style="green"))
            llm_paths = payload_out.get("llm_paths") or {}
            console.print(
                Panel(
                    json.dumps(llm_paths, indent=2, default=str),
                    title="LLM Paths (Separate Block)",
                    border_style="yellow",
                )
            )

        return

    typer.echo(f"Ticker: {payload_out.get('ticker')}")
    typer.echo(f"Price: {underlying.get('price')}")
    if report_path is not None:
        typer.echo(f"JSON report: {report_path}")
    typer.echo("Top strategies:")
    for rec in payload_out.get("recommendations", [])[:3]:
        strategy = (rec.get("strategy", {}) or {}).get("name", "unknown")
        metrics = rec.get("metrics", {}) or {}
        typer.echo(
            f"- {strategy}: score={metrics.get('composite_score')} pop={metrics.get('pop')} ev={metrics.get('expected_value')}"
        )
