#!/usr/bin/env python3
"""
N5 Discovery: Identify rallies >=15% in BTC/ETH daily history
and classify them by NAVE capture status.

Step 1: Find all significant rallies (>=15% from local trough to peak)
Using a swing-low/swing-high approach on daily close data.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

# ---- config ----
MIN_RALLY_PCT = 0.15         # >= 15% from trough to peak
MIN_RALLY_DURATION_DAYS = 14 # at least 2 weeks long
SWING_WINDOW = 5             # swing detection window in daily bars


def find_rallies(daily: pd.DataFrame, coin: str) -> list[dict]:
    """Find all rallies >=15% in a daily OHLCV DataFrame.

    Algorithm:
    1. Scan for local lows (close is the minimum over +-SWING_WINDOW days)
    2. From each local low, track price forward: the rally continues until
       price drops more than 10% from the running peak (drawdown filter)
    3. Keep rallies where peak - trough >= 15%
    """
    closes = daily["close"].astype(float).values
    timestamps = daily["timestamp"].values
    highs = daily["high"].astype(float).values
    lows = daily["low"].astype(float).values
    volumes = daily["volume"].astype(float).values
    n = len(closes)

    rallies = []
    used_troughs = set()  # avoid duplicate rallies from same trough

    for i in range(SWING_WINDOW, n - SWING_WINDOW):
        # Check if this is a local minimum in close
        window = closes[i - SWING_WINDOW: i + SWING_WINDOW + 1]
        if closes[i] != window.min():
            continue
        if closes[i] <= 0:
            continue
        # Check we haven't already covered this trough area
        if any(abs(i - used_i) < SWING_WINDOW for used_i in used_troughs):
            continue

        trough_price = closes[i]
        peak_price = trough_price
        peak_idx = i
        rally_end_idx = None

        for j in range(i + 1, min(i + 365, n)):  # max 1 year rally
            if closes[j] > peak_price:
                peak_price = closes[j]
                peak_idx = j

            # 10% trailing stop from peak to end the rally
            if (peak_price - closes[j]) / peak_price > 0.10:
                rally_end_idx = j
                break

        if rally_end_idx is None:
            rally_end_idx = min(i + 365, n) - 1

        rally_pct = (peak_price - trough_price) / trough_price
        duration_days = (timestamps[peak_idx] - timestamps[i]) / np.timedelta64(1, "D")

        if rally_pct >= MIN_RALLY_PCT and duration_days >= MIN_RALLY_DURATION_DAYS:
            # Characterize the rally's pace
            price_path = closes[i:peak_idx + 1]

            # Weekly velocity profile (resampled from daily)
            num_weeks = max(1, int(duration_days / 7))
            week_pct_changes = []
            for w in range(1, num_weeks + 1):
                w_end = min(i + w * 7, peak_idx)
                if w_end > i:
                    w_pct = (closes[w_end] - closes[i]) / closes[i]
                    prev_pct = (closes[i + (w-1)*7] - closes[i]) / closes[i] if w > 1 else 0
                    week_pct_changes.append((w_pct - prev_pct) * closes[i] / trough_price)

            # Max single-week gain as % of total rally
            max_week_gain = max(week_pct_changes) if week_pct_changes else 0
            total_rally_pct = rally_pct

            # Characterize pace: grind (slow, steady) vs spike (sharp)
            # grind = low max single week relative to total
            # spike = high max single week relative to total
            if total_rally_pct > 0:
                max_week_share = max_week_gain / total_rally_pct
            else:
                max_week_share = 0

            # Volume profile: vs 30-day avg
            if i > 30:
                avg_vol_30 = np.mean(volumes[max(i-30, 0):i])
                avg_vol_rally = np.mean(volumes[i:peak_idx + 1])
                vol_ratio = avg_vol_rally / avg_vol_30 if avg_vol_30 > 0 else 0
            else:
                vol_ratio = None

            rallies.append({
                "coin": coin,
                "trough_date": str(timestamps[i])[:10],
                "trough_price": round(float(trough_price), 2),
                "peak_date": str(timestamps[peak_idx])[:10],
                "peak_price": round(float(peak_price), 2),
                "rally_pct": round(rally_pct * 100, 2),
                "duration_days": int(duration_days),
                "duration_weeks": round(duration_days / 7, 1),
                "max_week_gain_pct": round(max_week_gain * 100, 2) if max_week_gain else 0,
                "max_week_share_of_total": round(max_week_share * 100, 1),
                "volume_ratio_vs_30d": round(vol_ratio, 2) if vol_ratio else None,
                "trough_idx": int(i),
                "peak_idx": int(peak_idx),
            })
            used_troughs.add(i)

    return rallies


def main():
    results = {}
    for coin in ["BTC", "ETH"]:
        daily = pd.read_parquet(
            PROJECT_ROOT / "data" / "binance_cache" / f"{coin}_1d.parquet"
        )
        daily = daily.sort_values("timestamp").reset_index(drop=True)
        rallies = find_rallies(daily, coin)
        results[coin] = rallies
        print(f"\n{coin}: {len(rallies)} rallies >=15% found")
        for r in rallies:
            print(f"  {r['trough_date']} -> {r['peak_date']}: "
                  f"+{r['rally_pct']}% in {r['duration_weeks']}w "
                  f"(max_week={r['max_week_gain_pct']}%, "
                  f"wk_share={r['max_week_share_of_total']}%, "
                  f"vol_ratio={r['volume_ratio_vs_30d']})")

    # Save
    out = PROJECT_ROOT / "docs" / "analysis" / "raw"
    out.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = out / f"n5_rally_scan_{ts}.json"
    path.write_text(json.dumps(results, indent=2))
    print(f"\nWrote {path.relative_to(PROJECT_ROOT)}")

if __name__ == "__main__":
    main()