#!/usr/bin/env python3
"""
N5 Discovery Step 2: Evaluate NAVE weekly bias at each identified rally.

For each rally (trough→peak), walk the weekly scan window and record whether
momentum_bias or range_breakout_bias would have fired "long" at any point.

Key insight: if NEITHER fires during the entire rally window, this is a
structural blind spot.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from trading.crypto.theory_v2 import momentum_bias, range_breakout_bias, weekly_atr


def build_weekly_from_daily(daily: pd.DataFrame) -> pd.DataFrame:
    """Resample daily OHLCV into weekly OHLCV (Monday-close)."""
    df = daily.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp")
    weekly = df.resample("W-MON").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }).dropna()
    weekly = weekly.reset_index()
    return weekly


def evaluate_rally_bias(weekly: pd.DataFrame, rally: dict) -> dict:
    """For a given rally, walk weekly bars during the rally and report bias status."""
    trough_date = pd.Timestamp(rally["trough_date"], tz="UTC")
    peak_date = pd.Timestamp(rally["peak_date"], tz="UTC")
    
    # Need warmup: at least 12 weeks before trough for ATR and lookback
    weekly_sub = weekly[weekly["timestamp"] >= trough_date - pd.Timedelta(weeks=12)]
    weekly_sub = weekly_sub[weekly_sub["timestamp"] <= peak_date + pd.Timedelta(weeks=4)]
    
    if len(weekly_sub) < 10:
        return {"sufficient_data": False, "rally": rally}
    
    results_by_week = []
    for idx in range(8, len(weekly_sub)):
        week_ts = weekly_sub.iloc[idx]["timestamp"]
        if week_ts < trough_date:
            continue
        if week_ts > peak_date + pd.Timedelta(weeks=2):
            break
        
        w_slice = weekly_sub.iloc[:idx + 1]
        
        mom_bias, velocity = momentum_bias(w_slice, lookback=4, min_velocity=1.2, atr_window=8)
        rb_bias, rb_diag = range_breakout_bias(w_slice, range_window=8, max_range_atrs=1.5, breakout_buffer_atrs=0.5, atr_window=8)
        
        combined_bias = "neutral"
        source = "neutral"
        if mom_bias != "neutral":
            combined_bias = mom_bias
            source = "momentum"
        elif rb_bias != "neutral":
            combined_bias = rb_bias
            source = "range_breakout"
        
        results_by_week.append({
            "week": str(week_ts)[:10],
            "close": float(weekly_sub.iloc[idx]["close"]),
            "momentum_bias": mom_bias,
            "momentum_velocity": round(velocity, 3) if velocity is not None else None,
            "range_breakout_bias": rb_bias,
            "rb_diag": rb_diag,
            "combined_bias": combined_bias,
            "bias_source": source,
        })
    
    # Check what the combined result is
    ever_long = any(w["combined_bias"] == "long" for w in results_by_week)
    first_long_week = next((w for w in results_by_week if w["combined_bias"] == "long"), None)
    
    # If it fired, how far into the rally? (as pct of total rally done)
    fire_pct_done = None
    if first_long_week and rally["peak_price"] > rally["trough_price"]:
        fire_price = first_long_week["close"]
        fire_pct_done = round(
            (fire_price - rally["trough_price"]) / (rally["peak_price"] - rally["trough_price"]) * 100, 1
        )
    
    return {
        "sufficient_data": True,
        "rally": rally,
        "ever_fired_long": ever_long,
        "first_long_week": first_long_week,
        "fire_pct_done": fire_pct_done,
        "num_weeks_checked": len(results_by_week),
        "mismatches": [
            {"week": w["week"], "mom_vel": w["momentum_velocity"], "rb_diag": w.get("rb_diag")}
            for w in results_by_week
            if w["combined_bias"] == "neutral"
            and w["momentum_velocity"] is not None
            and abs(w["momentum_velocity"]) > 0.8  # close to firing
        ],
        "max_velocity": max(
            (abs(w["momentum_velocity"]) for w in results_by_week 
             if w["momentum_velocity"] is not None),
            default=0
        ),
        "all_weeks": results_by_week,
    }


def main():
    # Load the rally scan
    raw_dir = PROJECT_ROOT / "docs" / "analysis" / "raw"
    scan_files = sorted(raw_dir.glob("n5_rally_scan_*.json"))
    if not scan_files:
        print("ERROR: No rally scan file found. Run _n5_rally_finder.py first.")
        sys.exit(1)
    
    last_scan = scan_files[-1]
    print(f"Loading rally scan: {last_scan.name}")
    all_rallies = json.loads(last_scan.read_text())
    
    results = {}
    for coin in ["BTC", "ETH"]:
        # Build weekly from daily
        daily = pd.read_parquet(PROJECT_ROOT / "data" / "binance_cache" / f"{coin}_1d.parquet")
        daily = daily.sort_values("timestamp").reset_index(drop=True)
        weekly = build_weekly_from_daily(daily)
        
        print(f"\n{coin} weekly bars: {len(weekly)} from {weekly['timestamp'].min()} to {weekly['timestamp'].max()}")
        
        coin_results = []
        for rally in all_rallies[coin]:
            print(f"\n  Evaluating {rally['trough_date']} -> {rally['peak_date']} "
                  f"(+{rally['rally_pct']}%, {rally['duration_weeks']}w, "
                  f"wk_share={rally['max_week_share_of_total']}%)...")
            result = evaluate_rally_bias(weekly, rally)
            coin_results.append(result)
            
            status = "FIRED" if result.get("ever_fired_long") else "MISSED"
            fire_week = result.get("first_long_week", {}).get("week", "n/a") if result.get("first_long_week") else "n/a"
            pct = result.get("fire_pct_done", "n/a")
            max_vel = result.get("max_velocity", 0)
            
            if result.get("sufficient_data"):
                print(f"    → {status} | fire_week={fire_week} | ~{pct}% done | max_vel={max_vel:.2f} ATRs")
            else:
                print(f"    → INSUFFICIENT DATA (weekly too short)")
        
        results[coin] = coin_results
    
    # Summary
    print("\n\n=== SUMMARY ===")
    for coin in results:
        sufficient = [r for r in results[coin] if r.get("sufficient_data")]
        fired = [r for r in sufficient if r.get("ever_fired_long")]
        missed = [r for r in sufficient if not r.get("ever_fired_long")]
        
        print(f"\n{coin}: {len(sufficient)} rallies with data, "
              f"{len(fired)} FIRED, {len(missed)} MISSED")
        
        if missed:
            print(f"  MISS DETAILS:")
            for r in missed:
                rally = r["rally"]
                print(f"    {rally['trough_date']} -> {rally['peak_date']}: "
                      f"+{rally['rally_pct']}% in {rally['duration_weeks']}w | "
                      f"wk_share={rally['max_week_share_of_total']}% | "
                      f"vol_ratio={rally['volume_ratio_vs_30d']} | "
                      f"max_vel={r.get('max_velocity', 0):.2f}")
    
    # Save
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = raw_dir / f"n5_bias_evaluation_{ts}.json"
    
    # Serialize (strip all_weeks detail for main save)
    serializable = {}
    for coin, rlist in results.items():
        serializable[coin] = []
        for r in rlist:
            entry = {k: v for k, v in r.items() if k != "all_weeks"}
            serializable[coin].append(entry)
    
    # Save full detail separately
    out_path_full = raw_dir / f"n5_bias_evaluation_full_{ts}.json"
    
    # Convert to JSON-safe
    def make_serializable(obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, pd.Timestamp):
            return str(obj)
        return obj
    
    import json as json_mod
    out_path.write_text(json_mod.dumps(serializable, indent=2, default=make_serializable))
    print(f"\nWrote {out_path.relative_to(PROJECT_ROOT)}")

if __name__ == "__main__":
    main()