#!/usr/bin/env python3
"""Full per-ticker strategy iteration loop (replay → walk-forward → registry → gems)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _load_dotenv() -> None:
    env = PROJECT_ROOT / ".env"
    if not env.is_file():
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(env)


def main() -> int:
    _load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backtest",
        action="store_true",
        help="Run fresh options_yearly_backtest first (slow)",
    )
    parser.add_argument("--months", type=int, default=12)
    parser.add_argument("--limit", type=int, default=40, help="Universe size for backtest/gems")
    parser.add_argument("--replay-json", type=Path, default=None)
    parser.add_argument("--registry", type=Path, default=None)
    parser.add_argument("--journal-dir", type=Path, default=None)
    parser.add_argument("--folds", type=int, default=4)
    parser.add_argument("--no-gems", action="store_true")
    parser.add_argument("--gems-top", type=int, default=10)
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()

    scan_fn = None
    if not args.no_gems:
        from options.factory import build_options_analyzer  # noqa: E402
        from options.universe_scan import scan_equity_options_universe  # noqa: E402
        from options.universe import get_sp500_top40

        def scan_fn(
            *,
            tickers: list[str],
            days_to_exp: int = 30,
            top_trades: int = 10,
            workers: int = 2,
        ) -> dict:
            analyzer = build_options_analyzer(source="yfinance")
            return scan_equity_options_universe(
                analyzer=analyzer,
                analyzer_factory=lambda: build_options_analyzer(source="yfinance"),
                tickers=tickers,
                days_to_exp=days_to_exp,
                top_trades=top_trades,
                workers=workers,
            )

    from options.strategy_loop import run_strategy_iteration  # noqa: E402
    from options.universe import get_sp500_top40  # noqa: E402

    tickers = list(get_sp500_top40())[: args.limit]

    print(f"=== Ticker strategy loop ({len(tickers)} names) ===")
    result = run_strategy_iteration(
        tickers=tickers,
        replay_json=args.replay_json,
        run_backtest=args.backtest,
        backtest_months=args.months,
        backtest_limit=args.limit,
        registry_dir=args.registry,
        run_gems=not args.no_gems,
        gems_limit=args.limit,
        gems_top=args.gems_top,
        gems_workers=args.workers,
        journal_dir=args.journal_dir,
        n_folds=args.folds,
        scan_fn=scan_fn,
    )

    print(f"\nReport JSON: {result['report_json']}")
    print(f"Report MD:   {result['report_md']}")
    print(f"\nWalk-forward: {result['walkforward']['with_oos_trades']} tickers with OOS trades")
    for row in (result["walkforward"].get("leaderboard") or [])[:8]:
        wr = row.get("oos_win_rate")
        wr_s = f"{wr:.0%}" if wr is not None else "—"
        print(
            f"  {row['ticker']}: OOS {wr_s} n={row['oos_trades']} "
            f"primary={row.get('last_primary')}"
        )

    hg = (result.get("hidden_gems") or {}).get("hidden_gems") or {}
    gems = hg.get("gems") or []
    print(f"\nGems: {len(gems)} passed filters")
    for g in gems[:5]:
        print(f"  {g['ticker']} score={g['gem_score']} {g.get('strategy')}")

    print("\nNext: nave options registry learn")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
