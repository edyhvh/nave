#!/usr/bin/env python3
"""
N5 Discovery: SQUEEZE BREAKOUT DETECTOR v2

Relaxed conditions to find more historical events.
Multiple threshold combinations tested.
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
    
    df["sma"] = df["close_f"].rolling(BB_WINDOW).mean()
    df["std"] = df["close_f"].rolling(BB_WINDOW).std()
    df["bb_width"] = (2 * df["std"] / df["sma"]) * 100
    
    prev_close = df["close_f"].shift(1)
    tr = pd.concat([
        df["high_f"] - df["low_f"],
        (df["high_f"] - prev_close).abs(),
        (df["low_f"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    df["atr"] = tr.rolling(ATR_WINDOW).mean()
    df["atr_pct"] = (df["atr"] / df["close_f"]) * 100
    
    df["range_pct"] = ((df["high_f"] - df["low_f"]) / df["close_f"]) * 100
    df["change_pct"] = df["close_f"].pct_change() * 100
    
    return df


def find_events(df, coin, bb_thresh, atr_thresh, min_days, breakout_mult):
    events = []
    n = len(df)
    
    # Squeeze detection
    df["in_squeeze"] = ((df["bb_width"] < bb_thresh) & (df["atr_pct"] < atr_thresh)).astype(int)
    squeeze_groups = (df["in_squeeze"] != df["in_squeeze"].shift()).cumsum()
    df["squeeze_streak"] = df.groupby(squeeze_groups)["in_squeeze"].cumsum()
    
    # Breakout: daily range > breakout_mult * ATR OR daily change > 5%
    df["is_breakout"] = ((df["range_pct"] > breakout_mult * df["atr_pct"]) | (df["change_pct"].abs() > 5)).astype(int)
    df["squeeze_breakout"] = (df["in_squeeze"].shift(1) == 1) & (df["is_breakout"] == 1)
    
    for i in range(BB_WINDOW + ATR_WINDOW, n):
        if not df.iloc[i]["squeeze_breakout"]:
            continue
        
        streak = int(df.iloc[i - 1]["squeeze_streak"])
        if streak < min_days:
            continue
        
        squeeze_start_idx = i - streak
        breakout_idx = i
        
        comp_period = df.iloc[squeeze_start_idx:breakout_idx]
        comp_close_mean = comp_period["close_f"].mean()
        bb_mean = comp_period["bb_width"].mean()
        atr_pct_mean = comp_period["atr_pct"].mean()
        
        breakout_bar = df.iloc[breakout_idx]
        breakout_change = breakout_bar["change_pct"]
        
        look_fwd = min(14, n - breakout_idx)
        if look_fwd < 3:
            continue
        
        post_max = df.iloc[breakout_idx:breakout_idx + look_fwd]["high_f"].max()
        post_min = df.iloc[breakout_idx:breakout_idx + look_fwd]["low_f"].min()
        
        up_pct = (post_max - comp_close_mean) / comp_close_mean * 100
        down_pct = (comp_close_mean - post_min) / comp_close_mean * 100
        
        events.append({
            "coin": coin,
            "squeeze_start": str(df.iloc[squeeze_start_idx]["timestamp"])[:10],
            "breakout_date": str(df.iloc[breakout_idx]["timestamp"])[:10],
            "squeeze_days": streak,
            "bb_mean_pct": round(bb_mean, 2),
            "atr_pct_mean": round(atr_pct_mean, 2),
            "breakout_change_pct": round(breakout_change, 2),
            "direction": "long" if breakout_change > 0 else "short",
            "max_expansion_pct": round(max(up_pct, down_pct), 1),
            "explosion_happened": max(up_pct, down_pct) >= 5.0,
        })
    
    return events


def main():
    # Test multiple threshold combinations
    configs = [
        {"bb": 3.5, "atr": 1.5, "days": 7, "mult": 3.0, "label": "Strict (BB<3.5%, ATR<1.5%)"},
        {"bb": 5.0, "atr": 2.0, "days": 7, "mult": 3.0, "label": "Medium (BB<5%, ATR<2%)"},
        {"bb": 5.0, "atr": 2.0, "days": 5, "mult": 2.5, "label": "Relaxed (BB<5%, ATR<2%, 5d, 2.5x)"},
        {"bb": 7.0, "atr": 3.0, "days": 7, "mult": 3.0, "label": "Wide (BB<7%, ATR<3%)"},
    ]
    
    for config in configs:
        print(f"\n{'='*75}")
        print(f"Config: {config['label']}")
        print(f"{'='*75}")
        
        all_events = []
        for coin in ["BTC", "ETH"]:
            daily = pd.read_parquet(PROJECT_ROOT / "data" / "binance_cache" / f"{coin}_1d.parquet")
            daily = daily.sort_values("timestamp").reset_index(drop=True)
            daily = compute_indicators(daily)
            
            events = find_events(daily, coin, config["bb"], config["atr"], config["days"], config["mult"])
            all_events.extend(events)
            
            tps = [e for e in events if e["explosion_happened"]]
            fps = [e for e in events if not e["explosion_happened"]]
            
            print(f"\n  {coin}: {len(events)} events ({len(tps)} TP / {len(fps)} FP)")
            for e in events:
                tag = "TP" if e["explosion_happened"] else "FP"
                print(f"    [{tag}] {e['squeeze_start']} -> {e['breakout_date']} "
                      f"({e['squeeze_days']}d) BB={e['bb_mean_pct']:.1f}% "
                      f"change={e['breakout_change_pct']:+.1f}% "
                      f"expansion={e['max_expansion_pct']:.1f}%")
        
        tps = [e for e in all_events if e["explosion_happened"]]
        fps = [e for e in all_events if not e["explosion_happened"]]
        precision = len(tps) / max(1, len(all_events)) * 100
        
        print(f"\n  TOTAL: {len(all_events)} events, {len(tps)} TP, {len(fps)} FP, "
              f"Precision={precision:.1f}%")
        if tps:
            print(f"  TP avg expansion: {np.mean([e['max_expansion_pct'] for e in tps]):.1f}%")


if __name__ == "__main__":
    main()
