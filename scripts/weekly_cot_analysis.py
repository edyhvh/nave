#!/usr/bin/env python3
"""
Weekly COT Analysis - Nave's Sunday trading setup generator.

Analyzes latest COT for BTC/ETH, compares setups per F.I.T.S. + IPDA philosophy,
recommends best asset, capital allocation ($2000 example), leverage, and scans
other Hyperliquid perps.

Usage:
    python scripts/weekly_cot_analysis.py --capital 2000 --paper
    python scripts/weekly_cot_analysis.py --capital 2000 --backtest

Examples:
    nave trading run --paper --strategy cot-weekly
    nave trading run --backtest --strategy cot-weekly
"""
from tests.backtest.utils.backtest_engine import BacktestEngine
from tests.backtest.mocks.mock_hyperliquid import MockHyperliquidClient
from tests.backtest.mocks.mock_cot_fetcher import HistoricalCotFetcher
from trading.utils.clean_backtest_files import clean_backtest_outputs
from trading.strategy import CotWeeklyStrategy
from trading.journal import TradeJournal
from trading.client import HyperliquidClient
from trading.signals import MacroSignalProducer, SignalAggregator
from trading.cot.cot_analyzer import COTAnalyzer
from trading.cot.cot_fetcher import build_cot_sections_from_datasets, fetch_latest_cot
from trading.config import DEFAULT_SETUPS
import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

sys.path.insert(0, str(Path(__file__).parent.parent))


logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def _write_timestamped_backtest_exports(
    report_text: str,
    patterns: list[dict[str, Any]],
    run_trades: list[Any],
) -> tuple[Path, Path]:
    """Persist timestamped learning exports for each generated backtest session."""
    out_dir = Path(__file__).parent.parent / "trade_journal"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    trades_payload = [t.to_dict() for t in run_trades]
    stats = _stats_from_trade_dicts(trades_payload)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "environment": "backtest",
        "total_trades": len(trades_payload),
        "stats": stats,
        "learning_report": report_text,
        "patterns": patterns,
        "trades": trades_payload,
    }
    summary = {
        "generated_at": payload["generated_at"],
        "total_trades": payload["total_trades"],
        "stats": stats,
        "learning_report": report_text,
        "patterns": patterns[:10],
        "sample_recent_trades": payload["trades"][:25],
    }

    snapshot_path = out_dir / f"backtest_snapshot_{stamp}.json"
    summary_path = out_dir / f"backtest_summary_{stamp}.json"
    snapshot_path.write_text(json.dumps(payload, indent=2))
    summary_path.write_text(json.dumps(summary, indent=2))
    return snapshot_path, summary_path


def _stats_from_trade_dicts(trades: list[dict[str, Any]]) -> dict[str, Any]:
    pnls = [float(t.get("pnl_absolute", 0.0) or 0.0) for t in trades]
    wins = sum(1 for p in pnls if p > 0)
    losses = sum(1 for p in pnls if p < 0)
    breakevens = sum(1 for p in pnls if p == 0)
    gross_profit = sum(p for p in pnls if p > 0)
    gross_loss = sum(p for p in pnls if p < 0)
    total = len(pnls)
    return {
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "breakevens": breakevens,
        "win_rate": (wins / total) if total else 0.0,
        "total_pnl": sum(pnls),
        "avg_pnl": (sum(pnls) / total) if total else 0.0,
        "avg_win": (gross_profit / wins) if wins else 0.0,
        "avg_loss": (gross_loss / losses) if losses else 0.0,
        "best_trade": max(pnls) if pnls else 0.0,
        "worst_trade": min(pnls) if pnls else 0.0,
        "profit_factor": (gross_profit / abs(gross_loss)) if gross_loss < 0 else float("inf"),
    }


def scan_hyperliquid_perps(client: HyperliquidClient) -> list:
    """Scan other promising Hyperliquid perps for liquidity, funding, etc."""
    try:
        meta = client.get_meta()
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
                "recommend": asset in ["SOL", "XRP"]  # example
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
    learn: bool = False,
    setups: list[str] | None = None,
    debug_cot: bool = False,
    include_micro: bool = False,
) -> Dict:
    """Main weekly COT analysis and recommendation."""
    active_setups = setups or list(DEFAULT_SETUPS)

    if debug_cot:
        logging.getLogger().setLevel(logging.DEBUG)

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

    def _print_section_block(title: str, section: dict[str, Any] | None) -> None:
        print(f"    {title}")
        if not section:
            print("      Net Non-Comm: N/A (Δ N/A)     | % of OI: N/A")
            print("      Net Commercial: N/A (Δ N/A)")
            print("      Open Interest: N/A (Δ N/A)")
            print("      # Traders: Non-Comm: N/A | Commercial: N/A")
            return
        print(
            f"      Net Non-Comm: {_fmt_signed(section.get('net_non_commercial'))} (Δ {_fmt_signed(section.get('net_non_commercial_delta'))})     | % of OI: {_fmt_pct(section.get('pct_oi'))}"
        )
        print(
            f"      Net Commercial: {_fmt_signed(section.get('net_commercial'))} (Δ {_fmt_signed(section.get('net_commercial_delta'))})"
        )
        print(
            f"      Open Interest: {_fmt_int(section.get('open_interest'))} (Δ {_fmt_signed(section.get('open_interest_delta'))})"
        )
        print(
            f"      # Traders: Non-Comm: {_fmt_int(section.get('traders_non_commercial'))} | Commercial: {_fmt_int(section.get('traders_commercial'))}"
        )

    print("\n" + "="*80)
    print("🚀 NAVE WEEKLY COT ANALYSIS")
    print("="*80)
    print(
        f"Date: {datetime.now().strftime('%Y-%m-%d')} (Sunday analysis of Friday COT)")
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
    setup_learner = None
    learned_patterns = []
    learning_report_text = ""
    export_paths: tuple[Path, Path] | None = None
    if learn:
        setup_learner, learned_patterns, learning_report_text, export_paths = run_setup_learning_pipeline(
            model_path=Path("tests/backtest/artifacts/setup_learner.joblib"),
            setups=active_setups,
            capital_usd=capital_usd,
        )

    analyzer = COTAnalyzer(setups=active_setups, setup_learner=setup_learner)
    biases = analyzer.analyze(cot_data)
    producer = MacroSignalProducer(setup_learner=setup_learner)
    signals = producer.produce({"cot_data": cot_data})

    # Compare BTC vs ETH
    btc_bias = biases.get("BTC")
    eth_bias = biases.get("ETH")
    best_asset = "ETH" if getattr(eth_bias, "confidence", 0) > getattr(
        btc_bias, "confidence", 0) else "BTC"
    best_conf = max(getattr(btc_bias, "confidence", 0.5),
                    getattr(eth_bias, "confidence", 0.5))

    print("COT Bias Summary:")
    for asset, b in biases.items():
        arrow = {"bullish": "▲", "bearish": "▼",
                 "neutral": "–"}.get(b.bias, "?")
        m = b.metadata
        section_info = cot_sections.get(asset, {})
        options_validation = section_info.get("options_validation", {})
        print(
            f"  {asset}: {b.bias.upper()} {arrow} (conf={b.confidence:.0%}, FITS={m['fits_weighted_score']}/100)")
        print(
            f"    Net Non-Comm: {b.net_non_commercial:+,} | Net Comm: {b.net_commercial:+,}")
        print(
            f"    OI: {b.open_interest:,} (Δ {b.oi_change_pct:+.1f}%) | %OI: {m['pct_oi']:+.1f}%")
        print(
            f"    Weekly Δ: {b.weekly_change:+,} | Percentile: {b.historical_percentile}")
        print(f"    → {m.get('percentile_interpretation', 'N/A')}")
        _print_section_block("FUTURES ONLY", section_info.get("futures_only"))
        if section_info.get("options"):
            _print_section_block("OPTIONS", section_info.get("options"))
        else:
            print(
                f"    OPTIONS\n      Options component unavailable ({options_validation.get('reason', 'invalid_derived_options')})"
            )
        _print_section_block(
            "COMBINED (Futures + Options)", section_info.get("combined"))

    print(f"\n🏆 BEST SETUP: {best_asset} (confidence {best_conf:.0%})")
    print("Recommendation: Allocate 100% capital to best setup on 4H/1H timeframe.")

    # Risk & sizing per philosophy
    risk_per_trade = 0.10  # 8-12%
    position_size = capital_usd * 0.8  # example
    leverage = 10 if best_asset == "ETH" else 5
    print(
        f"Capital: ${capital_usd:,} | Risk/trade: {risk_per_trade*100}% | Leverage: {leverage}x")
    print("SL: at invalidation (IPDA mitigation block or FVG)")
    print("TP: confluence zones (00/50 levels + setup confluence)")
    print(f"Setups: {', '.join(active_setups)}")

    # Perps scan
    print("\n🔍 Other Hyperliquid Opportunities:")
    try:
        client = HyperliquidClient(wallet_name=wallet, testnet=True)
        perps = scan_hyperliquid_perps(client)
        for p in perps[:3]:
            print(
                f"  {p['coin']}: mid~${p['mid']:.2f} | liq={p['liquidity_score']:.1f} | funding={p['funding_rate']:.4f}")
    except Exception:
        print("  (Hyperliquid client stub - connect wallet for live scan)")

    agg = SignalAggregator(signals)
    agg.summary()

    report = {
        "best_asset": best_asset,
        "capital_usd": capital_usd,
        "leverage": leverage,
        "recommended_size_usd": position_size,
        "signals": len(signals),
        "dry_run": dry_run,
        "learned_patterns": learned_patterns[:5],
        "learning_enabled": learn,
        "timestamp": datetime.now().isoformat(),
    }

    if setup_learner is not None:
        print()
        print(learning_report_text or setup_learner.generate_report(
            regime="all",
            setups=active_setups,
            patterns=learned_patterns,
        ))
        if export_paths is not None:
            print(
                f"Timestamped exports: {export_paths[0]} | {export_paths[1]}")

    print("\n✅ Report complete. Run with --live for execution (use vault).")
    print("="*80)
    return report


def run_setup_learning_pipeline(
    model_path: Path,
    setups: list[str],
    capital_usd: float,
):
    """Run the full setup-learning pipeline from a lightweight backtest."""
    model_path.parent.mkdir(parents=True, exist_ok=True)
    journal = TradeJournal()
    strategy = CotWeeklyStrategy(
        client=MockHyperliquidClient(),
        cot_fetcher=HistoricalCotFetcher(),
        capital_usd=capital_usd,
        test_mode=True,
        setups=setups,
    )
    engine = BacktestEngine(
        start_date=datetime(2019, 1, 1),
        end_date=datetime(2025, 12, 31),
        initial_capital=capital_usd,
        journal_enabled=True,
        journal=journal,
    )
    result = engine.run(strategy)
    learner = strategy.setup_learner
    learner.save_model(model_path)
    patterns = learner.discover_new_patterns(result)
    report_text = learner.generate_report(
        regime="all", setups=setups, patterns=patterns)
    run_trades = engine.get_journal_trades()
    snapshot_path, summary_path = _write_timestamped_backtest_exports(
        report_text=report_text,
        patterns=patterns,
        run_trades=run_trades,
    )
    clean_backtest_outputs(
        output_dir=Path(__file__).parent.parent / "trade_journal",
        archive_dir=Path(__file__).parent.parent /
        "backtest_archive" / "invalid",
        delete=False,
        verbose=True,
    )
    db_path = getattr(journal.storage, "db_path", "n/a")
    print(f"Backtest journal saved: trades={len(run_trades)} db={db_path}")
    return learner, patterns, report_text, (snapshot_path, summary_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Nave Weekly COT Analysis",
        epilog=(
            "Examples:\n"
            "  nave trading run --paper --strategy cot-weekly\n"
            "  nave trading run --backtest --strategy cot-weekly --learn\n"
            "  python scripts/weekly_cot_analysis.py --paper --capital 2000\n"
            "  python scripts/weekly_cot_analysis.py --backtest --learn --capital 2000"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--capital", type=float,
                        default=2000.0, help="Available capital USD")
    parser.add_argument("--paper", action="store_true",
                        help="Run paper mode analysis (default)")
    parser.add_argument("--backtest", action="store_true",
                        help="Run backtest mode analysis")
    parser.add_argument("--dry-run", action="store_true",
                        help="Force dry-run output mode")
    parser.add_argument("--live", action="store_true",
                        help="Disable dry-run (execution path, use with care)")
    parser.add_argument("--wallet", default="hermes")
    parser.add_argument("--learn", action="store_true",
                        help="Run setup learning from backtest and apply learned setups")
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
    args = parser.parse_args()

    mode = "paper"
    if args.backtest:
        mode = "backtest"

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
        learn=args.learn,
        setups=args.setups,
        debug_cot=args.debug_cot,
        include_micro=args.include_micro,
    )
    print(
        f"\nFinal recommendation: Allocate to {report['best_asset']} with {report['leverage']}x leverage.")
