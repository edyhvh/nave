#!/usr/bin/env python3
"""Pick latest momentum_backtest_* artifact per period and print pooled summary."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from trading.crypto.analysis.backtest import summarize_backtests  # noqa: E402
from trading.crypto.momentum.workflow import MOMENTUM_PERIOD_ORDER  # noqa: E402

RAW = PROJECT_ROOT / "docs" / "analysis" / "raw"


def latest_per_period() -> dict[str, dict]:
    payloads: dict[str, tuple[float, dict]] = {}
    for path in RAW.glob("momentum_backtest_*.json"):
        name = path.stem  # momentum_backtest_2022-bear_20260601T...
        parts = name.replace("momentum_backtest_", "", 1).rsplit("_", 1)
        if len(parts) != 2:
            continue
        period = parts[0]
        try:
            ts = float(parts[1].replace("T", "").replace("Z", ""))
        except ValueError:
            continue
        if period not in payloads or ts > payloads[period][0]:
            payloads[period] = (ts, json.loads(path.read_text()))
    return {period: data for period, (_, data) in payloads.items()}


def main() -> int:
    all_latest = latest_per_period()
    periods = [p for p in MOMENTUM_PERIOD_ORDER if p in all_latest and p != "TODAY"]
    payloads = {p: all_latest[p] for p in periods}
    summary = summarize_backtests(payloads)
    print(f"Artifacts: {len(payloads)} periods from {RAW}")
    print(f"Confidence: {summary['confidence'].upper()} — {summary['confidence_reason']}")
    print()
    for row in summary["rows"]:
        cov = "OK" if row.get("coverage_complete") else "PART"
        print(
            f"{row['period']:<28} {row['symbol']:<6} {row['trade_count']:>4} "
            f"WR={(row['win_rate'] or 0)*100:5.1f}% Exp={row['expectancy'] or 0:+.2f} {cov}"
        )
    p = summary["pooled"]
    print(f"\nPooled: {p['trade_count']} trades WR={p['win_rate']:.1%} Exp={p['expectancy']:+.2f}R")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())