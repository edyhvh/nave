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
from options.prompt_builder import build_llm_paths, build_llm_prompt
from options.visualization import TerminalChartDependencyError, render_terminal_charts

options_app = ProfessionalTyper(help="Options analytics commands")


def _build_options_analyzer(*, source: str) -> OptionsAnalyzer:
    try:
        return OptionsAnalyzer(fetcher_source=source)
    except TypeError:
        # Test doubles in unit tests may still expose the legacy constructor.
        return OptionsAnalyzer()


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


def _as_float(value: object) -> float | None:
    try:
        if isinstance(value, bool):
            return float(int(value))
        if isinstance(value, (int, float, str)):
            return float(value)
    except (TypeError, ValueError):
        return None
    return None


def _expected_value_cell(value: object) -> Text:
    expected_value = _as_float(value)
    if expected_value is None:
        return Text(str(value))
    if expected_value < 0:
        return Text(f"NEG EV {expected_value:.2f}", style="red bold")
    return Text(f"{expected_value:.2f}", style="green")


def _negative_ev_warning(recommendations: list[dict]) -> str | None:
    if not recommendations:
        return None
    top_metrics = recommendations[0].get("metrics") or {}
    top_strategy = (recommendations[0].get(
        "strategy") or {}).get("name", "top strategy")
    top_ev = _as_float(top_metrics.get("expected_value"))
    if top_ev is None or top_ev >= 0:
        return None
    return (
        f"Top-ranked strategy {top_strategy} has negative modeled expected value ({top_ev:.2f}). "
        "Treat the setup as a pass-or-recheck candidate before sizing risk."
    )


def _collect_risk_warnings(payload: dict, recommendations: list[dict]) -> list[str]:
    warnings: list[str] = []
    negative_warning = _negative_ev_warning(recommendations)
    if negative_warning:
        warnings.append(negative_warning)

    overlay = payload.get("analysis_overlay") or {}
    overlay_warnings = overlay.get("warnings") or []
    for warning in overlay_warnings:
        text = str(warning).strip()
        if text and text not in warnings:
            warnings.append(text)
    return warnings


def _strategy_bias_label(strategy_name: str) -> str:
    if strategy_name in {
        "bull_put_credit_spread",
        "bull_call_debit_spread",
        "cash_secured_put",
        "covered_call",
    }:
        return "Bullish"
    if strategy_name in {"iron_condor", "call_butterfly"}:
        return "Neutral"
    if strategy_name in {"long_strangle", "long_straddle"}:
        return "Long Volatility"
    return "Other"


def _group_recommendations_by_bias(recommendations: list[dict]) -> list[tuple[str, list[dict]]]:
    grouped: dict[str, list[dict]] = {}
    for rec in recommendations:
        strategy_name = str(
            (rec.get("strategy") or {}).get("name") or "unknown")
        label = _strategy_bias_label(strategy_name)
        grouped.setdefault(label, []).append(rec)
    order = ["Bullish", "Neutral", "Long Volatility", "Other"]
    return [(label, grouped[label]) for label in order if grouped.get(label)]


def _render_bias_tables(console: Console, recommendations: list[dict]) -> None:
    rank = 1
    for label, recs in _group_recommendations_by_bias(recommendations):
        rec_table = Table(
            title=f"{label} Strategy Ranking", box=box.SIMPLE_HEAVY)
        rec_table.add_column("Rank", justify="right")
        rec_table.add_column("Strategy")
        rec_table.add_column("Score", justify="right")
        rec_table.add_column("PoP %", justify="right")
        rec_table.add_column("EV", justify="right")
        rec_table.add_column("Touch %", justify="right")
        rec_table.add_column("Tradeoff")
        for rec in recs:
            strategy = (rec.get("strategy", {}) or {}).get("name", "unknown")
            metrics = rec.get("metrics", {}) or {}
            rec_table.add_row(
                str(rank),
                str(strategy),
                str(metrics.get("composite_score")),
                str(metrics.get("pop")),
                _expected_value_cell(metrics.get("expected_value")),
                str(metrics.get("probability_of_touch")),
                str(rec.get("tradeoff_comment") or ""),
            )
            rank += 1
        console.print(rec_table)


def _render_strategy_comparison_table(console: Console, payload: dict) -> None:
    overlay = payload.get("analysis_overlay") or {}
    rows = list(overlay.get("strategy_comparison_table") or [])
    if not rows:
        return

    table = Table(title="Strategy Comparison", box=box.SIMPLE_HEAVY)
    table.add_column("Strategy")
    table.add_column("PoP", justify="right")
    table.add_column("EV", justify="right")
    table.add_column("Max Loss", justify="right")
    table.add_column("Prob. Touch", justify="right")
    table.add_column("Forgivingness", justify="right")
    table.add_column("Theta/Day", justify="right")
    table.add_column("Key Commentary")

    for row in rows:
        strategy = str(row.get("strategy") or "unknown")
        table.add_row(
            strategy,
            str(row.get("pop")),
            str(row.get("expected_value")),
            str(row.get("max_loss")),
            str(row.get("probability_of_touch")),
            str(row.get("forgivingness_score")),
            str(row.get("theta_per_day")),
            str(row.get("key_commentary") or ""),
        )
    console.print(table)


def _render_prompt_data_block(
    console: Console,
    payload: dict,
    *,
    report_path: Path | None,
    llm_prompt_enabled: bool,
) -> None:
    """Render prompt/data block used by terminal chart mode."""
    console.print("\n[bold cyan]=== Prompt and Data ===[/bold cyan]")

    underlying = payload.get("underlying_analysis", {}) or {}
    implied = underlying.get("implied_volatility", {}) or {}
    expected_move = underlying.get("expected_move", {}) or {}
    recommendations = list(payload.get("recommendations") or [])

    data_table = Table(box=box.SIMPLE, show_header=True)
    data_table.add_column("Field")
    data_table.add_column("Value")
    data_table.add_row("Ticker", str(payload.get("ticker") or "N/A"))
    data_table.add_row("Generated At", str(
        payload.get("generated_at") or "N/A"))
    data_table.add_row("Underlying Price", str(underlying.get("price")))
    data_table.add_row("IV Rank", str(implied.get("iv_rank")))
    data_table.add_row("Expected Move (1sd)", str(
        expected_move.get("one_std_move")))
    data_table.add_row("Top Recommendations", str(len(recommendations[:3])))
    if report_path is not None:
        data_table.add_row("JSON Report", str(report_path))
    console.print(data_table)

    if llm_prompt_enabled:
        prompt = str(payload.get("llm_prompt") or "")
        llm_paths = payload.get("llm_paths") or {}
        if prompt:
            console.print(
                Panel(prompt, title="LLM Prompt (Copy/Paste)",
                      border_style="green")
            )
        console.print(
            Panel(
                json.dumps(llm_paths, indent=2, default=str),
                title="LLM Paths (Separate Block)",
                border_style="yellow",
            )
        )
        return

    console.print(
        Panel(
            "LLM prompt block is disabled. Re-run with --llm-prompt to include a copy-ready prompt and llm_paths payload.",
            title="Prompt Hint",
            border_style="cyan",
        )
    )


def _render_sheet_output(
    console: Console,
    payload_out: dict,
    *,
    recommendations: list[dict],
    risk_warnings: list[str],
    report_path: Path | None,
    include_llm_prompt_panels: bool,
) -> None:
    """Render Rich sheet output for options analysis."""
    underlying = payload_out.get("underlying_analysis", {})
    implied = underlying.get("implied_volatility", {}) or {}
    expected_move = underlying.get("expected_move", {}) or {}
    snapshot = underlying.get("options_market_snapshot", {}) or {}

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

    _render_bias_tables(console, recommendations)
    _render_strategy_comparison_table(console, payload_out)

    for warning in risk_warnings:
        console.print(
            Panel(
                warning,
                title="Risk Warning",
                border_style="red",
            )
        )

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

    if include_llm_prompt_panels:
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


def _render_plain_output(
    payload_out: dict,
    *,
    recommendations: list[dict],
    report_path: Path | None,
    risk_warnings: list[str],
) -> None:
    """Render minimal plain-text output."""
    underlying = payload_out.get("underlying_analysis", {})
    typer.echo(f"Ticker: {payload_out.get('ticker')}")
    typer.echo(f"Price: {underlying.get('price')}")
    if report_path is not None:
        typer.echo(f"JSON report: {report_path}")
    for warning in risk_warnings:
        typer.echo(f"WARNING: {warning}")
    for label, recs in _group_recommendations_by_bias(recommendations):
        typer.echo(f"{label} strategies:")
        for rec in recs:
            strategy = (rec.get("strategy", {}) or {}).get("name", "unknown")
            metrics = rec.get("metrics", {}) or {}
            ev_value = _as_float(metrics.get("expected_value"))
            ev_display = f"{ev_value:.2f}" if ev_value is not None else str(
                metrics.get("expected_value"))
            if ev_value is not None and ev_value < 0:
                ev_display = f"NEG_EV:{ev_display}"
            typer.echo(
                f"- {strategy}: score={metrics.get('composite_score')} pop={metrics.get('pop')} ev={ev_display}"
            )


def _parse_coin_list(value: str) -> list[str]:
    raw = value.replace(" ", ",").split(",")
    return [item.strip().upper() for item in raw if item.strip()]


def _render_opportunities_sheet(console: Console, payload: dict) -> None:
    summary = payload.get("summary") or {}
    momentum = payload.get("momentum") or {}
    tf = momentum.get("timeframes") or {}

    header = Table(title="Options Opportunities Summary", box=box.SIMPLE_HEAVY)
    header.add_column("Metric")
    header.add_column("Value")
    header.add_row("Coins Requested", str(summary.get("coins_requested")))
    header.add_row("Coins Supported", str(summary.get("coins_supported")))
    header.add_row("Momentum Allowed", str(summary.get("momentum_allowed")))
    header.add_row("Options Ready", str(summary.get("options_ready")))
    if tf:
        header.add_row(
            "Timeframes",
            f"bias={tf.get('bias')} setup={tf.get('setup')} trigger={tf.get('trigger')}",
        )
    console.print(header)

    table = Table(title="BTC/ETH Opportunity Details", box=box.SIMPLE_HEAVY)
    table.add_column("Coin")
    table.add_column("Status")
    table.add_column("Momentum")
    table.add_column("Top Strategy")
    table.add_column("EV", justify="right")
    table.add_column("Notes")

    opportunities = payload.get("opportunities") or {}
    for coin in sorted(opportunities.keys()):
        entry = opportunities.get(coin) or {}
        status = str(entry.get("status") or "unknown")
        momentum_ctx = entry.get("momentum") or {}
        momentum_value = momentum_ctx.get("confidence_score")
        momentum_display = str(
            momentum_value) if momentum_value is not None else "n/a"
        top_strategy = str(entry.get("top_strategy") or "-").replace("_", " ")
        ev = (entry.get("top_metrics") or {}).get("expected_value")
        notes = entry.get("reason") or entry.get("error") or ""
        table.add_row(
            coin,
            status,
            momentum_display,
            top_strategy,
            "-" if ev is None else str(ev),
            str(notes),
        )
    console.print(table)


@options_app.command("analyze")
def analyze(
    symbol: str | None = typer.Argument(
        None,
        metavar="TICKER",
        help="Optional ticker symbol positional argument (e.g. MSFT or BTC)",
    ),
    ticker: str | None = typer.Option(
        None, "--ticker", help="Underlying ticker symbol"),
    source: str = typer.Option(
        "yfinance",
        "--source",
        help="Data source for chain fetch (yfinance|deribit)",
    ),
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
    terminal_mode: bool = typer.Option(
        False,
        "--terminal",
        "--ascii",
        help="Render terminal-native charts (plotext) in additive mode",
    ),
    llm_prompt: bool = typer.Option(
        False,
        "--llm-prompt",
        help="Print a copy-ready prompt for another LLM using the saved JSON report",
    ),
) -> None:
    """Run options analysis and print recommendations."""
    resolved_ticker = (symbol or ticker or "MSFT").strip().upper()
    analyzer = _build_options_analyzer(source=source)
    console = Console()

    try:
        payload = analyzer.run(ticker=resolved_ticker, days_to_exp=days_to_exp)
    except OptionsError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    report_path: Path | None = None
    if save_json:
        report_path = _resolve_json_report_path(
            analyzer=analyzer,
            ticker=str(payload.get("ticker") or resolved_ticker),
            json_path=json_path,
        )

    payload_out = dict(payload)
    artifacts = dict(payload_out.get("artifacts") or {})
    artifacts["json_report_path"] = str(
        report_path) if report_path is not None else None
    payload_out["artifacts"] = artifacts

    if llm_prompt:
        prompt_source = dict(payload_out)
        payload_out["llm_prompt"] = build_llm_prompt(prompt_source)
        payload_out["llm_paths"] = build_llm_paths(payload_out, report_path)

    if save_json:
        report_path = _write_json_report(
            payload=payload_out,
            out_path=report_path if report_path is not None else _resolve_json_report_path(
                analyzer=analyzer,
                ticker=str(payload.get("ticker") or resolved_ticker),
                json_path=json_path,
            ),
        )

    if json_out:
        typer.echo(json.dumps(payload_out, indent=2, default=str))
        return

    recommendations = payload_out.get("recommendations", [])[:3]
    risk_warnings = _collect_risk_warnings(payload_out, recommendations)

    if terminal_mode:
        _render_prompt_data_block(
            console,
            payload_out,
            report_path=report_path,
            llm_prompt_enabled=llm_prompt,
        )

        console.print("\n[bold magenta]=== Graphs ===[/bold magenta]")
        try:
            render_terminal_charts(payload_out, console=console)
        except TerminalChartDependencyError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(code=1) from exc

        console.print("\n[bold green]=== Summary ===[/bold green]")
        if sheet:
            _render_sheet_output(
                console,
                payload_out,
                recommendations=recommendations,
                risk_warnings=risk_warnings,
                report_path=report_path,
                include_llm_prompt_panels=False,
            )
        else:
            _render_plain_output(
                payload_out,
                recommendations=recommendations,
                report_path=report_path,
                risk_warnings=risk_warnings,
            )
        return

    if sheet:
        _render_sheet_output(
            console,
            payload_out,
            recommendations=recommendations,
            risk_warnings=risk_warnings,
            report_path=report_path,
            include_llm_prompt_panels=llm_prompt,
        )
        return

    _render_plain_output(
        payload_out,
        recommendations=recommendations,
        report_path=report_path,
        risk_warnings=risk_warnings,
    )


@options_app.command("opportunities")
def opportunities(
    coins: str = typer.Option(
        "BTC,ETH",
        "--coins",
        help="Comma-separated coin list (currently supports BTC,ETH)",
    ),
    days_to_exp: int = typer.Option(
        30,
        "--days-to-exp",
        min=1,
        max=365,
        help="Target days to expiration",
    ),
    tf: str = typer.Option(
        "4h,1h",
        "--tf",
        help="Momentum setup/trigger timeframe pair (e.g. 4h,1h)",
    ),
    score_threshold: int = typer.Option(
        75,
        "--score-threshold",
        min=1,
        max=100,
        help="Minimum momentum score threshold",
    ),
    account_equity: float = typer.Option(
        10000.0,
        "--account-equity",
        min=1.0,
        help="Account equity context used by momentum sizing",
    ),
    risk_pct: float = typer.Option(
        0.005,
        "--risk-pct",
        min=0.001,
        max=0.02,
        help="Risk percentage passed to momentum filtering",
    ),
    require_tradeable: bool = typer.Option(
        True,
        "--require-tradeable/--allow-watchlist",
        help="Only run options analysis for momentum-tradeable setups",
    ),
    json_out: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-stable JSON output",
    ),
    sheet: bool = typer.Option(
        False,
        "--sheet",
        help="Render report as Rich terminal tables (human-readable).",
    ),
    source: str = typer.Option(
        "yfinance",
        "--source",
        help="Data source for option chains (yfinance|deribit)",
    ),
) -> None:
    """Scan BTC/ETH options opportunities using momentum as an upstream filter."""
    analyzer = _build_options_analyzer(source=source)
    console = Console()

    try:
        payload = analyzer.scan_crypto_opportunities(
            coins=_parse_coin_list(coins),
            days_to_exp=days_to_exp,
            tf=tf,
            account_equity=account_equity,
            risk_pct=risk_pct,
            score_threshold=score_threshold,
            require_tradeable=require_tradeable,
        )
    except OptionsError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if json_out and not sheet:
        typer.echo(json.dumps(payload, indent=2, default=str))
        return

    if sheet:
        _render_opportunities_sheet(console, payload)
        return

    summary = payload.get("summary") or {}
    typer.echo("Options opportunities")
    typer.echo(f"- coins_requested={summary.get('coins_requested')}")
    typer.echo(f"- momentum_allowed={summary.get('momentum_allowed')}")
    typer.echo(f"- options_ready={summary.get('options_ready')}")
    for coin, entry in sorted((payload.get("opportunities") or {}).items()):
        status = entry.get("status")
        strategy = entry.get("top_strategy")
        typer.echo(f"- {coin}: status={status} top_strategy={strategy}")
