#!/usr/bin/env python3
"""Batch-fetch X posts for all tickers in the top-40 registry."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from options.ticker_registry import DEFAULT_REGISTRY_DIR, RegistryPaths, load_registry  # noqa: E402
from trading.stocks.social_analyzer import analyze_tickers  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_DIR)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--limit", type=int, default=25, help="Posts per ticker")
    parser.add_argument("--batch-size", type=int, default=10)
    args = parser.parse_args()

    loaded = load_registry(RegistryPaths(args.registry))
    if loaded.get("status") != "ok":
        print("Registry missing — run build_ticker_registry.py first", file=sys.stderr)
        return 1

    tickers = list(loaded["index"].get("tickers") or [])
    print(f"Fetching X for {len(tickers)} tickers in batches of {args.batch_size}")

    for i in range(0, len(tickers), args.batch_size):
        batch = tickers[i : i + args.batch_size]
        print(f"  batch {i // args.batch_size + 1}: {', '.join(batch)}")
        try:
            payload = analyze_tickers(batch, days=args.days, limit_per_ticker=args.limit)
            print(f"    posts={payload.get('total_posts')} saved={payload.get('saved_to')}")
        except Exception as exc:  # noqa: BLE001
            print(f"    failed: {exc}")

    print("Done. Re-run: python3 scripts/build_ticker_registry.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())