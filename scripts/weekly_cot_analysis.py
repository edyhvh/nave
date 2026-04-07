#!/usr/bin/env python3
"""
Weekly COT Analysis - Nave's Sunday trading setup generator.

Analyzes latest COT for BTC/ETH, compares setups per F.I.T.S. + IPDA philosophy,
recommends best asset, capital allocation ($2000 example), leverage, and scans
other Hyperliquid perps.

Usage:
    python scripts/weekly_cot_analysis.py --capital 2000 --paper

Examples:
    nave trading run --paper --strategy cot-weekly
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from trading.client import HyperliquidClient
from trading.signals import MacroSignalProducer, SignalAggregator
from trading.cot.cot_analyzer import COTAnalyzer
from trading.cot.cot_historical_analyzer import COTHistoricalAnalyzer
from trading.cot.cot_position_generator import COTPositionGenerator
from trading.cot.cot_report_generator import COTReportGenerator
from trading.cot.cot_fetcher import build_cot_sections_from_datasets, fetch_latest_cot
from trading.config import DEFAULT_SETUPS

sys.path.insert(0, str(Path(__file__).parent.parent))


logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def _market_structure_4h(
    client: HyperliquidClient,
    coin: str,
    as_of_date: str,
) -> dict[str, Any]:
    """Build a lightweight 4H structure snapshot from real Hyperliquid candles."""
    as_of = datetime.fromisoformat(as_of_date).replace(tzinfo=timezone.utc)
    end_dt = as_of + timedelta(days=1)
    start_dt = end_dt - timedelta(days=10)
    candles = client.get_historical_candles(
        coin=coin,
        interval="4h",
        start_time_ms=int(start_dt.timestamp() * 1000),
        end_time_ms=int(end_dt.timestamp() * 1000),
        max_pages=32,
        throttle_seconds=0,
    )
    if not candles:
        return {
            "trend": "unknown",
            "price": 0.0,
            "swing_high": 0.0,
            "swing_low": 0.0,
            "atr": 1.0,
        }

    closes = [float(c["close"]) for c in candles]
    highs = [float(c["high"]) for c in candles]
    lows = [float(c["low"]) for c in candles]
    trend = "bullish" if closes[-1] >= closes[0] else "bearish"
    atr_window = list(zip(highs[-14:], lows[-14:]))
    atr = sum((high_val - low_val) for high_val, low_val in atr_window) / max(1, len(atr_window))
    return {
        "trend": trend,
        "price": closes[-1],
        "swing_high": max(highs[-18:]),
        "swing_low": min(lows[-18:]),
        "atr": atr,
    }


def scan_hyperliquid_perps(client: HyperliquidClient) -> list:
    """Scan other promising Hyperliquid perps for liquidity, funding, etc."""
    try:
        client.get_meta()
        mids = client.get_all_mids()
        # Simple filter for good opportunities (extensible)
        opportunities = []
        for asset in list(mids.keys())[:10]:  # limit
            if asset in ["BTC", "ETH"]:
                continue
            opp = {
                "coin": asset,
                "mid": float(mids.get(asset, 0)),
                "liquidity_score": 0.7,  # stub
                "funding_rate": 0.001,  # stub
                "recommend": asset in ["SOL", "XRP"],  # example
            }
            opportunities.append(opp)
        return opportunities
    except Exception as e:
        logger.warning("Perps scan failed: %s", e)
        return []


def generate_weekly_report(
    capital_usd: float = 2000,
    dry_run: bool = True,
    mode: str = "paper",
    wallet: str = "hermes",
    setups: list[str] | None = None,
    debug_cot: bool = False,
    include_micro: bool = False,
    cot_history: int | None = None,
) -> dict[str, Any]:
    """Main weekly COT analysis and recommendation."""
    active_setups = setups or list(DEFAULT_SETUPS)

    if debug_cot:
        logging.getLogger().setLevel(logging.DEBUG)

    reporter = COTReportGenerator()

    def _print_section_block(title: str, section: dict[str, Any] | None) -> None:
        print(f"    {title}")
        for line in reporter.format_section_lines(section):
            print(f"      {line}")

    def _history_weeks_for_months(months: int) -> int:
        # Keep enough weekly points to cover month windows plus delta context.
        return max(16, months * 6 + 4)

    if cot_history is not None:
        if not (1 <= cot_history <= 12):
            raise ValueError("cot_history must be between 1 and 12")
        historical_data = fetch_latest_cot(
            report_type="futures_and_options",
            debug=debug_cot,
            include_micro=include_micro,
            history_weeks=_history_weeks_for_months(cot_history),
        )
        historical = COTHistoricalAnalyzer().generate_historical_variation(
            months=cot_history,
            cot_data={k: v for k, v in historical_data.items() if k in {"BTC", "ETH"}},
        )
        historical_markdown = reporter.render_historical_markdown(
            months=cot_history,
            as_of=historical.get("as_of_date", "N/A"),
            per_asset=historical.get("assets", {}),
            observations=historical.get("observations", []),
        )
        print()
        print(historical_markdown)
        print()
        return {
            "report_type": "cot_historical_variation",
            "months": cot_history,
            "as_of_date": historical.get("as_of_date", "N/A"),
            "assets": historical.get("assets", {}),
            "observations": historical.get("observations", []),
            "timestamp": datetime.now().isoformat(),
        }

    print("\n" + "=" * 80)
    print("🚀 NAVE WEEKLY COT ANALYSIS")
    print("=" * 80)
    print(f"Date: {datetime.now().strftime('%Y-%m-%d')} (Sunday analysis of Friday COT)")
    print("Philosophy: F.I.T.S. + IPDA | Commercials move the market | COT-led setup stack")
    print(f"Mode: {mode} | Dry-run: {dry_run}")
    print(f"Configured setups: {', '.join(active_setups)}")
    print()

    # Fetch and analyze COT
    cot_data_futures_only = fetch_latest_cot(
        report_type="futures_only",
        debug=debug_cot,
        include_micro=include_micro,
    )
    cot_data = fetch_latest_cot(
        report_type="futures_and_options",
        debug=debug_cot,
        include_micro=include_micro,
    )
    cot_sections = build_cot_sections_from_datasets(
        futures_only_data=cot_data_futures_only,
        combined_data=cot_data,
    )
    analyzer = COTAnalyzer(setups=active_setups)
    biases = analyzer.analyze(cot_data)
    producer = MacroSignalProducer()
    signals = producer.produce({"cot_data": cot_data})

    # Compare BTC vs ETH
    btc_bias = biases.get("BTC")
    eth_bias = biases.get("ETH")
    best_asset = (
        "ETH" if getattr(eth_bias, "confidence", 0) > getattr(btc_bias, "confidence", 0) else "BTC"
    )
    best_conf = max(getattr(btc_bias, "confidence", 0.5), getattr(eth_bias, "confidence", 0.5))

    print("COT Bias Summary:")
    for asset, b in biases.items():
        arrow = {"bullish": "▲", "bearish": "▼", "neutral": "–"}.get(b.bias, "?")
        m = b.metadata
        section_info = cot_sections.get(asset, {})
        options_validation = section_info.get("options_validation", {})
        print(
            f"  {asset}: {b.bias.upper()} {arrow} (conf={b.confidence:.0%}, FITS={m['fits_weighted_score']}/100)"
        )
        print(f"    Net Non-Comm: {b.net_non_commercial:+,} | Net Comm: {b.net_commercial:+,}")
        print(f"    OI: {b.open_interest:,} (Δ {b.oi_change_pct:+.1f}%) | %OI: {m['pct_oi']:+.1f}%")
        print(f"    Weekly Δ: {b.weekly_change:+,} | Percentile: {b.historical_percentile}")
        print(f"    → {m.get('percentile_interpretation', 'N/A')}")
        _print_section_block("FUTURES ONLY", section_info.get("futures_only"))
        if section_info.get("options"):
            _print_section_block("OPTIONS", section_info.get("options"))
        else:
            print(
                f"    OPTIONS\n      Options component unavailable ({options_validation.get('reason', 'invalid_derived_options')})"
            )
        _print_section_block("COMBINED (Futures + Options)", section_info.get("combined"))

    print(f"\nBEST SETUP: {best_asset} (confidence {best_conf:.0%})")
    print("Recommendation: Allocate 100% capital to best setup on 4H/1H timeframe.")

    # Risk & sizing per philosophy
    risk_per_trade = 0.10  # 8-12%
    position_size = capital_usd * 0.8  # example
    leverage = 10 if best_asset == "ETH" else 5
    print(
        f"Capital: ${capital_usd:,} | Risk/trade: {risk_per_trade * 100}% | Leverage: {leverage}x"
    )
    print("SL: at invalidation (IPDA mitigation block or FVG)")
    print("TP: confluence zones (00/50 levels + setup confluence)")
    print(f"Setups: {', '.join(active_setups)}")

    # Perps scan
    print("\nOther Hyperliquid Opportunities:")
    try:
        client = HyperliquidClient(wallet_name=wallet, testnet=True)
        perps = scan_hyperliquid_perps(client)
        for p in perps[:3]:
            print(
                f"  {p['coin']}: mid~${p['mid']:.2f} | liq={p['liquidity_score']:.1f} | funding={p['funding_rate']:.4f}"
            )
    except Exception:
        print("  (Hyperliquid client stub - connect wallet for live scan)")

    agg = SignalAggregator(signals)
    agg.summary()

    position_generator = COTPositionGenerator(default_risk_pct=0.01)
    market_client = HyperliquidClient(wallet_name=wallet, testnet=True)
    market_data_4h: dict[str, dict[str, Any]] = {}
    for asset, bias in biases.items():
        as_of_date = str(bias.metadata.get("as_of_date") or datetime.now().date().isoformat())
        try:
            market_data_4h[asset] = _market_structure_4h(market_client, asset, as_of_date)
        except Exception as exc:
            logger.warning("4H structure fetch failed for %s: %s", asset, exc)
            market_data_4h[asset] = {
                "trend": "unknown",
                "price": 0.0,
                "swing_high": 0.0,
                "swing_low": 0.0,
                "atr": 1.0,
            }
    weekly_plan = position_generator.generate_weekly_plan(
        cot_data=cot_sections,
        market_data_4h=market_data_4h,
    )

    report: dict[str, Any] = {
        "best_asset": best_asset,
        "capital_usd": capital_usd,
        "leverage": leverage,
        "recommended_size_usd": position_size,
        "signals": len(signals),
        "dry_run": dry_run,
        "weekly_plan": weekly_plan,
        "timestamp": datetime.now().isoformat(),
    }

    print("\n✅ Report complete. Run with --live for execution (use vault).")
    print("=" * 80)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Nave Weekly COT Analysis",
        epilog=(
            "Examples:\n"
            "  nave trading run --paper --strategy cot-weekly\n"
            "  python scripts/weekly_cot_analysis.py --paper --capital 2000\n"
            "  python scripts/weekly_cot_analysis.py --paper --capital 2000 --cot-history 3"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--capital", type=float, default=2000.0, help="Available capital USD")
    parser.add_argument("--paper", action="store_true", help="Run paper mode analysis (default)")
    parser.add_argument("--dry-run", action="store_true", help="Force dry-run output mode")
    parser.add_argument(
        "--live", action="store_true", help="Disable dry-run (execution path, use with care)"
    )
    parser.add_argument("--wallet", default="hermes")
    parser.add_argument(
        "--setups",
        nargs="+",
        default=None,
        help="Override setup list (defaults to trading.config.DEFAULT_SETUPS)",
    )
    parser.add_argument(
        "--debug-cot",
        action="store_true",
        help="Print raw filtered DataFrame rows and debug COT data",
    )
    parser.add_argument(
        "--include-micro",
        action="store_true",
        help="Include MICRO contracts in COT filter",
    )
    parser.add_argument(
        "--cot-history",
        type=int,
        default=None,
        help="Generate historical variation report for the last N calendar months (1-12)",
    )
    args = parser.parse_args()

    mode = "paper"

    dry_run = True
    if args.live:
        dry_run = False
    elif args.dry_run:
        dry_run = True

    report = generate_weekly_report(
        capital_usd=args.capital,
        dry_run=dry_run,
        mode=mode,
        wallet=args.wallet,
        setups=args.setups,
        debug_cot=args.debug_cot,
        include_micro=args.include_micro,
        cot_history=args.cot_history,
    )
    if report.get("report_type") == "cot_historical_variation":
        print(
            f"\nHistorical report complete (last {report.get('months')} months, as-of {report.get('as_of_date')})."
        )
    else:
        print(
            f"\nFinal recommendation: Allocate to {report['best_asset']} with {report['leverage']}x leverage."
        )
