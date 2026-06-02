#!/usr/bin/env python3
"""Backtest monthly S&P 500 options entries over the last year (high-odds / high-return focus)."""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from options.analyzer import OptionsAnalyzer
from options.config import load_options_config
from options.replay import (
    analyze_ticker_at_date,
    bulk_price_history,
    iter_monthly_entry_dates,
    summarize_yearly_backtest,
)
from options.universe import get_sp500_tickers


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=100, help="S&P 500 tickers (100 faster, 200 full)")
    parser.add_argument("--months", type=int, default=12, help="Monthly entry points to replay")
    parser.add_argument("--hold-days", type=int, default=30, help="Days to hold each position")
    parser.add_argument("--workers", type=int, default=3, help="Parallel workers")
    parser.add_argument("--days-to-exp", type=int, default=30, help="Target DTE at entry")
    parser.add_argument("--min-pop", type=float, default=60.0, help="High-odds filter: min PoP")
    parser.add_argument("--max-touch", type=float, default=72.0, help="High-odds filter: max touch %")
    parser.add_argument(
        "--min-return-pct",
        type=float,
        default=40.0,
        help="High-return filter: min % of max profit captured",
    )
    parser.add_argument("--output", type=Path, default=None, help="JSON output path")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    today = datetime.now(timezone.utc).date()
    tickers = list(get_sp500_tickers(args.limit))
    config = load_options_config()

    periods = iter_monthly_entry_dates(months=args.months, hold_days=args.hold_days)
    if not periods:
        raise SystemExit("No monthly entry periods generated.")

    hist_start = periods[0][0]
    print(f"Loading {len(tickers)} tickers, history from {hist_start}...")
    price_history = bulk_price_history(tickers, start=hist_start, end=today)
    print(f"  loaded {len(price_history)} series, {len(periods)} monthly entries")

    all_rows: list[dict] = []
    workers = max(1, min(args.workers, 3))

    for period_idx, (entry_date, exit_date) in enumerate(periods, start=1):
        print(
            f"\n=== Period {period_idx}/{len(periods)}: "
            f"entry {entry_date} → exit {exit_date} ==="
        )

        def _work(symbol: str) -> dict:
            analyzer = OptionsAnalyzer(config=config)
            return analyze_ticker_at_date(
                analyzer,
                symbol,
                entry_date=entry_date,
                exit_date=exit_date,
                days_to_exp=args.days_to_exp,
                price_history=price_history,
            )

        period_rows: list[dict] = []
        if workers == 1:
            for idx, symbol in enumerate(tickers, start=1):
                period_rows.append(_work(symbol))
                if idx % 25 == 0:
                    print(f"  {idx}/{len(tickers)}")
        else:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(_work, s): s for s in tickers}
                done = 0
                for future in as_completed(futures):
                    period_rows.append(future.result())
                    done += 1
                    if done % 25 == 0:
                        print(f"  {done}/{len(tickers)}")

        summary = summarize_yearly_backtest(
            period_rows,
            min_pop=args.min_pop,
            max_touch=args.max_touch,
            min_return_pct=args.min_return_pct,
        )
        ho = summary.get("high_odds") or {}
        print(
            f"  all trades={summary.get('trade_candidates')} "
            f"high_odds={ho.get('trades')} "
            f"ho_win_rate={(ho.get('win_rate') or 0):.1%} "
            f"ho_avg_pnl=${(ho.get('avg_pnl_dollars') or 0):.0f}"
        )
        all_rows.extend(period_rows)

    yearly = summarize_yearly_backtest(
        all_rows,
        min_pop=args.min_pop,
        max_touch=args.max_touch,
        min_return_pct=args.min_return_pct,
    )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "universe": f"sp500_top_{args.limit}",
        "months": args.months,
        "hold_days": args.hold_days,
        "periods": [
            {"entry_date": e.isoformat(), "exit_date": x.isoformat()}
            for e, x in periods
        ],
        "summary": yearly,
        "rows": all_rows,
    }

    out = args.output
    if out is None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out = Path("docs/analysis/raw") / f"options_yearly_{ts}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nWrote {out}")

    print("\n=== Year summary (all trades) ===")
    print(
        f"  trades={yearly.get('trade_candidates')} "
        f"win_rate={yearly.get('win_rate', 0):.1%} "
        f"avg_pnl=${yearly.get('avg_pnl_dollars', 0):.0f}"
    )
    ho = yearly.get("high_odds") or {}
    print("\n=== High odds (PoP>=%s, touch<%s) ===" % (args.min_pop, args.max_touch))
    print(
        f"  trades={ho.get('trades')} win_rate={ho.get('win_rate', 0):.1%} "
        f"avg_pnl=${ho.get('avg_pnl_dollars', 0):.0f}"
    )
    print("\n=== Top tickers (high-odds, 2+ trades) ===")
    for item in (yearly.get("ticker_leaderboard") or [])[:10]:
        print(
            f"  {item['ticker']}: win_rate={item['win_rate']:.1%} "
            f"trades={item['trades']} total_pnl=${item['total_pnl']:.0f}"
        )
    print("\n=== Best high-odds + high-return examples ===")
    for ex in (yearly.get("high_odds_high_return") or {}).get("examples") or []:
        print(
            f"  {ex.get('entry_date')} {ex.get('ticker')} {ex.get('strategy')} "
            f"pop={ex.get('pop'):.0f}% ret={ex.get('return_pct'):.0f}% "
            f"pnl=${ex.get('pnl_dollars'):.0f}"
        )


if __name__ == "__main__":
    main()