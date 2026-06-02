#!/usr/bin/env python3
"""Replay S&P 500 options recommendations from 1w and 2w ago; mark P/L today."""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

from options.analyzer import OptionsAnalyzer
from options.config import load_options_config
from options.replay import analyze_ticker_at_date, bulk_price_history, summarize_replay_rows
from options.universe import get_sp500_tickers


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=200, help="S&P 500 tickers to scan")
    parser.add_argument("--workers", type=int, default=6, help="Parallel workers")
    parser.add_argument("--days-to-exp", type=int, default=30, help="Target DTE at entry")
    parser.add_argument(
        "--offsets",
        type=str,
        default="7,14",
        help="Comma-separated lookback days (e.g. 7,14)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="JSON output path (default: docs/analysis/raw/options_retro_*.json)",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    offsets = [int(item.strip()) for item in str(args.offsets).split(",") if item.strip()]
    today = datetime.now(timezone.utc).date()
    tickers = list(get_sp500_tickers(args.limit))
    config = load_options_config()

    payload: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "universe": f"sp500_top_{args.limit}",
        "offsets_days": offsets,
        "days_to_exp": args.days_to_exp,
        "windows": {},
    }

    hist_start = today - timedelta(days=max(offsets) + 45)
    print(f"Loading price history for {len(tickers)} tickers...")
    price_history = bulk_price_history(tickers, start=hist_start, end=today)
    print(f"  loaded {len(price_history)} price series")

    for offset in offsets:
        entry_date = today - timedelta(days=offset)
        print(f"\n=== Replay entry {entry_date.isoformat()} ({offset}d ago) ===")
        rows: list[dict] = []

        def _work(symbol: str) -> dict:
            analyzer = OptionsAnalyzer(config=config)
            return analyze_ticker_at_date(
                analyzer,
                symbol,
                entry_date=entry_date,
                days_to_exp=args.days_to_exp,
                exit_date=today,
                price_history=price_history,
            )

        workers = max(1, min(args.workers, len(tickers), 3))
        if workers == 1:
            for idx, symbol in enumerate(tickers, start=1):
                row = _work(symbol)
                rows.append(row)
                if idx % 20 == 0:
                    print(f"  {idx}/{len(tickers)} scanned")
        else:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(_work, symbol): symbol for symbol in tickers}
                done = 0
                for future in as_completed(futures):
                    rows.append(future.result())
                    done += 1
                    if done % 20 == 0:
                        print(f"  {done}/{len(tickers)} scanned")

        summary = summarize_replay_rows(rows)
        payload["windows"][str(offset)] = {
            "entry_date": entry_date.isoformat(),
            "exit_date": today.isoformat(),
            "summary": summary,
            "rows": rows,
        }
        print(
            f"  trades={summary['trade_candidates']} "
            f"wins={summary['wins']} losses={summary['losses']} "
            f"win_rate={summary['win_rate']:.1%} "
            f"avg_pnl=${summary['avg_pnl_dollars']:.0f}"
        )
        print(f"  by_strategy: {summary['by_strategy']}")

    out = args.output
    if out is None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out = Path("docs/analysis/raw") / f"options_retro_{ts}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()