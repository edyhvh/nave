#!/usr/bin/env python3
"""
N5 Squeeze A/B Experiment Harness.

Runs the TheoryV2 backtest in two modes over the same 8 periods:
  - CONTROL: squeeze OFF (production default — momentum + range_breakout only)
  - TREATMENT: squeeze ON (SqueezeConfig defaults added as 4th bias source)

Compares pooled R, WR, FP rate, and checks whether the treatment
captures the BTC 63k→78k rally (Aug 2026 OOS target).

Usage:
    python scripts/n5_squeeze_ab.py [--coins BTC ETH]

Acceptance gates (pre-registered in 13_n5_squeeze_discovery.md):
  - Pooled R ≥ 27.69 (baseline)
  - WR ≥ 85%
  - FP ≤ 10%
  - Captures 63k→78k rally
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

from trading.crypto.analysis.squeeze_detector import SqueezeConfig  # noqa: E402
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

# OOS window for the rally 63k→78k (Aug 2026)
OOS_RALLY_START = pd.Timestamp("2026-08-01", tz="UTC")
OOS_RALLY_END = pd.Timestamp("2026-08-31", tz="UTC")


def _resolve_zc_outcome(
    h1_forward: pd.DataFrame,
    direction: str,
    entry: float,
    sl: float,
    targets: list[float],
) -> tuple[str | None, float]:
    """ZC1/ZC2 partial-exit resolver (copied from theory_v2_backtest.py)."""
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
                zc1_reward = (zc1 - entry) / risk
                trail_reward = (trail_sl - entry) / risk
                total = 0.8 * zc1_reward + 0.2 * trail_reward
                return "correct", total
            if not zc1_hit and high >= zc1:
                zc1_hit = True
                trail_sl = entry
            if zc1_hit and high >= zc2:
                zc1_reward = (zc1 - entry) / risk
                zc2_reward = (zc2 - entry) / risk
                total = 0.8 * zc1_reward + 0.2 * zc2_reward
                return "correct", total
        else:
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

    if zc1_hit:
        zc1_reward = abs(zc1 - entry) / risk
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
    """Walk one period and collect stats + squeeze-specific diagnostics."""
    try:
        weekly_full = data_loader.load(coin, "1W", start - pd.Timedelta(days=120), end)
        daily_full = data_loader.load(coin, "1D", start - pd.Timedelta(days=120), end)
        h4_full = data_loader.load(coin, "4H", start - pd.Timedelta(days=60), end)
        h1_full = data_loader.load(coin, "1H", start - pd.Timedelta(days=60), end + pd.Timedelta(days=14))
    except DataNotFoundError as exc:
        return {"skipped": True, "reason": str(exc)}

    stats: dict[str, Any] = {
        "fired": 0,
        "correct": 0,
        "incorrect": 0,
        "unresolved": 0,
        "total_r": 0.0,
        "stage_counts": {},
        "rejected_by": {},
        "squeeze_fired": 0,
        "squeeze_correct": 0,
        "squeeze_incorrect": 0,
        "squeeze_r": 0.0,
        "trades": [],
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
        bias_source = sig.metadata.get("bias_source", "unknown")

        forward = h1_full[
            (h1_full["timestamp"] > week_start)
            & (h1_full["timestamp"] <= week_start + pd.Timedelta(days=14))
        ]
        outcome, pnl_r = _resolve_zc_outcome(forward, direction, entry, sl, targets)
        stats["fired"] += 1
        stats["total_r"] += pnl_r

        is_squeeze = bias_source == "squeeze"
        trade_record = {
            "week": str(week_start.date()),
            "coin": coin,
            "direction": direction,
            "bias_source": bias_source,
            "entry": round(entry, 2),
            "sl": round(sl, 2),
            "targets": [round(t, 2) for t in targets],
            "outcome": outcome,
            "pnl_r": round(pnl_r, 2),
            "squeeze": is_squeeze,
        }

        if outcome == "correct":
            stats["correct"] += 1
            if is_squeeze:
                stats["squeeze_correct"] += 1
        elif outcome == "incorrect":
            stats["incorrect"] += 1
            if is_squeeze:
                stats["squeeze_incorrect"] += 1
        else:
            stats["unresolved"] += 1

        if is_squeeze:
            stats["squeeze_fired"] += 1
            stats["squeeze_r"] += pnl_r

        stats["trades"].append(trade_record)

    return stats


def _walk_oos_rally(
    coin: str,
    engine: TheoryV2Engine,
) -> dict[str, Any]:
    """Check if the engine captures the 63k→78k rally in the OOS window."""
    start = OOS_RALLY_START - pd.Timedelta(days=180)
    end = OOS_RALLY_END + pd.Timedelta(days=14)
    try:
        weekly_full = data_loader.load(coin, "1W", start, end)
        daily_full = data_loader.load(coin, "1D", start, end)
        h4_full = data_loader.load(coin, "4H", start, end)
        h1_full = data_loader.load(coin, "1H", start, end)
    except DataNotFoundError as exc:
        return {"skipped": True, "reason": str(exc)}

    # Walk daily during the rally window to find squeeze breakouts
    results = []
    days = pd.date_range(start=OOS_RALLY_START, end=OOS_RALLY_END, freq="D", tz="UTC")
    for day in days:
        weekly_slice = weekly_full[weekly_full["timestamp"] <= day]
        daily_slice = daily_full[daily_full["timestamp"] <= day]
        h4_slice = h4_full[h4_full["timestamp"] <= day]
        h1_slice = h1_full[h1_full["timestamp"] <= day]
        decision = engine.evaluate(
            coin, weekly_slice, daily_slice, h4_slice, h1_slice, as_of=day
        )
        if decision.signal is not None:
            sig = decision.signal
            results.append({
                "date": str(day.date()),
                "direction": sig.direction.value,
                "bias_source": sig.metadata.get("bias_source"),
                "entry": float(sig.metadata["entry_price"]),
            })

    return {
        "coin": coin,
        "rally_captured": len(results) > 0,
        "signals": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="N5 Squeeze A/B Experiment")
    parser.add_argument("--coins", nargs="+", default=["BTC", "ETH"])
    args = parser.parse_args()

    btc_cot_history = load_cached_cot_history("BTC")

    def _cot_provider(_coin: str, _as_of: pd.Timestamp) -> pd.DataFrame:
        return btc_cot_history

    # --- CONTROL: squeeze OFF (production default) ---
    print("=" * 70)
    print("CONTROL: squeeze OFF (production default)")
    print("=" * 70)
    engine_control = TheoryV2Engine(cot_history_fn=_cot_provider)

    # --- TREATMENT: squeeze ON ---
    print("\n" + "=" * 70)
    print("TREATMENT: squeeze ON (SqueezeConfig defaults)")
    print("=" * 70)
    squeeze_cfg = SqueezeConfig()
    engine_treatment = TheoryV2Engine(
        cot_history_fn=_cot_provider,
        squeeze_config=squeeze_cfg,
    )

    control_results: dict[str, dict[str, Any]] = {}
    treatment_results: dict[str, dict[str, Any]] = {}
    control_pooled = {c: {"fired": 0, "correct": 0, "incorrect": 0, "unresolved": 0, "total_r": 0.0} for c in args.coins}
    treatment_pooled = {c: {"fired": 0, "correct": 0, "incorrect": 0, "unresolved": 0, "total_r": 0.0,
                            "squeeze_fired": 0, "squeeze_correct": 0, "squeeze_incorrect": 0, "squeeze_r": 0.0} for c in args.coins}

    for period, (s_str, e_str) in PERIODS.items():
        start = pd.Timestamp(s_str, tz="UTC")
        end = pd.Timestamp(e_str, tz="UTC")
        control_results[period] = {}
        treatment_results[period] = {}

        for coin in args.coins:
            # Control
            c_stats = _walk_period(coin, start, end, engine_control)
            control_results[period][coin] = c_stats
            if not c_stats.get("skipped"):
                for k in ("fired", "correct", "incorrect", "unresolved", "total_r"):
                    control_pooled[coin][k] += c_stats.get(k, 0)

            # Treatment
            t_stats = _walk_period(coin, start, end, engine_treatment)
            treatment_results[period][coin] = t_stats
            if not t_stats.get("skipped"):
                for k in ("fired", "correct", "incorrect", "unresolved", "total_r",
                          "squeeze_fired", "squeeze_correct", "squeeze_incorrect", "squeeze_r"):
                    treatment_pooled[coin][k] += t_stats.get(k, 0)

            # Per-period comparison
            c_r = c_stats.get("total_r", 0)
            t_r = t_stats.get("total_r", 0)
            delta = t_r - c_r
            sq_fired = t_stats.get("squeeze_fired", 0)
            marker = " *** SQUEEZE" if sq_fired > 0 else ""
            print(
                f"[{period}] {coin}: "
                f"control={c_r:+.2f}R  treatment={t_r:+.2f}R  Δ={delta:+.2f}R"
                f"  squeeze_fired={sq_fired}{marker}"
            )

    # --- Pooled comparison ---
    print("\n" + "=" * 70)
    print("POOLED COMPARISON")
    print("=" * 70)

    all_control_r = 0.0
    all_treatment_r = 0.0
    all_treatment_fired = 0
    all_treatment_resolved = 0
    all_treatment_correct = 0
    all_treatment_incorrect = 0
    all_squeeze_fired = 0
    all_squeeze_correct = 0
    all_squeeze_incorrect = 0
    all_squeeze_r = 0.0

    for coin in args.coins:
        cp = control_pooled[coin]
        tp = treatment_pooled[coin]
        c_resolved = cp["correct"] + cp["incorrect"]
        t_resolved = tp["correct"] + tp["incorrect"]
        c_wr = cp["correct"] / c_resolved if c_resolved else 0
        t_wr = tp["correct"] / t_resolved if t_resolved else 0
        sq_resolved = tp["squeeze_correct"] + tp["squeeze_incorrect"]
        sq_wr = tp["squeeze_correct"] / sq_resolved if sq_resolved else 0

        print(f"\n  {coin}:")
        print(f"    CONTROL   : fired={cp['fired']} resolved={c_resolved} "
              f"WR={c_wr*100:.1f}% totalR={cp['total_r']:+.2f}")
        print(f"    TREATMENT : fired={tp['fired']} resolved={t_resolved} "
              f"WR={t_wr*100:.1f}% totalR={tp['total_r']:+.2f}")
        print(f"    Δ R       : {tp['total_r'] - cp['total_r']:+.2f}")
        if tp["squeeze_fired"] > 0:
            print(f"    SQUEEZE   : fired={tp['squeeze_fired']} resolved={sq_resolved} "
                  f"WR={sq_wr*100:.1f}% R={tp['squeeze_r']:+.2f}")

        all_control_r += cp["total_r"]
        all_treatment_r += tp["total_r"]
        all_treatment_fired += tp["fired"]
        all_treatment_resolved += t_resolved
        all_treatment_correct += tp["correct"]
        all_treatment_incorrect += tp["incorrect"]
        all_squeeze_fired += tp["squeeze_fired"]
        all_squeeze_correct += tp["squeeze_correct"]
        all_squeeze_incorrect += tp["squeeze_incorrect"]
        all_squeeze_r += tp["squeeze_r"]

    pooled_wr = all_treatment_correct / all_treatment_resolved if all_treatment_resolved else 0
    sq_total_resolved = all_squeeze_correct + all_squeeze_incorrect
    sq_fp_rate = all_squeeze_incorrect / sq_total_resolved if sq_total_resolved else 0

    print(f"\n  COMBINED:")
    print(f"    CONTROL total R  : {all_control_r:+.2f}")
    print(f"    TREATMENT total R: {all_treatment_r:+.2f}")
    print(f"    Δ total R        : {all_treatment_r - all_control_r:+.2f}")
    print(f"    TREATMENT WR     : {pooled_wr*100:.1f}%")
    if all_squeeze_fired > 0:
        print(f"    SQUEEZE trades   : {all_squeeze_fired} fired, "
              f"{all_squeeze_correct}W / {all_squeeze_incorrect}L, "
              f"WR={all_squeeze_correct/sq_total_resolved*100:.1f}%, "
              f"FP={sq_fp_rate*100:.1f}%, R={all_squeeze_r:+.2f}")

    # --- OOS Rally check ---
    print("\n" + "=" * 70)
    print("OOS RALLY CHECK: BTC 63k→78k (Aug 2026)")
    print("=" * 70)
    for coin in ["BTC"]:
        rally = _walk_oos_rally(coin, engine_treatment)
        if rally.get("skipped"):
            print(f"  {coin}: SKIPPED — {rally['reason']}")
        else:
            captured = rally["rally_captured"]
            print(f"  {coin}: rally_captured={captured}")
            for sig in rally.get("signals", []):
                print(f"    {sig['date']} {sig['direction']} via {sig['bias_source']} @ {sig['entry']:.2f}")

    # --- Acceptance gates ---
    print("\n" + "=" * 70)
    print("ACCEPTANCE GATES")
    print("=" * 70)
    baseline_r = 27.69
    gate_r = all_treatment_r >= baseline_r
    gate_wr = pooled_wr >= 0.85
    gate_fp = sq_fp_rate <= 0.10 if all_squeeze_fired > 0 else True
    rally_captured = _walk_oos_rally("BTC", engine_treatment).get("rally_captured", False)

    print(f"  [{'PASS' if gate_r else 'FAIL'}] Pooled R ≥ {baseline_r}: {all_treatment_r:+.2f}")
    print(f"  [{'PASS' if gate_wr else 'FAIL'}] WR ≥ 85%: {pooled_wr*100:.1f}%")
    print(f"  [{'PASS' if gate_fp else 'FAIL'}] Squeeze FP ≤ 10%: {sq_fp_rate*100:.1f}%")
    print(f"  [{'PASS' if rally_captured else 'FAIL'}] Captures 63k→78k rally: {rally_captured}")

    verdict = "ACCEPT" if (gate_r and gate_wr and gate_fp and rally_captured) else "REJECT"
    print(f"\n  VERDICT: {verdict}")

    # --- Write artifact ---
    out_dir = PROJECT_ROOT / "docs" / "analysis" / "raw"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"n5_squeeze_ab_{ts}.json"

    artifact = {
        "experiment": "N5",
        "hypothesis": "Volatility squeeze as 4th weekly bias source",
        "date": datetime.now(timezone.utc).isoformat(),
        "coins": args.coins,
        "per_period": {
            "control": control_results,
            "treatment": treatment_results,
        },
        "pooled": {
            "control": {c: control_pooled[c] for c in args.coins},
            "treatment": {c: treatment_pooled[c] for c in args.coins},
        },
        "squeeze_stats": {
            "total_fired": all_squeeze_fired,
            "correct": all_squeeze_correct,
            "incorrect": all_squeeze_incorrect,
            "fp_rate": round(sq_fp_rate, 4),
            "total_r": round(all_squeeze_r, 2),
        },
        "acceptance": {
            "pooled_r": round(all_treatment_r, 2),
            "baseline_r": baseline_r,
            "gate_r_pass": gate_r,
            "wr": round(pooled_wr, 4),
            "gate_wr_pass": gate_wr,
            "squeeze_fp_rate": round(sq_fp_rate, 4),
            "gate_fp_pass": gate_fp,
            "rally_captured": rally_captured,
            "verdict": verdict,
        },
    }
    out_path.write_text(json.dumps(artifact, indent=2, default=str))
    print(f"\nWrote {out_path.relative_to(PROJECT_ROOT)}")

    return 0 if verdict == "ACCEPT" else 1


if __name__ == "__main__":
    raise SystemExit(main())
