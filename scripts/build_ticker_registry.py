#!/usr/bin/env python3
"""Build the S&P top-40 per-ticker playbook registry."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from options.ticker_registry import (  # noqa: E402
    DEFAULT_REGISTRY_DIR,
    RegistryPaths,
    build_registry,
)
from options.universe import SP500_TOP_40_TICKERS, get_sp500_top40  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tickers",
        default="",
        help="Comma-separated override (default: top 40)",
    )
    parser.add_argument(
        "--replay-json",
        type=Path,
        default=None,
        help="Yearly replay JSON for setup stats",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Include live options snapshot per ticker (slow)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_REGISTRY_DIR,
        help="Registry output directory",
    )
    args = parser.parse_args()

    if args.tickers.strip():
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    else:
        tickers = list(get_sp500_top40())

    print(f"Building registry for {len(tickers)} tickers → {args.out}")
    result = build_registry(
        tickers,
        paths=RegistryPaths(args.out),
        replay_json=args.replay_json,
        include_live_options=args.live,
    )
    index = result["index"]
    print(f"Wrote {args.out / 'index.json'}")
    for sym in tickers:
        pb = result["profiles"][sym]["playbook"]
        xo = result["profiles"][sym]["x_opinion"] or {}
        ch = result["profiles"][sym].get("congress_holdings") or {}
        print(
            f"  {sym}: bias={pb.get('bias_20d')} setup={pb.get('preferred_setup')} "
            f"x={xo.get('status')} entry={xo.get('entry_zone') or '-'} "
            f"congress={ch.get('proxy_signal', ch.get('status'))}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())