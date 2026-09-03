#!/usr/bin/env python3
"""
N3 cross-asset confirmation — A/B backtest.

Hypothesis (pre-registered before running): a sub-threshold directional weekly
velocity (|velocity| >= 0.5 ATR but < min_velocity 1.2) can be accepted as bias
WHEN the other coin's weekly momentum bias agrees in direction. Targets the N1
blind spot (gradual recoveries oscillate near zero velocity) without reusing
the rejected recovery-detector approach. This is a SOFT confirmation: it only
ADDS trades; existing baseline trades are untouched.

Pre-registered criteria (vs re-captured baseline +27.69R pooled):
- ACCEPT: pooled in-sample total R > +27.69 AND pooled WR not lower by more
  than 1pp AND no period drops > 2R unless another rises by 4R+ AND OOS 2026
  treatment >= control.
- INCONCLUSIVE: pooled R improves but WR drops > 1pp.
- REJECT: everything else.

Usage:
    python scripts/n3_cross_asset_confirm_ab.py [--coins BTC ETH] [--oos-only]
        [--min-velocity 0.5]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import data_loader  # noqa: E402
from data_loader import DataNotFoundError  # noqa: E402

from trading.crypto.cot.cot_gate import load_cached_cot_history  # noqa: E402
from trading.crypto.theory_v2 import TheoryV2Engine, momentum_bias  # noqa: E402

PERIODS: dict[str, tuple[str, str]] = {
    "2017-bull+2018-bear": ("2017-01-01", "2018-12-31"),
    "2019-recovery": ("2019-01-01", "2019-12-31"),
    "2020-covid-crash": ("2020-01-01", "2020-06-30"),
    "2020-recovery+2021-ATH": ("2020-07-01", "2021-12-31"),
    "2022-bear": ("2022-01-01", "2022-12-31"),
    "2023-recovery": ("2023-01-01", "2023-12-31"),
    "2024-ETF-approval": ("2024-01-01", "2024-06-30"),
    "2024-2025-bull": ("2024-07-01", "2025-03-31"),
}
OOS_PERIOD = ("2026-01-01", "2026-08-25")


def _resolve_zc_outcome(h1_forward, direction, entry, sl, targets):
    if h1_forward.empty or not targets:
        return None, 0.0
    risk = abs(entry - sl)
    if risk <= 0:
        return None, 0.0
    zc1 = targets[0]
    zc2 = targets[1] if len(targets) > 1 else zc1
    zc1_hit = False
    trail_sl = sl
    for _, row in h1_forward.iterrows():
        high = float(row["high"])
        low = float(row["low"])
        if direction == "long":
            if not zc1_hit and low <= sl:
                return "incorrect", -1.0
            if zc1_hit and low <= trail_sl:
                return "correct", 0.8 * (zc1 - entry) / risk + 0.2 * (trail_sl - entry) / risk
            if not zc1_hit and high >= zc1:
                zc1_hit = True
                trail_sl = entry
            if zc1_hit and high >= zc2:
                return "correct", 0.8 * (zc1 - entry) / risk + 0.2 * (zc2 - entry) / risk
        else:
            if not zc1_hit and high >= sl:
                return "incorrect", -1.0
            if zc1_hit and high >= trail_sl:
                return "correct", 0.8 * (entry - zc1) / risk + 0.2 * (entry - trail_sl) / risk
            if not zc1_hit and low <= zc1:
                zc1_hit = True
                trail_sl = entry
            if zc1_hit and low <= zc2:
                return "correct", 0.8 * (entry - zc1) / risk + 0.2 * (entry - zc2) / risk
    if zc1_hit:
        zc1_reward = abs(zc1 - entry) / risk
        last_close = float(h1_forward["close"].iloc[-1])
        trail_reward = (
            (last_close - entry) / risk if direction == "long" else (entry - last_close) / risk
        )
        return "correct", 0.8 * zc1_reward + 0.2 * trail_reward
    return None, 0.0


def _walk(coin, start, end, engine, oos=False):
    warmup = 140 if oos else 120
    try:
        weekly = data_loader.load(coin, "1W", start - pd.Timedelta(days=warmup * 7), end)
        daily = data_loader.load(coin, "1D", start - pd.Timedelta(days=warmup), end)
        h4 = data_loader.load(coin, "4H", start - pd.Timedelta(days=warmup), end)
        h1 = data_loader.load(
            coin, "1H", start - pd.Timedelta(days=warmup), end + pd.Timedelta(days=14)
        )
    except DataNotFoundError as exc:
        return {"skipped": True, "reason": str(exc)}

    stats = {
        "fired": 0, "correct": 0, "incorrect": 0, "unresolved": 0, "total_r": 0.0,
        "bias_sources": {},
        "trades": [],
    }
    weeks = pd.date_range(start=start, end=end, freq="W-MON", tz="UTC")
    for week_start in weeks:
        decision = engine.evaluate(
            coin,
            weekly[weekly["timestamp"] <= week_start],
            daily[daily["timestamp"] <= week_start],
            h4[h4["timestamp"] <= week_start],
            h1[h1["timestamp"] <= week_start],
            as_of=week_start,
        )
        if decision.signal is None:
            continue
        sig = decision.signal
        entry = float(sig.metadata["entry_price"])
        sl = float(sig.invalidation)
        targets = [float(t) for t in sig.targets]
        direction = sig.direction.value
        bias_source = sig.metadata.get("bias_source", "momentum")
        forward = h1[
            (h1["timestamp"] > week_start)
            & (h1["timestamp"] <= week_start + pd.Timedelta(days=14))
        ]
        outcome, pnl = _resolve_zc_outcome(forward, direction, entry, sl, targets)
        stats["fired"] += 1
        stats["total_r"] += pnl
        stats["bias_sources"][bias_source] = stats["bias_sources"].get(bias_source, 0) + 1
        if outcome == "correct":
            stats["correct"] += 1
        elif outcome == "incorrect":
            stats["incorrect"] += 1
        else:
            stats["unresolved"] += 1
        stats["trades"].append({
            "week": week_start.strftime("%Y-%m-%d"),
            "direction": direction,
            "bias_source": bias_source,
            "outcome": outcome,
            "pnl_r": round(pnl, 4),
        })
    return stats


def _rep(name, p):
    resolved = p["correct"] + p["incorrect"]
    wr = p["correct"] / resolved if resolved else 0.0
    avg = p["total_r"] / resolved if resolved else 0.0
    return (
        f"{name}: fired={p['fired']} resolved={resolved} WR={wr*100:.1f}% "
        f"totalR={p['total_r']:+.2f} avgR={avg:+.3f}"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--coins", nargs="+", default=["BTC", "ETH"])
    ap.add_argument("--oos-only", action="store_true")
    ap.add_argument("--min-velocity", type=float, default=0.5)
    args = ap.parse_args()

    btc_cot = load_cached_cot_history("BTC")

    def _cot(_c, _a):
        return btc_cot

    # Full weekly frames for the other-bias provider (no look-ahead: sliced to as_of).
    def _load_weekly(coin):
        return data_loader.load(
            coin, "1W", pd.Timestamp("2016-08-01", tz="UTC"), pd.Timestamp("2026-08-25", tz="UTC")
        )

    weekly_all = {c: _load_weekly(c) for c in args.coins}

    def _other_bias(coin: str, as_of: pd.Timestamp) -> str:
        others = [c for c in args.coins if c != coin]
        if len(others) != 1:
            return "neutral"
        frame = weekly_all[others[0]]
        sub = frame[frame["timestamp"] <= as_of]
        bias, _ = momentum_bias(sub)
        return bias

    control = TheoryV2Engine(cot_history_fn=_cot)
    treat = TheoryV2Engine(
        cot_history_fn=_cot,
        cross_asset_fn=_other_bias,
        cross_confirm_min_velocity=args.min_velocity,
    )

    results = {
        "coins": args.coins,
        "cross_confirm_min_velocity": args.min_velocity,
        "periods": {},
        "oos": {},
    }

    if not args.oos_only:
        for period, (s, e) in PERIODS.items():
            start, end = pd.Timestamp(s, tz="UTC"), pd.Timestamp(e, tz="UTC")
            results["periods"][period] = {}
            print(f"--- {period} ---")
            for coin in args.coins:
                c = _walk(coin, start, end, control)
                t = _walk(coin, start, end, treat)
                results["periods"][period][coin] = {"control": c, "treatment": t}
                if c.get("skipped") or t.get("skipped"):
                    print(f"  {coin}: SKIPPED")
                    continue
                print(f"  {coin} control   : {_rep('', c)}")
                print(f"  {coin} treatment : {_rep('', t)}")
                print(f"       treatment bias_sources: {t['bias_sources']}")
                print(f"       delta R: {t['total_r'] - c['total_r']:+.2f}")

    s, e = OOS_PERIOD
    start, end = pd.Timestamp(s, tz="UTC"), pd.Timestamp(e, tz="UTC")
    print(f"\n--- OUT-OF-SAMPLE {s} -> {e} (N1 blind spot window) ---")
    for coin in args.coins:
        c = _walk(coin, start, end, control, oos=True)
        t = _walk(coin, start, end, treat, oos=True)
        results["oos"][coin] = {"control": c, "treatment": t}
        print(f"  {coin} control   : {_rep('', c)}")
        print(f"  {coin} treatment : {_rep('', t)}")
        print(f"       treatment bias_sources: {t.get('bias_sources', {})}")
        print(f"       delta R: {t['total_r'] - c['total_r']:+.2f}")

    if not args.oos_only:
        keys = ("fired", "correct", "incorrect", "unresolved", "total_r")
        pooled = {
            arm: {k: 0.0 for k in keys} for arm in ("control", "treatment")
        }
        for period in results["periods"].values():
            for coin in args.coins:
                for arm in ("control", "treatment"):
                    p = period.get(coin, {}).get(arm, {})
                    for k in keys:
                        pooled[arm][k] += p.get(k, 0)
        print("\n=== POOLED IN-SAMPLE A/B ===")
        print(f"  control   : {_rep('', pooled['control'])}")
        print(f"  treatment : {_rep('', pooled['treatment'])}")
        d = pooled["treatment"]["total_r"] - pooled["control"]["total_r"]
        rc = pooled["control"]["correct"] + pooled["control"]["incorrect"]
        rt = pooled["treatment"]["correct"] + pooled["treatment"]["incorrect"]
        wrc = pooled["control"]["correct"] / rc if rc else 0.0
        wrt = pooled["treatment"]["correct"] / rt if rt else 0.0
        print(f"  deltaR={d:+.2f}  WR {wrc*100:.1f}% -> {wrt*100:.1f}% ({(wrt-wrc)*100:+.1f}pp)")
        results["pooled"] = pooled

    out = PROJECT_ROOT / "docs" / "analysis" / "raw"
    out.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = out / f"n3_cross_asset_confirm_ab_{ts}.json"
    path.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nWrote {path.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
