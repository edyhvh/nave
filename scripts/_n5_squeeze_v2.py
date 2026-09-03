#!/usr/bin/env python3
"""
N5 Discovery: COMPREHENSIVE volatility compression scan.

Two approaches:
1. Absolute: BB width < 5% for >= 7 days
2. Relative: BB width below 15th percentile of rolling 365-day history

For each squeeze event, check if the subsequent 10-14 day window saw
an expansion >= 10% (directional explosion).
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent

BB_WINDOW = 20
PCT_WINDOW = 120   # 120-day rolling percentile for relative detection

def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
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
    df["atr_14"] = tr.rolling(14).mean()
    df["atr_pct"] = (df["atr_14"] / df["close_f"]) * 100

    # Daily range %
    df["range_pct"] = ((df["high_f"] - df["low_f"]) / df["close_f"]) * 100

    # Rolling percentile of BB width (relative compression)
    df["bb_width_pctl"] = df["bb_width"].rolling(PCT_WINDOW, min_periods=60).rank(pct=True) * 100

    # Rolling percentile of ATR
    df["atr_pct_pctl"] = df["atr_pct"].rolling(PCT_WINDOW, min_periods=60).rank(pct=True) * 100

    # Relative squeeze: BB width AND ATR both below 25th percentile
    df["squeeze_rel"] = ((df["bb_width_pctl"] < 25) & (df["atr_pct_pctl"] < 25)).astype(int)

    # Absolute squeeze
    df["squeeze_abs"] = (df["bb_width"] < 3.5).astype(int)

    # Combined (either works)
    df["squeeze"] = df["squeeze_rel"]  # primary: relative

    # Consecutive days
    squeeze_groups = (df["squeeze"] != df["squeeze"].shift()).cumsum()
    df["squeeze_streak"] = df.groupby(squeeze_groups)["squeeze"].cumsum()
    df["squeeze_ending"] = (df["squeeze"].shift(1) == 1) & (df["squeeze"] == 0)

    return df


def find_events(df: pd.DataFrame, coin: str, min_days: int = 7) -> list[dict]:
    """Find squeeze→explosion events."""
    events = []
    n = len(df)

    for i in range(PCT_WINDOW + BB_WINDOW, n):
        if not df.iloc[i]["squeeze_ending"]:
            continue

        streak = int(df.iloc[i - 1]["squeeze_streak"])
        if streak < min_days:
            continue

        # Skip if too close to data start/end
        if i - streak < 0:
            continue

        comp_start_idx = i - streak
        squeeze_end_idx = i

        # Avoid duplicates if squeeze was long (sub-divide into shorter windows)
        # Actually don't — just record the whole squeeze ending

        comp_period = df.iloc[comp_start_idx:squeeze_end_idx]
        comp_close_mean = comp_period["close_f"].mean()
        trough_close = comp_period["close_f"].min()
        bb_min = comp_period["bb_width"].min()
        bb_mean = comp_period["bb_width"].mean()
        range_mean = comp_period["range_pct"].mean()
        atr_pct_mean = comp_period["atr_pct"].mean()

        # Look forward (14 days max)
        look_fwd = min(14, n - squeeze_end_idx)
        if look_fwd < 3:
            continue

        post_close_end = df.iloc[squeeze_end_idx + look_fwd - 1]["close_f"] if squeeze_end_idx + look_fwd - 1 < n else None
        post_max = df.iloc[squeeze_end_idx:squeeze_end_idx + look_fwd]["high_f"].max()
        post_min = df.iloc[squeeze_end_idx:squeeze_end_idx + look_fwd]["low_f"].min()

        up_pct = (post_max - comp_close_mean) / comp_close_mean * 100
        down_pct = (comp_close_mean - post_min) / comp_close_mean * 100

        # The FIRST big bar in the post-squeeze period
        big_bar_pct = 0
        big_bar_date = None
        for j in range(squeeze_end_idx, min(squeeze_end_idx + 5, n)):
            bar_pct = df.iloc[j]["range_pct"]
            if bar_pct > big_bar_pct:
                big_bar_pct = bar_pct
                big_bar_date = str(df.iloc[j]["timestamp"])[:10]
            if bar_pct > 4.0:  # bar >4% = explosion detected
                break

        # Ending compression at peak of squeeze (BB width at squeeze end)
        bb_at_exit = df.iloc[squeeze_end_idx - 1]["bb_width"]
        bb_pctl_at_exit = df.iloc[squeeze_end_idx - 1]["bb_width_pctl"]

        events.append({
            "coin": coin,
            "squeeze_start": str(df.iloc[comp_start_idx]["timestamp"])[:10],
            "squeeze_end": str(df.iloc[squeeze_end_idx]["timestamp"])[:10],
            "duration_days": streak,
            "comp_close_mean": round(comp_close_mean, 2),
            "trough_close": round(trough_close, 2),
            "bb_min_pct": round(bb_min, 2),
            "bb_mean_pct": round(bb_mean, 2),
            "bb_at_exit_pct": round(bb_at_exit, 2),
            "bb_pctl_at_exit": round(bb_pctl_at_exit, 1),
            "range_mean_pct": round(range_mean, 2),
            "atr_pct_mean": round(atr_pct_mean, 2),
            "expansion_up_pct": round(up_pct, 1),
            "expansion_down_pct": round(down_pct, 1),
            "max_expansion_pct": round(max(up_pct, down_pct), 1),
            "direction": "up" if up_pct > down_pct else "down",
            "big_bar_pct": round(big_bar_pct, 2),
            "big_bar_date": big_bar_date,
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

        events = find_events(daily, coin, min_days=7)
        results[coin] = events

        print(f"\n{'='*75}")
        print(f"{coin}: {len(events)} squeeze events (relative pctl+ATR, >=7d)")
        print(f"{'='*75}")

        tps = [e for e in events if e["explosion_happened"]]
        fps = [e for e in events if not e["explosion_happened"]]

        print(f"  TP: {len(tps)} | FP: {len(fps)} | "
              f"Precision: {len(tps)/max(1,len(events))*100:.1f}%")

        for e in events:
            tag = "TP" if e["explosion_happened"] else "FP"
            print(f"\n  [{tag}] {e['squeeze_start']} → {e['squeeze_end']} "
                  f"({e['duration_days']}d, bb={e['bb_mean_pct']:.2f}%, "
                  f"range={e['range_mean_pct']:.2f}%, "
                  f"atr={e['atr_pct_mean']:.2f}%)")
            print(f"    Close Streak: ${e['comp_close_mean']:,.0f} "
                  f"(bb_pctl@exit={e['bb_pctl_at_exit']:.0f}%, "
                  f"bb={e['bb_at_exit_pct']:.2f}%)")
            up = e["expansion_up_pct"]
            down = e["expansion_down_pct"]
            print(f"    Expansion 14d: +{up:+.1f}% / -{down:+.1f}% = "
                  f"max={e['max_expansion_pct']:.1f}% | "
                  f"big_bar={e['big_bar_pct']:.1f}% on {e['big_bar_date']}")

    # Verbose dump of Aug 2026 area
    print(f"\n\n{'='*75}")
    print("AUG 2026 CONTEXT: BB width and ATR for BTC")
    print(f"{'='*75}")
    daily = pd.read_parquet(PROJECT_ROOT / "data" / "binance_cache" / "BTC_1d.parquet")
    daily = daily.sort_values("timestamp").reset_index(drop=True)
    daily = compute_indicators(daily)

    aug = daily[(daily["timestamp"] >= "2026-07-20") & (daily["timestamp"] <= "2026-08-30")]
    for _, row in aug.iterrows():
        bb = row.get("bb_width", None)
        pctl = row.get("bb_width_pctl", None)
        sq = row.get("squeeze", 0)
        streak = row.get("squeeze_streak", 0)
        pctl_str = f"{pctl:.0f}" if pd.notna(pctl) else "n/a"
        bb_str = f"{bb:.2f}" if pd.notna(bb) else "n/a"
        close = row.get("close_f", 0)
        print(f"  {str(row['timestamp'])[:10]}  close=${close:>8,.0f}  "
              f"bb={bb_str:>5}% (pctl={pctl_str:>4}%)  "
              f"sq={sq} str={streak:.0f}")

    # Overall stats
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
        print(f"  TP avg duration: {np.mean([e['duration_days'] for e in tps]):.0f}d")
        print(f"  TP avg bb_at_exit: {np.mean([e['bb_at_exit_pct'] for e in tps]):.2f}%")
    if fps:
        print(f"  FP avg max_expansion: {np.mean([e['max_expansion_pct'] for e in fps]):.1f}%")

    # Save
    out = PROJECT_ROOT / "docs" / "analysis" / "raw"
    out.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out / f"n5_squeeze_comprehensive_{ts}.json"
    out_path.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nWrote {out_path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()