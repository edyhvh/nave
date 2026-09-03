#!/usr/bin/env python3
"""
N5 Discovery Step 4: Deep analysis of grind-class rallies and the
"uncategorized" borderline one (1.43 velocity, 6.4w).

Also check: are there rallies NAVE CAUGHT but only very late (>80% done)?
Those are functionally misses even if they technically fired.
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
    return df.resample("W-MON").agg({
        "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum",
    }).dropna().reset_index()


def get_velocity_profile(weekly, trough_date, peak_date):
    """Get week-by-week velocity and bias for a rally."""
    weekly_sub = weekly[weekly["timestamp"] >= trough_date - pd.Timedelta(weeks=12)]
    weekly_sub = weekly_sub[weekly_sub["timestamp"] <= peak_date + pd.Timedelta(weeks=2)]

    rows = []
    for idx in range(8, len(weekly_sub)):
        week_ts = weekly_sub.iloc[idx]["timestamp"]
        if week_ts < trough_date:
            continue
        if week_ts > peak_date + pd.Timedelta(weeks=2):
            break

        w_slice = weekly_sub.iloc[:idx + 1]
        mom_bias, velocity = momentum_bias(w_slice, lookback=4, min_velocity=1.2, atr_window=8)
        rb_bias, rb_diag = range_breakout_bias(w_slice, range_window=8, max_range_atrs=1.5, atr_window=0.5, atr_window=8)
        atr = weekly_atr(w_slice, 8)

        rows.append({
            "week": str(week_ts)[:10],
            "close": float(weekly_sub.iloc[idx]["close"]),
            "velocity": velocity,
            "momentum_bias": mom_bias,
            "range_breakout_bias": rb_bias,
            "rb_range_atrs": rb_diag.get("range_size_atrs") if rb_diag else None,
            "atr": atr,
        })
    return rows


def main():
    raw_dir = PROJECT_ROOT / "docs" / "analysis" / "raw"

    # Load bias eval for late-fire analysis
    bias_files = sorted(raw_dir.glob("n5_bias_evaluation_*.json"))
    bias_data = json.loads(bias_files[-1].read_text())

    scan_files = sorted(raw_dir.glob("n5_rally_scan_*.json"))
    all_rallies = json.loads(scan_files[-1].read_text())

    print("=" * 70)
    print("LATE-FIRE ANALYSIS: Rallies that FIRED but at >80% completion")
    print("=" * 70)

    late_fire_count = 0
    total_fired = 0
    for coin in ["BTC", "ETH"]:
        rally_list = all_rallies[coin]
        bias_list = bias_data[coin]

        for rally, bias in zip(rally_list, bias_list):
            if not bias.get("sufficient_data") or not bias.get("ever_fired_long"):
                continue
            total_fired += 1
            pct = bias.get("fire_pct_done", 0)
            if pct >= 80:
                late_fire_count += 1
                print(f"  {coin} {rally['trough_date']}->{rally['peak_date']}: "
                      f"+{rally['rally_pct']}% fired at ~{pct}% done | "
                      f"weeks={rally['duration_weeks']} | wk_share={rally['max_week_share_of_total']}%")

    print(f"\nTotal FIRED: {total_fired}, Late-fire (>80% done): {late_fire_count} "
          f"({late_fire_count/total_fired*100:.1f}%)")

    # Deep dive: velocity profile for grind-class rallies
    print("\n\n" + "=" * 70)
    print("GRIND-CLASS VELOCITY PROFILES (sub-1.5 velocity, >=4w)")
    print("=" * 70)

    grind_rallies = [
        # BTC grind
        ("BTC", "2022-07-12", "2022-08-13", "+26.45%", "4.6w"),
        ("BTC", "2025-06-22", "2025-08-13", "+22.13%", "7.4w"),
        ("BTC", "2025-07-01", "2025-08-13", "+16.68%", "6.1w"),
        # ETH grind
        ("ETH", "2023-06-14", "2023-07-13", "+21.41%", "4.1w"),
        # Borderline (1.43 vel, 6.4w)
        ("BTC", "2022-09-21", "2022-11-05", "+15.37%", "6.4w"),
        # The 63k→78k prototype from N2 (using iter16 dates)
        ("BTC", "2026-03-03", "2026-04-20", "~+15.7%", "7.3w (iter16 claim)"),
        # Also: ETH late-2025/early-2026 grinds
        ("ETH", "2025-12-18", "2026-01-14", "+18.61%", "3.9w"),
        ("ETH", "2026-03-29", "2026-04-17", "+21.89%", "2.7w"),
    ]

    for coin, trough, peak, size, dur in grind_rallies:
        daily = pd.read_parquet(PROJECT_ROOT / "data" / "binance_cache" / f"{coin}_1d.parquet")
        daily = daily.sort_values("timestamp").reset_index(drop=True)
        weekly = build_weekly_from_daily(daily)

        trough_d = pd.Timestamp(trough, tz="UTC")
        peak_d = pd.Timestamp(peak, tz="UTC")

        profile = get_velocity_profile(weekly, trough_d, peak_d)
        print(f"\n  {coin} {trough}->{peak} ({size}, {dur}):")
        for p in profile:
            vel_str = f"{p['velocity']:+.2f}" if p['velocity'] is not None else "n/a"
            rb_str = f"rb={p['range_breakout_bias']},rng={p['rb_range_atrs']:.1f}" if p['rb_range_atrs'] else "rb=n/a"
            print(f"    {p['week']} close={p['close']:,.0f} vel={vel_str} "
                  f"mom={p['momentum_bias']} {rb_str}")

    # What signal would have caught these?
    print("\n\n" + "=" * 70)
    print("HYPOTHESIS EXPLORATION: What daily structure precedes grind rallies?")
    print("=" * 70)
    print("""
The grind-class rallies share these properties:
1. Low weekly velocity (<1.2 ATRs/4w average) - the MOVE is slow
2. Duration >= 4 weeks (often 5-7 weeks)
3. High-low range >1.5 ATRs (wide, so breakout doesn't fire)
4. Volume ratio ~0.7-1.4x vs 30d average (no distinctive volume signal)
5. max_week_share_of_total ~44-67% (balanced across weeks)

The key structural observation from iter16 is that the DAILY tape was
"screaming momentum" even while the WEEKLY showed near-zero velocity.
The daily ROC-10 was ≈+11% (5 daily ATRs) at the point the weekly
velocity was still 0.83 ATRs.

This suggests the real question is: can we use a DAILY-FOR-WEEKLY
confirmation signal? i.e., "weekly momentum maybe neutral, but if daily
velocity over the same period is high, fire anyway."

The iter16 sweep tried this and all variants degraded. BUT iter16
tested daily confirmation as an ADDITION to the weekly gate (AND),
not as an ALTERNATIVE that could OVERRIDE the weekly neutral. The
difference matters:
- iter16: weekly=0.8 AND daily=1.5 → fire (tightened to 0.8+1.5)
- Hypothesis: weekly=neutral BUT daily_acceleration over sufficient
  bars (>1.0 ATRs over >=5 consecutive daily bars in one direction)
  → arm the gate anyway

The key distinction: iter16 added daily as a CONFIRMATION GATE on
already-thresholded weekly, which admitted MORE noise. The grind
rally hypothesis needs a DAILY PERSISTENCE signal: "price has risen
>=5% over >=5 days with no pullback >2%" — a structural property
of the daily path, not a velocity spike.
""")


if __name__ == "__main__":
    main()