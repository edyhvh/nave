#!/usr/bin/env python3
"""
Backtest runner for COT strategy.

Usage:
    python run_backtests.py --objective setup-discovery
    python run_backtests.py --objective strategy-validation
    python run_backtests.py --all

This script runs the backtest tests and generates reports.
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

ROOT_DIR = Path(__file__).parent.parent.parent


def _write_timestamped_backtest_exports(
    report_text: str,
    patterns: list[dict],
    run_trades: list[Any],
) -> tuple[Path, Path]:
    """Persist timestamped backtest learning exports for later LLM analysis."""

    out_dir = ROOT_DIR / "trade_journal"
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


def run_setup_discovery():
    """Run setup discovery optimization tests."""
    print("=" * 60)
    print("SETUP DISCOVERY OPTIMIZATION")
    print("=" * 60)
    print()
    print("Objective: Find optimal COT signal parameters")
    print()
    
    import subprocess
    result = subprocess.run(
        ["python", "-m", "pytest", "test_setup_discovery.py", "-v", "-s"],
        cwd=Path(__file__).parent,
        capture_output=False
    )
    return result.returncode


def run_strategy_validation():
    """Run full strategy validation tests."""
    print("=" * 60)
    print("STRATEGY VALIDATION")
    print("=" * 60)
    print()
    print("Objective: Validate complete CotWeeklyStrategy")
    print()
    
    import subprocess
    result = subprocess.run(
        ["python", "-m", "pytest", "test_strategy.py", "-v", "-s"],
        cwd=Path(__file__).parent,
        capture_output=False
    )
    return result.returncode


def run_setup_learning():
    """Run backtest → learn setups → discover patterns pipeline."""
    print("=" * 60)
    print("SETUP LEARNING PIPELINE")
    print("=" * 60)
    print()
    print("Objective: Learn setup rankings and discover new pattern clusters")
    print()

    from trading.strategy import CotWeeklyStrategy
    from trading.journal import TradeJournal
    from tests.backtest.mocks.mock_hyperliquid import MockHyperliquidClient
    from tests.backtest.mocks.mock_cot_fetcher import HistoricalCotFetcher
    from tests.backtest.utils.backtest_engine import BacktestEngine

    model_path = Path(__file__).parent / "artifacts" / "setup_learner.joblib"
    journal = TradeJournal()
    engine = BacktestEngine(
        start_date=datetime(2023, 1, 1),
        end_date=datetime(2024, 12, 31),
        initial_capital=10000.0,
        journal_enabled=True,
        journal=journal,
    )
    strategy = CotWeeklyStrategy(
        client=MockHyperliquidClient(),
        cot_fetcher=HistoricalCotFetcher(),
        test_mode=True,
    )
    result = engine.run(strategy)
    learner = strategy.setup_learner
    learner.save_model(model_path)
    patterns = learner.discover_new_patterns(result)
    report = learner.generate_report(regime="all", patterns=patterns)
    print(report)
    run_trades = engine.get_journal_trades()
    snapshot_path, summary_path = _write_timestamped_backtest_exports(
        report_text=report,
        patterns=patterns,
        run_trades=run_trades,
    )
    db_path = getattr(journal.storage, "db_path", "n/a")
    print(
        f"\nBacktest journal saved: trades={len(run_trades)} "
        f"db={db_path}"
    )
    print(f"Timestamped exports: {snapshot_path} | {summary_path}")
    print(f"\nSaved model: {model_path}")
    return 0


def run_all():
    """Run all backtest tests."""
    print("=" * 60)
    print("COMPLETE BACKTEST SUITE")
    print("=" * 60)
    print()
    
    import subprocess
    result = subprocess.run(
        ["python", "-m", "pytest", ".", "-v", "--tb=short"],
        cwd=Path(__file__).parent,
        capture_output=False
    )
    return result.returncode


def generate_report():
    """Generate HTML report from test results."""
    import subprocess
    result = subprocess.run(
        ["python", "-m", "pytest", ".", "--html=backtest_report.html", "--self-contained-html"],
        cwd=Path(__file__).parent,
        capture_output=False
    )
    if result.returncode == 0:
        print(f"\nReport generated: {Path(__file__).parent / 'backtest_report.html'}")
    else:
        print("\nReport generation failed (missing pytest-html plugin?)")
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description="Run COT strategy backtests")
    parser.add_argument(
        "--objective",
        choices=["setup-discovery", "strategy-validation", "setup-learning"],
        help="Which objective to run"
    )
    parser.add_argument("--all", action="store_true", help="Run all tests")
    parser.add_argument("--report", action="store_true", help="Generate HTML report")
    parser.add_argument("--quick", action="store_true", help="Run quick tests only")
    
    args = parser.parse_args()
    
    if args.report:
        return generate_report()
    
    if args.objective == "setup-discovery":
        return run_setup_discovery()
    elif args.objective == "strategy-validation":
        return run_strategy_validation()
    elif args.objective == "setup-learning":
        return run_setup_learning()
    elif args.all:
        return run_all()
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
