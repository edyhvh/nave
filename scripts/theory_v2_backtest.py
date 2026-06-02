#!/usr/bin/env python3
"""
theory_v2_backtest — re-run the AGENTS.md period list against the refined
``TheoryV2Engine`` (with the iter 4 / iter 5 / iter 6 gates active) and
compare aggregate edge to the baseline numbers in
``docs/analysis/btc_eth_historical_review.md``.

Usage:
    python scripts/theory_v2_backtest.py [--coins BTC ETH]

Output is printed and also written to
``docs/analysis/raw/theory_v2_validation_{ts}.json``.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import data_loader  # noqa: E402
from data_loader import DataNotFoundError  # noqa: E402

from trading.crypto.cot.cot_gate import load_cached_cot_history  # noqa: E402
from trading.crypto.theory_v2 import TheoryV2Engine  # noqa: E402


PERIODS: dict[str, tuple[str, str]] = {
    "2017-bull+2018-bear": ("2017-01-01", "2018-12-31"),
    "2019-recovery": ("2019-01-01", "2019-12-31"),
    "2020-covid-crash": ("2020-01-01", "2020-06-30"),
    "2020-recovery+2021-ATH": ("2020-07-01", "2021-12-31"),
    "2022-bear": ("2022-01-01", "2022-12-31"),
    "2023-recovery": ("2023-01-01", "2023-12-31"),
    "2024-ETF-approval": ("2024-01-01", "2024-06-30"),
    "2024-2025-bull": ("2024-07-01", "2025-03-31"),
}


def _resolve_outcome(
    h1_forward: pd.DataFrame,
    direction: str,
    entry: float,
    sl: float,
    tp: float,
) -> str | None:
    """Legacy single-target resolver (kept for compatibility)."""
    if h1_forward.empty:
        return None
    for _, row in h1_forward.iterrows():
        high = float(row["high"])
        low = float(row["low"])
        if direction == "long":
            if low <= sl:
                return "incorrect"
            if high >= tp:
                return "correct"
        else:
            if high >= sl:
                return "incorrect"
            if low <= tp:
                return "correct"
    return None


def _resolve_zc_outcome(
    h1_forward: pd.DataFrame,
    direction: str,
    entry: float,
    sl: float,
    targets: list[float],
) -> tuple[str | None, float]:
    """ZC1/ZC2 partial-exit resolver.

    Simulates:
      - 80% closed at ZC1 (targets[0])
      - 20% trails with stop moved to breakeven after ZC1 hit
      - If ZC2 (targets[1]) reached, full exit

    Returns (outcome, pnl_in_R) where pnl is the total R-multiple earned.
    """
    if h1_forward.empty or not targets:
        return None, 0.0

    risk = abs(entry - sl)
    if risk <= 0:
        return None, 0.0

    zc1 = targets[0]
    zc2 = targets[1] if len(targets) > 1 else zc1

    zc1_hit = False
    trail_sl = sl  # trailing stop for the remaining 20%

    for _, row in h1_forward.iterrows():
        high = float(row["high"])
        low = float(row["low"])

        if direction == "long":
            # Check stop first
            if not zc1_hit and low <= sl:
                return "incorrect", -1.0
            if zc1_hit and low <= trail_sl:
                # 80% already banked at ZC1, 20% stopped at breakeven or trail
                zc1_reward = (zc1 - entry) / risk
                trail_reward = (trail_sl - entry) / risk
                total = 0.8 * zc1_reward + 0.2 * trail_reward
                return "correct", total

            # Check ZC1
            if not zc1_hit and high >= zc1:
                zc1_hit = True
                trail_sl = entry  # move stop to breakeven for remaining 20%

            # Check ZC2
            if zc1_hit and high >= zc2:
                zc1_reward = (zc1 - entry) / risk
                zc2_reward = (zc2 - entry) / risk
                total = 0.8 * zc1_reward + 0.2 * zc2_reward
                return "correct", total
        else:
            # Short direction
            if not zc1_hit and high >= sl:
                return "incorrect", -1.0
            if zc1_hit and high >= trail_sl:
                zc1_reward = (entry - zc1) / risk
                trail_reward = (entry - trail_sl) / risk
                total = 0.8 * zc1_reward + 0.2 * trail_reward
                return "correct", total

            if not zc1_hit and low <= zc1:
                zc1_hit = True
                trail_sl = entry

            if zc1_hit and low <= zc2:
                zc1_reward = (entry - zc1) / risk
                zc2_reward = (entry - zc2) / risk
                total = 0.8 * zc1_reward + 0.2 * zc2_reward
                return "correct", total

    # Unresolved — if ZC1 was hit, count partial profit
    if zc1_hit:
        zc1_reward = abs(zc1 - entry) / risk
        # Use last close for the trailing portion
        last_close = float(h1_forward["close"].iloc[-1])
        if direction == "long":
            trail_reward = (last_close - entry) / risk
        else:
            trail_reward = (entry - last_close) / risk
        total = 0.8 * zc1_reward + 0.2 * trail_reward
        return "correct", total
    return None, 0.0


def _walk_period(
    coin: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    engine: TheoryV2Engine,
) -> dict[str, Any]:
    try:
        weekly_full = data_loader.load(coin, "1W", start - pd.Timedelta(days=120), end)
        daily_full = data_loader.load(coin, "1D", start - pd.Timedelta(days=120), end)
        h4_full = data_loader.load(coin, "4H", start - pd.Timedelta(days=60), end)
        h1_full = data_loader.load(coin, "1H", start - pd.Timedelta(days=60), end + pd.Timedelta(days=14))
    except DataNotFoundError as exc:
        return {"skipped": True, "reason": str(exc)}

    stats = {
        "fired": 0,
        "correct": 0,
        "incorrect": 0,
        "unresolved": 0,
        "total_r": 0.0,
        "stage_counts": {},
        "rejected_by": {},
    }

    weeks = pd.date_range(start=start, end=end, freq="W-MON", tz="UTC")
    for week_start in weeks:
        weekly_slice = weekly_full[weekly_full["timestamp"] <= week_start]
        daily_slice = daily_full[daily_full["timestamp"] <= week_start]
        h4_slice = h4_full[h4_full["timestamp"] <= week_start]
        h1_slice = h1_full[h1_full["timestamp"] <= week_start]
        decision = engine.evaluate(
            coin, weekly_slice, daily_slice, h4_slice, h1_slice, as_of=week_start
        )
        stats["stage_counts"][decision.stage] = stats["stage_counts"].get(decision.stage, 0) + 1

        if decision.signal is None:
            stats["rejected_by"][decision.stage] = stats["rejected_by"].get(decision.stage, 0) + 1
            continue

        sig = decision.signal
        entry = float(sig.metadata["entry_price"])
        sl = float(sig.invalidation)
        targets = [float(t) for t in sig.targets]
        direction = sig.direction.value

        forward = h1_full[
            (h1_full["timestamp"] > week_start)
            & (h1_full["timestamp"] <= week_start + pd.Timedelta(days=14))
        ]
        outcome, pnl_r = _resolve_zc_outcome(forward, direction, entry, sl, targets)
        stats["fired"] += 1
        stats["total_r"] += pnl_r
        if outcome == "correct":
            stats["correct"] += 1
        elif outcome == "incorrect":
            stats["incorrect"] += 1
        else:
            stats["unresolved"] += 1

    return stats


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--coins", nargs="+", default=["BTC", "ETH"])
    args = parser.parse_args()

    btc_cot_history = load_cached_cot_history("BTC")

    def _cot_provider(_coin: str, _as_of: pd.Timestamp) -> pd.DataFrame:
        return btc_cot_history

    engine = TheoryV2Engine(cot_history_fn=_cot_provider)
    print(
        f"Loaded BTC COT history: {len(btc_cot_history)} rows "
        f"({btc_cot_history['report_date'].min() if not btc_cot_history.empty else 'n/a'} "
        f"→ {btc_cot_history['report_date'].max() if not btc_cot_history.empty else 'n/a'})"
    )
    results: dict[str, dict[str, Any]] = {}
    pooled = {coin: {"fired": 0, "correct": 0, "incorrect": 0, "unresolved": 0, "total_r": 0.0}
              for coin in args.coins}
    pooled_stages: dict[str, dict[str, int]] = {coin: {} for coin in args.coins}

    for period, (s_str, e_str) in PERIODS.items():
        start = pd.Timestamp(s_str, tz="UTC")
        end = pd.Timestamp(e_str, tz="UTC")
        results[period] = {}
        for coin in args.coins:
            stats = _walk_period(coin, start, end, engine)
            results[period][coin] = stats
            if stats.get("skipped"):
                print(f"[{period}] {coin}: SKIPPED — {stats['reason'][:80]}")
                continue
            for k in ("fired", "correct", "incorrect", "unresolved", "total_r"):
                pooled[coin][k] += stats.get(k, 0)
            for stage, n in stats.get("stage_counts", {}).items():
                pooled_stages[coin][stage] = pooled_stages[coin].get(stage, 0) + n
            print(
                f"[{period}] {coin}: fired={stats['fired']:3d} "
                f"win={stats['correct']:3d} loss={stats['incorrect']:3d} "
                f"unr={stats['unresolved']:3d} totalR={stats['total_r']:+.2f}"
            )

    print("\n=== Pooled (theory_v2 with ZC1/ZC2 dynamic exits) ===")
    for coin in args.coins:
        p = pooled[coin]
        resolved = p["correct"] + p["incorrect"]
        wr = p["correct"] / resolved if resolved else 0.0
        avg_r = p["total_r"] / resolved if resolved else 0.0
        print(
            f"  {coin}: fired={p['fired']} resolved={resolved} "
            f"WR={wr*100:.1f}%  totalR={p['total_r']:+.2f}  avgR={avg_r:+.3f}R/trade"
        )
        print(f"        stage counts: {pooled_stages[coin]}")

    out_dir = PROJECT_ROOT / "docs" / "analysis" / "raw"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"theory_v2_validation_{ts}.json"
    out_path.write_text(json.dumps({"per_period": results, "pooled": pooled,
                                    "stage_counts": pooled_stages}, indent=2))
    print(f"\nWrote {out_path.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
