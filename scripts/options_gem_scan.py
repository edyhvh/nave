#!/usr/bin/env python3
"""Daily hidden-gem options scan — simple structures + cached X interest."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from options.factory import build_options_analyzer  # noqa: E402
from options.gems_pipeline import format_gem_digest, run_hidden_gems_scan  # noqa: E402
from options.universe_scan import scan_equity_options_universe  # noqa: E402
from options.universe import SP500_TOP_100_TICKERS, get_sp500_tickers  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--top", type=int, default=15)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    tickers = (
        list(get_sp500_tickers(args.limit))
        if args.limit > len(SP500_TOP_100_TICKERS)
        else list(SP500_TOP_100_TICKERS[: args.limit])
    )
    analyzer = build_options_analyzer(source="yfinance")
    scan = scan_equity_options_universe(
        analyzer=analyzer,
        analyzer_factory=lambda: build_options_analyzer(source="yfinance"),
        tickers=tickers,
        days_to_exp=30,
        top_trades=args.top,
        workers=args.workers,
    )
    payload = run_hidden_gems_scan(scan, top=args.top, fetch_x_for_top=0)
    gems = payload["hidden_gems"]
    out = args.out or PROJECT_ROOT / "var" / "reports" / f"hidden_gems_{datetime.now(timezone.utc).date().isoformat()}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"Wrote {out}")
    print(format_gem_digest(gems))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
