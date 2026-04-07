"""Unified Nave CLI using Typer.

Provides clean commands for data, trading, API, MCP, and COT analysis.
Orchestrates existing components without removing integrations.
"""

import typer
from typing import Any, Optional
from pathlib import Path
import json

app = typer.Typer(
    name="nave",
    help="Nave - Professional macro trading and data platform CLI",
    add_completion=True,
)

# Sub-apps
data_app = typer.Typer(help="Data fetching and analysis commands")
trading_app = typer.Typer(help="Trading and strategy commands")
api_app = typer.Typer(help="Backend API commands")
mcp_app = typer.Typer(help="MCP server commands")
cot_app = typer.Typer(help="COT specific commands")
journal_app = typer.Typer(help="Manual trade journal commands")

app.add_typer(data_app, name="data")
app.add_typer(trading_app, name="trading")
app.add_typer(api_app, name="api")
app.add_typer(mcp_app, name="mcp")
app.add_typer(cot_app, name="cot")
trading_app.add_typer(journal_app, name="journal")


def _select_option(label: str, choices: list[str], default: Optional[str] = None) -> str:
    """Use arrow-key menu when available; fallback to typed selection."""
    try:
        import questionary

        prompt = questionary.select(
            label,
            choices=choices,
            default=default,
            qmark=">",
            pointer=">",
        )
        answer = prompt.ask()
        if answer:
            return str(answer)
    except Exception:
        pass

    typer.echo(label)
    for idx, value in enumerate(choices, start=1):
        typer.echo(f"  {idx}. {value}")
    selected = typer.prompt("Choose option", default="1")
    try:
        index = int(selected) - 1
    except ValueError as exc:
        raise typer.BadParameter("Selection must be a number") from exc
    if index < 0 or index >= len(choices):
        raise typer.BadParameter("Invalid selection")
    return choices[index]


def _prompt_float(label: str, default: Optional[float] = None, min_value: float = 0.0) -> float:
    while True:
        value = typer.prompt(label, default=default)
        try:
            result = float(value)
        except (TypeError, ValueError):
            typer.echo("Please provide a numeric value.")
            continue
        if result < min_value:
            typer.echo(f"Value must be >= {min_value}")
            continue
        return result


@journal_app.command("create")
def journal_create():
    """Create a manual trade record with interactive prompts."""
    from trading.journal.manual_trade import (
        ManualTrade,
        ManualTradeStore,
        fetch_cot_insight,
        MARKET_TYPES,
        SIDES,
        TRADING_MODES,
    )

    store = ManualTradeStore()
    asset = typer.prompt("Asset", default="BTC").strip().upper()
    platform = typer.prompt("Platform", default="binance").strip().lower()
    side = _select_option("Select side", list(SIDES), default="long")
    market_type = _select_option(
        "Select market type", list(MARKET_TYPES), default="futures")
    trading_mode = _select_option(
        "Select trading mode", list(TRADING_MODES), default="demo")

    entry_price = _prompt_float("Entry price", min_value=0.000001)
    target_price = _prompt_float("Target price", min_value=0.000001)
    stop_loss_price = _prompt_float("Stop loss price", min_value=0.000001)
    fees = _prompt_float("Fees", default=0.0, min_value=0.0)
    size = _prompt_float("Position size (USD/contracts)", min_value=0.0)
    leverage = _prompt_float("Leverage", default=1.0, min_value=1.0)
    setup = typer.prompt("Setup (optional)", default="")
    notes = typer.prompt("Notes (optional)", default="")

    cot_insight = None
    cot_warning = None
    try:
        cot_insight = fetch_cot_insight(asset)
    except Exception as exc:
        typer.echo(f"COT fetch failed: {exc}")
        retry = typer.confirm("Retry COT fetch once?", default=True)
        if retry:
            try:
                cot_insight = fetch_cot_insight(asset)
            except Exception as second_exc:
                cot_warning = f"COT unavailable after retry: {second_exc}"
        else:
            cot_warning = "COT fetch skipped by user"

    trade = ManualTrade(
        asset=asset,
        platform=platform,
        side=side,
        market_type=market_type,
        trading_mode=trading_mode,
        entry_price=entry_price,
        target_price=target_price,
        stop_loss_price=stop_loss_price,
        fees=fees,
        size=size,
        leverage=leverage,
        setup=setup,
        notes=notes,
        cot_insight=cot_insight,
        cot_warning=cot_warning,
    )
    store.create_trade(trade)
    typer.echo(f"Created manual trade: {trade.trade_id}")
    typer.echo("Next: nave trading journal update --id <TRADE_ID>")


@journal_app.command("update")
def journal_update(
    id: str = typer.Option(..., "--id", help="Trade ID to update"),
):
    """Update an existing manual trade with guided actions."""
    from trading.journal.manual_trade import ManualTradeStore

    store = ManualTradeStore()
    trade = store.get_trade(id)
    if trade is None:
        raise typer.BadParameter(f"Trade not found: {id}")

    action = _select_option(
        "Select update action",
        [
            "take_profit_price_1",
            "take_profit_price_2",
            "take_profit_final_price",
            "stop_loss adjustment",
            "fees adjustment",
            "notes update",
        ],
        default="take_profit_price_1",
    )

    if action == "notes update":
        value = typer.prompt("New notes")
    else:
        value = _prompt_float("New value", min_value=0.0)

    updated = store.apply_update(id, action, value)
    typer.echo(f"Updated trade: {updated.trade_id}")
    typer.echo(f"Status: {updated.status}")
    if action == "take_profit_price_1" and updated.tp1_progress_percent is not None:
        typer.echo(f"TP1 progress: {updated.tp1_progress_percent:.2f}%")
    if action == "take_profit_price_2" and updated.tp2_progress_percent is not None:
        typer.echo(f"TP2 progress: {updated.tp2_progress_percent:.2f}%")


@journal_app.command("list")
def journal_list(
    status: Optional[str] = typer.Option(
        None, help="Filter by status (open/closed)"),
):
    """List manual journal trades."""
    from trading.journal.manual_trade import ManualTradeStore

    store = ManualTradeStore()
    trades = store.list_trades(status=status)
    if not trades:
        typer.echo("No manual trades found.")
        return

    for trade in trades:
        synced = "yes" if trade.sync.get("wiki_synced_at") else "no"
        typer.echo(
            f"{trade.trade_id} | {trade.asset} {trade.side} | {trade.trading_mode} | "
            f"status={trade.status} | synced={synced}"
        )


@journal_app.command("show")
def journal_show(
    id: str = typer.Option(..., "--id", help="Trade ID"),
):
    """Show full manual trade JSON."""
    from trading.journal.manual_trade import ManualTradeStore

    store = ManualTradeStore()
    trade = store.get_trade(id)
    if trade is None:
        raise typer.BadParameter(f"Trade not found: {id}")
    typer.echo(json.dumps(trade.to_dict(), indent=2))


@journal_app.command("sync-wiki")
def journal_sync_wiki(
    owner: str = typer.Option("edyhvh", help="GitHub owner"),
    repo: str = typer.Option("nave", help="GitHub repository name"),
    token: Optional[str] = typer.Option(
        None, help="GitHub token; defaults to NAVE_GITHUB_TOKEN"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Preview unsynced trades only"),
):
    """Sync unsynced manual trades to monthly GitHub wiki pages."""
    import os
    from trading.journal.manual_trade import ManualTradeStore
    from trading.journal.manual_wiki_sync import ManualTradeWikiSync

    store = ManualTradeStore()
    rows = store.unsynced_trades()
    if not rows:
        typer.echo("No unsynced trades found.")
        return

    typer.echo(f"Unsynced trades: {len(rows)}")
    if dry_run:
        for trade in rows:
            typer.echo(f"- {trade.trade_id} ({trade.date_created[:7]})")
        return

    github_token = token or os.getenv("NAVE_GITHUB_TOKEN", "")
    if not github_token:
        raise typer.BadParameter(
            "Missing token: use --token or set NAVE_GITHUB_TOKEN")

    if not typer.confirm("Proceed with wiki sync?", default=False):
        typer.echo("Sync cancelled.")
        return

    syncer = ManualTradeWikiSync(owner=owner, repo=repo, token=github_token)
    result = syncer.sync(rows)
    if result["synced"] == 0:
        typer.echo("No new entries were synced.")
        return

    month_pages = sorted({f"Journal-{t.date_created[:7]}" for t in rows})
    for page in month_pages:
        ids = [t.trade_id for t in rows if page.endswith(t.date_created[:7])]
        store.mark_synced(ids, page)
    typer.echo(
        f"Synced {result['synced']} trades across {result['pages']} page(s).")


@app.command()
def version():
    """Show Nave version."""
    typer.echo("Nave v0.1.0 (refactored with unified CLI)")

# Stub commands - will be fleshed out in later steps


@data_app.command("fetch")
def fetch_data(indicator: str = typer.Argument("all")):
    """Fetch macro data using OpenBB."""
    from backend.app.services.aaii import fetch_aaii_sentiment
    from backend.app.services.onchain import fetch_onchain_metrics
    from backend.app.services.openbb import fetch_openbb_indicator

    if indicator == "all":
        payload = {
            "aaii": fetch_aaii_sentiment(),
            "onchain_btc": fetch_onchain_metrics("bitcoin"),
            "rrp": fetch_openbb_indicator("rrp"),
            "tga": fetch_openbb_indicator("tga"),
        }
        typer.echo(payload)
        return

    if indicator == "aaii":
        typer.echo(fetch_aaii_sentiment())
        return

    if indicator in {"onchain", "onchain_btc"}:
        typer.echo(fetch_onchain_metrics("bitcoin"))
        return

    typer.echo(fetch_openbb_indicator(indicator))


@trading_app.command("run-strategy")
def run_strategy(
    wallet: str = typer.Option("hermes", help="Wallet name"),
    coins: Optional[str] = typer.Option(None, help="Coins to trade"),
    dry_run: bool = typer.Option(True, help="Dry run mode"),
    mainnet: bool = typer.Option(False, help="Use mainnet"),
):
    """Run trading strategy (delegates to trading.strategy)."""
    from trading.client import HyperliquidClient
    from trading.strategy import MacroMomentumStrategy

    parsed_coins = coins.split() if coins else ["BTC", "ETH"]
    client = HyperliquidClient(wallet_name=wallet, testnet=not mainnet)
    strategy = MacroMomentumStrategy(
        client,
        coins=parsed_coins,
        dry_run=dry_run,
    )
    result = strategy.run_once()
    typer.echo(result)


@trading_app.command("run")
def run_trading(
    strategy: str = typer.Option(
        "cot-weekly",
        "--strategy",
        help="Strategy id to run (e.g. cot-weekly)",
    ),
    wallet: str = typer.Option("hermes", help="Wallet name"),
    capital: float = typer.Option(
        2000.0, help="Capital for weekly COT analysis"),
    paper: bool = typer.Option(
        False,
        "--paper",
        help="Run in paper mode (recommended default path)",
    ),
    backtest: bool = typer.Option(
        False,
        "--backtest",
        help="Run backtest mode for strategy validation",
    ),
    live: bool = typer.Option(
        False,
        "--live",
        help="Disable dry-run safeguards (real execution path)",
    ),
    learn: bool = typer.Option(
        False,
        "--learn",
        help="Run setup learning pipeline from backtest outcomes",
    ),
):
    """Run trading workflows.

    Examples:
        nave trading run --paper --strategy cot-weekly
        nave trading run --backtest --strategy cot-weekly
    """
    import subprocess
    import sys

    if paper and backtest:
        raise typer.BadParameter("Use either --paper or --backtest, not both.")

    if strategy == "cot-weekly":
        cmd = [sys.executable, "scripts/weekly_cot_analysis.py",
               f"--capital={capital}"]
        if backtest:
            cmd.append("--backtest")
        else:
            cmd.append("--paper")
        if live:
            cmd.append("--live")
        if learn:
            cmd.append("--learn")
        typer.echo(
            f"Running {strategy} (paper={not backtest}, backtest={backtest})")
        subprocess.run(cmd, check=False)
        return

    cmd = [sys.executable, "-m", "trading.strategy", f"--wallet={wallet}"]
    if not live:
        cmd.append("--dry-run")
    typer.echo(f"Running strategy={strategy} via trading.strategy module")
    subprocess.run(cmd, check=False)


@api_app.command("start")
def start_api(
    host: str = typer.Option("127.0.0.1", help="Host to bind"),
    port: int = typer.Option(8000, help="Port to listen on"),
    reload: bool = typer.Option(True, help="Enable auto-reload"),
):
    """Start the FastAPI backend server."""
    typer.echo(f"Starting Nave API on {host}:{port} (reload={reload})...")
    import subprocess
    cmd = [
        "uvicorn",
        "--app-dir=backend",
        "app.main:app",
        f"--host={host}",
        f"--port={port}",
        "--reload" if reload else "",
    ]
    cmd = [c for c in cmd if c]
    subprocess.run(cmd, check=False)


@mcp_app.command("run")
def run_mcp():
    """Run the MCP server for AI agents."""
    typer.echo("Starting MCP server (uses trading/mcp_server)...")
    import subprocess
    import sys
    subprocess.run([sys.executable, "-m", "trading.mcp_server"], check=False)


@cot_app.command("analyze")
def analyze_cot(coins: str = typer.Option("BTC ETH", help="Coins to analyze")):
    """Analyze COT data as main trading driver."""
    typer.echo(f"Analyzing COT for {coins}...")
    import subprocess
    import sys
    subprocess.run(
        [sys.executable, "-m", "trading.cot.cot_analyzer"], check=False)


@cot_app.command("report")
def cot_report(
    coins: str = typer.Option(
        "BTC ETH", help="Coins to analyze (space-separated)"),
    capital: float = typer.Option(2000.0, help="Available capital USD"),
    json_out: bool = typer.Option(
        False, "--json", help="Output as JSON instead of table"),
    debug: bool = typer.Option(
        False, "--debug-cot", help="Print raw filtered DataFrame rows for debugging"),
    include_micro: bool = typer.Option(
        False, "--include-micro", help="Include MICRO contracts in COT filter"),
    report_type: str = typer.Option(
        "futures_and_options", "--report-type",
        help="CFTC report type: futures_only or futures_and_options (legacy_combined alias supported)"),
    cot_history: int | None = typer.Option(
        None,
        "--cot-history",
        help="Generate historical COT variation report for the last N calendar months (1-12)",
    ),
):
    """Weekly COT report with indicators for manual setup hunting.

    Fetches latest CFTC COT data, computes bias/strength/regime/volatility
    for each coin, and prints a clean summary you can use to find setups
    on the 4H/1H chart yourself.

    The output is designed to be easily parsed by an LLM for generating
    concrete trading setups with direction, timeframes, and confluences.

    Examples:
        nave cot report
        nave cot report --coins "BTC ETH"
        nave cot report --json
        nave cot report --debug-cot
        nave cot report --include-micro
    """
    import json as _json
    import logging as _logging
    from datetime import date as _date
    from datetime import datetime as _dt
    from datetime import timedelta as _timedelta
    from datetime import timezone as _timezone

    from trading.client import HyperliquidClient
    from trading.cot.cot_fetcher import build_cot_sections_from_datasets, fetch_latest_cot
    from trading.cot.cot_analyzer import COTAnalyzer

    def _parse_date(value: str) -> _date | None:
        dt = _dt.fromisoformat(str(value)) if "T" in str(
            value) else _dt.strptime(str(value), "%Y-%m-%d")
        return dt.date()

    def _compute_price_context(coin: str, as_of_date: _date | None) -> dict[str, object]:
        """Fetch report-close price, weekly delta, and a basic 4H trend state."""
        if as_of_date is None:
            return {
                "price_close": None,
                "weekly_price_delta_pct": None,
                "trend_4h": "unknown",
            }

        try:
            client = HyperliquidClient(wallet_name=None, testnet=False)
            end_dt = _dt.combine(
                as_of_date + _timedelta(days=1), _dt.min.time(), tzinfo=_timezone.utc)
            start_dt = end_dt - _timedelta(days=14)
            end_ms = int(end_dt.timestamp() * 1000)
            start_ms = int(start_dt.timestamp() * 1000)

            daily = client.get_historical_candles(
                coin=coin,
                interval="1d",
                start_time_ms=start_ms,
                end_time_ms=end_ms,
                max_pages=12,
                throttle_seconds=0,
            )
            by_day = [c for c in daily if c.get("timestamp")]
            by_day.sort(key=lambda x: x["timestamp_ms"])

            report_close = None
            for c in by_day:
                cdate = c["timestamp"].date()
                if cdate <= as_of_date:
                    report_close = float(c["close"])

            prev_week_target = as_of_date - _timedelta(days=7)
            prev_week_close = None
            for c in by_day:
                cdate = c["timestamp"].date()
                if cdate <= prev_week_target:
                    prev_week_close = float(c["close"])

            weekly_delta = None
            if report_close and prev_week_close:
                weekly_delta = (
                    (report_close - prev_week_close) / prev_week_close) * 100

            trend_4h = "unknown"
            four_h = client.get_historical_candles(
                coin=coin,
                interval="4h",
                start_time_ms=int(
                    (end_dt - _timedelta(days=10)).timestamp() * 1000),
                end_time_ms=end_ms,
                max_pages=16,
                throttle_seconds=0,
            )
            if len(four_h) >= 8:
                first = float(four_h[0]["close"])
                last = float(four_h[-1]["close"])
                if last > first:
                    trend_4h = "bullish"
                elif last < first:
                    trend_4h = "bearish"
                else:
                    trend_4h = "flat"

            return {
                "price_close": report_close,
                "weekly_price_delta_pct": weekly_delta,
                "trend_4h": trend_4h,
            }
        except Exception:
            return {
                "price_close": None,
                "weekly_price_delta_pct": None,
                "trend_4h": "unknown",
            }

    def _cot_vs_price_action(bias: str, trend_4h: str) -> str:
        if trend_4h == "unknown":
            return "Trend data unavailable (4H) -> use price action confirmation before sizing"
        if bias == "bullish" and trend_4h == "bearish":
            return "Divergence detected (COT bullish vs 4H bearish structure) -> Caution"
        if bias == "bearish" and trend_4h == "bullish":
            return "Divergence detected (COT bearish vs 4H bullish structure) -> Caution"
        return "COT and 4H price action broadly aligned"

    def _position_intensity(pct_oi_abs: float) -> str:
        if pct_oi_abs >= 15.0:
            return "heavily"
        if pct_oi_abs >= 5.0:
            return "moderately"
        if pct_oi_abs > 0.0:
            return "slightly"
        return "near-neutral"

    def _history_weeks_for_months(months: int) -> int:
        # 6 weeks/month cushion preserves enough Tuesday snapshots for calendar windows.
        return max(16, months * 6 + 4)

    if debug:
        _logging.basicConfig(level=_logging.DEBUG,
                             format="%(levelname)s: %(message)s")
    else:
        _logging.basicConfig(level=_logging.INFO, format="%(message)s")

    if report_type not in {"futures_only", "futures_and_options", "legacy_combined"}:
        raise typer.BadParameter(
            "--report-type must be futures_only or futures_and_options (legacy_combined alias supported)"
        )

    if cot_history is not None and not (1 <= cot_history <= 12):
        raise typer.BadParameter("--cot-history must be between 1 and 12")

    primary_report_type = "futures_only" if report_type == "futures_only" else "futures_and_options"
    primary_report_label = "Futures Only" if primary_report_type == "futures_only" else "Futures + Options"

    coin_list = coins.split()
    cot_data_futures_only = {}
    cot_data_futures_and_options = {}

    analyzer = COTAnalyzer()

    if cot_history is not None:
        history_weeks = _history_weeks_for_months(cot_history)
        historical_data = fetch_latest_cot(
            report_type=primary_report_type,
            include_micro=include_micro,
            debug=debug,
            history_weeks=history_weeks,
        )
        historical_data = {
            coin: historical_data[coin]
            for coin in coin_list
            if coin in historical_data
        }
        historical = analyzer.generate_historical_variation_report(
            months=cot_history,
            cot_data=historical_data,
        )

        if json_out:
            payload = {
                "generated_at": _dt.now().strftime("%Y-%m-%d %H:%M"),
                "report_type": "cot_historical_variation",
                "bias_source": primary_report_type,
                "months": cot_history,
                "as_of_date": historical.get("as_of_date", "N/A"),
                "coins": historical.get("assets", {}),
                "observations": historical.get("observations", []),
            }
            typer.echo(_json.dumps(payload, indent=2))
            return

        typer.echo()
        typer.echo(historical.get(
            "markdown", "No historical report output available."))
        return

    cot_data_futures_only = fetch_latest_cot(
        report_type="futures_only",
        include_micro=include_micro,
        debug=debug,
    )
    cot_data_futures_and_options = fetch_latest_cot(
        report_type="futures_and_options",
        include_micro=include_micro,
        debug=debug,
    )

    biases_futures_only = analyzer.analyze(cot_data_futures_only)
    biases_futures_and_options = analyzer.analyze(cot_data_futures_and_options)

    if primary_report_type == "futures_only":
        cot_data = cot_data_futures_only
        biases = biases_futures_only
    else:
        cot_data = cot_data_futures_and_options
        biases = biases_futures_and_options

    now = _dt.now().strftime("%Y-%m-%d")
    now_full = _dt.now().strftime("%Y-%m-%d %H:%M")

    cot_sections = build_cot_sections_from_datasets(
        futures_only_data=cot_data_futures_only,
        combined_data=cot_data_futures_and_options,
    )

    def _fmt_signed(value: Any) -> str:
        if value is None:
            return "N/A"
        return f"{int(value):+,}"

    def _fmt_int(value: Any) -> str:
        if value is None:
            return "N/A"
        return f"{int(value):,}"

    def _fmt_pct(value: Any) -> str:
        if value is None:
            return "N/A"
        return f"{float(value):.1f}%"

    def _fmt_section_lines(section: dict[str, Any] | None) -> list[str]:
        if not section:
            return [
                "Net Non-Comm: N/A (Δ N/A)     | % of OI: N/A",
                "Net Commercial: N/A (Δ N/A)",
                "Open Interest: N/A (Δ N/A)",
                "# Traders: Non-Comm: N/A | Commercial: N/A",
            ]
        return [
            f"Net Non-Comm: {_fmt_signed(section.get('net_non_commercial'))} (Δ {_fmt_signed(section.get('net_non_commercial_delta'))})     | % of OI: {_fmt_pct(section.get('pct_oi'))}",
            f"Net Commercial: {_fmt_signed(section.get('net_commercial'))} (Δ {_fmt_signed(section.get('net_commercial_delta'))})",
            f"Open Interest: {_fmt_int(section.get('open_interest'))} (Δ {_fmt_signed(section.get('open_interest_delta'))})",
            f"# Traders: Non-Comm: {_fmt_int(section.get('traders_non_commercial'))} | Commercial: {_fmt_int(section.get('traders_commercial'))}",
        ]

    # Debug: print raw DataFrame rows per asset
    if debug:
        import pandas as pd
        debug_sets = [
            ("FUTURES ONLY", cot_data_futures_only),
            ("FUTURES + OPTIONS", cot_data_futures_and_options),
        ]
        for dataset_label, dataset in debug_sets:
            for coin in coin_list:
                d = dataset.get(coin)
                if not d:
                    continue
                raw = d.get("raw", [])
                if raw:
                    df = pd.DataFrame(raw)
                    typer.echo(
                        f"\n=== DEBUG: {coin} [{dataset_label}] raw filtered data ({len(df)} rows) ==="
                    )
                    if "market_and_exchange_names" in df.columns:
                        names = df["market_and_exchange_names"].astype(
                            str).unique().tolist()
                        typer.echo(f"Matched market names: {names}")
                    typer.echo(df.tail(5).to_string(index=False))
                else:
                    typer.echo(
                        f"\n=== DEBUG: {coin} [{dataset_label}] — no raw rows (using pre-computed mock) ==="
                    )
                    typer.echo(f"  Pre-computed: {d}")

    price_context: dict[str, dict[str, object]] = {}
    for coin in coin_list:
        b = biases.get(coin)
        if not b:
            continue
        as_of_raw = b.metadata.get(
            "as_of_date", b.metadata.get("report_date", "N/A"))
        as_of = None
        try:
            as_of = _parse_date(str(as_of_raw))
        except Exception:
            as_of = None
        price_context[coin] = _compute_price_context(coin, as_of)

    if json_out:
        payload = {
            "generated_at": now_full,
            "capital_usd": capital,
            "philosophy": "F.I.T.S. contrarian COT",
            "coins": {},
        }
        for coin in coin_list:
            b = biases.get(coin)
            if not b:
                continue
            m = b.metadata
            payload["coins"][coin] = {
                "bias": b.bias,
                "confidence": round(b.confidence, 2),
                "bias_source": primary_report_type,
                "bias_strength": m["bias_strength"],
                "fits_score": m["fits_weighted_score"],
                "market_regime": m["market_regime"],
                "net_non_commercial": b.net_non_commercial,
                "pct_oi": m["pct_oi"],
                "weekly_change": b.weekly_change,
                "net_commercial": b.net_commercial,
                "open_interest": b.open_interest,
                "oi_change_pct": b.oi_change_pct,
                "historical_percentile": b.historical_percentile,
                "percentile_interpretation": m.get("percentile_interpretation", ""),
                "percentile_warning": m.get("percentile_warning", ""),
                "volatility": round(m["volatility"], 4),
                "report_date": m.get("report_date", "N/A"),
                "as_of_date": m.get("as_of_date", "N/A"),
                "release_date": m.get("release_date", "N/A"),
                "bias_label": m.get("bias_label", b.bias.upper()),
                "cot_interpretation": m.get("cot_interpretation", "N/A"),
                "pct_oi_signed": m.get("pct_oi_signed", 0.0),
                "pct_oi_position_side": m.get("pct_oi_position_side", "net long"),
                "price_at_report_close": price_context.get(coin, {}).get("price_close"),
                "weekly_price_delta_pct": price_context.get(coin, {}).get("weekly_price_delta_pct"),
                "trend_4h": price_context.get(coin, {}).get("trend_4h", "unknown"),
                "cot_vs_price_action": _cot_vs_price_action(
                    b.bias,
                    str(price_context.get(coin, {}).get("trend_4h", "unknown")),
                ),
                "cached": m.get("cached", False),
                "futures_only": cot_sections.get(coin, {}).get("futures_only"),
                "options": cot_sections.get(coin, {}).get("options"),
                "futures_and_options": cot_sections.get(coin, {}).get("combined"),
                "options_validation": cot_sections.get(coin, {}).get("options_validation"),
            }
        typer.echo(_json.dumps(payload, indent=2))
        return

    # ── Pretty report output (LLM-friendly) ──
    # Determine cache status from first available asset
    any_cached_futures_only = any(
        cot_data_futures_only.get(c, {}).get("cached", False) for c in coin_list
    )
    any_cached_futures_and_options = any(
        cot_data_futures_and_options.get(c, {}).get("cached", False) for c in coin_list
    )
    cache_label = (
        f"Futures Only: {'YES' if any_cached_futures_only else 'NO'} | "
        f"Futures+Options: {'YES' if any_cached_futures_and_options else 'NO'}"
    )

    # Find the report data-as-of date from biases
    as_of_dates = [
        biases[c].metadata.get(
            "as_of_date", biases[c].metadata.get("report_date", "N/A"))
        for c in coin_list if c in biases
    ]
    release_dates = [
        biases[c].metadata.get("release_date", "N/A")
        for c in coin_list if c in biases
    ]
    data_as_of = as_of_dates[0] if as_of_dates else "N/A"
    released_on = release_dates[0] if release_dates else "N/A"

    as_of_fo = next(
        (
            biases_futures_only[c].metadata.get(
                "as_of_date", biases_futures_only[c].metadata.get("report_date", "N/A"))
            for c in coin_list
            if c in biases_futures_only
        ),
        "N/A",
    )
    as_of_fof = next(
        (
            biases_futures_and_options[c].metadata.get(
                "as_of_date", biases_futures_and_options[c].metadata.get(
                    "report_date", "N/A")
            )
            for c in coin_list
            if c in biases_futures_and_options
        ),
        "N/A",
    )
    merged_as_of = as_of_fo if as_of_fo == as_of_fof else f"{as_of_fo} / {as_of_fof}"

    typer.echo()
    typer.echo(
        f"Fetched latest COT (Futures Only / Futures+Options) as-of {merged_as_of}")
    typer.echo(f"NAVE WEEKLY COT REPORT — {now}")
    typer.echo("=" * 68)
    typer.echo(
        f"Capital: ${capital:,.0f} | Philosophy: F.I.T.S. contrarian COT")
    typer.echo(
        f"Data as-of: {data_as_of} (Released: {released_on}) | Cached: {cache_label}")
    typer.echo(f"Report Type: {primary_report_label}")
    typer.echo()

    for coin in coin_list:
        b = biases.get(coin)
        if not b:
            typer.echo(f"  {coin}: no COT data available")
            typer.echo()
            continue
        m = b.metadata
        price = price_context.get(coin, {})
        price_close = price.get("price_close")
        weekly_delta = price.get("weekly_price_delta_pct")
        trend_4h = str(price.get("trend_4h", "unknown"))
        cot_vs_price = _cot_vs_price_action(b.bias, trend_4h)

        arrow = {"bullish": "▲", "bearish": "▼",
                 "neutral": "–"}.get(b.bias, "?")
        vol = m["volatility"]
        direction = "LONG" if b.bias == "bullish" else (
            "SHORT" if b.bias == "bearish" else "FLAT")
        pct_oi_abs = float(m.get("pct_oi", 0.0))
        net_side = "net long" if b.net_non_commercial >= 0 else "net short"
        net_label = f"speculators {_position_intensity(pct_oi_abs)} {net_side}"
        pct_side = m.get("pct_oi_position_side", "net long")
        section_info = cot_sections.get(coin, {})
        futures_only_metrics = section_info.get("futures_only")
        options_metrics = section_info.get("options")
        combined_metrics = section_info.get("combined")
        options_validation = section_info.get("options_validation", {})
        price_line = "N/A"
        if isinstance(price_close, (int, float)):
            if isinstance(weekly_delta, (int, float)):
                price_line = f"~${float(price_close):,.0f} | Weekly Price Δ: {float(weekly_delta):+.1f}%"
            else:
                price_line = f"~${float(price_close):,.0f} | Weekly Price Δ: N/A"

        typer.echo(f"┌─ {coin} {'─' * (50 - len(coin))}")
        typer.echo(
            f"│ Bias: {m.get('bias_label', b.bias.upper())} {arrow} (confidence {b.confidence:.0%})")
        typer.echo(
            f"│ Bias Strength: {m['bias_strength'].upper()} (FITS score {m['fits_weighted_score']}/100)")
        typer.echo(
            f"│ Market Regime (COT flow): {m['market_regime']} | Weekly Vol: {vol:.1%}")
        typer.echo(f"│")
        typer.echo(f"│ Net Non-Comm: {b.net_non_commercial:+,} ({net_label})")
        typer.echo(
            f"│ % of OI: {float(m['pct_oi']):.1f}% ({pct_side} position)")
        typer.echo(f"│ Weekly Δ Non-Comm: {b.weekly_change:+,}")
        typer.echo(f"│ Net Commercial: {b.net_commercial:+,}")
        typer.echo(
            f"│ Open Interest: {b.open_interest:,} (Δ {b.oi_change_pct:+.1f}%)")
        typer.echo(f"│")
        typer.echo("│ FUTURES ONLY")
        for line in _fmt_section_lines(futures_only_metrics):
            typer.echo(f"│ {line}")
        typer.echo("│")
        typer.echo("│ OPTIONS")
        if options_metrics:
            for line in _fmt_section_lines(options_metrics):
                typer.echo(f"│ {line}")
        else:
            reason = options_validation.get(
                "reason", "invalid_derived_options")
            typer.echo(f"│ Options component unavailable ({reason})")
        typer.echo("│")
        typer.echo("│ COMBINED (Futures + Options)")
        for line in _fmt_section_lines(combined_metrics):
            typer.echo(f"│ {line}")
        typer.echo(f"│ Price at report close: {price_line}")
        typer.echo(
            f"│ Historical Context: {m.get('percentile_interpretation', 'N/A')}")
        pct_warn = str(m.get("percentile_warning", "")).strip()
        if pct_warn:
            typer.echo(f"│ Percentile Warning: {pct_warn}")
        if debug:
            typer.echo(
                f"│ Debug Sections: options_valid={bool(options_validation.get('valid', False))} reason={options_validation.get('reason', 'N/A')}"
            )
        typer.echo(f"│")
        typer.echo(
            f"│ COT Interpretation: {m.get('cot_interpretation', 'N/A')}")
        typer.echo(f"│ COT vs Price Action: {cot_vs_price}")
        typer.echo(f"│")
        if b.bias != "neutral":
            if "Divergence detected" in cot_vs_price:
                typer.echo(
                    "│ Recommended setups: Wait for better confluence. High-quality entries only after 4H confirms. Reduce position size."
                )
            else:
                typer.echo(
                    f"│ Recommended setups: {direction} on 4H/1H (Order Blocks, FVG, liquidity sweeps + COT confirmation)"
                )
        else:
            typer.echo(
                f"│ Recommended setups: NEUTRAL — no clear edge, wait or reduce size")
        typer.echo(f"└{'─' * 55}")
        typer.echo()

    # Best asset summary
    ranked = sorted(
        [(c, biases[c]) for c in coin_list if c in biases],
        key=lambda x: x[1].confidence,
        reverse=True,
    )
    if ranked:
        best_coin, best_bias = ranked[0]
        best_m = best_bias.metadata
        best_arrow = {"bullish": "▲", "bearish": "▼",
                      "neutral": "–"}.get(best_bias.bias, "?")
        typer.echo(
            f"Best Edge: {best_coin} {best_m.get('bias_label', best_bias.bias.upper())} {best_arrow} "
            f"({best_bias.confidence:.0%} confidence, {best_m['bias_strength']} strength)"
        )
    typer.echo("=" * 68)
    typer.echo()


if __name__ == "__main__":
    app()
