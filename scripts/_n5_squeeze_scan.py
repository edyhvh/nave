#!/usr/bin/env python3
"""
N5 Discovery: VOLATILITY SQUEEZE DETECTION SCAN

Core question: can we detect the compression phase BEFORE the explosion,
using a symmetry metric that the engine could fire on?

Hypothesis: the BTC 63k→78k explosion was a "volatility squeeze" —
a period of extreme compression (BB width < 3%, daily range < 0.5% for
N consecutive days) followed by a violent expansion.

Nave misses these because during the compression phase:
- momentum velocity ≈ 0 (method A: no displacement)
- range too wide for range_breakout (method B: prior range is 3+ ATRs)
- recovery_detector needs crash + recovery (method C: precondition missed)

The proposed detector would arm WHEN:
1. Compression phase detected (daily closes tightly clustered)
2. First expansion bar exceeds N daily ATRs from compression zone
3. Then the existing downstream gates (daily confirm, COT, etc.) apply

This script identifies all historical squeeze events in BTC/ETH.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Configuration
BB_WINDOW = 20
TR_WINDOW = 20
SQUEEZE_BB_THRESHOLD = 0.03      # BB width < 3%
SQUEEZE_ATR_RATIO_THRESHOLD = 1.0  # ATR/price < 1.0%
MIN_SQUEEZE_DAYS = 10
EXPLOSION_ATR_MULT = 2.0         # first bar > 2x daily ATR from the zone
POST_SQUEEZE_WINDOW = 10         # look 10 days forward for explosion


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Compute Bollinger Bands, ATR, and squeeze indicators."""
    df = df.copy()
    df["close_f"] = df["close"].astype(float)
    df["high_f"] = df["high"].astype(float)
    df["low_f"] = df["low"].astype(float)

    # Bollinger Band Width (as % of price)
    df["sma"] = df["close_f"].rolling(BB_WINDOW).mean()
    df["std"] = df["close_f"].rolling(BB_WINDOW).std()
    df["bb_width"] = (2 * df["std"] / df["sma"]) * 100

    # ATR as % of price
    prev_close = df["close_f"].shift(1)
    tr = pd.concat([
        df["high_f"] - df["low_f"],
        (df["high_f"] - prev_close).abs(),
        (df["low_f"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    df["atr"] = tr.rolling(TR_WINDOW).mean()
    df["atr_pct"] = (df["atr"] / df["close_f"]) * 100

    # Daily range as % of close
    df["range_pct"] = ((df["high_f"] - df["low_f"]) / df["close_f"]) * 100

    # Rolling mean of daily range (smooth)
    df["range_pct_ma5"] = df["range_pct"].rolling(5).mean()

    # Squeeze flags
    df["in_squeeze"] = (df["bb_width"] < SQUEEZE_BB_THRESHOLD * 100).astype(int)

    # Consecutive squeeze days
    squeeze_groups = (df["in_squeeze"] != df["in_squeeze"].shift()).cumsum()
    df["squeeze_streak"] = df.groupby(squeeze_groups)["in_squeeze"].cumsum()

    # Check squeeze END (in_squeeze was 1, now 0)
    df["squeeze_ending"] = (df["in_squeeze"].shift(1) == 1) & (df["in_squeeze"] == 0)

    return df


def find_squeeze_events(df: pd.DataFrame, coin: str) -> list[dict]:
    """Find all squeeze→explosion events."""
    events = []
    n = len(df)

    for i in range(TR_WINDOW + BB_WINDOW, n - POST_SQUEEZE_WINDOW):
        if df.iloc[i]["squeeze_ending"]:
            squeeze_end_idx = i
            streak = df.iloc[i - 1]["squeeze_streak"]
            if streak < MIN_SQUEEZE_DAYS:
                continue

            # Compression stats
            comp_start_idx = squeeze_end_idx - int(streak) - 1  # -1 because squeeze_ending means it just ended
            if comp_start_idx < 0:
                continue
            comp_period = df.iloc[comp_start_idx:squeeze_end_idx]
            comp_close_mean = comp_period["close_f"].mean()
            comp_bb_min = comp_period["bb_width"].min()
            comp_range_mean = comp_period["range_pct"].mean()

            # Look forward for explosion
            post_window = df.iloc[squeeze_end_idx:squeeze_end_idx + POST_SQUEEZE_WINDOW]
            if post_window.empty:
                continue

            post_max = post_window["high_f"].max()
            post_min = post_window["low_f"].min()
            expansion_up_pct = (post_max - comp_close_mean) / comp_close_mean * 100
            expansion_down_pct = (comp_close_mean - post_min) / comp_close_mean * 100

            # Maximum single-day move
            max_daily_move_pct = post_window["range_pct"].max()

            # Did an explosion happen? >= 5% move in 10 days
            explosion_happened = expansion_up_pct >= 5.0 or expansion_down_pct >= 5.0
            direction = "up" if expansion_up_pct > expansion_down_pct else "down"
            max_expansion = max(expansion_up_pct, expansion_down_pct)

            # When did the first big bar happen?
            big_bar_idx = None
            big_bar_pct = 0
            for j in range(squeeze_end_idx, min(squeeze_end_idx + 5, n)):
                bar_range = df.iloc[j]["range_pct"]
                if bar_range > df.iloc[j]["atr"] / df.iloc[j]["close_f"] * 100 * EXPLOSION_ATR_MULT:
                    if bar_range > big_bar_pct:
                        big_bar_idx = j
                        big_bar_pct = bar_range
                    break

            events.append({
                "coin": coin,
                "squeeze_start": str(df.iloc[comp_start_idx]["timestamp"])[:10],
                "squeeze_end": str(df.iloc[squeeze_end_idx]["timestamp"])[:10],
                "squeeze_days": int(streak),
                "comp_close_mean": round(comp_close_mean, 2),
                "comp_bb_min_pct": round(comp_bb_min, 2),
                "comp_range_mean_pct": round(comp_range_mean, 2),
                "explosion_happened": explosion_happened,
                "direction": direction,
                "max_expansion_pct": round(max_expansion, 1),
                "expansion_up_pct": round(expansion_up_pct, 1),
                "expansion_down_pct": round(expansion_down_pct, 1),
                "max_daily_move_pct": round(max_daily_move_pct, 2),
                "big_bar_day": str(df.iloc[big_bar_idx]["timestamp"])[:10] if big_bar_idx else None,
                "big_bar_pct": round(big_bar_pct, 2) if big_bar_pct else None,
            })

    return events


def main():
    results = {}

    for coin in ["BTC", "ETH"]:
        daily = pd.read_parquet(PROJECT_ROOT / "data" / "binance_cache" / f"{coin}_1d.parquet")
        daily = daily.sort_values("timestamp").reset_index(drop=True)
        daily = compute_indicators(daily)
        events = find_squeeze_events(daily, coin)
        results[coin] = events

        print(f"\n{'='*70}")
        print(f"{coin}: {len(events)} squeeze events found (>={MIN_SQUEEZE_DAYS}d)")
        print(f"{'='*70}")

        tp = [e for e in events if e["explosion_happened"]]
        ft = [e for e in events if not e["explosion_happened"]]

        print(f"\n  TP (explosion >=5%): {len(tp)}  |  "
              f"FP (no explosion): {len(ft)}  |  "
              f"Precision: {len(tp)/len(events)*100:.1f}%")

        for e in events:
            status = "TP" if e["explosion_happened"] else "FP"
            print(f"\n  [{status}] {e['squeeze_start']} → squeeze end {e['squeeze_end']} "
                  f"({e['squeeze_days']}d, bb={e['comp_bb_min_pct']}%, "
                  f"range={e['comp_range_mean_pct']}%)")
            print(f"    Expansion: {e['direction']} "
                  f"up={e['expansion_up_pct']}% down={e['expansion_down_pct']}% "
                  f"max_daily={e['max_daily_move_pct']}%")
            if e['big_bar_day']:
                print(f"    Big bar: {e['big_bar_day']} ({e['big_bar_pct']}%)")

    # Overall precision/recall
    all_events = results["BTC"] + results["ETH"]
    tps = [e for e in all_events if e["explosion_happened"]]
    fps = [e for e in all_events if not e["explosion_happened"]]

    print(f"\n\n{'='*70}")
    print("OVERALL SQUEEZE DETECTOR PERFORMANCE")
    print(f"{'='*70}")
    print(f"  Events: {len(all_events)} total")
    print(f"  TP (explosion): {len(tps)} ({len(tps)/len(all_events)*100:.1f}%)")
    print(f"  FP (no explosion): {len(fps)} ({len(fps)/len(all_events)*100:.1f}%)")

    # Summary stats of TP events
    if tps:
        exp_pcts = [e["max_expansion_pct"] for e in tps]
        print(f"\n  TP expansion range: min={min(exp_pcts):.1f}% avg={np.mean(exp_pcts):.1f}% "
              f"max={max(exp_pcts):.1f}%")
        squeeze_durs = [e["squeeze_days"] for e in tps]
        print(f"  TP squeeze duration: min={min(squeeze_durs)}d avg={np.mean(squeeze_durs):.0f}d "
              f"max={max(squeeze_durs)}d")

    # Classification: can we distinguish TP from FP at the squeeze END?
    if fps:
        print(f"\n  FP squeeze profiles:")
        for e in fps:
            print(f"    {e['coin']} {e['squeeze_start']}: "
                  f"dur={e['squeeze_days']}d bb={e['comp_bb_min_pct']}% "
                  f"range={e['comp_range_mean_pct']}% → max_exp={e['max_expansion_pct']}%")

    # Save
    out = PROJECT_ROOT / "docs" / "analysis" / "raw"
    out.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out / f"n5_squeeze_scan_{ts}.json"
    out_path.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nWrote {out_path.relative_to(PROJECT_ROOT)}")

if __name__ == "__main__":
    main()