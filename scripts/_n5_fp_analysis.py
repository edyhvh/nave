#!/usr/bin/env python3
"""
N5: Detailed analysis of the 2 False Positives and the TP/FP boundary.
Also: what part of NAVE pipeline would this feed into?
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Load the raw comprehensive scan
raw_dir = PROJECT_ROOT / "docs" / "analysis" / "raw"
files = sorted(raw_dir.glob("n5_squeeze_comprehensive_*.json"))
data = json.loads(files[-1].read_text())

print("=" * 70)
print("FALSE POSITIVE ANALYSIS")
print("=" * 70)

fps = []
for coin in data:
    for e in data[coin]:
        if not e["explosion_happened"]:
            fps.append(e)
            print(f"\n  FP: {coin} {e['squeeze_start']} → {e['squeeze_end']}")
            print(f"    Duration: {e['duration_days']} days")
            print(f"    BB width mean: {e['bb_mean_pct']:.2f}%")
            print(f"    BB at exit: {e['bb_at_exit_pct']:.2f}% (pctl={e['bb_pctl_at_exit']:.0f}%)")
            print(f"    Range: {e['range_mean_pct']:.2f}%")
            print(f"    ATR: {e['atr_pct_mean']:.2f}%")
            print(f"    Close: ${e['comp_close_mean']:,.0f}")
            print(f"    Expansion: max={e['max_expansion_pct']:.1f}%")
            print(f"    Big bar: {e['big_bar_pct']:.1f}% on {e['big_bar_date']}")

print(f"\n\nBoth FPs have expansion of exactly 5.0% (borderline).")
print(f"They follow shorter squeezes (7-25 days) with higher BB widths")
print(f"than the TPs.")

# TP stats for comparison
tps = []
for coin in data:
    for e in data[coin]:
        if e["explosion_happened"]:
            tps.append(e)

print(f"\n\n{'='*70}")
print("TP vs FP BOUNDARY ANALYSIS")
print(f"{'='*70}")

print(f"\n  Metric              | TP (n={len(tps)})  | FP (n={len(fps)})")
print(f"  {'-'*48}")
print(f"  Duration (days)     | avg={np.mean([e['duration_days'] for e in tps]):.0f}     | avg={np.mean([e['duration_days'] for e in fps]):.0f}")
print(f"  BB width mean (%)   | avg={np.mean([e['bb_mean_pct'] for e in tps]):.2f}    | avg={np.mean([e['bb_mean_pct'] for e in fps]):.2f}")
print(f"  ATR % mean          | avg={np.mean([e['atr_pct_mean'] for e in tps]):.2f}     | avg={np.mean([e['atr_pct_mean'] for e in fps]):.2f}")
print(f"  BB pctl at exit     | avg={np.mean([e['bb_pctl_at_exit'] for e in tps]):.0f}        | avg={np.mean([e['bb_pctl_at_exit'] for e in fps]):.0f}")

# Decompose by compression DEPTH
print(f"\n\nEvents by BB width depth:")
for threshold in [3, 4, 5]:
    deep_tp = [e for e in tps if e["bb_mean_pct"] < threshold]
    all_events = [e for e in tps + fps if e["bb_mean_pct"] < threshold]
    deep_fp = [e for e in fps if e["bb_mean_pct"] < threshold]
    if all_events:
        print(f"  BB < {threshold}%: {len(all_events)} events, "
              f"{len(deep_tp)} TP / {len(deep_fp)} FP = "
              f"precision {len(deep_tp)/len(all_events)*100:.1f}%")

# Direction analysis
print(f"\n\nDirection analysis for TPs:")
up = [e for e in tps if e["direction"] == "up"]
down = [e for e in tps if e["direction"] == "down"]
print(f"  UP explosions: {len(up)} ({len(up)/len(tps)*100:.1f}%)")
print(f"  DOWN explosions: {len(down)} ({len(down)/len(tps)*100:.1f}%)")
print(f"\n  Note: direction is determined AFTER the explosion, not before.")
print(f"  The squeeze detector alone cannot determine THE direction;")
print(f"  it only says 'a big move is coming'. The NAVE downstream gates")
print(f"  (daily confirm, chase gate, 4H setup, 1H entry) would need to")
print(f"  determine direction on the first expansion bar.")

# Key insight
print(f"\n\n{'='*70}")
print("KEY ARCHITECTURAL INSIGHT")
print(f"{'='*70}")
print("""
The squeeze detector is a REGIME IDENTIFIER, not a direction signal.

Current NAVE flow:
  weekly bias (momentum/range/recovery) → COT → daily confirm → climax → chase → 4H → 1H

Proposed squeeze flow:
  weekly bias = neutral AND squeeze detected on daily → 
    ARM the squeeze mode →
    first daily bar > N× ATR from compression zone →
    determine direction from that bar →
    skip the weekly COT filter (squeeze overrides weekly structure) →
    apply daily confirm (now the direction is known from the breakout) →
    standard downstream (climax, chase, 4H, 1H)

The squeeze mode ARMS the engine (removes the "no weekly bias" barrier)
and the breakout bar DIRECTIONS it (first bar above/below compression
range gives the direction).

This is structurally different from N2 (recovery_detector) which tried
to be both regime+direction. The squeeze detector only does regime;
the breakout bar is direction.
""")

# Check: for each TP event, when does the breakout direction become clear?
print(f"\n{'='*70}")
print("DIRECTION TIMING: For each TP, is the first big bar reliable?")
print(f"{'='*70}")
for e in tps:
    size = e["expansion_up_pct"] - e["expansion_down_pct"]
    actual_dir = "long" if size > 0 else "short"
    print(f"  {e['coin']} {e['squeeze_start']}: first move={actual_dir} "
          f"({'UP' if e['direction'] == 'up' else 'DOWN'} to +{e['expansion_up_pct']:.1f}%) "
          f"({e['duration_days']}d squeeze, bb={e['bb_mean_pct']:.1f}%)")