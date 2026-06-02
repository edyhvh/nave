#!/usr/bin/env python3
"""Run momentum+COT backtests across all AGENTS.md regimes and assess confidence."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from trading.crypto.analysis.backtest import (  # noqa: E402
    HISTORICAL_PERIODS,
    run_all_periods,
    summarize_backtests,
)
from trading.crypto.momentum.workflow import run_period_backtest  # noqa: E402


RAW_DIR = PROJECT_ROOT / "docs" / "analysis" / "raw"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--periods",
        nargs="+",
        default=None,
        help=f"Subset of regimes (default: all {len(HISTORICAL_PERIODS)} historical).",
    )
    parser.add_argument("--symbols", nargs="+", default=["BTC", "ETH"])
    parser.add_argument("--include-today", action="store_true")
    parser.add_argument("--no-write", action="store_true", help="Skip per-period JSON artifacts.")
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Skip baseline comparison pass (~2x faster per period).",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.periods:
        payloads: dict = {}
        for period in args.periods:
            payloads[period] = run_period_backtest(
                period,
                symbols=args.symbols,
                skip_baseline_compare=args.fast,
            )
        summary = summarize_backtests(payloads)
    else:
        summary = run_all_periods(
            symbols=args.symbols,
            include_today=args.include_today,
            write_artifacts=not args.no_write,
            skip_baseline_compare=args.fast,
        )

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = RAW_DIR / f"unified_backtest_{ts}.json"
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(summary, indent=2))
        return 0

    print("Unified momentum backtest (historical COT overlay on post-2022 cache)")
    print(f"Confidence: {summary['confidence'].upper()} — {summary['confidence_reason']}")
    print()
    print(f"{'Period':<28} {'Symbol':<6} {'Trades':>6} {'Win%':>7} {'Exp':>7} {'MaxDD':>7} {'>=8%':>7} {'Cov':>4}")
    for row in summary["rows"]:
        cov = "OK" if row.get("coverage_complete") else "PART"
        print(
            f"{row['period']:<28} {row['symbol']:<6} "
            f"{row['trade_count']:>6} "
            f"{(row['win_rate'] or 0) * 100:>6.1f} "
            f"{row['expectancy'] or 0:>7.2f} "
            f"{row['max_drawdown'] or 0:>7.2f} "
            f"{(row['pct_reaching_8'] or 0) * 100:>6.1f} "
            f"{cov:>4}"
        )
    pooled = summary["pooled"]
    print()
    print(
        f"Pooled: {pooled['trade_count']} trades | "
        f"WR {pooled['win_rate']:.1%} | Exp {pooled['expectancy']:+.2f}R | "
        f"Active regimes {pooled['periods_with_trades']}/{pooled['period_count']}"
    )
    if summary.get("partial_periods"):
        print(f"Partial coverage: {', '.join(summary['partial_periods'])}")
    if summary.get("losing_periods"):
        print(f"Negative-expectancy regimes: {', '.join(summary['losing_periods'])}")
    print(f"\nSaved: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())