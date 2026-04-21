#!/usr/bin/env python3
"""
run_theory_loop — select the next unanalyzed AGENTS.md period and run the
theory backtest entrypoint for it.

This script intentionally stops after a single backtest invocation. The
assistant loop around it is responsible for reading the latest output, applying
one theory improvement, committing, and invoking this script again.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ITERATIONS_DIR = PROJECT_ROOT / "docs" / "analysis" / "iterations"
PERIOD_ORDER = [
    "2017-bull+2018-bear",
    "2019-recovery",
    "2020-covid-crash",
    "2020-recovery+2021-ATH",
    "2022-bear",
    "2023-recovery",
    "2024-ETF-approval",
    "2024-2025-bull",
    "TODAY",
]
PERIOD_PATTERNS = [
    re.compile(r"^\> \*\*Command:\*\* `python scripts/theory_backtest\.py --period (?P<period>[^ ]+) "),
    re.compile(r"^\> \*\*Backtest command:\*\* `python scripts/theory_backtest\.py --period (?P<period>[^ ]+) "),
]


def completed_periods() -> list[str]:
    periods: list[str] = []
    for path in sorted(ITERATIONS_DIR.glob("iter_*.md")):
        for line in path.read_text(encoding="utf-8").splitlines():
            for pattern in PERIOD_PATTERNS:
                match = pattern.match(line)
                if match:
                    periods.append(match.group("period"))
                    break
            else:
                continue
            break
    return periods


def next_period() -> str | None:
    done = set(completed_periods())
    for period in PERIOD_ORDER:
        if period not in done:
            return period
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the next theory backtest period")
    parser.add_argument("--period", help="override auto-selected period")
    args = parser.parse_args()

    period = args.period or next_period()
    if not period:
        print("[loop] all AGENTS.md periods already have iteration files")
        return 0

    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "theory_backtest.py"),
        "--period",
        period,
        "--coins",
        "BTC ETH",
    ]
    print(f"[loop] running next period: {period}")
    print(f"[loop] command: {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=PROJECT_ROOT)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
