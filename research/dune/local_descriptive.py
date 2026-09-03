"""Descriptive summaries from acquired local slices; never optimizes a rule."""

from __future__ import annotations

import argparse
import json
import statistics
from datetime import timedelta
from pathlib import Path

from research.dune.efficient import read_json_rows
from research.dune.panel import parse_ts


def quantiles(values):
    if not values:
        return {}
    values = sorted(values)
    return {f"p{p}": values[min(len(values) - 1, int((p / 100) * (len(values) - 1)))] for p in (50, 75, 90, 95, 99)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="data/research/dune")
    args = parser.parse_args()
    root = Path(args.root)
    raw = root / "raw/2026-08-27"
    panel = read_json_rows(raw / "token_panel_1000.json")
    returns = [
        row["high_price_60m_usd"] / row["open_price_60m_usd"] - 1
        for row in panel
        if row.get("high_price_60m_usd") and row.get("open_price_60m_usd") and row["open_price_60m_usd"] > 0
    ]
    pump_rows = read_json_rows(raw / "pumpfun_first_hour_7_migrated.json")
    swap_rows = read_json_rows(raw / "pumpswap_7_migrated.json")
    launches = {row["mint"]: parse_ts(row["launch_ts"]) for row in read_json_rows(raw / "launches.json")}
    post_marks = {}
    for mint in {row["mint"] for row in read_json_rows(raw / "migrations_1000.json")}:
        rows = [row for row in swap_rows if row.get("mint") == mint]
        rows = [(parse_ts(row.get("event_time")), (float(row.get("amount_usd")) / float(row.get("token_amount"))) if row.get("amount_usd") and row.get("token_amount") else None) for row in rows]
        marks = {}
        for label, seconds in (("4h", 14400), ("24h", 86400), ("48h", 172800), ("72h", 259200)):
            target = launches[mint] + timedelta(seconds=seconds)
            candidates = [(abs((ts - target).total_seconds()), price) for ts, price in rows if ts and price and abs((ts - target).total_seconds()) <= 300]
            marks[label] = min(candidates)[1] if candidates else None
        post_marks[mint] = marks
    summary = {
        "status": "DESCRIPTIVE_ONLY_NO_EDGE_CLAIM",
        "sample": {"eligible_launches": len(panel), "price_return_rows": len(returns), "first_hour_trade_coverage": sum((r.get("trade_count_60m") or 0) > 0 for r in panel)},
        "max_mark_return_within_60m_proxy": {
            "definition": "high_price_60m_usd / open_price_60m_usd - 1; mark proxy, not executable return",
            "median": statistics.median(returns) if returns else None,
            "mean": statistics.mean(returns) if returns else None,
            "quantiles": quantiles(returns),
            "threshold_counts": {"100pct": sum(x >= 1 for x in returns), "200pct": sum(x >= 2 for x in returns), "500pct": sum(x >= 5 for x in returns)},
        },
        "migrated_postmigration_marks": {
            "tokens": len(post_marks),
            "resolved": {h: sum(mark[h] is not None for mark in post_marks.values()) for h in ("4h", "24h", "48h", "72h")},
            "scope": "PumpSwap-only marks for seven migrated sample mints; not a representative graduation cohort.",
        },
        "trajectory_families": "Not classified: one calendar day and only seven long-horizon migrated examples are insufficient for stable FAST_BURST/FALSE_RUNNER/SUSTAINED_RUNNER/DEAD_SLOW_BLEED claims.",
        "participant_presence_above_token_features": "Not tested; participant data is targeted and identity-independent labels are unavailable.",
    }
    (root / "local_descriptive.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
