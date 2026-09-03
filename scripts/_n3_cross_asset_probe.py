#!/usr/bin/env python3
"""N3 probe: cross-asset confirmation / relative-strength.

Question: does agreement between BTC and ETH weekly momentum bias predict the
outcome of a fired trade better than the baseline (which evaluates each coin
independently)? If trades taken while the correlated asset's weekly bias agrees
have materially higher WR / R than those taken while it disagrees, a
cross-asset confirmation filter is a candidate N3 edge.

This is a STANDALONE evidence probe. It does not modify production code. It
reuses the N2 A/B harness semantics (same engine, same resolver, same periods)
but only walks the CONTROL (baseline) arm, and for every fired trade it records
the OTHER coin's weekly momentum bias at that week.

Usage:
    python scripts/_n3_cross_asset_probe.py [--oos-only]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import data_loader  # noqa: E402
from data_loader import DataNotFoundError  # noqa: E402
from trading.crypto.cot.cot_gate import load_cached_cot_history  # noqa: E402
from trading.crypto.theory_v2 import TheoryV2Engine, momentum_bias  # noqa: E402

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
OOS_PERIOD = ("2026-01-01", "2026-08-25")

COINS = ["BTC", "ETH"]


def _resolve_zc_outcome(h1_forward, direction, entry, sl, targets):
    if h1_forward.empty or not targets:
        return None, 0.0
    risk = abs(entry - sl)
    if risk <= 0:
        return None, 0.0
    zc1 = targets[0]
    zc2 = targets[1] if len(targets) > 1 else zc1
    zc1_hit = False
    trail_sl = sl
    for _, row in h1_forward.iterrows():
        high = float(row["high"]); low = float(row["low"])
        if direction == "long":
            if not zc1_hit and low <= sl:
                return "incorrect", -1.0
            if zc1_hit and low <= trail_sl:
                return "correct", 0.8 * (zc1 - entry) / risk + 0.2 * (trail_sl - entry) / risk
            if not zc1_hit and high >= zc1:
                zc1_hit = True; trail_sl = entry
            if zc1_hit and high >= zc2:
                return "correct", 0.8 * (zc1 - entry) / risk + 0.2 * (zc2 - entry) / risk
        else:
            if not zc1_hit and high >= sl:
                return "incorrect", -1.0
            if zc1_hit and high >= trail_sl:
                return "correct", 0.8 * (entry - zc1) / risk + 0.2 * (entry - trail_sl) / risk
            if not zc1_hit and low <= zc1:
                zc1_hit = True; trail_sl = entry
            if zc1_hit and low <= zc2:
                return "correct", 0.8 * (entry - zc1) / risk + 0.2 * (entry - zc2) / risk
    if zc1_hit:
        zc1_reward = abs(zc1 - entry) / risk
        last_close = float(h1_forward["close"].iloc[-1])
        trail_reward = (last_close - entry) / risk if direction == "long" else (entry - last_close) / risk
        return "correct", 0.8 * zc1_reward + 0.2 * trail_reward
    return None, 0.0


def _other_weekly_bias(coin, weekly_full, week_start):
    other = "ETH" if coin == "BTC" else "BTC"
    other_weekly = weekly_full[other][weekly_full[other]["timestamp"] <= week_start]
    bias, _ = momentum_bias(other_weekly)
    return bias


def _walk(coin, start, end, engine, weekly_full_all, oos=False):
    warmup = 140 if oos else 120
    try:
        weekly = data_loader.load(coin, "1W", start - pd.Timedelta(days=warmup * 7), end)
        daily = data_loader.load(coin, "1D", start - pd.Timedelta(days=warmup), end)
        h4 = data_loader.load(coin, "4H", start - pd.Timedelta(days=warmup), end)
        h1 = data_loader.load(coin, "1H", start - pd.Timedelta(days=warmup), end + pd.Timedelta(days=14))
    except DataNotFoundError as exc:
        return {"skipped": True, "reason": str(exc)}

    stats = {"fired": 0, "correct": 0, "incorrect": 0, "unresolved": 0, "total_r": 0.0,
             "agree": {"correct": 0, "incorrect": 0, "unresolved": 0, "total_r": 0.0, "fired": 0},
             "disagree": {"correct": 0, "incorrect": 0, "unresolved": 0, "total_r": 0.0, "fired": 0},
             "neutral_other": {"correct": 0, "incorrect": 0, "unresolved": 0, "total_r": 0.0, "fired": 0},
             "trades": []}
    weeks = pd.date_range(start=start, end=end, freq="W-MON", tz="UTC")
    for week_start in weeks:
        decision = engine.evaluate(
            coin,
            weekly[weekly["timestamp"] <= week_start],
            daily[daily["timestamp"] <= week_start],
            h4[h4["timestamp"] <= week_start],
            h1[h1["timestamp"] <= week_start],
            as_of=week_start,
        )
        if decision.signal is None:
            continue
        sig = decision.signal
        entry = float(sig.metadata["entry_price"])
        sl = float(sig.invalidation)
        targets = [float(t) for t in sig.targets]
        direction = sig.direction.value
        other_bias = _other_weekly_bias(coin, weekly_full_all, week_start)
        forward = h1[(h1["timestamp"] > week_start) & (h1["timestamp"] <= week_start + pd.Timedelta(days=14))]
        outcome, pnl = _resolve_zc_outcome(forward, direction, entry, sl, targets)

        stats["fired"] += 1
        stats["total_r"] += pnl
        bucket = ("agree" if other_bias == direction
                  else ("disagree" if (other_bias in ("long", "short") and other_bias != direction)
                        else "neutral_other"))
        stats[bucket]["fired"] += 1
        stats[bucket]["total_r"] += pnl
        if outcome == "correct":
            stats["correct"] += 1; stats[bucket]["correct"] += 1
        elif outcome == "incorrect":
            stats["incorrect"] += 1; stats[bucket]["incorrect"] += 1
        else:
            stats["unresolved"] += 1; stats[bucket]["unresolved"] += 1
        stats["trades"].append({
            "week": week_start.strftime("%Y-%m-%d"), "direction": direction,
            "other_bias": other_bias, "outcome": outcome, "pnl_r": round(pnl, 4),
        })
    return stats


def _rep(name, p):
    resolved = p["correct"] + p["incorrect"]
    wr = p["correct"] / resolved if resolved else 0.0
    avg = p["total_r"] / resolved if resolved else 0.0
    return f"{name}: fired={p['fired']} resolved={resolved} WR={wr*100:.1f}% totalR={p['total_r']:+.2f} avgR={avg:+.3f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--oos-only", action="store_true")
    args = ap.parse_args()

    btc_cot = load_cached_cot_history("BTC")
    def _cot(_c, _a): return btc_cot
    engine = TheoryV2Engine(cot_history_fn=_cot)

    # Preload full weekly for both coins for the other-bias lookup
    def _load_weekly(coin):
        return data_loader.load(coin, "1W", pd.Timestamp("2016-08-01", tz="UTC"), pd.Timestamp("2026-08-25", tz="UTC"))
    weekly_full_all = {"BTC": _load_weekly("BTC"), "ETH": _load_weekly("ETH")}

    results = {"oos": {}}
    if not args.oos_only:
        results["periods"] = {}
        for period, (s, e) in PERIODS.items():
            start, end = pd.Timestamp(s, tz="UTC"), pd.Timestamp(e, tz="UTC")
            results["periods"][period] = {}
            print(f"--- {period} ---")
            for coin in COINS:
                r = _walk(coin, start, end, engine, weekly_full_all)
                results["periods"][period][coin] = r
                if r.get("skipped"):
                    print(f"  {coin}: SKIPPED"); continue
                print(f"  {coin} all     : {_rep('', r)}")
                for b in ("agree", "disagree", "neutral_other"):
                    print(f"      {b:14s}: {_rep('', r[b])}")

    # OOS
    s, e = OOS_PERIOD
    start, end = pd.Timestamp(s, tz="UTC"), pd.Timestamp(e, tz="UTC")
    print(f"\n--- OOS {s} -> {e} ---")
    for coin in COINS:
        r = _walk(coin, start, end, engine, weekly_full_all, oos=True)
        results["oos"][coin] = r
        print(f"  {coin} all     : {_rep('', r)}")
        for b in ("agree", "disagree", "neutral_other"):
            print(f"      {b:14s}: {_rep('', r[b])}")

    # Pooled
    if not args.oos_only:
        pool = {b: {"correct": 0, "incorrect": 0, "unresolved": 0, "total_r": 0.0, "fired": 0} for b in ("agree", "disagree", "neutral_other")}
        pool["all"] = {"correct": 0, "incorrect": 0, "unresolved": 0, "total_r": 0.0, "fired": 0}
        for period in results["periods"].values():
            for coin in COINS:
                r = period.get(coin, {})
                for k in pool["all"]:
                    pool["all"][k] += r.get(k, 0)
                for b in ("agree", "disagree", "neutral_other"):
                    for k in pool[b]:
                        pool[b][k] += r[b].get(k, 0)
        print("\n=== POOLED CROSS-ASSET ===")
        for b in ("all", "agree", "disagree", "neutral_other"):
            print(f"  {b:14s}: {_rep('', pool[b])}")
        results["pooled"] = pool

    out = PROJECT_ROOT / "docs" / "analysis" / "raw"
    out.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = out / f"n3_cross_asset_probe_{ts}.json"
    path.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nWrote {path.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
