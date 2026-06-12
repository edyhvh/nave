"""COT command group for Nave CLI."""

from __future__ import annotations

import logging as _logging
from datetime import date as _date
from datetime import datetime as _dt
from datetime import timedelta as _timedelta
from datetime import timezone as _timezone

import typer

from cli.professional_typer import ProfessionalTyper
from core.config import CliDefaults
from trading.crypto.client import HyperliquidClient
from trading.crypto.cot.cot_analyzer import COTAnalyzer
from trading.crypto.cot.cot_fetcher import build_cot_sections_from_datasets, fetch_latest_cot
from trading.crypto.cot.cot_report_generator import COTReportGenerator

DEFAULTS = CliDefaults.from_env()

cot_app = ProfessionalTyper(help="COT specific commands")


@cot_app.command("analyze")
def analyze_cot(coins: str = typer.Option(DEFAULTS.coins, help="Coins to analyze")) -> None:
    """Analyze COT data as weekly context (contrarian + confirmation)."""
    import subprocess
    import sys

    typer.echo(f"Analyzing COT for {coins}...")
    subprocess.run([sys.executable, "-m", "trading.crypto.cot.cot_analyzer"], check=False)


def _parse_date(value: str) -> _date | None:
    dt = (
        _dt.fromisoformat(str(value)) if "T" in str(value) else _dt.strptime(str(value), "%Y-%m-%d")
    )
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
        end_dt = _dt.combine(as_of_date + _timedelta(days=1), _dt.min.time(), tzinfo=_timezone.utc)
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
        by_day = [candle for candle in daily if candle.get("timestamp")]
        by_day.sort(key=lambda item: item["timestamp_ms"])

        report_close = None
        for candle in by_day:
            cdate = candle["timestamp"].date()
            if cdate <= as_of_date:
                report_close = float(candle["close"])

        prev_week_target = as_of_date - _timedelta(days=7)
        prev_week_close = None
        for candle in by_day:
            cdate = candle["timestamp"].date()
            if cdate <= prev_week_target:
                prev_week_close = float(candle["close"])

        weekly_delta = None
        if report_close and prev_week_close:
            weekly_delta = ((report_close - prev_week_close) / prev_week_close) * 100

        trend_4h = "unknown"
        four_h = client.get_historical_candles(
            coin=coin,
            interval="4h",
            start_time_ms=int((end_dt - _timedelta(days=10)).timestamp() * 1000),
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
    return max(16, months * 6 + 4)


@cot_app.command("report")
def cot_report(
    coins: str = typer.Option(DEFAULTS.coins, help="Coins to analyze (space-separated)"),
    capital: float = typer.Option(DEFAULTS.capital_usd, help="Available capital USD"),
    json_out: bool = typer.Option(False, "--json", help="Output as JSON instead of table"),
    debug: bool = typer.Option(False, "--debug-cot", help="Print raw filtered rows for debugging"),
    include_micro: bool = typer.Option(False, "--include-micro", help="Include MICRO contracts"),
    report_type: str = typer.Option(
        "futures_and_options",
        "--report-type",
        help="CFTC report type: futures_only or futures_and_options",
    ),
    cot_history: int | None = typer.Option(
        None,
        "--cot-history",
        help="Generate historical COT variation report for the last N months (1-12)",
    ),
) -> None:
    """Weekly COT report with indicators for manual setup hunting."""
    import json as _json

    if debug:
        _logging.basicConfig(level=_logging.DEBUG, format="%(levelname)s: %(message)s")
    else:
        _logging.basicConfig(level=_logging.INFO, format="%(message)s")

    if report_type not in {"futures_only", "futures_and_options", "legacy_combined"}:
        raise typer.BadParameter(
            "--report-type must be futures_only or futures_and_options (legacy_combined alias supported)"
        )

    if cot_history is not None and not (1 <= cot_history <= 12):
        raise typer.BadParameter("--cot-history must be between 1 and 12")

    primary_report_type = "futures_only" if report_type == "futures_only" else "futures_and_options"
    primary_report_label = (
        "Futures Only" if primary_report_type == "futures_only" else "Futures + Options"
    )

    coin_list = coins.split()
    analyzer = COTAnalyzer()
    report_generator = COTReportGenerator()

    if cot_history is not None:
        history_weeks = _history_weeks_for_months(cot_history)
        historical_data = fetch_latest_cot(
            report_type=primary_report_type,
            include_micro=include_micro,
            debug=debug,
            history_weeks=history_weeks,
        )
        historical_data = {
            coin: historical_data[coin] for coin in coin_list if coin in historical_data
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
        typer.echo(historical.get("markdown", "No historical report output available."))
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
    biases = (
        biases_futures_only if primary_report_type == "futures_only" else biases_futures_and_options
    )

    now = _dt.now().strftime("%Y-%m-%d")
    now_full = _dt.now().strftime("%Y-%m-%d %H:%M")

    cot_sections = build_cot_sections_from_datasets(
        futures_only_data=cot_data_futures_only,
        combined_data=cot_data_futures_and_options,
    )

    price_context: dict[str, dict[str, object]] = {}
    for coin in coin_list:
        bias = biases.get(coin)
        if not bias:
            continue
        as_of_raw = bias.metadata.get("as_of_date", bias.metadata.get("report_date", "N/A"))
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
            bias = biases.get(coin)
            if not bias:
                continue
            metadata = bias.metadata
            payload["coins"][coin] = {
                "bias": bias.bias,
                "confidence": round(bias.confidence, 2),
                "bias_source": primary_report_type,
                "bias_strength": metadata["bias_strength"],
                "fits_score": metadata["fits_weighted_score"],
                "market_regime": metadata["market_regime"],
                "net_non_commercial": bias.net_non_commercial,
                "pct_oi": metadata["pct_oi"],
                "weekly_change": bias.weekly_change,
                "net_commercial": bias.net_commercial,
                "open_interest": bias.open_interest,
                "oi_change_pct": bias.oi_change_pct,
                "historical_percentile": bias.historical_percentile,
                "percentile_interpretation": metadata.get("percentile_interpretation", ""),
                "percentile_warning": metadata.get("percentile_warning", ""),
                "volatility": round(metadata["volatility"], 4),
                "report_date": metadata.get("report_date", "N/A"),
                "as_of_date": metadata.get("as_of_date", "N/A"),
                "release_date": metadata.get("release_date", "N/A"),
                "bias_label": metadata.get("bias_label", bias.bias.upper()),
                "cot_interpretation": metadata.get("cot_interpretation", "N/A"),
                "pct_oi_signed": metadata.get("pct_oi_signed", 0.0),
                "pct_oi_position_side": metadata.get("pct_oi_position_side", "net long"),
                "price_at_report_close": price_context.get(coin, {}).get("price_close"),
                "weekly_price_delta_pct": price_context.get(coin, {}).get("weekly_price_delta_pct"),
                "trend_4h": price_context.get(coin, {}).get("trend_4h", "unknown"),
                "cot_vs_price_action": _cot_vs_price_action(
                    bias.bias,
                    str(price_context.get(coin, {}).get("trend_4h", "unknown")),
                ),
                "cached": metadata.get("cached", False),
                "futures_only": cot_sections.get(coin, {}).get("futures_only"),
                "options": cot_sections.get(coin, {}).get("options"),
                "futures_and_options": cot_sections.get(coin, {}).get("combined"),
                "options_validation": cot_sections.get(coin, {}).get("options_validation"),
            }
        typer.echo(_json.dumps(payload, indent=2))
        return

    any_cached_futures_only = any(
        cot_data_futures_only.get(coin, {}).get("cached", False) for coin in coin_list
    )
    any_cached_futures_and_options = any(
        cot_data_futures_and_options.get(coin, {}).get("cached", False) for coin in coin_list
    )
    cache_label = (
        f"Futures Only: {'YES' if any_cached_futures_only else 'NO'} | "
        f"Futures+Options: {'YES' if any_cached_futures_and_options else 'NO'}"
    )

    as_of_dates = [
        biases[coin].metadata.get("as_of_date", biases[coin].metadata.get("report_date", "N/A"))
        for coin in coin_list
        if coin in biases
    ]
    release_dates = [
        biases[coin].metadata.get("release_date", "N/A") for coin in coin_list if coin in biases
    ]
    data_as_of = as_of_dates[0] if as_of_dates else "N/A"
    released_on = release_dates[0] if release_dates else "N/A"

    as_of_fo = next(
        (
            biases_futures_only[coin].metadata.get(
                "as_of_date", biases_futures_only[coin].metadata.get("report_date", "N/A")
            )
            for coin in coin_list
            if coin in biases_futures_only
        ),
        "N/A",
    )
    as_of_fof = next(
        (
            biases_futures_and_options[coin].metadata.get(
                "as_of_date", biases_futures_and_options[coin].metadata.get("report_date", "N/A")
            )
            for coin in coin_list
            if coin in biases_futures_and_options
        ),
        "N/A",
    )
    merged_as_of = as_of_fo if as_of_fo == as_of_fof else f"{as_of_fo} / {as_of_fof}"

    typer.echo()
    typer.echo(f"Fetched latest COT (Futures Only / Futures+Options) as-of {merged_as_of}")
    typer.echo(f"NAVE WEEKLY COT REPORT — {now}")
    typer.echo("=" * 68)
    typer.echo(f"Capital: ${capital:,.0f} | Philosophy: F.I.T.S. contrarian COT")
    typer.echo(f"Data as-of: {data_as_of} (Released: {released_on}) | Cached: {cache_label}")
    typer.echo(f"Report Type: {primary_report_label}")
    typer.echo()

    for coin in coin_list:
        bias = biases.get(coin)
        if not bias:
            typer.echo(f"  {coin}: no COT data available")
            typer.echo()
            continue

        metadata = bias.metadata
        price = price_context.get(coin, {})
        price_close = price.get("price_close")
        weekly_delta = price.get("weekly_price_delta_pct")
        trend_4h = str(price.get("trend_4h", "unknown"))
        cot_vs_price = _cot_vs_price_action(bias.bias, trend_4h)

        arrow = {"bullish": "▲", "bearish": "▼", "neutral": "–"}.get(bias.bias, "?")
        vol = metadata["volatility"]
        direction = (
            "LONG" if bias.bias == "bullish" else ("SHORT" if bias.bias == "bearish" else "FLAT")
        )
        pct_oi_abs = float(metadata.get("pct_oi", 0.0))
        net_side = "net long" if bias.net_non_commercial >= 0 else "net short"
        net_label = f"speculators {_position_intensity(pct_oi_abs)} {net_side}"
        pct_side = metadata.get("pct_oi_position_side", "net long")
        section_info = cot_sections.get(coin, {})
        futures_only_metrics = section_info.get("futures_only")
        options_metrics = section_info.get("options")
        combined_metrics = section_info.get("combined")
        options_validation = section_info.get("options_validation", {})
        price_line = "N/A"
        if isinstance(price_close, (int, float)):
            if isinstance(weekly_delta, (int, float)):
                price_line = (
                    f"~${float(price_close):,.0f} | Weekly Price Δ: {float(weekly_delta):+.1f}%"
                )
            else:
                price_line = f"~${float(price_close):,.0f} | Weekly Price Δ: N/A"

        typer.echo(f"┌─ {coin} {'─' * (50 - len(coin))}")
        typer.echo(
            f"│ Bias: {metadata.get('bias_label', bias.bias.upper())} {arrow} (confidence {bias.confidence:.0%})"
        )
        typer.echo(
            f"│ Bias Strength: {metadata['bias_strength'].upper()} (FITS score {metadata['fits_weighted_score']}/100)"
        )
        typer.echo(
            f"│ Market Regime (COT flow): {metadata['market_regime']} | Weekly Vol: {vol:.1%}"
        )
        typer.echo("│")
        typer.echo(f"│ Net Non-Comm: {bias.net_non_commercial:+,} ({net_label})")
        typer.echo(f"│ % of OI: {float(metadata['pct_oi']):.1f}% ({pct_side} position)")
        typer.echo(f"│ Weekly Δ Non-Comm: {bias.weekly_change:+,}")
        typer.echo(f"│ Net Commercial: {bias.net_commercial:+,}")
        typer.echo(f"│ Open Interest: {bias.open_interest:,} (Δ {bias.oi_change_pct:+.1f}%)")
        typer.echo("│")
        typer.echo("│ FUTURES ONLY")
        for line in report_generator.format_section_lines(futures_only_metrics):
            typer.echo(f"│ {line}")
        typer.echo("│")
        typer.echo("│ OPTIONS")
        if options_metrics:
            for line in report_generator.format_section_lines(options_metrics):
                typer.echo(f"│ {line}")
        else:
            reason = options_validation.get("reason", "invalid_derived_options")
            typer.echo(f"│ Options component unavailable ({reason})")
        typer.echo("│")
        typer.echo("│ COMBINED (Futures + Options)")
        for line in report_generator.format_section_lines(combined_metrics):
            typer.echo(f"│ {line}")
        typer.echo(f"│ Price at report close: {price_line}")
        typer.echo(f"│ Historical Context: {metadata.get('percentile_interpretation', 'N/A')}")
        pct_warn = str(metadata.get("percentile_warning", "")).strip()
        if pct_warn:
            typer.echo(f"│ Percentile Warning: {pct_warn}")
        if debug:
            typer.echo(
                "│ Debug Sections: "
                f"options_valid={bool(options_validation.get('valid', False))} "
                f"reason={options_validation.get('reason', 'N/A')}"
            )
        typer.echo("│")
        typer.echo(f"│ COT Interpretation: {metadata.get('cot_interpretation', 'N/A')}")
        typer.echo(f"│ COT vs Price Action: {cot_vs_price}")
        typer.echo("│")
        if bias.bias != "neutral":
            if "Divergence detected" in cot_vs_price:
                typer.echo(
                    "│ Recommended setups: Wait for better confluence. "
                    "High-quality entries only after 4H confirms. Reduce position size."
                )
            else:
                typer.echo(
                    "│ Recommended setups: "
                    f"{direction} on 4H/1H (Order Blocks, FVG, liquidity sweeps + COT confirmation)"
                )
        else:
            typer.echo("│ Recommended setups: NEUTRAL — no clear edge, wait or reduce size")
        typer.echo(f"└{'─' * 55}")
        typer.echo()

    ranked = sorted(
        [(coin, biases[coin]) for coin in coin_list if coin in biases],
        key=lambda item: item[1].confidence,
        reverse=True,
    )
    if ranked:
        best_coin, best_bias = ranked[0]
        best_metadata = best_bias.metadata
        best_arrow = {"bullish": "▲", "bearish": "▼", "neutral": "–"}.get(best_bias.bias, "?")
        typer.echo(
            f"Best Edge: {best_coin} {best_metadata.get('bias_label', best_bias.bias.upper())} {best_arrow} "
            f"({best_bias.confidence:.0%} confidence, {best_metadata['bias_strength']} strength)"
        )
    typer.echo("=" * 68)
    typer.echo()
