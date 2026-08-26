#!/usr/bin/env python3
"""
N5 Discovery: SQUEEZE BREAKOUT DETECTOR

Instead of looking for squeeze endings, look for breakout bars
DURING active squeezes. This catches the Aug 2026 explosion.

Logic:
1. Detect squeeze: BB width < 3.5% AND ATR/price < 1.5% for >= 7 days
2. Detect breakout: daily range > 3x ATR OR daily change > 5%
3. Fire signal on the breakout bar
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent

BB_WINDOW = 20
ATR_WINDOW = 14

def compute_indicators(df):
    df = df.copy()
    df["close_f"] = df["close"].astype(float)
    df["high_f"] = df["high"].astype(float)
    df["low_f"] = df["low"].astype(float)
    
    # BB Width
    df["sma"] = df["close_f"].rolling(BB_WINDOW).mean()
    df["std"] = df["close_f"].rolling(BB_WINDOW).std()
    df["bb_width"] = (2 * df["std"] / df["sma"]) * 100
    
    # ATR
    prev_close = df["close_f"].shift(1)
    tr = pd.concat([
        df["high_f"] - df["low_f"],
        (df["high_f"] - prev_close).abs(),
        (df["low_f"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    df["atr"] = tr.rolling(ATR_WINDOW).mean()
    df["atr_pct"] = (df["atr"] / df["close_f"]) * 100
    
    # Daily range %
    df["range_pct"] = ((df["high_f"] - df["low_f"]) / df["close_f"]) * 100
    
    # Daily change %
    df["change_pct"] = df["close_f"].pct_change() * 100
    
    # Squeeze: BB width < 3.5% AND ATR < 1.5%
    df["in_squeeze"] = ((df["bb_width"] < 3.5) & (df["atr_pct"] < 1.5)).astype(int)
    
    # Consecutive squeeze days
    squeeze_groups = (df["in_squeeze"] != df["in_squeeze"].shift()).cumsum()
    df["squeeze_streak"] = df.groupby(squeeze_groups)["in_squeeze"].cumsum()
    
    # Breakout: daily range > 3x ATR OR daily change > 5%
    df["is_breakout"] = ((df["range_pct"] > 3 * df["atr_pct"]) | (df["change_pct"].abs() > 5)).astype(int)
    
    # Squeeze breakout: in squeeze AND breakout
    df["squeeze_breakout"] = (df["in_squeeze"].shift(1) == 1) & (df["is_breakout"] == 1)
    
    return df


def find_squeeze_breakouts(df, coin, min_squeeze_days=7):
    events = []
    n = len(df)
    
    for i in range(BB_WINDOW + ATR_WINDOW, n):
        if not df.iloc[i]["squeeze_breakout"]:
            continue
        
        streak = int(df.iloc[i - 1]["squeeze_streak"])
        if streak < min_squeeze_days:
            continue
        
        squeeze_start_idx = i - streak
        breakout_idx = i
        
        comp_period = df.iloc[squeeze_start_idx:breakout_idx]
        comp_close_mean = comp_period["close_f"].mean()
        bb_min = comp_period["bb_width"].min()
        bb_mean = comp_period["bb_width"].mean()
        atr_pct_mean = comp_period["atr_pct"].mean()
        
        breakout_bar = df.iloc[breakout_idx]
        breakout_range = breakout_bar["range_pct"]
        breakout_change = breakout_bar["change_pct"]
        breakout_close = breakout_bar["close_f"]
        
        look_fwd = min(14, n - breakout_idx)
        if look_fwd < 3:
            continue
        
        post_max = df.iloc[breakout_idx:breakout_idx + look_fwd]["high_f"].max()
        post_min = df.iloc[breakout_idx:breakout_idx + look_fwd]["low_f"].min()
        
        up_pct = (post_max - comp_close_mean) / comp_close_mean * 100
        down_pct = (comp_close_mean - post_min) / comp_close_mean * 100
        
        direction = "long" if breakout_change > 0 else "short"
        
        events.append({
            "coin": coin,
            "squeeze_start": str(df.iloc[squeeze_start_idx]["timestamp"])[:10],
            "breakout_date": str(df.iloc[breakout_idx]["timestamp"])[:10],
            "squeeze_days": streak,
            "comp_close_mean": round(comp_close_mean, 2),
            "bb_min_pct": round(bb_min, 2),
            "bb_mean_pct": round(bb_mean, 2),
            "atr_pct_mean": round(atr_pct_mean, 2),
            "breakout_range_pct": round(breakout_range, 2),
            "breakout_change_pct": round(breakout_change, 2),
            "breakout_close": round(breakout_close, 2),
            "direction": direction,
            "expansion_up_pct": round(up_pct, 1),
            "expansion_down_pct": round(down_pct, 1),
            "max_expansion_pct": round(max(up_pct, down_pct), 1),
            "explosion_happened": max(up_pct, down_pct) >= 5.0,
            "look_fwd_days": look_fwd,
        })
    
    return events


def main():
    results = {}
    for coin in ["BTC", "ETH"]:
        daily = pd.read_parquet(PROJECT_ROOT / "data" / "binance_cache" / f"{coin}_1d.parquet")
        daily = daily.sort_values("timestamp").reset_index(drop=True)
        daily = compute_indicators(daily)
        
        events = find_squeeze_breakouts(daily, coin, min_squeeze_days=7)
        results[coin] = events
        
        print(f"\n{'='*75}")
        print(f"{coin}: {len(events)} squeeze breakout events")
        print(f"{'='*75}")
        
        tps = [e for e in events if e["explosion_happened"]]
        fps = [e for e in events if not e["explosion_happened"]]
        
        print(f"  TP: {len(tps)} | FP: {len(fps)} | "
              f"Precision: {len(tps)/max(1,len(events))*100:.1f}%")
        
        for e in events:
            tag = "TP" if e["explosion_happened"] else "FP"
            print(f"\n  [{tag}] {e['squeeze_start']} -> breakout {e['breakout_date']} "
                  f"({e['squeeze_days']}d squeeze)")
            print(f"    BB: {e['bb_mean_pct']:.2f}% (min={e['bb_min_pct']:.2f}%), "
                  f"ATR: {e['atr_pct_mean']:.2f}%")
            print(f"    Breakout: range={e['breakout_range_pct']:.2f}%, "
                  f"change={e['breakout_change_pct']:+.2f}%, "
                  f"direction={e['direction']}")
            print(f"    Expansion 14d: +{e['expansion_up_pct']:.1f}% / "
                  f"-{e['expansion_down_pct']:.1f}% = "
                  f"max={e['max_expansion_pct']:.1f}%")
    
    all_events = results["BTC"] + results["ETH"]
    tps = [e for e in all_events if e["explosion_happened"]]
    fps = [e for e in all_events if not e["explosion_happened"]]
    
    print(f"\n\n{'='*75}")
    print("AGGREGATE STATS")
    print(f"{'='*75}")
    print(f"  Total events: {len(all_events)}")
    print(f"  TP: {len(tps)} | FP: {len(fps)}")
    if tps:
        print(f"  TP avg max_expansion: {np.mean([e['max_expansion_pct'] for e in tps]):.1f}%")
        print(f"  TP avg squeeze duration: {np.mean([e['squeeze_days'] for e in tps]):.0f}d")
    if fps:
        print(f"  FP avg max_expansion: {np.mean([e['max_expansion_pct'] for e in fps]):.1f}%")
    
    out = PROJECT_ROOT / "docs" / "analysis" / "raw"
    out.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out / f"n5_squeeze_breakout_{ts}.json"
    out_path.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nWrote {out_path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
