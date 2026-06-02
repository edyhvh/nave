#!/usr/bin/env python3
"""Spike: do Glassnode on-chain overlays improve nave BTC momentum entries?

Requires Glassnode CLI auth (free Standard + OAuth often works for Basic T1 @ 24h):
  gn login
  # or: export GLASSNODE_API_KEY=...

Fetches a small metric set, aligns to unified-backtest entry dates, and
reports counterfactual filters vs baseline R-multiples.

Usage:
  python scripts/glassnode_position_spike.py
  python scripts/glassnode_position_spike.py --backtest docs/analysis/raw/unified_backtest_20260601T222143Z.json
  python scripts/glassnode_position_spike.py --gn /Users/jhonny/nave/.local/bin/gn --since 2017-01-01
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = PROJECT_ROOT / "var" / "glassnode_cache"
DEFAULT_GN = PROJECT_ROOT / ".local" / "bin" / "gn"

# Basic-tier friendly paths (24h). Confirm with: gn metric list --asset BTC
METRICS = {
    "sopr": "indicators/sopr",
    "exchange_netflow": "transactions/transfers_volume_to_exchanges_sum",
    "price": "market/price_usd_close",
}


@dataclass(frozen=True)
class TradeRow:
    period: str
    side: str
    entry_time: str
    r_multiple: float
    confidence_score: int | None


@dataclass(frozen=True)
class OverlayRule:
    name: str
    description: str

    def blocks(self, side: str, snap: dict[str, float | None]) -> bool:
        sopr = snap.get("sopr")
        netflow = snap.get("exchange_netflow")
        if side == "long":
            if sopr is not None and sopr > 1.02:
                return True
            if netflow is not None and netflow > 0:
                return True
        if side == "short":
            if sopr is not None and sopr < 0.98:
                return True
            if netflow is not None and netflow < 0:
                return True
        return False


RULES = [
    OverlayRule(
        "profit_taking_longs",
        "Block longs when SOPR>1.02 or exchange inflow (netflow>0).",
    ),
    OverlayRule(
        "capitulation_shorts",
        "Block shorts when SOPR<0.98 or exchange outflow (netflow<0).",
    ),
]


def _resolve_gn(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    for candidate in (DEFAULT_GN, Path("gn")):
        if candidate.exists() or candidate == Path("gn"):
            return candidate
    return Path("gn")


def _gn_fetch(
    gn: Path,
    metric_path: str,
    *,
    since: str,
    until: str | None = None,
    interval: str = "24h",
) -> list[dict]:
    cache_key = f"{metric_path.replace('/', '_')}_{since}_{until or 'now'}_{interval}.json"
    cache_path = CACHE_DIR / cache_key
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))

    cmd = [
        str(gn),
        "metric",
        "get",
        metric_path,
        "--asset",
        "BTC",
        "--interval",
        interval,
        "--since",
        since,
        "-o",
        "json",
    ]
    if until:
        cmd.extend(["--until", until])
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "gn metric get failed")

    rows = json.loads(proc.stdout)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(rows), encoding="utf-8")
    return rows


def _series_by_day(rows: list[dict]) -> dict[str, float]:
    out: dict[str, float] = {}
    for row in rows:
        ts = row.get("t")
        val = row.get("v")
        if ts is None or val is None:
            continue
        if isinstance(ts, (int, float)):
            day = datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d")
        else:
            day = str(ts)[:10]
        out[day] = float(val)
    return out


def _load_trades(backtest_path: Path) -> list[TradeRow]:
    payload = json.loads(backtest_path.read_text(encoding="utf-8"))
    periods = payload.get("periods") or {}
    trades: list[TradeRow] = []
    for period_name, period in periods.items():
        results = (period.get("results") or {}).get("BTC") or {}
        for trade in results.get("trades") or []:
            trades.append(
                TradeRow(
                    period=period_name,
                    side=str(trade.get("side") or ""),
                    entry_time=str(trade.get("entry_time") or ""),
                    r_multiple=float(trade.get("r_multiple") or 0.0),
                    confidence_score=trade.get("confidence_score"),
                )
            )
    return trades


def _snapshot_for_entry(
    entry_time: str,
    series: dict[str, dict[str, float]],
) -> dict[str, float | None]:
    day = entry_time[:10]
    return {key: values.get(day) for key, values in series.items()}


def _summarize_bucket(label: str, rows: list[TradeRow]) -> dict:
    if not rows:
        return {"label": label, "count": 0}
    rs = [r.r_multiple for r in rows]
    wins = sum(1 for r in rs if r > 0)
    return {
        "label": label,
        "count": len(rows),
        "win_rate": round(wins / len(rows), 4),
        "avg_r": round(sum(rs) / len(rows), 4),
        "sum_r": round(sum(rs), 4),
    }


def _evaluate_overlay(trades: list[TradeRow], series: dict[str, dict[str, float]], rule: OverlayRule) -> dict:
    kept: list[TradeRow] = []
    blocked: list[TradeRow] = []
    missing: list[TradeRow] = []
    for trade in trades:
        snap = _snapshot_for_entry(trade.entry_time, series)
        if snap.get("sopr") is None and snap.get("exchange_netflow") is None:
            missing.append(trade)
            kept.append(trade)
            continue
        if rule.blocks(trade.side, snap):
            blocked.append(trade)
        else:
            kept.append(trade)
    return {
        "rule": rule.name,
        "description": rule.description,
        "baseline": _summarize_bucket("all_trades", trades),
        "kept": _summarize_bucket("kept", kept),
        "blocked": _summarize_bucket("blocked", blocked),
        "missing_snapshots": len(missing),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backtest",
        type=Path,
        default=PROJECT_ROOT / "docs/analysis/raw/unified_backtest_20260601T222143Z.json",
    )
    parser.add_argument("--gn", default=None, help="Path to gn binary (default: .local/bin/gn or PATH)")
    parser.add_argument("--since", default="2017-01-01")
    parser.add_argument("--until", default=None)
    parser.add_argument("--skip-fetch", action="store_true", help="Use only var/glassnode_cache")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if not args.backtest.exists():
        print(f"Backtest file not found: {args.backtest}", file=sys.stderr)
        return 1

    trades = _load_trades(args.backtest)
    btc_trades = [t for t in trades if t.side in {"long", "short"}]
    print(f"Loaded {len(btc_trades)} BTC trades from {args.backtest.name}")

    gn = _resolve_gn(args.gn)
    series: dict[str, dict[str, float]] = {}
    fetch_errors: list[str] = []

    if not args.skip_fetch:
        for key, path in METRICS.items():
            try:
                rows = _gn_fetch(gn, path, since=args.since, until=args.until)
                series[key] = _series_by_day(rows)
                print(f"  {key}: {len(series[key])} daily points")
            except Exception as exc:
                fetch_errors.append(f"{key}: {exc}")
    else:
        for key in METRICS:
            cache_glob = list(CACHE_DIR.glob(f"{METRICS[key].replace('/', '_')}_{args.since}_*.json"))
            if cache_glob:
                rows = json.loads(cache_glob[0].read_text(encoding="utf-8"))
                series[key] = _series_by_day(rows)
                print(f"  {key}: {len(series[key])} daily points (cache)")

    if fetch_errors and not series:
        print("\nGlassnode fetch failed. Authenticate first:", file=sys.stderr)
        print("  gn login", file=sys.stderr)
        print("  # or export GLASSNODE_API_KEY=...", file=sys.stderr)
        for err in fetch_errors:
            print(f"  - {err}", file=sys.stderr)
        print("\nBaseline trade stats (no on-chain overlay):", file=sys.stderr)
        baseline = _summarize_bucket("all", btc_trades)
        print(json.dumps({"baseline": baseline, "trades": len(btc_trades)}, indent=2))
        return 2

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "trade_count": len(btc_trades),
        "metrics": METRICS,
        "fetch_errors": fetch_errors,
        "overlays": [_evaluate_overlay(btc_trades, series, rule) for rule in RULES],
    }

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("\nOverlay counterfactual (BTC momentum backtest entries)")
        for block in report["overlays"]:
            b = block["baseline"]
            k = block["kept"]
            bl = block["blocked"]
            print(f"\n[{block['rule']}] {block['description']}")
            print(f"  baseline: n={b['count']} win={b.get('win_rate')} avgR={b.get('avg_r')}")
            print(f"  kept:     n={k['count']} win={k.get('win_rate')} avgR={k.get('avg_r')}")
            print(f"  blocked:  n={bl['count']} win={bl.get('win_rate')} avgR={bl.get('avg_r')}")
            if bl["count"] and k["count"]:
                delta = (k.get("avg_r") or 0) - (b.get("avg_r") or 0)
                print(f"  avgR delta (kept - baseline): {delta:+.4f}")

    out_path = PROJECT_ROOT / "docs/analysis/raw" / f"glassnode_spike_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())