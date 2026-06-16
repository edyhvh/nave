#!/usr/bin/env python3
"""Evaluate conviction sizing overlays on primary momentum entries.

This is a pure risk-overlay experiment: it reuses existing primary backtest
trades and changes only risk size by score band. Entry selection and exits stay
unchanged, so results isolate whether sizing high-confidence entries improves
capital efficiency.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

RAW_DIR = Path("docs/analysis/raw")
BASE_RISK_PCT = 0.005


@dataclass(frozen=True)
class TradeRow:
    period: str
    symbol: str
    side: str
    r_multiple: float
    confidence_score: int
    entry_time: str


def score_band(score: int) -> str:
    if score >= 95:
        return "95-100"
    if score >= 90:
        return "90-94"
    if score >= 80:
        return "80-89"
    return "<80"


def latest_momentum_artifacts(raw_dir: Path = RAW_DIR) -> list[Path]:
    latest: dict[str, Path] = {}
    for path in sorted(raw_dir.glob("momentum_backtest_*.json")):
        stem = path.stem.replace("momentum_backtest_", "", 1)
        if "_" not in stem:
            continue
        period, _ = stem.rsplit("_", 1)
        latest[period] = path
    return [latest[key] for key in sorted(latest)]


def load_trades(paths: list[Path]) -> list[TradeRow]:
    trades: list[TradeRow] = []
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        period = str(payload.get("period") or path.stem)
        for symbol, result in (payload.get("results") or {}).items():
            for trade in result.get("trades", []):
                trades.append(
                    TradeRow(
                        period=period,
                        symbol=str(trade.get("symbol") or symbol),
                        side=str(trade.get("side") or "unknown"),
                        r_multiple=float(trade.get("r_multiple", 0.0) or 0.0),
                        confidence_score=int(trade.get("confidence_score", 0) or 0),
                        entry_time=str(trade.get("entry_time") or ""),
                    )
                )
    trades.sort(key=lambda trade: trade.entry_time)
    return trades


def policy_flat(score: int) -> float:
    return BASE_RISK_PCT


def policy_proposed(score: int) -> float:
    if score >= 90:
        return 0.0075
    if score >= 78:
        return 0.005
    return 0.003


def policy_conservative(score: int) -> float:
    if score >= 95:
        return 0.0075
    if score >= 90:
        return 0.00625
    if score >= 80:
        return 0.005
    return 0.003


def policy_quality_gate(score: int) -> float:
    if score >= 90:
        return 0.0075
    return 0.0


POLICIES: dict[str, Callable[[int], float]] = {
    "flat_0_5pct": policy_flat,
    "proposed_90plus_0_75pct": policy_proposed,
    "conservative_95plus_0_75pct": policy_conservative,
    "quality_gate_90plus_only": policy_quality_gate,
}


def _max_drawdown(values: list[float]) -> float:
    cumulative = peak = max_dd = 0.0
    for value in values:
        cumulative += value
        peak = max(peak, cumulative)
        max_dd = min(max_dd, cumulative - peak)
    return abs(max_dd)


def _metrics(values: list[float], trades: list[TradeRow]) -> dict[str, Any]:
    active = [(value, trade) for value, trade in zip(values, trades) if value != 0.0]
    if not active:
        return {
            "trades": 0,
            "win_rate": 0.0,
            "avg_weighted_r": 0.0,
            "total_weighted_r": 0.0,
            "max_dd_weighted_r": 0.0,
            "return_pct": 0.0,
            "max_dd_pct": 0.0,
        }
    active_values = [value for value, _ in active]
    wins = sum(1 for value in active_values if value > 0)
    return {
        "trades": len(active_values),
        "win_rate": round(wins / len(active_values), 4),
        "avg_weighted_r": round(sum(active_values) / len(active_values), 4),
        "total_weighted_r": round(sum(active_values), 4),
        "max_dd_weighted_r": round(_max_drawdown(active_values), 4),
        "return_pct": round(sum(value * BASE_RISK_PCT for value in active_values), 4),
        "max_dd_pct": round(_max_drawdown([value * BASE_RISK_PCT for value in active_values]), 4),
    }


def _group_metrics(
    trades: list[TradeRow],
    values: list[float],
    key_fn: Callable[[TradeRow], str],
) -> dict[str, dict[str, Any]]:
    keys = sorted({key_fn(trade) for trade in trades})
    out: dict[str, dict[str, Any]] = {}
    for key in keys:
        sub_trades = [trade for trade in trades if key_fn(trade) == key]
        sub_values = [value for value, trade in zip(values, trades) if key_fn(trade) == key]
        out[key] = _metrics(sub_values, sub_trades)
    return out


def evaluate_policy(trades: list[TradeRow], policy: Callable[[int], float]) -> dict[str, Any]:
    weighted_values: list[float] = []
    risk_pcts: list[float] = []
    for trade in trades:
        risk_pct = policy(trade.confidence_score)
        risk_pcts.append(risk_pct)
        weighted_values.append(trade.r_multiple * (risk_pct / BASE_RISK_PCT))

    active_risks = [risk for risk in risk_pcts if risk > 0]
    return {
        "metrics": _metrics(weighted_values, trades),
        "average_risk_pct": round(sum(active_risks) / len(active_risks), 6) if active_risks else 0.0,
        "by_score_band": _group_metrics(trades, weighted_values, lambda trade: score_band(trade.confidence_score)),
        "by_period": _group_metrics(trades, weighted_values, lambda trade: trade.period),
        "by_symbol": _group_metrics(trades, weighted_values, lambda trade: trade.symbol),
    }


def run(paths: list[Path]) -> dict[str, Any]:
    trades = load_trades(paths)
    policies = {name: evaluate_policy(trades, fn) for name, fn in POLICIES.items()}
    flat = policies["flat_0_5pct"]["metrics"]
    for name, result in policies.items():
        metrics = result["metrics"]
        metrics["delta_return_pct_vs_flat"] = round(
            metrics["return_pct"] - flat["return_pct"], 4
        )
        metrics["delta_max_dd_pct_vs_flat"] = round(
            metrics["max_dd_pct"] - flat["max_dd_pct"], 4
        )
    return {
        "source_artifacts": [str(path) for path in paths],
        "trade_count": len(trades),
        "base_risk_pct": BASE_RISK_PCT,
        "policies": policies,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", nargs="+", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    paths = args.artifacts or latest_momentum_artifacts()
    payload = run(paths)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0

    print("=== Conviction sizing experiment ===")
    print(f"trades: {payload['trade_count']} | base risk: {payload['base_risk_pct']:.2%}")
    print(f"{'policy':<30}{'trades':>8}{'ret%':>10}{'dd%':>10}{'avg risk':>10}")
    for name, result in payload["policies"].items():
        metrics = result["metrics"]
        print(
            f"{name:<30}{metrics['trades']:>8}"
            f"{metrics['return_pct'] * 100:>9.2f}%"
            f"{metrics['max_dd_pct'] * 100:>9.2f}%"
            f"{result['average_risk_pct'] * 100:>9.3f}%"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
