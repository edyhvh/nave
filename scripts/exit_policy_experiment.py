#!/usr/bin/env python3
"""A/B exit-policy experiment on identical momentum entries.

The production backtester exits 100% of every position at ``tp2`` (or the
invalidation stop, or a time-based close). This script reuses the *same*
tradeable entries and replays each trade's future path under several exit
policies to measure the earnings impact (expectancy in R) of partial
scale-outs, breakeven stops, and runners.

Usage:
    python scripts/exit_policy_experiment.py --periods 2022-bear 2023-recovery
    python scripts/exit_policy_experiment.py            # all historical periods
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from trading.crypto.momentum import MomentumBacktester, load_momentum_config  # noqa: E402
from trading.crypto.momentum.execution_plan import TradePlan  # noqa: E402
from trading.crypto.momentum.workflow import (  # noqa: E402
    MOMENTUM_PERIOD_ORDER,
    load_symbol_frames,
    resolve_period,
)

HISTORICAL_PERIODS = [p for p in MOMENTUM_PERIOD_ORDER if p != "TODAY"]


@dataclass
class Fill:
    weight: float
    price: float


def _signed_r(side: str, entry: float, exit_price: float, risk: float) -> float:
    if risk <= 0:
        return 0.0
    if side == "long":
        return (exit_price - entry) / risk
    return (entry - exit_price) / risk


def simulate_policy(
    *,
    side: str,
    entry: float,
    stop0: float,
    tp1: float,
    tp2: float,
    tp3: float,
    path: pd.DataFrame,
    max_bars: int,
    policy: str,
) -> float:
    """Return realized R for ``policy`` walking ``path`` once.

    Intrabar ordering is conservative: the active stop is always checked
    before take-profit levels, matching the production simulator.
    """
    risk = abs(entry - stop0)
    if risk <= 0 or path.empty:
        return 0.0

    horizon = path.head(max_bars)

    # (weight, target_price) ladder + whether to move stop to breakeven once the
    # first scale level fills, and whether the final tranche trails.
    if policy == "baseline":
        ladder = [(1.0, tp2)]
        move_be_after = None
        trail_runner = False
    elif policy == "tp1_be_tp2":
        ladder = [(0.5, tp1), (0.5, tp2)]
        move_be_after = 0
        trail_runner = False
    elif policy == "tp1_be_runner":
        ladder = [(0.4, tp1), (0.3, tp2), (0.3, tp3)]
        move_be_after = 0
        trail_runner = True
    elif policy == "tp1_tp2_be":
        ladder = [(0.5, tp1), (0.5, tp3)]
        move_be_after = 0
        trail_runner = False
    else:
        raise ValueError(f"unknown policy: {policy}")

    remaining = 1.0
    realized = 0.0
    next_level = 0
    cur_stop = stop0
    best_price = entry  # for trailing the runner

    def hit_stop(low: float, high: float) -> bool:
        return low <= cur_stop if side == "long" else high >= cur_stop

    def hit_target(low: float, high: float, target: float) -> bool:
        return high >= target if side == "long" else low <= target

    for _, row in horizon.iterrows():
        low = float(row["low"])
        high = float(row["high"])

        # 1) stop check first (conservative)
        if hit_stop(low, high):
            realized += remaining * _signed_r(side, entry, cur_stop, risk)
            remaining = 0.0
            break

        # 2) fill take-profit levels reachable this bar, in ladder order
        while next_level < len(ladder) and hit_target(low, high, ladder[next_level][1]):
            weight, target = ladder[next_level]
            weight = min(weight, remaining)
            realized += weight * _signed_r(side, entry, target, risk)
            remaining -= weight
            next_level += 1
            if move_be_after is not None and next_level > move_be_after:
                cur_stop = entry  # move stop to breakeven after first scale
            if remaining <= 1e-9:
                break

        if remaining <= 1e-9:
            break

        # 3) trail the final runner tranche after the ladder is exhausted
        if trail_runner and next_level >= len(ladder) - 1:
            if side == "long":
                best_price = max(best_price, high)
                cur_stop = max(cur_stop, best_price - risk)
            else:
                best_price = min(best_price, low)
                cur_stop = min(cur_stop, best_price + risk)

    # time-based close on whatever remains
    if remaining > 1e-9:
        last_close = float(horizon["close"].iloc[-1])
        realized += remaining * _signed_r(side, entry, last_close, risk)

    return realized


def _entry_price(plan: TradePlan) -> float:
    return float(plan.entry_zone[-1] if plan.side == "long" else plan.entry_zone[0])


def _metrics(rs: list[float]) -> dict[str, float]:
    if not rs:
        return {"trades": 0, "win_rate": 0.0, "expectancy": 0.0, "total_r": 0.0, "max_dd": 0.0}
    wins = sum(1 for r in rs if r > 0)
    cum = peak = mdd = 0.0
    for r in rs:
        cum += r
        peak = max(peak, cum)
        mdd = min(mdd, cum - peak)
    return {
        "trades": len(rs),
        "win_rate": round(wins / len(rs), 4),
        "expectancy": round(sum(rs) / len(rs), 4),
        "total_r": round(sum(rs), 3),
        "max_dd": round(abs(mdd), 3),
    }


POLICIES = ["baseline", "tp1_be_tp2", "tp1_tp2_be", "tp1_be_runner"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--periods", nargs="+", default=None)
    parser.add_argument("--symbols", nargs="+", default=["BTC", "ETH"])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    periods = args.periods or HISTORICAL_PERIODS
    config = load_momentum_config()
    backtester = MomentumBacktester(config)
    max_bars = config.execution.max_holding_bars

    per_policy: dict[str, list[float]] = {p: [] for p in POLICIES}
    per_period_rows: list[dict] = []

    for period in periods:
        start, end = resolve_period(period)
        period_policy: dict[str, list[float]] = {p: [] for p in POLICIES}
        for symbol in args.symbols:
            try:
                frames = load_symbol_frames(symbol, start, end)
            except Exception as exc:  # noqa: BLE001
                print(f"[skip] {period} {symbol}: {exc}", file=sys.stderr)
                continue
            for plan, future_trigger, base_trade in backtester.iter_entries(
                symbol=f"{symbol}USDT",
                daily_frame=frames["daily"],
                setup_frame=frames["setup"],
                trigger_frame=frames["trigger"],
            ):
                entry = _entry_price(plan)
                for policy in POLICIES:
                    r = simulate_policy(
                        side=plan.side,
                        entry=entry,
                        stop0=plan.invalidation,
                        tp1=plan.tp1,
                        tp2=plan.tp2,
                        tp3=plan.tp3,
                        path=future_trigger,
                        max_bars=max_bars,
                        policy=policy,
                    )
                    per_policy[policy].append(r)
                    period_policy[policy].append(r)
        row = {"period": period}
        for policy in POLICIES:
            m = _metrics(period_policy[policy])
            row[policy] = m
        per_period_rows.append(row)
        n = len(period_policy["baseline"])
        base = _metrics(period_policy["baseline"])["expectancy"]
        print(f"[{period}] {n} entries  baseline_exp={base:+.3f}R", file=sys.stderr)

    summary = {
        "policies": {p: _metrics(per_policy[p]) for p in POLICIES},
        "per_period": per_period_rows,
    }

    if args.json:
        sys.stdout.write(json.dumps(summary, indent=2) + "\n")
        return 0

    print("\n=== Exit policy A/B (identical entries) ===")
    print(f"{'policy':<16}{'trades':>7}{'win%':>8}{'exp(R)':>9}{'totalR':>9}{'maxDD':>8}")
    for policy in POLICIES:
        m = summary["policies"][policy]
        print(
            f"{policy:<16}{m['trades']:>7}{m['win_rate'] * 100:>8.1f}"
            f"{m['expectancy']:>9.3f}{m['total_r']:>9.1f}{m['max_dd']:>8.1f}"
        )
    base_exp = summary["policies"]["baseline"]["expectancy"]
    print(f"\nbaseline expectancy = {base_exp:+.3f}R")
    for policy in POLICIES:
        if policy == "baseline":
            continue
        delta = summary["policies"][policy]["expectancy"] - base_exp
        print(f"  {policy:<16} Δexp = {delta:+.3f}R  ({delta / base_exp * 100:+.1f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
