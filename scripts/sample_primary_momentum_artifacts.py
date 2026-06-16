#!/usr/bin/env python3
"""Generate sampled primary momentum trade artifacts for sizing research."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from trading.crypto.momentum import MomentumBacktester, load_momentum_config  # noqa: E402
from trading.crypto.momentum.workflow import (  # noqa: E402
    MOMENTUM_PERIOD_ORDER,
    load_symbol_frames,
    resolve_period,
)

RAW_DIR = PROJECT_ROOT / "docs" / "analysis" / "raw"
HISTORICAL_PERIODS = [period for period in MOMENTUM_PERIOD_ORDER if period != "TODAY"]


def _metrics(trades: list[dict[str, Any]]) -> dict[str, float]:
    if not trades:
        return {"win_rate": 0.0, "expectancy": 0.0, "max_drawdown": 0.0}
    wins = sum(1 for trade in trades if float(trade.get("r_multiple", 0.0)) > 0)
    cumulative = peak = max_dd = 0.0
    for trade in trades:
        cumulative += float(trade.get("r_multiple", 0.0))
        peak = max(peak, cumulative)
        max_dd = min(max_dd, cumulative - peak)
    return {
        "win_rate": round(wins / len(trades), 4),
        "expectancy": round(sum(float(t.get("r_multiple", 0.0)) for t in trades) / len(trades), 4),
        "max_drawdown": round(abs(max_dd), 4),
    }


def run_sampled_period(period: str, symbols: list[str], *, step_bars: int) -> dict[str, Any]:
    start, end = resolve_period(period)
    config = load_momentum_config()
    backtester = MomentumBacktester(config)
    results: dict[str, Any] = {}
    pooled: list[dict[str, Any]] = []
    skipped: dict[str, str] = {}

    for coin in symbols:
        try:
            frames = load_symbol_frames(coin, start, end)
        except Exception as exc:  # noqa: BLE001
            skipped[coin] = str(exc)
            continue
        try:
            payload = backtester.evaluate(
                symbol=f"{coin}USDT",
                daily_frame=frames["daily"],
                setup_frame=frames["setup"],
                trigger_frame=frames["trigger"],
                skip_baseline_compare=True,
                step_bars=step_bars,
            )
        except Exception as exc:  # noqa: BLE001
            skipped[coin] = str(exc)
            continue
        results[coin] = payload
        pooled.extend(payload.get("trades", []))

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "period": period,
        "symbols": symbols,
        "sampled": True,
        "step_bars": step_bars,
        "results": results,
        "pooled": {
            "trade_count": len(pooled),
            "metrics": _metrics(pooled),
        },
        "skipped": skipped,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--periods", nargs="+", default=HISTORICAL_PERIODS)
    parser.add_argument("--symbols", nargs="+", default=["BTC", "ETH"])
    parser.add_argument("--step-bars", type=int, default=24)
    parser.add_argument("--output-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    payloads: dict[str, Any] = {}
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for period in args.periods:
        payload = run_sampled_period(period, [s.upper() for s in args.symbols], step_bars=args.step_bars)
        path = args.output_dir / f"momentum_backtest_{period}_sampled{args.step_bars}_{ts}.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        paths.append(str(path))
        payloads[period] = payload
        print(f"[sampled] {period}: {payload['pooled']['trade_count']} trades -> {path}", file=sys.stderr)

    summary = {"artifacts": paths, "periods": payloads}
    if args.json:
        print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
