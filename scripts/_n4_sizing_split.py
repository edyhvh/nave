#!/usr/bin/env python3
"""N4 experiment: cross-asset agreement as soft sizing input.

Uses the N3 cross-asset weekly momentum agreement buckets (agree / neutral_other /
disagree) as a *sizing multiplier* -- NOT a hard filter.  The agree bucket gets a
boost (>1.0x); the neutral_other bucket gets a discount (<1.0x).  Disagree never
fires at weekly scale so it is irrelevant.

Sweep: neutral_other discount in {0.25, 0.5, 0.75}, agree boost in {1.1, 1.25, 1.5}.

Gate vs baseline +27.69R:
  1. Pooled R > +27.69R
  2. WR pooled not lower by >1pp
  3. Per-period regressions limited (no period drops >2R unless another rises >4R)

Usage:
    python scripts/_n4_sizing_split.py [--oos-only]
"""
from __future__ import annotations

import argparse
import json
import sys
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

BASELINE_R = 27.69
# 18 correct out of 21 resolved (pooled from N3 probe: 12 agree correct + 6 neutral correct)
BASELINE_WR = 18 / 21


def _resolve_zc_outcome(h1_forward, direction, entry, sl, targets):
    """Identical ZC1/ZC2 resolver used in N3 probe."""
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
        high = float(row["high"])
        low = float(row["low"])
        if direction == "long":
            if not zc1_hit and low <= sl:
                return "incorrect", -1.0
            if zc1_hit and low <= trail_sl:
                return "correct", 0.8 * (zc1 - entry) / risk + 0.2 * (trail_sl - entry) / risk
            if not zc1_hit and high >= zc1:
                zc1_hit = True
                trail_sl = entry
            if zc1_hit and high >= zc2:
                return "correct", 0.8 * (zc1 - entry) / risk + 0.2 * (zc2 - entry) / risk
        else:
            if not zc1_hit and high >= sl:
                return "incorrect", -1.0
            if zc1_hit and high >= trail_sl:
                return "correct", 0.8 * (entry - zc1) / risk + 0.2 * (entry - trail_sl) / risk
            if not zc1_hit and low <= zc1:
                zc1_hit = True
                trail_sl = entry
            if zc1_hit and low <= zc2:
                return "correct", 0.8 * (entry - zc1) / risk + 0.2 * (entry - zc2) / risk
    if zc1_hit:
        zc1_reward = abs(zc1 - entry) / risk
        last_close = float(h1_forward["close"].iloc[-1])
        trail_reward = (
            (last_close - entry) / risk if direction == "long" else (entry - last_close) / risk
        )
        return "correct", 0.8 * zc1_reward + 0.2 * trail_reward
    return None, 0.0


def _other_weekly_bias(coin, weekly_full, week_start):
    other = "ETH" if coin == "BTC" else "BTC"
    other_weekly = weekly_full[other][weekly_full[other]["timestamp"] <= week_start]
    bias, _ = momentum_bias(other_weekly)
    return bias


def _walk(coin, start, end, engine, weekly_full_all, agree_mult, neutral_mult, oos=False):
    """Walk one period, applying sizing multipliers per agreement bucket."""
    warmup = 140 if oos else 120
    try:
        weekly = data_loader.load(coin, "1W", start - pd.Timedelta(days=warmup * 7), end)
        daily = data_loader.load(coin, "1D", start - pd.Timedelta(days=warmup), end)
        h4 = data_loader.load(coin, "4H", start - pd.Timedelta(days=warmup), end)
        h1 = data_loader.load(
            coin, "1H", start - pd.Timedelta(days=warmup), end + pd.Timedelta(days=14)
        )
    except DataNotFoundError as exc:
        return {"skipped": True, "reason": str(exc)}

    stats = {
        "fired": 0,
        "correct": 0,
        "incorrect": 0,
        "unresolved": 0,
        "total_r": 0.0,
        "sized_r": 0.0,
        "agree": {
            "correct": 0, "incorrect": 0, "unresolved": 0,
            "total_r": 0.0, "sized_r": 0.0, "fired": 0,
        },
        "disagree": {
            "correct": 0, "incorrect": 0, "unresolved": 0,
            "total_r": 0.0, "sized_r": 0.0, "fired": 0,
        },
        "neutral_other": {
            "correct": 0, "incorrect": 0, "unresolved": 0,
            "total_r": 0.0, "sized_r": 0.0, "fired": 0,
        },
        "trades": [],
    }
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
        forward = h1[
            (h1["timestamp"] > week_start)
            & (h1["timestamp"] <= week_start + pd.Timedelta(days=14))
        ]
        outcome, pnl = _resolve_zc_outcome(forward, direction, entry, sl, targets)

        bucket = (
            "agree"
            if other_bias == direction
            else (
                "disagree"
                if (other_bias in ("long", "short") and other_bias != direction)
                else "neutral_other"
            )
        )
        mult = {"agree": agree_mult, "disagree": 1.0, "neutral_other": neutral_mult}[bucket]
        sized_pnl = pnl * mult

        stats["fired"] += 1
        stats["total_r"] += pnl
        stats["sized_r"] += sized_pnl
        stats[bucket]["fired"] += 1
        stats[bucket]["total_r"] += pnl
        stats[bucket]["sized_r"] += sized_pnl
        if outcome == "correct":
            stats["correct"] += 1
            stats[bucket]["correct"] += 1
        elif outcome == "incorrect":
            stats["incorrect"] += 1
            stats[bucket]["incorrect"] += 1
        else:
            stats["unresolved"] += 1
            stats[bucket]["unresolved"] += 1
        stats["trades"].append(
            {
                "week": week_start.strftime("%Y-%m-%d"),
                "direction": direction,
                "other_bias": other_bias,
                "outcome": outcome,
                "pnl_r": round(pnl, 4),
                "sized_pnl_r": round(sized_pnl, 4),
                "bucket": bucket,
                "mult": mult,
            }
        )
    return stats


def _run_sweep(agree_mult, neutral_mult, engine, weekly_full_all, oos_only=False):
    """Run one (agree_mult, neutral_mult) configuration across all periods."""
    results = {"oos": {}}
    if not oos_only:
        results["periods"] = {}
        for period, (s, e) in PERIODS.items():
            start, end = pd.Timestamp(s, tz="UTC"), pd.Timestamp(e, tz="UTC")
            results["periods"][period] = {}
            for coin in COINS:
                r = _walk(coin, start, end, engine, weekly_full_all, agree_mult, neutral_mult)
                results["periods"][period][coin] = r

    # OOS
    s, e = OOS_PERIOD
    start, end = pd.Timestamp(s, tz="UTC"), pd.Timestamp(e, tz="UTC")
    for coin in COINS:
        r = _walk(coin, start, end, engine, weekly_full_all, agree_mult, neutral_mult, oos=True)
        results["oos"][coin] = r

    # Pooled
    if not oos_only:
        pool = {
            b: {
                "correct": 0, "incorrect": 0, "unresolved": 0,
                "total_r": 0.0, "sized_r": 0.0, "fired": 0,
            }
            for b in ("agree", "disagree", "neutral_other")
        }
        pool["all"] = {
            "correct": 0, "incorrect": 0, "unresolved": 0,
            "total_r": 0.0, "sized_r": 0.0, "fired": 0,
        }
        for period in results["periods"].values():
            for coin in COINS:
                r = period.get(coin, {})
                if r.get("skipped"):
                    continue
                for k in pool["all"]:
                    pool["all"][k] += r.get(k, 0)
                for b in ("agree", "disagree", "neutral_other"):
                    for k in pool[b]:
                        pool[b][k] += r[b].get(k, 0)
        results["pooled"] = pool

    return results


def _evaluate_gate(results, agree_mult, neutral_mult):
    """Evaluate the strict gate vs baseline. Returns (pass, details)."""
    pooled = results.get("pooled", {})
    if not pooled:
        return False, {"reason": "no pooled data"}

    all_p = pooled["all"]
    resolved = all_p["correct"] + all_p["incorrect"]
    sized_r = all_p["sized_r"]
    wr = all_p["correct"] / resolved if resolved else 0.0

    # Gate 1: Pooled R > baseline
    gate1 = sized_r > BASELINE_R
    # Gate 2: WR not lower by >1pp
    baseline_wr_pct = BASELINE_WR * 100
    wr_pct = wr * 100
    gate2 = (baseline_wr_pct - wr_pct) <= 1.0
    # Gate 3: Per-period regressions
    period_regressions = []
    period_improvements = []
    for period, coins in results.get("periods", {}).items():
        base_r = 0.0
        sized_r_period = 0.0
        for coin in COINS:
            r = coins.get(coin, {})
            if r.get("skipped"):
                continue
            base_r += r.get("total_r", 0.0)
            sized_r_period += r.get("sized_r", 0.0)
        delta = sized_r_period - base_r
        if delta < -2.0:
            period_regressions.append((period, round(delta, 4), round(base_r, 4), round(sized_r_period, 4)))
        if delta > 4.0:
            period_improvements.append((period, round(delta, 4)))
    gate3 = len(period_regressions) == 0 or any(
        imp[1] > 4.0 for imp in period_improvements
    )

    passed = gate1 and gate2 and gate3
    details = {
        "agree_mult": agree_mult,
        "neutral_mult": neutral_mult,
        "sized_r": round(sized_r, 4),
        "baseline_r": BASELINE_R,
        "delta_r": round(sized_r - BASELINE_R, 4),
        "wr_pct": round(wr_pct, 2),
        "baseline_wr_pct": round(baseline_wr_pct, 2),
        "wr_delta_pp": round(wr_pct - baseline_wr_pct, 2),
        "resolved": resolved,
        "fired": all_p["fired"],
        "avg_r": round(sized_r / resolved, 4) if resolved else 0.0,
        "gate1_r_gt_baseline": gate1,
        "gate2_wr_ok": gate2,
        "gate3_periods_ok": gate3,
        "period_regressions": period_regressions,
        "passed": passed,
    }
    return passed, details


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--oos-only", action="store_true")
    args = ap.parse_args()

    btc_cot = load_cached_cot_history("BTC")

    def _cot(_c, _a):
        return btc_cot

    engine = TheoryV2Engine(cot_history_fn=_cot)

    def _load_weekly(coin):
        return data_loader.load(
            coin,
            "1W",
            pd.Timestamp("2016-08-01", tz="UTC"),
            pd.Timestamp("2026-08-25", tz="UTC"),
        )

    weekly_full_all = {"BTC": _load_weekly("BTC"), "ETH": _load_weekly("ETH")}

    # Sweep: agree boost x neutral_other discount
    agree_mults = [1.1, 1.25, 1.5]
    neutral_mults = [0.25, 0.5, 0.75]

    all_results = []
    best = None

    print("=" * 80)
    print("N4 EXPERIMENT: Cross-asset agreement as soft sizing input")
    print(f"Baseline: +{BASELINE_R}R, WR {BASELINE_WR*100:.1f}%")
    print(f"Sweep: agree_boost in {agree_mults}, neutral_discount in {neutral_mults}")
    print("=" * 80)

    for am in agree_mults:
        for nm in neutral_mults:
            print(f"\n--- agree_mult={am}x neutral_mult={nm}x ---")
            res = _run_sweep(am, nm, engine, weekly_full_all, oos_only=args.oos_only)
            passed, details = _evaluate_gate(res, am, nm)
            all_results.append(details)

            pooled = res.get("pooled", {}).get("all", {})
            print(f"  Sized R: {details['sized_r']:+.2f}  (Delta vs base: {details['delta_r']:+.2f})")
            print(f"  WR: {details['wr_pct']:.1f}%  (Delta: {details['wr_delta_pp']:+.2f}pp)")
            print(
                f"  Trades: {details['fired']} fired, {details['resolved']} resolved, "
                f"avgR={details['avg_r']:+.3f}"
            )
            print(
                f"  Gate1(R>base): {'PASS' if details['gate1_r_gt_baseline'] else 'FAIL'}  "
                f"Gate2(WR): {'PASS' if details['gate2_wr_ok'] else 'FAIL'}  "
                f"Gate3(periods): {'PASS' if details['gate3_periods_ok'] else 'FAIL'}"
            )
            print(f"  => {'PASS' if passed else 'FAIL'}")

            if passed:
                if best is None or details["sized_r"] > best["sized_r"]:
                    best = details

            # Per-period detail
            if res.get("periods"):
                for period, coins in res["periods"].items():
                    base_r = 0.0
                    sized_r_p = 0.0
                    for coin in COINS:
                        r = coins.get(coin, {})
                        if r.get("skipped"):
                            continue
                        base_r += r.get("total_r", 0.0)
                        sized_r_p += r.get("sized_r", 0.0)
                    delta = sized_r_p - base_r
                    flag = " REGRESS" if delta < -2.0 else (" BOOST" if delta > 4.0 else "")
                    print(
                        f"    {period:30s} base={base_r:+.2f} sized={sized_r_p:+.2f} "
                        f"Delta={delta:+.2f}{flag}"
                    )

    # Summary
    print("\n" + "=" * 80)
    print("SWEEP SUMMARY")
    print("=" * 80)
    print(f"{'agree':>6s} {'neutral':>8s} {'sized_R':>8s} {'delta_R':>7s} {'WR%':>6s} {'d_WR':>6s} {'gate':>6s}")
    print("-" * 55)
    for d in all_results:
        print(
            f"{d['agree_mult']:>6.2f} {d['neutral_mult']:>8.2f} "
            f"{d['sized_r']:>+8.2f} {d['delta_r']:>+7.2f} "
            f"{d['wr_pct']:>6.1f} {d['wr_delta_pp']:>+6.2f} "
            f"{'PASS' if d['passed'] else 'FAIL':>6s}"
        )

    # Verdict
    print("\n" + "=" * 80)
    if best:
        print(
            f"VERDICT: ACCEPT -- best config: agree={best['agree_mult']}x "
            f"neutral={best['neutral_mult']}x"
        )
        print(
            f"  Sized R: {best['sized_r']:+.2f} (Delta {best['delta_r']:+.2f}), "
            f"WR {best['wr_pct']:.1f}%"
        )
        verdict = "ACCEPT"
    else:
        max_delta = max(d["delta_r"] for d in all_results) if all_results else -999
        if max_delta < 0.5:
            print(
                f"VERDICT: REJECT -- no config produces >+0.5R over baseline "
                f"(best Delta={max_delta:+.2f}R)"
            )
            print(
                "  Structural reason: neutral_other bucket has net-positive resolved trades;"
            )
            print(
                "  discounting it always reduces total R. Boosting agree alone cannot compensate"
            )
            print(
                "  unless agree_mult is extreme (>1.4x), which is not a legitimate sizing signal."
            )
            verdict = "REJECT"
        else:
            print(
                f"VERDICT: INCONCLUSIVE -- best Delta={max_delta:+.2f}R but no config passes all gates"
            )
            verdict = "INCONCLUSIVE"
    print("=" * 80)

    # Save raw results
    out = PROJECT_ROOT / "docs" / "analysis" / "raw"
    out.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = out / f"n4_sizing_split_{ts}.json"
    payload = {
        "verdict": verdict,
        "baseline_r": BASELINE_R,
        "baseline_wr": round(BASELINE_WR * 100, 2),
        "sweep": all_results,
        "best": best,
    }
    path.write_text(json.dumps(payload, indent=2, default=str))
    print(f"\nWrote {path.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
