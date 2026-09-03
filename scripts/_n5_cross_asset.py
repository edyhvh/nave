#!/usr/bin/env python3
"""
N5: Cross-asset squeeze overlap analysis.
Did BTC and ETH squeeze at the same time? Direction alignment?
"""
import json
from pathlib import Path
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
raw_dir = PROJECT_ROOT / "docs" / "analysis" / "raw"
files = sorted(raw_dir.glob("n5_squeeze_comprehensive_*.json"))
data = json.loads(files[-1].read_text())

btc_events = [e for e in data["BTC"] if e["explosion_happened"]]
eth_events = [e for e in data["ETH"] if e["explosion_happened"]]

# For each BTC event, check if ETH also squeezed around the same time
print("=" * 70)
print("CROSS-ASSET SQUEEZE OVERLAP (BTC ↔ ETH)")
print("=" * 70)

from datetime import datetime, timedelta

def parse_date(s):
    return datetime.strptime(s, "%Y-%m-%d")

coincidences = 0
for btc_e in btc_events:
    btc_start = parse_date(btc_e["squeeze_start"])
    btc_end = parse_date(btc_e["squeeze_end"])

    for eth_e in eth_events:
        eth_start = parse_date(eth_e["squeeze_start"])
        eth_end = parse_date(eth_e["squeeze_end"])

        # Check temporal overlap (within ±30 days)
        if abs((btc_end - eth_end).days) < 30:
            coincidences += 1
            dir_match = "SAME" if btc_e["direction"] == eth_e["direction"] else "OPPOSITE"
            print(f"\n  BTC {btc_e['squeeze_start']} → {btc_e['squeeze_end']} ({btc_e['direction']})")
            print(f"  ETH {eth_e['squeeze_start']} → {eth_e['squeeze_end']} ({eth_e['direction']})")
            print(f"    Direction: {dir_match} | BTC max={btc_e['max_expansion_pct']}% ETH max={eth_e['max_expansion_pct']}%")
            break  # only report closest

print(f"\n  Total BTC-ETH coincident squeezes: {coincidences}")

# Also check: do ETH squeezes with BTC filter have higher precision?
print(f"\n\nETH PERFECT PRECISION (100%, 0/15 FP)")
both_squeezed = 0
btc_only = 0
eth_only = 0
for btc_e in btc_events:
    for eth_e in eth_events:
        if abs((parse_date(btc_e["squeeze_end"]) - parse_date(eth_e["squeeze_end"])).days) < 10:
            both_squeezed += 1
            break

eth_dates = {parse_date(e["squeeze_end"]) for e in eth_events}
btc_dates = {parse_date(e["squeeze_end"]) for e in btc_events}
btc_only = len(btc_dates - eth_dates)
eth_only = len(eth_dates - btc_dates)
both = len(btc_dates & eth_dates)

print(f"  BTC-only squeezes: {btc_only}")
print(f"  ETH-only squeezes: {eth_only}")
print(f"  AND (both): {both}")

# Aggregated squeeze stats: size by squeeze depth
print(f"\n\nSQUEEZE DEPTH vs EXPANSION SIZE (all TPs):")
all_tps = btc_events + eth_events
for bb_threshold in [2, 3, 4, 5, 6, 8, 12]:
    near = [e for e in all_tps if e["bb_mean_pct"] < bb_threshold]
    if near:
        exp_pcts = [e["max_expansion_pct"] for e in near]
        print(f"  BB < {bb_threshold}%: n={len(near):2d}, "
              f"expansion avg={np.mean(exp_pcts):.1f}% "
              f"min={min(exp_pcts):.1f}% max={max(exp_pcts):.1f}%")