#!/usr/bin/env python3
"""Run ISM contracting-industry short backtest for Ondo-eligible symbols."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from trading.stocks.short_backtest import ISMShortBacktester  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--snapshot-dir",
        default="stocks_history",
        help="Directory containing ism_*.json monthly snapshots",
    )
    parser.add_argument(
        "--kinds",
        default="manufacturing,services",
        help="Comma-separated ISM kinds to include",
    )
    parser.add_argument("--from", dest="from_month", default=None, help="Start month YYYY-MM")
    parser.add_argument("--to", dest="to_month", default=None, help="End month YYYY-MM")
    parser.add_argument("--min-confidence", type=float, default=0.3)
    parser.add_argument(
        "--min-short-score",
        type=float,
        default=None,
        help="Require short score above this floor; defaults to 0.05 in normal mode.",
    )
    parser.add_argument(
        "--research-mode",
        action="store_true",
        help="Allow explicit relaxed short-score research thresholds.",
    )
    parser.add_argument(
        "--latest-months",
        type=int,
        default=6,
        help="Use the latest N snapshot months when --from is omitted.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Disable the latest-months window and use all matching snapshots.",
    )
    parser.add_argument(
        "--include-non-ondo",
        action="store_true",
        help="Include shorts outside the Ondo v1 universe",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON report")
    parser.add_argument(
        "--output",
        default=None,
        help="Optional path to write JSON report",
    )
    args = parser.parse_args()

    kinds = [part.strip() for part in args.kinds.split(",") if part.strip()]
    backtester = ISMShortBacktester()
    payload = backtester.evaluate(
        snapshot_dir=args.snapshot_dir,
        kinds=kinds,
        from_month=args.from_month,
        to_month=args.to_month,
        min_confidence=args.min_confidence,
        min_short_score=args.min_short_score,
        research_mode=args.research_mode,
        latest_months=None if args.all else args.latest_months,
        ondo_only=not args.include_non_ondo,
    )

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2))

    if args.json:
        print(json.dumps(payload, indent=2))
        return 0

    summary = payload["summary"]
    print("ISM Ondo short backtest")
    print(
        "Window: "
        f"{payload['lookback']['from_month']} -> {payload['lookback']['to_month']} "
        f"(latest_months={payload['lookback']['latest_months']})"
    )
    print(f"Snapshots: {len(payload['snapshots_used'])}")
    print(
        f"Trades: {summary['trade_count']} | "
        f"Win rate: {summary['win_rate']:.1%} | "
        f"Avg return: {summary['avg_return_pct']:.2f}%"
    )
    for kind, stats in payload.get("by_kind", {}).items():
        print(
            f"  {kind}: {stats['trade_count']} trades, "
            f"avg {stats['avg_return_pct']:.2f}%"
        )
    if args.output:
        print(f"Saved: {args.output}")
    else:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        default_out = Path("var/reports/stocks") / f"ism_short_backtest_{ts}.json"
        default_out.parent.mkdir(parents=True, exist_ok=True)
        default_out.write_text(json.dumps(payload, indent=2))
        print(f"Saved: {default_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
