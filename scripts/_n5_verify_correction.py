#!/usr/bin/env python3
"""
N5 Discovery: VERIFY Joni's correction about the 63k→78k BTC move.

Was it really a 2-day explosion from compression?
Check daily data around that period.
"""
import pandas as pd

daily = pd.read_parquet("data/binance_cache/BTC_1d.parquet")
daily = daily.sort_values("timestamp").reset_index(drop=True)

# Look at late July through August 2026
mask = (daily["timestamp"] >= "2026-07-01") & (daily["timestamp"] <= "2026-08-31")
period = daily[mask].copy()
period["close"] = period["close"].astype(float)
period["pct_change"] = period["close"].pct_change() * 100
period["high"] = period["high"].astype(float)
period["low"] = period["low"].astype(float)

print("BTC Daily: July-August 2026")
print("=" * 80)
for _, row in period.iterrows():
    print(f"  {str(row['timestamp'])[:10]}  close={row['close']:>10,.2f}  "
          f"high={row['high']:>10,.2f}  low={row['low']:>10,.2f}  "
          f"pct={row['pct_change']:+6.2f}%")

# Look at the pre-explosion compression zone: June-July 2026
print("\n\nBTC Daily: June 2026 (pre-compression)")
print("=" * 80)
mask2 = (daily["timestamp"] >= "2026-06-01") & (daily["timestamp"] <= "2026-07-15")
period2 = daily[mask2].copy()
period2["close"] = period2["close"].astype(float)
period2["pct_change"] = period2["close"].pct_change() * 100
for _, row in period2.iterrows():
    print(f"  {str(row['timestamp'])[:10]}  close={row['close']:>10,.2f}  "
          f"pct={row['pct_change']:+6.2f}%")

# Range compression stats
print("\n\nRange Compression Analysis:")
june_july = daily[(daily["timestamp"] >= "2026-06-01") & (daily["timestamp"] <= "2026-08-19")]
june_july["daily_range"] = (june_july["high"].astype(float) - june_july["low"].astype(float))
june_july["range_pct"] = june_july["daily_range"] / june_july["close"].astype(float) * 100
print(f"  Jun 1 - Aug 19: avg daily range = {june_july['range_pct'].mean():.2f}%")
print(f"  Aug 19: range = {june_july[june_july['timestamp'] >= '2026-08-19']['range_pct'].values}")
print(f"\n  Last 5 days before explosion (Aug 14-18):")
pre = june_july[(june_july["timestamp"] >= "2026-08-14") & (june_july["timestamp"] <= "2026-08-18")]
for _, row in pre.iterrows():
    rng_pct = (float(row["high"]) - float(row["low"])) / float(row["close"]) * 100
    print(f"    {str(row['timestamp'])[:10]}  range={rng_pct:.2f}%  close={row['close']:,.0f}")

# Bollinger-band width analysis
print("\n\n20-day rolling Bollinger Band Width (close-based):")
df = daily.copy()
df["close"] = df["close"].astype(float)
df["sma20"] = df["close"].rolling(20).mean()
df["std20"] = df["close"].rolling(20).std()
df["bb_width"] = (2 * df["std20"] / df["sma20"]) * 100  # as % of price
aug = df[(df["timestamp"] >= "2026-07-01") & (df["timestamp"] <= "2026-08-25")]
for _, row in aug.iterrows():
    if pd.notna(row["bb_width"]):
        print(f"  {str(row['timestamp'])[:10]}  BB_width={row['bb_width']:.2f}%")

# Compare to historical BB width to find compression events
print("\n\nHistorical BB Width Minima (compression events):")
df_valid = df[df["bb_width"].notna()].copy()
# Find local minima
for i in range(1, len(df_valid) - 1):
    curr = df_valid.iloc[i]["bb_width"]
    prev = df_valid.iloc[i-1]["bb_width"]
    nxt = df_valid.iloc[i+1]["bb_width"]
    if curr < prev and curr < nxt and curr < 2.5:  # tight squeeze
        ts = str(df_valid.iloc[i]["timestamp"])[:10]
        close = df_valid.iloc[i]["close"]
        print(f"  {ts}  close={close:>10,.0f}  BB_width={curr:.2f}%")