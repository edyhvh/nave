#!/usr/bin/env python3
"""Select the next unanalyzed regime and run the momentum backtest once.

This intentionally performs a single period run. The refinement loop around it
is responsible for reading the output, changing one strategy parameter or rule,
and invoking the script again.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from trading.crypto.momentum.workflow import next_period


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the next momentum backtest period")
    parser.add_argument("--period", help="override auto-selected period")
    parser.add_argument("--trigger-timeframe", default="1H", help="1H or 15m")
    args = parser.parse_args()

    period = args.period or next_period()
    if not period:
        print("[loop] all momentum periods already have iteration files")
        return 0

    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "momentum_backtest.py"),
        "--period",
        period,
        "--symbols",
        "BTC",
        "ETH",
        "--trigger-timeframe",
        args.trigger_timeframe,
    ]
    print(f"[loop] running next momentum period: {period}")
    print(f"[loop] command: {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=PROJECT_ROOT)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())