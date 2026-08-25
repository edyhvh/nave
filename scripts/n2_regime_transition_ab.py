#!/usr/bin/env python3
"""
N2 regime-transition detector — A/B backtest.

Runs the SAME historical periods as the baseline (theory_v2_backtest.py) with
the detector DISABLED (control) and ENABLED (treatment). One variable changed:
the optional third weekly bias source. Also runs an out-of-sample walk on the
2026 window (Jan 1 -> Aug 25, 2026) covering the 63k->78k move that N1 missed,
which was NOT used to design the detector.

Usage:
    python scripts/n2_regime_transition_ab.py [--coins BTC ETH] [--oos-only]

Output:
    per-period + pooled A/B table, per-trade bias-source breakdown, and a raw
    JSON dump under docs/analysis/raw/n2_regime_transition_ab_{ts}.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
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
from trading.crypto.analysis.recovery_detector import (  # noqa: E402
    RecoveryTransitionConfig,
)


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

# Out-of-sample: the 63k->78k recovery and the whole first 8 months of 2026.
OOS_PERIOD = ("2026-01-01", "2026-08-25")


def _resolve_zc_outcome(
    h1_forward: pd.DataFrame,
    direction: str,
    entry: float,
    sl: float,
    targets: list[float],
) -> tuple[str | None, float]:
    """ZC1/ZC2 partial-exit resolver (mirrors theory_v2_backtest)."""
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
                return "correct", 0.8 * zc1_reward + 0.2 * trail_reward
            if not zc1_hit and high >= zc1:
                zc1_hit = True
                trail_sl = entry
            if zc1_hit and high >= zc2:
                zc1_reward = (zc1 - entry) / risk
                zc2_reward = (zc2 - entry) / risk
                return "correct", 0.8 * zc1_reward + 0.2 * zc2_reward
        else:
            if not zc1_hit and high >= sl:
                return "incorrect", -1.0
            if zc1_hit and high >= trail_sl:
                zc1_reward = (entry - zc1) / risk
                trail_reward = (entry - trail_sl) / risk
                return "correct", 0.8 * zc1_reward + 0.2 * trail_reward
            if not zc1_hit and low <= zc1:
                zc1_hit = True
                trail_sl = entry
            if zc1_hit and low <= zc2:
                zc1_reward = (entry - zc1) / risk
                zc2_reward = (entry - zc2) / risk
                return "correct", 0.8 * zc1_reward + 0.2 * zc2_reward
    if zc1_hit:
        zc1_reward = abs(zc1 - entry) / risk
        last_close = float(h1_forward["close"].iloc[-1])
        if direction == "long":
            trail_reward = (last_close - entry) / risk
        else:
            trail_reward = (entry - last_close) / risk
        return "correct", 0.8 * zc1_reward + 0.2 * trail_reward
    return None, 0.0


def _walk_period(
    coin: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    engine: TheoryV2Engine,
    oos: bool = False,
) -> dict[str, Any]:
    warmup = 140 if oos else 120  # extra warmup for 2026 window
    try:
        weekly_full = data_loader.load(coin, "1W", start - pd.Timedelta(days=warmup * 7), end)
        daily_full = data_loader.load(coin, "1D", start - pd.Timedelta(days=warmup), end)
        h4_full = data_loader.load(coin, "4H", start - pd.Timedelta(days=warmup), end)
        h1_full = data_loader.load(coin, "1H", start - pd.Timedelta(days=warmup), end + pd.Timedelta(days=14))
    except DataNotFoundError as exc:
        return {"skipped": True, "reason": str(exc)}

    stats = {
        "fired": 0, "correct": 0, "incorrect": 0, "unresolved": 0, "total_r": 0.0,
        "stage_counts": {}, "bias_sources": Counter(),
        "trades": [],
    }
    weeks = pd.date_range(start=start, end=end, freq="W-MON", tz="UTC")
    for week_start in weeks:
        weekly_slice = weekly_full[weekly_full["timestamp"] <= week_start]
        daily_slice = daily_full[daily_full["timestamp"] <= week_start]
        h4_slice = h4_full[h4_full["timestamp"] <= week_start]
        h1_slice = h1_full[h1_full["timestamp"] <= week_start]
        decision = engine.evaluate(coin, weekly_slice, daily_slice, h4_slice, h1_slice, as_of=week_start)
        stats["stage_counts"][decision.stage] = stats["stage_counts"].get(decision.stage, 0) + 1
        if decision.signal is None:
            continue
        sig = decision.signal
        entry = float(sig.metadata["entry_price"])
        sl = float(sig.invalidation)
        targets = [float(t) for t in sig.targets]
        direction = sig.direction.value
        bias_source = sig.metadata.get("bias_source", "momentum")

        forward = h1_full[
            (h1_full["timestamp"] > week_start)
            & (h1_full["timestamp"] <= week_start + pd.Timedelta(days=14))
        ]
        outcome, pnl_r = _resolve_zc_outcome(forward, direction, entry, sl, targets)
        stats["fired"] += 1
        stats["total_r"] += pnl_r
        stats["bias_sources"][bias_source] += 1
        if outcome == "correct":
            stats["correct"] += 1
        elif outcome == "incorrect":
            stats["incorrect"] += 1
        else:
            stats["unresolved"] += 1
        stats["trades"].append({
            "week": week_start.strftime("%Y-%m-%d"),
            "direction": direction,
            "bias_source": bias_source,
            "entry": round(entry, 2),
            "sl": round(sl, 2),
            "outcome": outcome,
            "pnl_r": round(pnl_r, 4),
        })
    return stats


def _report(name: str, p: dict[str, Any]) -> str:
    resolved = p["correct"] + p["incorrect"]
    wr = p["correct"] / resolved if resolved else 0.0
    avg_r = p["total_r"] / resolved if resolved else 0.0
    lines = [f"  {name}: fired={p['fired']} resolved={resolved} WR={wr*100:.1f}%  "
             f"totalR={p['total_r']:+.2f}  avgR={avg_r:+.3f}R/trade"]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--coins", nargs="+", default=["BTC", "ETH"])
    parser.add_argument("--oos-only", action="store_true", help="run only the 2026 OOS window")
    args = parser.parse_args()

    btc_cot_history = load_cached_cot_history("BTC")

    def _cot_provider(_coin: str, _as_of: pd.Timestamp) -> pd.DataFrame:
        return btc_cot_history

    control = TheoryV2Engine(cot_history_fn=_cot_provider)
    treat = TheoryV2Engine(
        cot_history_fn=_cot_provider,
        recovery_config=RecoveryTransitionConfig(),
    )

    results: dict[str, Any] = {"coins": args.coins, "periods": {}, "oos": {}}

    if not args.oos_only:
        for period, (s_str, e_str) in PERIODS.items():
            start = pd.Timestamp(s_str, tz="UTC")
            end = pd.Timestamp(e_str, tz="UTC")
            results["periods"][period] = {}
            print(f"--- {period} ---")
            for coin in args.coins:
                c = _walk_period(coin, start, end, control)
                t = _walk_period(coin, start, end, treat)
                results["periods"][period][coin] = {"control": c, "treatment": t}
                if c.get("skipped") or t.get("skipped"):
                    print(f"  {coin}: SKIPPED")
                    continue
                print(_report(f"{coin} control   ", c))
                print(_report(f"{coin} treatment ", t))
                print(f"       treatment bias_sources: {dict(t['bias_sources'])}")
                rt = round(t["total_r"] - c["total_r"], 2)
                print(f"       delta R: {rt:+.2f}")

    # OOS 2026 window
    s_str, e_str = OOS_PERIOD
    start = pd.Timestamp(s_str, tz="UTC")
    end = pd.Timestamp(e_str, tz="UTC")
    print(f"\n--- OUT-OF-SAMPLE {s_str} -> {e_str} (N1 blind spot window) ---")
    for coin in args.coins:
        c = _walk_period(coin, start, end, control, oos=True)
        t = _walk_period(coin, start, end, treat, oos=True)
        results["oos"][coin] = {"control": c, "treatment": t}
        print(_report(f"{coin} control   ", c))
        print(_report(f"{coin} treatment ", t))
        print(f"       treatment bias_sources: {dict(t['bias_sources'])}")
        print(f"       delta R: {t['total_r'] - c['total_r']:+.2f}")

    # Pooled (in-sample) A/B
    if not args.oos_only:
        pooled = {coin: {"control": {"fired": 0, "correct": 0, "incorrect": 0, "unresolved": 0, "total_r": 0.0},
                         "treatment": {"fired": 0, "correct": 0, "incorrect": 0, "unresolved": 0, "total_r": 0.0}}
                  for coin in args.coins}
        for period in results["periods"].values():
            for coin in args.coins:
                for arm in ("control", "treatment"):
                    p = period.get(coin, {}).get(arm, {})
                    for k in ("fired", "correct", "incorrect", "unresolved", "total_r"):
                        pooled[coin][arm][k] += p.get(k, 0)
        print("\n=== POOLED IN-SAMPLE A/B ===")
        tot_c = {"fired": 0, "correct": 0, "incorrect": 0, "unresolved": 0, "total_r": 0.0}
        tot_t = {"fired": 0, "correct": 0, "incorrect": 0, "unresolved": 0, "total_r": 0.0}
        for coin in args.coins:
            c = pooled[coin]["control"]
            t = pooled[coin]["treatment"]
            print(_report(f"{coin} control   ", c))
            print(_report(f"{coin} treatment ", t))
            for k in tot_c:
                tot_c[k] += c[k]
                tot_t[k] += t[k]
        print(_report("POOLED control   ", tot_c))
        print(_report("POOLED treatment ", tot_t))
        print(f"  POOLED delta R: {tot_t['total_r'] - tot_c['total_r']:+.2f}")
        results["pooled"] = {"control": tot_c, "treatment": tot_t}

    out_dir = PROJECT_ROOT / "docs" / "analysis" / "raw"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"n2_regime_transition_ab_{ts}.json"
    # serialise Counters
    def _clean(o: Any) -> Any:
        if isinstance(o, Counter):
            return dict(o)
        if isinstance(o, dict):
            return {k: _clean(v) for k, v in o.items()}
        if isinstance(o, list):
            return [_clean(v) for v in o]
        return o
    out_path.write_text(json.dumps(_clean(results), indent=2, default=str))
    print(f"\nWrote {out_path.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
