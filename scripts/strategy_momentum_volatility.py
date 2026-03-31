#!/usr/bin/env python3
"""
Momentum + Volatility strategy runner for 1h/4h with liquidity bias.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from trading.strategy import StrategyConfig, build_strategy_signal


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build high-probability momentum+volatility signal with liquidity filter."
    )
    parser.add_argument("--symbol", default="BTC-USD", help="Asset symbol (default: BTC-USD)")
    parser.add_argument("--timeframe", choices=["1h", "4h"], default="1h")
    parser.add_argument("--limit", type=int, default=400, help="Candles to fetch")
    parser.add_argument(
        "--liquidity-pulse",
        type=float,
        required=True,
        help="Normalized liquidity pulse in [-1,1] from your liquidity model.",
    )
    args = parser.parse_args()

    from openbb import obb  # Local import so module can still be imported without OpenBB.

    data = obb.equity.price.historical(
        symbol=args.symbol,
        interval=args.timeframe,
        limit=args.limit,
    )
    signal = build_strategy_signal(
        data,
        liquidity_pulse=args.liquidity_pulse,
        config=StrategyConfig(timeframe=args.timeframe),
    )

    print(
        json.dumps(
            {
                "symbol": args.symbol,
                "timeframe": args.timeframe,
                "signal": signal.__dict__,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
