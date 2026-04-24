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

stocks_app = typer.Typer(help="ISM-driven stock trading workflow (Alpaca + Ondo stubs).")


def _resolve_universe(universe_json: Optional[str]) -> dict[str, list[str]]:
    if not universe_json:
        return DEFAULT_UNIVERSE
    try:
        parsed = _json.loads(universe_json)
    except _json.JSONDecodeError as exc:
        raise typer.BadParameter(f"--universe-json is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise typer.BadParameter("--universe-json must be an object mapping sector → [tickers]")
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
    json_out: bool = typer.Option(False, "--json", help="Emit JSON instead of a table."),
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
                {"rank": r.rank, "industry": r.industry, "gics_sector": r.gics_sector}
                for r in report.expanding
            ],
            "contracting": [
                {"rank": r.rank, "industry": r.industry, "gics_sector": r.gics_sector}
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
    kind: str = typer.Option("manufacturing", "--kind", help="ISM report flavour"),
    top_n: int = typer.Option(5, "--top-n", help="Return the top N candidates"),
    capital: float = typer.Option(10000.0, "--capital", help="Total USD to equal-weight across picks"),
    max_pe_ratio: Optional[float] = typer.Option(
        None,
        "--max-pe",
        help="Optional PE filter (keep only tickers with PE <= this value).",
    ),
    min_eps_growth: Optional[float] = typer.Option(
        None,
        "--min-eps-growth",
        help="Optional EPS-growth filter in percent (next-year estimate).",
    ),
    universe_json: Optional[str] = typer.Option(
        None,
        "--universe-json",
        help="Override sector → tickers mapping as a JSON string.",
    ),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON plan instead of table."),
    dry_run: bool = typer.Option(True, "--dry-run/--live", help="Default dry-run. Broker is stubbed."),
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
        max_pe_ratio=max_pe_ratio,
        min_eps_growth_next_year=min_eps_growth,
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
    kind: str = typer.Option("manufacturing", "--kind", help="ISM report flavour"),
    top_n: int = typer.Option(5, "--top-n", help="Top N stocks per ISM trend bucket"),
    max_pe_ratio: Optional[float] = typer.Option(
        None,
        "--max-pe",
        help="Optional PE filter (keep only tickers with PE <= this value).",
    ),
    min_eps_growth: Optional[float] = typer.Option(
        None,
        "--min-eps-growth",
        help="Optional EPS-growth filter in percent (next-year estimate).",
    ),
    universe_json: Optional[str] = typer.Option(
        None,
        "--universe-json",
        help="Override sector → tickers mapping as a JSON string.",
    ),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON report."),
) -> None:
    """Build ISM hottest/worst industry report and filtered stock candidates."""
    if kind not in {"manufacturing", "services"}:
        raise typer.BadParameter("--kind must be manufacturing or services")

    payload = build_ism_industry_report(
        kind=kind,
        top_n=top_n,
        max_pe_ratio=max_pe_ratio,
        min_eps_growth_next_year=min_eps_growth,
        universe=_resolve_universe(universe_json),
    )

    if json_out:
        typer.echo(_json.dumps(payload, indent=2, default=str))
        return

    typer.echo(f"ISM {payload['kind'].capitalize()} — {payload['report_month']}")
    if payload.get("pmi") is not None:
        typer.echo(f"Headline PMI: {payload['pmi']}")
    typer.echo(
        "Criteria: "
        f"top_n={payload['criteria']['top_n']}, "
        f"max_pe={payload['criteria']['max_pe_ratio']}, "
        f"min_eps_growth={payload['criteria']['min_eps_growth_next_year']}"
    )
    typer.echo()

    hottest = payload["hottest_industries"][:5]
    worst = payload["worst_industries"][:5]
    typer.echo("Hottest industries (ISM expanding):")
    for item in hottest:
        typer.echo(f"  {item['rank']:>2}. {item['industry']}  ->  {item['gics_sector'] or '?'}")
    typer.echo()
    typer.echo("Worst industries (ISM contracting):")
    for item in worst:
        typer.echo(f"  {item['rank']:>2}. {item['industry']}  ->  {item['gics_sector'] or '?'}")
    typer.echo()

    for label, key in (("Filtered picks from hottest sectors", "expanding"), ("Filtered picks from worst sectors", "contracting")):
        typer.echo(f"{label}:")
        rows = payload["candidates"][key]
        if not rows:
            typer.echo("  (none)")
            continue
        for row in rows:
            typer.echo(
                f"  {row['symbol']:<6} [{row['sector']}] score={row['score']:+.3f}  "
                f"PE={row['pe_ratio']}  EPS(next)={row['eps_growth_next_year']}%"
            )


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
