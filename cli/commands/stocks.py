"""Stocks CLI command group — ISM-driven equity workflow.

Subcommands:
    nave stocks ism-scan       Fetch and render the latest ISM report.
    nave stocks screen         Run the PE-vs-sector + EPS-growth screener.
    nave stocks journal-stats  Print stock-only journal stats.
"""

from __future__ import annotations

import json as _json
import logging
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from cli.professional_typer import ProfessionalTyper
from core.logger import configure_logger
from trading.brokers import AlpacaBroker
from trading.stocks import (
    DEFAULT_UNIVERSE,
    ISMReportFetcher,
    ISMSectorStrategy,
    MassiveClient,
    SectorScreener,
    StockJournal,
    build_ism_industry_report,
)

logger = configure_logger(__name__, level=logging.INFO)

stocks_app = ProfessionalTyper(
    help="ISM-driven stock trading workflow (Alpaca + Ondo stubs).")


def _resolve_universe(universe_json: Optional[str]) -> dict[str, list[str]]:
    if not universe_json:
        return DEFAULT_UNIVERSE
    try:
        parsed = _json.loads(universe_json)
    except _json.JSONDecodeError as exc:
        raise typer.BadParameter(
            f"--universe-json is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise typer.BadParameter(
            "--universe-json must be an object mapping sector → [tickers]")
    return {str(k): [str(t) for t in v] for k, v in parsed.items()}


@stocks_app.command("ism-scan")
def ism_scan(
    kind: str = typer.Option(
        "manufacturing",
        "--kind",
        help="Report flavour: manufacturing or services",
    ),
    url: Optional[str] = typer.Option(
        None,
        "--url",
        help="Override source URL (useful for fixtures / alternative mirrors).",
    ),
    use_playwright: bool = typer.Option(
        False,
        "--playwright/--no-playwright",
        help="Use the Playwright fallback instead of httpx+BS4.",
    ),
    json_out: bool = typer.Option(
        False, "--json", help="Emit JSON instead of a table."),
) -> None:
    """Fetch the latest ISM Report On Business® and print the ranking."""
    if kind not in {"manufacturing", "services"}:
        raise typer.BadParameter("--kind must be manufacturing or services")

    fetcher = ISMReportFetcher(use_playwright=use_playwright)
    report = fetcher.fetch_report(kind, url=url)  # type: ignore[arg-type]

    if json_out:
        payload = {
            "kind": report.kind,
            "report_month": report.report_month,
            "pmi": report.pmi,
            "source_url": report.source_url,
            "expanding": [
                {"rank": r.rank, "industry": r.industry,
                    "gics_sector": r.gics_sector}
                for r in report.expanding
            ],
            "contracting": [
                {"rank": r.rank, "industry": r.industry,
                    "gics_sector": r.gics_sector}
                for r in report.contracting
            ],
        }
        typer.echo(_json.dumps(payload, indent=2))
        return

    typer.echo(f"ISM {report.kind.capitalize()} — {report.report_month}")
    if report.pmi is not None:
        typer.echo(f"Headline PMI: {report.pmi}")
    typer.echo(f"Source: {report.source_url}")
    typer.echo()
    typer.echo(f"Expanding ({len(report.expanding)}):")
    for r in report.expanding:
        sector = r.gics_sector or "?"
        typer.echo(f"  {r.rank:>2}. {r.industry}  →  {sector}")
    typer.echo()
    typer.echo(f"Contracting ({len(report.contracting)}):")
    for r in report.contracting:
        sector = r.gics_sector or "?"
        typer.echo(f"  {r.rank:>2}. {r.industry}  →  {sector}")


@stocks_app.command("screen")
def screen(
    kind: str = typer.Option("manufacturing", "--kind",
                             help="ISM report flavour"),
    top_n: int = typer.Option(
        5, "--top-n", help="Return the top N candidates"),
    capital: float = typer.Option(
        10000.0, "--capital", help="Total USD to equal-weight across picks"),
    min_eps_growth: Optional[float] = typer.Option(
        None,
        "--min-eps-growth",
        help="Optional EPS-growth filter in percent (next-year estimate).",
    ),
    min_confidence: float = typer.Option(
        0.3,
        "--min-confidence",
        help="Minimum final confidence score (0-1) for screen candidates.",
    ),
    universe_json: Optional[str] = typer.Option(
        None,
        "--universe-json",
        help="Override sector → tickers mapping as a JSON string.",
    ),
    json_out: bool = typer.Option(
        False, "--json", help="Emit JSON plan instead of table."),
    dry_run: bool = typer.Option(
        True, "--dry-run/--live", help="Default dry-run. Broker is stubbed."),
) -> None:
    """Run the full ISM → fundamentals screener and show the proposed plan."""
    if kind not in {"manufacturing", "services"}:
        raise typer.BadParameter("--kind must be manufacturing or services")

    universe = _resolve_universe(universe_json)
    massive = MassiveClient()
    broker = AlpacaBroker()
    strategy = ISMSectorStrategy(
        broker=broker,
        massive=massive,
        universe=universe,
        report_kind=kind,  # type: ignore[arg-type]
        capital_usd=capital,
        max_positions=top_n,
        min_eps_growth_next_year=min_eps_growth,
        min_confidence=min_confidence,
        dry_run=dry_run,
    )
    summary = strategy.run_once()

    if json_out:
        payload = {
            "strategy": summary["strategy"],
            "broker": summary["broker"],
            "dry_run": summary["dry_run"],
            "plan": [p.as_dict() for p in summary["plan"]],
            "result": summary["result"],
        }
        typer.echo(_json.dumps(payload, indent=2, default=str))
        return

    typer.echo(
        f"{summary['strategy']} via {summary['broker']}  "
        f"(dry_run={summary['dry_run']})"
    )
    if not summary["plan"]:
        typer.echo("No candidates — check --universe-json or widen the screener.")
        return
    for item in summary["plan"]:
        typer.echo(
            f"  long {item.symbol:<6}  ~${item.size_usd:>9,.2f}  "
            f"[{item.sector}] score={item.score:+.3f}  {item.reason}"
        )


@stocks_app.command("ism-report")
def ism_report(
    kind: str = typer.Option("manufacturing", "--kind",
                             help="ISM report flavour"),
    top_n: int = typer.Option(
        10, "--top-n", help="Top N stocks per ISM side bucket (long/short)"),
    min_eps_growth: Optional[float] = typer.Option(
        None,
        "--min-eps-growth",
        help="Optional EPS-growth filter in percent (next-year estimate).",
    ),
    min_confidence: float = typer.Option(
        0.3,
        "--min-confidence",
        help="Minimum final confidence score (0-1) for report candidates.",
    ),
    universe_json: Optional[str] = typer.Option(
        None,
        "--universe-json",
        help="Override sector → tickers mapping as a JSON string.",
    ),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON report."),
    sheet: bool = typer.Option(
        False,
        "--sheet",
        help="Render report as Rich terminal tables (human-readable).",
    ),
    save_snapshot: bool = typer.Option(
        True,
        "--save-snapshot/--no-save-snapshot",
        help="Save monthly ISM rankings + screened companies to var/stocks_history as JSON.",
    ),
    snapshot_dir: Optional[str] = typer.Option(
        None,
        "--snapshot-dir",
        help="Optional output directory for monthly ISM snapshot JSON files.",
    ),
) -> None:
    """Build ISM hottest/worst industry report and filtered stock candidates."""
    if kind not in {"manufacturing", "services"}:
        raise typer.BadParameter("--kind must be manufacturing or services")

    payload = build_ism_industry_report(
        kind=kind,
        top_n=top_n,
        min_eps_growth_next_year=min_eps_growth,
        min_confidence=min_confidence,
        universe=_resolve_universe(universe_json),
        persist_snapshot=save_snapshot,
        snapshot_dir=snapshot_dir,
    )

    if json_out and not sheet:
        typer.echo(_json.dumps(payload, indent=2, default=str))
        return

    if sheet:
        _render_ism_report_sheet(payload)
        return

    typer.echo(
        f"ISM {payload['kind'].capitalize()} — {payload['report_month']}")
    if payload.get("pmi") is not None:
        typer.echo(f"Headline PMI: {payload['pmi']}")
    typer.echo(
        "Criteria: "
        f"top_n={payload['criteria']['top_n']}, "
        f"min_eps_growth={payload['criteria']['min_eps_growth_next_year']}, "
        f"min_conf={payload['criteria']['min_confidence']}"
    )
    if payload.get("saved_to"):
        typer.echo(f"Snapshot saved: {payload['saved_to']}")
    typer.echo()

    hottest = payload["hottest_industries"][:5]
    worst = payload["worst_industries"][:5]
    typer.echo("Hottest industries (ISM expanding):")
    for item in hottest:
        typer.echo(
            f"  {item['rank']:>2}. {item['industry']}  ->  {item['gics_sector'] or '?'}")
    typer.echo()
    typer.echo("Worst industries (ISM contracting):")
    for item in worst:
        typer.echo(
            f"  {item['rank']:>2}. {item['industry']}  ->  {item['gics_sector'] or '?'}")
    typer.echo()

    for label, key in (("Top longs (hottest sectors)", "longs"), ("Top shorts (worst sectors)", "shorts")):
        typer.echo(f"{label}:")
        rows = payload["candidates"].get(key) or payload["candidates"][
            "expanding" if key == "longs" else "contracting"
        ]
        if not rows:
            typer.echo("  (none)")
            continue
        for row in rows:
            industry = row.get("industry") or "?"
            driver_industry = row.get("driver_industry") or "?"
            momentum = row.get("industry_momentum") or "?"
            side = row.get("side") or ("long" if key == "longs" else "short")
            typer.echo(
                f"  {row['symbol']:<6} [{row['sector']}] company={industry}  driver={driver_industry}  "
                f"{side.upper()} momentum={momentum}  "
                f"conf={row.get('confidence', '?')}  score={row['score']:+.3f}  "
                f"EPS(next)={row['eps_growth_next_year']}% "
                f"src={row.get('eps_growth_source') or '?'}"
            )


def _render_ism_report_sheet(payload: dict[str, object]) -> None:
    console = Console()
    criteria = payload.get("criteria") if isinstance(payload, dict) else {}
    if not isinstance(criteria, dict):
        criteria = {}

    console.print(
        f"ISM {(payload.get('kind') or '').__str__().capitalize()} — {payload.get('report_month') or '?'}"
    )
    if payload.get("pmi") is not None:
        console.print(f"Headline PMI: {payload.get('pmi')}")
    console.print(
        "Criteria: "
        f"top_n={criteria.get('top_n')}, "
        f"min_eps_growth={criteria.get('min_eps_growth_next_year')}, "
        f"min_conf={criteria.get('min_confidence')}"
    )
    saved_to = payload.get("saved_to")
    if saved_to:
        console.print(f"Snapshot saved: {saved_to}")
    console.print("")

    hottest = payload.get("hottest_industries")
    if isinstance(hottest, list):
        table = Table(title="Hottest industries (ISM expanding)")
        table.add_column("Rank", justify="right")
        table.add_column("Industry")
        table.add_column("GICS sector")
        for item in hottest[:10]:
            if not isinstance(item, dict):
                continue
            table.add_row(
                str(item.get("rank", "?")),
                str(item.get("industry", "?")),
                str(item.get("gics_sector") or "?"),
            )
        console.print(table)

    worst = payload.get("worst_industries")
    if isinstance(worst, list):
        table = Table(title="Worst industries (ISM contracting)")
        table.add_column("Rank", justify="right")
        table.add_column("Industry")
        table.add_column("GICS sector")
        for item in worst[:10]:
            if not isinstance(item, dict):
                continue
            table.add_row(
                str(item.get("rank", "?")),
                str(item.get("industry", "?")),
                str(item.get("gics_sector") or "?"),
            )
        console.print(table)

    candidates = payload.get("candidates")
    if not isinstance(candidates, dict):
        return

    for key, title in (
        ("longs", "Top longs (hottest sectors)"),
        ("shorts", "Top shorts (worst sectors)"),
    ):
        rows = candidates.get(key)
        if rows is None:
            rows = candidates.get("expanding" if key ==
                                  "longs" else "contracting")
        table = Table(title=title)
        table.add_column("Symbol")
        table.add_column("Name")
        table.add_column("Side")
        table.add_column("Sector")
        table.add_column("Industry")
        table.add_column("Driver")
        table.add_column("Momentum")
        table.add_column("Source")
        table.add_column("Confidence", justify="right")
        table.add_column("Score", justify="right")
        table.add_column("EPS next %", justify="right")
        table.add_column("EPS src")
        if isinstance(rows, list) and rows:
            for row in rows:
                if not isinstance(row, dict):
                    continue
                table.add_row(
                    str(row.get("symbol") or "?"),
                    str(row.get("company_name") or ""),
                    str(row.get("side") or ("long" if key == "longs" else "short")),
                    str(row.get("sector") or "?"),
                    str(row.get("industry") or "?"),
                    str(row.get("driver_industry") or "?"),
                    str(row.get("industry_momentum") or "?"),
                    str(row.get("industry_source") or "?"),
                    str(row.get("confidence") if row.get(
                        "confidence") is not None else "?"),
                    str(row.get("score") if row.get(
                        "score") is not None else "?"),
                    str(
                        row.get("eps_growth_next_year")
                        if row.get("eps_growth_next_year") is not None
                        else "?"
                    ),
                    str(row.get("eps_growth_source") or "?"),
                )
        else:
            table.add_row("(none)", "", "", "", "", "", "", "", "", "", "")
        console.print(table)


@stocks_app.command("journal-stats")
def journal_stats(json_out: bool = typer.Option(False, "--json")) -> None:
    """Print stock-only journal stats (filters by asset_class=stock)."""
    journal = StockJournal()
    stats = journal.stats()
    if json_out:
        typer.echo(_json.dumps(stats, indent=2, default=str))
        return
    typer.echo("Stock journal stats:")
    for k, v in stats.items():
        typer.echo(f"  {k}: {v}")
