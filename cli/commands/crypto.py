"""Crypto momentum command group for BTC/ETH derivatives scans."""

from __future__ import annotations

import json
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from cli.professional_typer import ProfessionalTyper
from trading.crypto.momentum import load_momentum_config
from trading.crypto.momentum.service import MomentumMarketService

crypto_app = ProfessionalTyper(help="Crypto derivatives momentum commands")
DEFAULT_SCORE_THRESHOLD = load_momentum_config().score_tradeable_threshold


def _json_default(value: Any) -> Any:
    """Serialize numpy/pandas scalar values emitted by live market frames."""
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return item()
        except Exception:
            pass
    return str(value)


def _build_scan_payload(
    *,
    symbols: str,
    tf: str,
    account_equity: float,
    risk_pct: float,
    score_threshold: int,
    apply_cadence_policy: bool,
) -> dict:
    service = MomentumMarketService()
    return service.scan_live(
        symbols=service.parse_symbols(symbols),
        timeframes=service.parse_timeframes(tf),
        account_equity=account_equity,
        risk_pct=risk_pct,
        score_threshold=score_threshold,
        apply_cadence_policy=apply_cadence_policy,
    )


def _build_playbook_payload(
    *,
    symbol: str,
    side: str,
    tf: str,
    account_equity: float,
    risk_pct: float,
    score_threshold: int,
) -> dict:
    service = MomentumMarketService()
    return service.playbook_live(
        symbol=service.parse_symbols(symbol)[0],
        side=side.lower(),
        timeframes=service.parse_timeframes(tf),
        account_equity=account_equity,
        risk_pct=risk_pct,
        score_threshold=score_threshold,
    )


def _render_scan(payload: dict) -> None:
    console = Console()
    table = Table(title="Derivatives momentum scan", show_lines=False)
    table.add_column("Symbol")
    table.add_column("Side")
    table.add_column("Status")
    table.add_column("Tradeable")
    table.add_column("Score", justify="right")
    table.add_column("Entry", justify="right")
    table.add_column("Invalidation", justify="right")
    table.add_column("TP2", justify="right")
    table.add_column("RR", justify="right")
    table.add_column("Move %", justify="right")

    for symbol, entry in payload["results"].items():
        for plan in entry["plans"]:
            table.add_row(
                symbol,
                plan["side"],
                plan["setup_status"],
                "yes" if plan["tradeable"] else "no",
                str(plan["confidence_score"]),
                f"{plan['entry_zone'][-1]:.2f}",
                f"{plan['invalidation']:.2f}",
                f"{plan['tp2']:.2f}",
                f"{plan['rr_estimated']:.2f}",
                f"{plan['expected_move_pct'] * 100:.1f}",
            )
    console.print(table)


def _render_playbook(payload: dict) -> None:
    plan = payload["plan"]
    console = Console()
    console.print(f"[bold]{payload['symbol']}[/bold] {plan['side']} momentum playbook")
    console.print(f"status: {plan['setup_status']}  tradeable: {plan['tradeable']}  score: {plan['confidence_score']}")
    console.print(f"entry zone: {plan['entry_zone'][0]:.2f} -> {plan['entry_zone'][1]:.2f}")
    console.print(f"invalidation: {plan['invalidation']:.2f}")
    console.print(f"targets: {plan['tp1']:.2f} / {plan['tp2']:.2f} / {plan['tp3']:.2f}")
    console.print(f"expected move: {plan['expected_move_pct'] * 100:.1f}%  RR: {plan['rr_estimated']:.2f}")


@crypto_app.command("momentum-scan")
def momentum_scan(
    symbols: str = typer.Option("BTCUSDT,ETHUSDT", "--symbols", help="Comma-separated perp symbols."),
    tf: str = typer.Option("4h,1h", "--tf", help="Setup and trigger timeframe, e.g. 4h,1h or 4h,15m."),
    account_equity: float = typer.Option(10000.0, "--account-equity", help="Account equity used for sizing context."),
    risk_pct: float = typer.Option(0.005, "--risk-pct", help="Risk per trade as decimal, e.g. 0.005 = 0.5%."),
    score_threshold: int = typer.Option(
        DEFAULT_SCORE_THRESHOLD,
        "--score-threshold",
        help="Minimum score to flag a setup as tradeable.",
    ),
    adaptive_threshold: bool = typer.Option(
        False,
        "--adaptive-threshold/--no-adaptive-threshold",
        help="Apply the cadence-recommended threshold instead of only reporting it.",
    ),
    telegram_markdown_v2: bool = typer.Option(
        False,
        "--telegram-markdown-v2",
        help="Render Telegram-friendly MarkdownV2 digest (chunked).",
    ),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON only."),
) -> None:
    """Scan BTC/ETH derivatives for fresh momentum setups."""
    payload = _build_scan_payload(
        symbols=symbols,
        tf=tf,
        account_equity=account_equity,
        risk_pct=risk_pct,
        score_threshold=score_threshold,
        apply_cadence_policy=adaptive_threshold,
    )
    if json_out:
        typer.echo(json.dumps(payload, indent=2, default=_json_default))
        return
    if telegram_markdown_v2:
        from trading.crypto.momentum.formatters import render_momentum_scan_markdown_v2

        messages = render_momentum_scan_markdown_v2(payload)
        for idx, message in enumerate(messages, start=1):
            if idx > 1:
                typer.echo("\n---\n")
            typer.echo(message)
        return
    _render_scan(payload)


@crypto_app.command("scan")
def scan(
    symbols: str = typer.Option("BTCUSDT,ETHUSDT", "--symbols", help="Comma-separated perp symbols."),
    tf: str = typer.Option("4h,1h", "--tf", help="Setup and trigger timeframe, e.g. 4h,1h or 4h,15m."),
    account_equity: float = typer.Option(10000.0, "--account-equity", help="Account equity used for sizing context."),
    risk_pct: float = typer.Option(0.005, "--risk-pct", help="Risk per trade as decimal, e.g. 0.005 = 0.5%."),
    score_threshold: int = typer.Option(
        DEFAULT_SCORE_THRESHOLD,
        "--score-threshold",
        help="Minimum score to flag a setup as tradeable.",
    ),
    adaptive_threshold: bool = typer.Option(
        False,
        "--adaptive-threshold/--no-adaptive-threshold",
        help="Apply the cadence-recommended threshold instead of only reporting it.",
    ),
    telegram_markdown_v2: bool = typer.Option(
        False,
        "--telegram-markdown-v2",
        help="Render Telegram-friendly MarkdownV2 digest (chunked).",
    ),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON only."),
) -> None:
    """Default market scan: routes to the momentum engine."""
    payload = _build_scan_payload(
        symbols=symbols,
        tf=tf,
        account_equity=account_equity,
        risk_pct=risk_pct,
        score_threshold=score_threshold,
        apply_cadence_policy=adaptive_threshold,
    )
    if json_out:
        typer.echo(json.dumps(payload, indent=2, default=_json_default))
        return
    if telegram_markdown_v2:
        from trading.crypto.momentum.formatters import render_momentum_scan_markdown_v2

        messages = render_momentum_scan_markdown_v2(payload)
        for idx, message in enumerate(messages, start=1):
            if idx > 1:
                typer.echo("\n---\n")
            typer.echo(message)
        return
    _render_scan(payload)


@crypto_app.command("momentum-playbook")
def momentum_playbook(
    symbol: str = typer.Option(..., "--symbol", help="Perp symbol, e.g. BTCUSDT."),
    side: str = typer.Option(..., "--side", help="Trade direction: long or short."),
    tf: str = typer.Option("4h,1h", "--tf", help="Setup and trigger timeframe, e.g. 4h,1h or 4h,15m."),
    account_equity: float = typer.Option(10000.0, "--account-equity", help="Account equity used for sizing context."),
    risk_pct: float = typer.Option(0.005, "--risk-pct", help="Risk per trade as decimal, e.g. 0.005 = 0.5%."),
    score_threshold: int = typer.Option(
        DEFAULT_SCORE_THRESHOLD,
        "--score-threshold",
        help="Minimum score to flag a setup as tradeable.",
    ),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON only."),
) -> None:
    """Build a concrete derivatives momentum playbook for one symbol and side."""
    payload = _build_playbook_payload(
        symbol=symbol,
        side=side,
        tf=tf,
        account_equity=account_equity,
        risk_pct=risk_pct,
        score_threshold=score_threshold,
    )
    if json_out:
        typer.echo(json.dumps(payload, indent=2, default=_json_default))
        return
    _render_playbook(payload)


@crypto_app.command("playbook")
def playbook(
    symbol: str = typer.Option(..., "--symbol", help="Perp symbol, e.g. BTCUSDT."),
    side: str = typer.Option(..., "--side", help="Trade direction: long or short."),
    tf: str = typer.Option("4h,1h", "--tf", help="Setup and trigger timeframe, e.g. 4h,1h or 4h,15m."),
    account_equity: float = typer.Option(10000.0, "--account-equity", help="Account equity used for sizing context."),
    risk_pct: float = typer.Option(0.005, "--risk-pct", help="Risk per trade as decimal, e.g. 0.005 = 0.5%."),
    score_threshold: int = typer.Option(
        DEFAULT_SCORE_THRESHOLD,
        "--score-threshold",
        help="Minimum score to flag a setup as tradeable.",
    ),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON only."),
) -> None:
    """Default trade-plan builder: routes to the momentum engine."""
    payload = _build_playbook_payload(
        symbol=symbol,
        side=side,
        tf=tf,
        account_equity=account_equity,
        risk_pct=risk_pct,
        score_threshold=score_threshold,
    )
    if json_out:
        typer.echo(json.dumps(payload, indent=2, default=_json_default))
        return
    _render_playbook(payload)


@crypto_app.command("momentum-backtest")
def momentum_backtest(
    symbols: str = typer.Option("BTCUSDT,ETHUSDT", "--symbols", help="Comma-separated perp symbols."),
    tf: str = typer.Option("4h,1h", "--tf", help="Setup and trigger timeframe, e.g. 4h,1h or 4h,15m."),
    lookback_days: int = typer.Option(180, "--lookback-days", help="Historical days to evaluate."),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON only."),
) -> None:
    """Run the simple historical momentum evaluator versus the baseline breakout."""
    service = MomentumMarketService()
    payload = service.backtest_live(
        symbols=service.parse_symbols(symbols),
        timeframes=service.parse_timeframes(tf),
        lookback_days=lookback_days,
    )
    if json_out:
        typer.echo(json.dumps(payload, indent=2, default=_json_default))
        return

    console = Console()
    table = Table(title="Derivatives momentum backtest", show_lines=False)
    table.add_column("Symbol")
    table.add_column("Trades", justify="right")
    table.add_column("Win %", justify="right")
    table.add_column("Expectancy", justify="right")
    table.add_column("Max DD", justify="right")
    table.add_column(">=8%", justify="right")
    table.add_column("Delta Exp", justify="right")
    for symbol, result in payload["results"].items():
        metrics = result["metrics"]
        delta = result.get("baseline", {}).get("delta", {})
        table.add_row(
            symbol,
            str(result["trade_count"]),
            f"{metrics['win_rate'] * 100:.1f}",
            f"{metrics['expectancy']:.2f}",
            f"{metrics['max_drawdown']:.2f}",
            f"{metrics['pct_reaching_8'] * 100:.1f}",
            f"{delta.get('expectancy', 0.0):+.2f}",
        )
    console.print(table)