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
import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from trading.config import DEFAULT_SETUPS
from trading.cot.cot_fetcher import fetch_latest_cot
from trading.cot.cot_analyzer import COTAnalyzer
from trading.signals import MacroSignalProducer, SignalAggregator
from trading.client import HyperliquidClient
from trading.journal import TradeJournal
from trading.strategy import CotWeeklyStrategy

from tests.backtest.mocks.mock_cot_fetcher import HistoricalCotFetcher
from tests.backtest.mocks.mock_hyperliquid import MockHyperliquidClient
from tests.backtest.utils.backtest_engine import BacktestEngine

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
) -> Dict:
    """Main weekly COT analysis and recommendation."""
    active_setups = setups or list(DEFAULT_SETUPS)

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
    cot_data = fetch_latest_cot()
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
        print(
            f"  {asset}: {b.bias.upper()} (net={b.net_non_commercial}, conf={b.confidence:.2f})")

    print(f"\n🏆 BEST SETUP: {best_asset} (confidence {best_conf:.2f})")
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
            print(f"Timestamped exports: {export_paths[0]} | {export_paths[1]}")

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
    report_text = learner.generate_report(regime="all", setups=setups, patterns=patterns)
    run_trades = engine.get_journal_trades()
    snapshot_path, summary_path = _write_timestamped_backtest_exports(
        report_text=report_text,
        patterns=patterns,
        run_trades=run_trades,
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
    )
    print(
        f"\nFinal recommendation: Allocate to {report['best_asset']} with {report['leverage']}x leverage.")
