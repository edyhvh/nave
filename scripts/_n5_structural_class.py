#!/usr/bin/env python3
"""
N5 Discovery Step 3: Structural classification of MISSED vs FIRED rallies.

Analyzes WHY NAVE missed each rally by examining the weekly velocity/range,
and classifying into sub-types:
  - "grind_low_velocity": slow accumulation, never hits 1.2 ATRs velocity
  - "grind_wide_range": slow accumulation but range too wide for breakout
  - "short_spike": brief burst that doesn't produce enough weekly displacement
  - "post_retest": rally after a crash that doesn't show consistent higher lows
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
    df = daily.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp")
    weekly = df.resample("W-MON").agg({
        "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum",
    }).dropna().reset_index()
    return weekly


def classify_missed_rally(weekly: pd.DataFrame, rally: dict) -> dict:
    """Deep analysis of why a rally was missed."""
    trough_date = pd.Timestamp(rally["trough_date"], tz="UTC")
    peak_date = pd.Timestamp(rally["peak_date"], tz="UTC")
    
    weekly_sub = weekly[weekly["timestamp"] >= trough_date - pd.Timedelta(weeks=12)]
    weekly_sub = weekly_sub[weekly_sub["timestamp"] <= peak_date + pd.Timedelta(weeks=4)]
    
    if len(weekly_sub) < 10:
        return {"classification": "insufficient_data"}
    
    velocities = []
    range_sizes = []
    rally_weekly_pcts = []
    
    for idx in range(8, len(weekly_sub)):
        week_ts = weekly_sub.iloc[idx]["timestamp"]
        if week_ts < trough_date:
            continue
        if week_ts > peak_date + pd.Timedelta(weeks=2):
            break
        
        w_slice = weekly_sub.iloc[:idx + 1]
        _, velocity = momentum_bias(w_slice, lookback=4, min_velocity=1.2, atr_window=8)
        _, rb_diag = range_breakout_bias(w_slice, range_window=8, max_range_atrs=1.5, atr_window=8)
        atr_val = weekly_atr(w_slice, 8)
        
        velocities.append({
            "week": str(week_ts)[:10],
            "velocity": velocity,
            "range_size_atrs": rb_diag.get("range_size_atrs") if rb_diag else None,
            "atr": atr_val,
            "close": float(weekly_sub.iloc[idx]["close"]),
        })
    
    if not velocities:
        return {"classification": "no_weekly_data"}
    
    max_vel = max(abs(v["velocity"]) for v in velocities if v["velocity"] is not None)
    avg_vel = np.mean([abs(v["velocity"]) for v in velocities if v["velocity"] is not None])
    max_range_atrs = max([v["range_size_atrs"] for v in velocities if v["range_size_atrs"] is not None], default=None)
    
    # Weekly pct change during the rally  
    weekly_closes = [v["close"] for v in velocities]
    weekly_returns = []
    for i in range(1, len(weekly_closes)):
        if weekly_closes[i-1] > 0:
            weekly_returns.append((weekly_closes[i] - weekly_closes[i-1]) / weekly_closes[i-1] * 100)
    
    avg_weekly_return = np.mean(weekly_returns) if weekly_returns else 0
    max_weekly_return = max(weekly_returns) if weekly_returns else 0
    
    # Classify
    classification = "unknown"
    if rally["duration_weeks"] >= 4 and max_vel < 1.2:
        classification = "grind_low_velocity"
    elif rally["duration_weeks"] >= 4 and max_vel < 1.5 and rally["max_week_share_of_total"] < 35:
        classification = "grind_moderate_velocity"  
    elif rally["duration_weeks"] < 4 and max_vel < 1.5:
        classification = "short_below_threshold"
    elif rally["duration_weeks"] < 4 and max_vel >= 1.5:
        classification = "short_above_threshold_miss"
    elif rally["duration_weeks"] >= 4 and max_vel >= 1.5:
        classification = "long_no_weekly_confirm"
    else:
        classification = f"uncategorized_dur={rally['duration_weeks']}w_vel={max_vel:.2f}"
    
    return {
        "classification": classification,
        "max_velocity": round(max_vel, 3),
        "avg_velocity": round(avg_vel, 3),
        "max_range_atrs": round(max_range_atrs, 2) if max_range_atrs else None,
        "avg_weekly_return_pct": round(avg_weekly_return, 2),
        "max_weekly_return_pct": round(max_weekly_return, 2),
        "rally_pct": rally["rally_pct"],
        "duration_weeks": rally["duration_weeks"],
        "wk_share": rally["max_week_share_of_total"],
        "vol_ratio": rally["volume_ratio_vs_30d"],
    }


def run_structural_analysis(coin: str, rallies: list[dict], bias_results: list[dict]) -> list[dict]:
    daily = pd.read_parquet(PROJECT_ROOT / "data" / "binance_cache" / f"{coin}_1d.parquet")
    daily = daily.sort_values("timestamp").reset_index(drop=True)
    weekly = build_weekly_from_daily(daily)
    
    classified = []
    for rally, bias_r in zip(rallies, bias_results):
        if not bias_r.get("sufficient_data"):
            continue
        if bias_r.get("ever_fired_long"):
            continue  # only analyze MISSED rallies
        
        analysis = classify_missed_rally(weekly, rally)
        if analysis.get("classification") in ("insufficient_data", "no_weekly_data"):
            continue
        analysis["coin"] = coin
        analysis["trough_date"] = rally["trough_date"]
        analysis["peak_date"] = rally["peak_date"]
        # Carry forward key rally metrics for summary display
        analysis["rally_pct"] = rally["rally_pct"]
        analysis["duration_weeks"] = rally["duration_weeks"]
        classified.append(analysis)
    
    return classified


def main():
    raw_dir = PROJECT_ROOT / "docs" / "analysis" / "raw"
    
    # Load rally scan
    scan_files = sorted(raw_dir.glob("n5_rally_scan_*.json"))
    all_rallies = json.loads(scan_files[-1].read_text())
    
    # Load bias eval
    bias_files = sorted(raw_dir.glob("n5_bias_evaluation_*.json"))
    bias_data = json.loads(bias_files[-1].read_text())
    
    all_classified = []
    for coin in ["BTC", "ETH"]:
        classified = run_structural_analysis(coin, all_rallies[coin], bias_data[coin])
        all_classified.extend(classified)
        
        print(f"\n{'='*60}")
        print(f"{coin} MISSED RALLIES CLASSIFICATION ({len(classified)} total)")
        print(f"{'='*60}")
        
        for c in classified:
            print(f"\n  {c['trough_date']} -> {c['peak_date']}: "
                  f"+{c['rally_pct']}% in {c['duration_weeks']}w")
            print(f"    Classification: {c['classification']}")
            print(f"    max_vel={c['max_velocity']} avg_vel={c['avg_velocity']} | "
                  f"max_range={c.get('max_range_atrs', 'n/a')} ATRs | "
                  f"wk_ret={c['avg_weekly_return_pct']}% avg, {c['max_weekly_return_pct']}% max | "
                  f"wk_share={c['wk_share']}% | vol_ratio={c['vol_ratio']}")
    
    # Aggregate pattern summary
    print(f"\n\n{'='*60}")
    print("PATTERN SUMMARY — What classes of rallies does NAVE miss?")
    print(f"{'='*60}")
    
    from collections import Counter
    classes = Counter(c["classification"] for c in all_classified)
    for cls, count in classes.most_common():
        members = [c for c in all_classified if c["classification"] == cls]
        avg_pct = np.mean([c["rally_pct"] for c in members])
        avg_dur = np.mean([c["duration_weeks"] for c in members])
        avg_vel = np.mean([c["max_velocity"] for c in members])
        avg_wk = np.mean([c["wk_share"] for c in members])
        print(f"\n  {cls}: {count} instances")
        print(f"    Avg rally: +{avg_pct:.1f}% in {avg_dur:.1f}w | "
              f"max_vel={avg_vel:.2f} | wk_share={avg_wk:.1f}%")
        for c in members:
            print(f"      {c['coin']} {c['trough_date']}->{c['peak_date']}: "
                  f"+{c['rally_pct']}% {c['duration_weeks']}w vel={c['max_velocity']:.2f}")
    
    # Now analyze: what % of ALL rallies >15% are missed vs fired?
    total_rallies = sum(len(all_rallies[c]) for c in ["BTC", "ETH"])
    print(f"\n\nOVERALL: {total_rallies} total rallies >=15%, {len(all_classified)} MISSED "
          f"({len(all_classified)/total_rallies*100:.1f}%)")
    
    # Focus on the "grind" class specifically
    grind_misses = [c for c in all_classified if c["classification"].startswith("grind")]
    print(f"\nGRIND-CLASS rallies (>=4w, sub-1.5 velocity): {len(grind_misses)}")
    if grind_misses:
        avg_grind_pct = np.mean([c["rally_pct"] for c in grind_misses])
        avg_grind_dur = np.mean([c["duration_weeks"] for c in grind_misses])
        print(f"  Average: +{avg_grind_pct:.1f}% in {avg_grind_dur:.1f}w")
        print(f"  These are the rallies NAVE CANNOT see with current gates.")
    
    # Save
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = raw_dir / f"n5_structural_classification_{ts}.json"
    out.write_text(json.dumps(all_classified, indent=2, default=str))
    print(f"\nWrote {out.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()