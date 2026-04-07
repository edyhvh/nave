#!/usr/bin/env python3
"""
Backtest runner for COT strategy.

Usage:
    python run_backtests.py --objective setup-discovery
    python run_backtests.py --objective strategy-validation
    python run_backtests.py --all

This script runs the backtest tests and generates reports.
"""

from trading.utils.clean_backtest_files import clean_backtest_outputs
import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

import pandas as pd

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

ROOT_DIR = Path(__file__).parent.parent.parent


def _write_timestamped_backtest_exports(
    report_text: str,
    patterns: list[dict],
    run_trades: list[Any],
    run_config: dict[str, Any] | None = None,
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
        "run_config": run_config or {},
        "learning_report": report_text,
        "patterns": patterns,
        "trades": trades_payload,
    }
    summary = {
        "generated_at": payload["generated_at"],
        "total_trades": payload["total_trades"],
        "stats": stats,
        "run_config": payload["run_config"],
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


def _build_intraday_price_snapshot(timeframe: str, coins: list[str]) -> tuple[Path, dict[str, Any]]:
    """Build merged coin-aware parquet for MockHyperliquidClient intraday runs."""
    snapshots_dir = ROOT_DIR / "data" / "hyperliquid_snapshots"
    out_path = ROOT_DIR / "tests" / "backtest" / \
        "fixtures" / f"hyperliquid_{timeframe}_merged.parquet"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    frames: list[pd.DataFrame] = []
    coverage: dict[str, Any] = {}

    for coin in coins:
        src = snapshots_dir / f"{coin}_{timeframe}.parquet"
        if not src.exists():
            raise FileNotFoundError(
                f"Missing snapshot file: {src}. Generate snapshots first via scripts/fetch_hyperliquid_snapshots.py"
            )

        df = pd.read_parquet(src)
        if "timestamp" not in df.columns or "close" not in df.columns:
            raise ValueError(
                f"Snapshot file {src} missing required columns timestamp/close")

        coin_df = df.copy()
        coin_df["coin"] = coin
        coin_df["timestamp"] = pd.to_datetime(
            coin_df["timestamp"], utc=True).dt.tz_localize(None)
        coin_df = coin_df[["timestamp", "close", "coin"]].dropna(
            subset=["timestamp", "close"])
        coin_df = coin_df.sort_values("timestamp")
        if coin_df.empty:
            raise ValueError(
                f"Snapshot file {src} is empty after normalization")

        coverage[coin] = {
            "rows": int(len(coin_df)),
            "start": coin_df["timestamp"].iloc[0].isoformat(),
            "end": coin_df["timestamp"].iloc[-1].isoformat(),
        }
        frames.append(coin_df)

    merged = pd.concat(frames, ignore_index=True)
    merged = merged.sort_values(["timestamp", "coin"]).drop_duplicates(
        subset=["timestamp", "coin"])
    merged.to_parquet(out_path, index=False)

    starts = [pd.Timestamp(v["start"]) for v in coverage.values()]
    ends = [pd.Timestamp(v["end"]) for v in coverage.values()]
    overlap_start = max(starts).to_pydatetime()
    overlap_end = min(ends).to_pydatetime()

    meta = {
        "timeframe": timeframe,
        "source": "hyperliquid_snapshots",
        "coins": list(coins),
        "snapshot_file": str(out_path),
        "coin_coverage": coverage,
        "overlap_window": {
            "start": overlap_start.isoformat(),
            "end": overlap_end.isoformat(),
        },
    }
    return out_path, meta


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


def run_setup_learning(timeframe: str = "weekly", capital: float = 2000.0):
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
    price_data_path: str | None = None
    data_source_meta: dict[str, Any] = {"mode": "default_daily_mock"}
    start_date = datetime(2019, 1, 1)
    end_date = datetime(2025, 12, 31)

    if timeframe in {"1h", "4h"}:
        merged_path, snapshot_meta = _build_intraday_price_snapshot(timeframe, [
                                                                    "BTC", "ETH"])
        price_data_path = str(merged_path)
        data_source_meta = snapshot_meta
        overlap_start = datetime.fromisoformat(
            snapshot_meta["overlap_window"]["start"])
        overlap_end = datetime.fromisoformat(
            snapshot_meta["overlap_window"]["end"])
        # For fair comparison across timeframes, use only the overlapping window.
        start_date = overlap_start
        end_date = overlap_end

    engine = BacktestEngine(
        start_date=start_date,
        end_date=end_date,
        initial_capital=capital,
        journal_enabled=True,
        journal=journal,
    )
    strategy = CotWeeklyStrategy(
        client=MockHyperliquidClient(price_data_path=price_data_path),
        cot_fetcher=HistoricalCotFetcher(),
        capital_usd=capital,
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
        run_config={
            "objective": "setup-learning",
            "timeframe": timeframe,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "initial_capital": engine.config.initial_capital,
            "strategy": {
                "capital_usd": strategy.capital_usd,
                "risk_pct": strategy.risk_pct,
                "max_leverage": strategy.max_leverage,
                "leverage_mode": "dynamic_cot_proxy",
                "setup_selection": "ranked",
                "setup_policy": "neutral_data_collection",
                "setups": strategy.setups,
            },
            "data_source": data_source_meta,
        },
    )
    clean_backtest_outputs(
        output_dir=ROOT_DIR / "trade_journal",
        archive_dir=ROOT_DIR / "backtest_archive" / "invalid",
        delete=False,
        verbose=True,
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
        ["python", "-m", "pytest", ".",
            "--html=backtest_report.html", "--self-contained-html"],
        cwd=Path(__file__).parent,
        capture_output=False
    )
    if result.returncode == 0:
        print(
            f"\nReport generated: {Path(__file__).parent / 'backtest_report.html'}")
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
    parser.add_argument("--report", action="store_true",
                        help="Generate HTML report")
    parser.add_argument("--quick", action="store_true",
                        help="Run quick tests only")
    parser.add_argument(
        "--timeframe",
        choices=["weekly", "1h", "4h"],
        default="weekly",
        help="Backtest candle source timeframe for setup-learning objective",
    )
    parser.add_argument(
        "--capital",
        type=float,
        default=2000.0,
        help="Initial capital for setup-learning backtest (default: 2000)",
    )

    args = parser.parse_args()

    if args.report:
        return generate_report()

    if args.objective == "setup-discovery":
        return run_setup_discovery()
    elif args.objective == "strategy-validation":
        return run_strategy_validation()
    elif args.objective == "setup-learning":
        return run_setup_learning(timeframe=args.timeframe, capital=args.capital)
    elif args.all:
        return run_all()
    else:
        print(
            "No objective specified; defaulting to '--objective setup-learning' "
            "to generate backtest exports."
        )
        return run_setup_learning(capital=args.capital if hasattr(args, 'capital') else 2000.0)


if __name__ == "__main__":
    sys.exit(main())
