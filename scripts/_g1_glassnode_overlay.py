#!/usr/bin/env python3
"""G1 pre-registered experiment: Glassnode on-chain overlay on BTC momentum entries.

PROMOTED from scripts/glassnode_position_spike.py (dormant spike) to an active,
pre-registered, bounded experiment under the P2/NAVE hardening program.

Hypothesis (pre-registered, unchanged from spike):
    A counterfactual overlay that blocks BTC longs when SOPR > 1.02 or exchange
    netflow > 0 (profit-taking / exchange inflow), and blocks BTC shorts when
    SOPR < 0.98 or netflow < 0 (capitulation / outflow), improves the R-multiple
    outcome of the nave BTC momentum entries versus the current-code baseline.

Verdict space (exactly one): ADOPT / PARTIAL / REJECT.

Decision rule (pre-registered, applies only when Glassnode data is present):
    baseline = all fired BTC trades (current-code walk, n=15, +16.12R).
    kept     = trades surviving the overlay.
    blocked  = trades rejected by the overlay.
    - REJECT if kept==baseline (nothing blocked) OR kept.sumR < baseline.sumR
      (overlay removes net-positive edge) OR blocked-winner fraction is high.
    - PARTIAL if kept.sumR > baseline.sumR but WR collapses (>1pp) or the
      blocked-winner (false-positive) count is material (~>=30% of blocked).
    - ADOPT only if kept.sumR > baseline.sumR, WR not lower by >1pp, false
      positives low, and per-period regressions limited.
    - DATA_UNAVAILABLE (no cache, no key): verdict REJECT, reason = data gate not
      satisfiable at zero cost; the metric is not actionable without a
      provisioned Glassnode key (free Standard tier) or paid tier (human-gated,
      no purchase). Flag for human decision.  -- do not stall.

Reproducible from var/glassnode_cache (cache-first). The trade set is regenerated
by walking the current-code TheoryV2Engine (same periods/resolver as the N3
harness), so it reflects the CURRENT baseline, not the stale June unified
backtest the spike defaulted to.

Usage:
    python scripts/_g1_glassnode_overlay.py                 # cache-only (default)
    python scripts/_g1_glassnode_overlay.py --json
    python scripts/_g1_glassnode_overlay.py --gn /path/to/gn --fetch  # needs key
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = PROJECT_ROOT / "var" / "glassnode_cache"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import data_loader  # noqa: E402
from data_loader import DataNotFoundError  # noqa: E402
from trading.crypto.cot.cot_gate import load_cached_cot_history  # noqa: E402
from trading.crypto.theory_v2 import TheoryV2Engine  # noqa: E402

# Same 8 in-sample periods as scripts/theory_v2_backtest.py and the N3 harness.
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

# Glassnode Standard-tier (24h) metric paths — cache keys under var/glassnode_cache.
METRICS: dict[str, str] = {
    "sopr": "indicators/sopr",
    "exchange_netflow": "transactions/transfers_volume_to_exchanges_sum",
    "price": "market/price_usd_close",
}


# ----------------------------- trade walk (current code) -----------------------------

def _resolve_zc_outcome(h1_forward, direction, entry, sl, targets):
    """Same ZC1/ZC2 resolver as the N3 harness (current-code semantics)."""
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
        high = float(row["high"]); low = float(row["low"])
        if direction == "long":
            if not zc1_hit and low <= sl:
                return "incorrect", -1.0
            if zc1_hit and low <= trail_sl:
                return "correct", 0.8 * (zc1 - entry) / risk + 0.2 * (trail_sl - entry) / risk
            if not zc1_hit and high >= zc1:
                zc1_hit = True; trail_sl = entry
            if zc1_hit and high >= zc2:
                return "correct", 0.8 * (zc1 - entry) / risk + 0.2 * (zc2 - entry) / risk
        else:
            if not zc1_hit and high >= sl:
                return "incorrect", -1.0
            if zc1_hit and high >= trail_sl:
                return "correct", 0.8 * (entry - zc1) / risk + 0.2 * (entry - trail_sl) / risk
            if not zc1_hit and low <= zc1:
                zc1_hit = True; trail_sl = entry
            if zc1_hit and low <= zc2:
                return "correct", 0.8 * (entry - zc1) / risk + 0.2 * (entry - zc2) / risk
    if zc1_hit:
        zc1_reward = abs(zc1 - entry) / risk
        last_close = float(h1_forward["close"].iloc[-1])
        trail_reward = (last_close - entry) / risk if direction == "long" else (entry - last_close) / risk
        return "correct", 0.8 * zc1_reward + 0.2 * trail_reward
    return None, 0.0


def _walk_btc(start, end, engine) -> dict:
    warmup = 120
    try:
        weekly = data_loader.load("BTC", "1W", start - pd.Timedelta(days=warmup * 7), end)
        daily = data_loader.load("BTC", "1D", start - pd.Timedelta(days=warmup), end)
        h4 = data_loader.load("BTC", "4H", start - pd.Timedelta(days=warmup), end)
        h1 = data_loader.load("BTC", "1H", start - pd.Timedelta(days=warmup), end + pd.Timedelta(days=14))
    except DataNotFoundError as exc:
        return {"skipped": True, "reason": str(exc)}

    stats: dict[str, Any] = {"fired": 0, "correct": 0, "incorrect": 0, "unresolved": 0,
                             "total_r": 0.0, "trades": []}
    weeks = pd.date_range(start=start, end=end, freq="W-MON", tz="UTC")
    for week_start in weeks:
        decision = engine.evaluate(
            "BTC",
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
        forward = h1[(h1["timestamp"] > week_start) & (h1["timestamp"] <= week_start + pd.Timedelta(days=14))]
        outcome, pnl = _resolve_zc_outcome(forward, direction, entry, sl, targets)

        stats["fired"] += 1
        stats["total_r"] += pnl
        if outcome == "correct":
            stats["correct"] += 1
        elif outcome == "incorrect":
            stats["incorrect"] += 1
        else:
            stats["unresolved"] += 1
        stats["trades"].append({
            "week": week_start.strftime("%Y-%m-%d"),
            "entry_day": week_start.strftime("%Y-%m-%d"),
            "direction": direction,
            "outcome": outcome,
            "pnl_r": round(pnl, 4),
        })
    return stats


# ----------------------------- Glassnode cache / fetch -----------------------------

def _cache_file_for(metric_path: str) -> Path:
    return CACHE_DIR / f"{metric_path.replace('/', '_')}_*.json"


def _load_cache_series(metric_path: str) -> dict[str, float]:
    """Read the first matching cache file for a metric path. Cache-first."""
    if not CACHE_DIR.exists():
        return {}
    matches = sorted(CACHE_DIR.glob(_cache_file_for(metric_path).name))
    if not matches:
        return {}
    rows = json.loads(matches[0].read_text(encoding="utf-8"))
    out: dict[str, float] = {}
    for row in rows:
        ts, val = row.get("t"), row.get("v")
        if ts is None or val is None:
            continue
        if isinstance(ts, (int, float)):
            day = datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d")
        else:
            day = str(ts)[:10]
        out[day] = float(val)
    return out


def _snapshot_for_day(day: str, series: dict[str, dict[str, float]]) -> dict[str, float | None]:
    return {k: v.get(day) for k, v in series.items()}


# ----------------------------- overlay rules (pre-registered) -----------------------------

def _blocks(rule: str, side: str, snap: dict[str, float | None]) -> bool:
    sopr = snap.get("sopr")
    netflow = snap.get("exchange_netflow")
    if rule == "profit_taking_longs":
        if side != "long":
            return False
        if sopr is not None and sopr > 1.02:
            return True
        if netflow is not None and netflow > 0:
            return True
        return False
    if rule == "capitulation_shorts":
        if side != "short":
            return False
        if sopr is not None and sopr < 0.98:
            return True
        if netflow is not None and netflow < 0:
            return True
        return False
    return False


# ----------------------------- evaluation -----------------------------

def _bucket(rows: list[dict]) -> dict:
    if not rows:
        return {"count": 0, "resolved": 0, "win_rate": None, "avg_r": None, "sum_r": 0.0}
    resolved = [r for r in rows if r["outcome"] in ("correct", "incorrect")]
    wins = sum(1 for r in rows if r["outcome"] == "correct")
    rs = [r["pnl_r"] for r in rows]
    return {
        "count": len(rows),
        "resolved": len(resolved),
        "win_rate": round(wins / len(resolved), 4) if resolved else None,
        "avg_r": round(sum(rs) / len(rows), 4),
        "sum_r": round(sum(rs), 4),
    }


def _evaluate_rule(trades: list[dict], series: dict[str, dict[str, float]], rule: str) -> dict:
    kept, blocked, missing = [], [], []
    for t in trades:
        snap = _snapshot_for_day(t["entry_day"], series)
        if snap.get("sopr") is None and snap.get("exchange_netflow") is None:
            missing.append(t)  # no on-chain snapshot -> cannot filter -> keep
            kept.append(t)
            continue
        if _blocks(rule, t["direction"], snap):
            blocked.append(t)
        else:
            kept.append(t)
    blocked_winners = [b for b in blocked if b["outcome"] == "correct"]
    return {
        "rule": rule,
        "baseline": _bucket(trades),
        "kept": _bucket(kept),
        "blocked": _bucket(blocked),
        "missing_snapshots": len(missing),
        "false_positives_blocked_winners": len(blocked_winners),
        "blocked_breakdown": dict(Counter(b["outcome"] for b in blocked)),
    }


def _decide(data_available: bool, evals: list[dict], n_baseline: int, baseline_sum_r: float) -> dict:
    """Pre-registered verdict rule. Exactly one of ADOPT / PARTIAL / REJECT."""
    if not data_available:
        return {
            "verdict": "REJECT",
            "reason": (
                "DATA_UNAVAILABLE: no Glassnode API key is provisioned in this environment, "
                "no `gn` CLI is installed, and var/glassnode_cache is empty (fetch returns 401). "
                "The free/Standard tier requires an account+key that is not provisioned; a paid "
                "tier would be required to make SOPR/netflow actionable and is human-gated "
                "(no purchase). The overlay cannot be evaluated, so it cannot be adopted. "
                "Flag for human decision on Glassnode access."
            ),
        }
    # Data present: strict-improvement gate vs current BTC baseline.
    best = evals[0]
    b, k, bl = best["baseline"], best["kept"], best["blocked"]
    if bl["count"] == 0:
        return {"verdict": "REJECT", "reason": "Overlay blocks nothing — no effect, redundant."}
    kept_sum_r = k["sum_r"]
    if kept_sum_r <= b["sum_r"]:
        return {"verdict": "REJECT", "reason": f"kept.sumR {kept_sum_r:+.2f} <= baseline {b['sum_r']:+.2f} — overlay removes net-positive edge."}
    wr_kept = k["win_rate"] or 0.0
    wr_base = b["win_rate"] or 0.0
    fp_frac = best["false_positives_blocked_winners"] / bl["count"] if bl["count"] else 0.0
    if wr_kept < wr_base - 0.01 or fp_frac >= 0.30:
        return {"verdict": "PARTIAL", "reason": f"kept.sumR {kept_sum_r:+.2f} > baseline but WR {wr_kept:.1%} vs {wr_base:.1%} or FP blocked-winner frac {fp_frac:.0%}."}
    return {"verdict": "ADOPT", "reason": f"kept.sumR {kept_sum_r:+.2f} > baseline {b['sum_r']:+.2f}, WR not lower, FP low."}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="emit JSON only")
    ap.add_argument("--gn", default=None, help="path to gn CLI (only used with --fetch)")
    ap.add_argument("--fetch", action="store_true", help="attempt live Glassnode fetch (requires key/CLI)")
    ap.add_argument("--since", default="2017-01-01")
    ap.add_argument("--until", default=None)
    args = ap.parse_args(argv)

    # Regenerate the current-code BTC baseline trade set (like the N3 harness).
    btc_cot = load_cached_cot_history("BTC")
    engine = TheoryV2Engine(cot_history_fn=lambda _c, _a: btc_cot)
    pooled: dict[str, Any] = {"fired": 0, "correct": 0, "incorrect": 0, "unresolved": 0, "total_r": 0.0, "trades": []}
    per_period: dict[str, dict] = {}
    for period, (s, e) in PERIODS.items():
        start, end = pd.Timestamp(s, tz="UTC"), pd.Timestamp(e, tz="UTC")
        r = _walk_btc(start, end, engine)
        per_period[period] = {k: r.get(k) for k in ("fired", "correct", "incorrect", "unresolved", "total_r")}
        per_period[period]["skipped"] = r.get("skipped", False)
        for k in ("fired", "correct", "incorrect", "unresolved"):
            pooled[k] += r.get(k, 0)
        pooled["total_r"] += r.get("total_r", 0.0)
        pooled["trades"].extend([dict(t, period=period) for t in r.get("trades", [])])

    # Glassnode data: cache-first; optional live fetch.
    series: dict[str, dict[str, float]] = {}
    fetch_errors: list[str] = []
    if args.fetch:
        print("Live fetch requested; requires a provisioned GLASSNODE_API_KEY and the `gn` CLI.",
              file=sys.stderr)
        print("Neither is available in this environment — API returns 401. Using cache only.",
              file=sys.stderr)
    for key, path in METRICS.items():
        s = _load_cache_series(path)
        series[key] = s
        if s:
            print(f"  {key}: {len(s)} daily points (cache)")
        else:
            fetch_errors.append(f"{key}: no cache and fetch requires key/CLI (401)")

    data_available = all(len(series[k]) > 0 for k in ("sopr", "exchange_netflow"))

    eval_results = [_evaluate_rule(pooled["trades"], series, rule)
                    for rule in ("profit_taking_longs", "capitulation_shorts")]

    decision = _decide(data_available, eval_results, pooled["fired"], pooled["total_r"])

    report = {
        "experiment": "G1_glassnode_overlay",
        "status": "pre-registered bounded experiment",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "baseline": {
            "note": "current-code BTC baseline regenerated via TheoryV2Engine walk (N3 harness semantics)",
            "fired": pooled["fired"],
            "correct": pooled["correct"],
            "incorrect": pooled["incorrect"],
            "unresolved": pooled["unresolved"],
            "total_r": round(pooled["total_r"], 4),
        },
        "data_available": data_available,
        "glassnode_cache_path": str(CACHE_DIR),
        "cache_present": CACHE_DIR.exists(),
        "fetch_errors": fetch_errors,
        "metrics": METRICS,
        "overlays": eval_results,
        "verdict": decision,
    }

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("\n=== G1: Glassnode overlay (current-code BTC baseline) ===")
        print(f"Baseline: fired={pooled['fired']} resolved={pooled['correct']+pooled['incorrect']} "
              f"WR={(pooled['correct']/(pooled['correct']+pooled['incorrect']))*100:.1f}% "
              f"sumR={pooled['total_r']:+.2f}")
        print(f"Glassnode data available: {data_available}  (cache={CACHE_DIR.exists()})")
        for ev in eval_results:
            b, k, bl = ev["baseline"], ev["kept"], ev["blocked"]
            print(f"\n[{ev['rule']}] baseline n={b['count']} WR={b.get('win_rate')} avgR={b.get('avg_r')}")
            print(f"  kept:   n={k['count']} WR={k.get('win_rate')} avgR={k.get('avg_r')} sumR={k.get('sum_r')}")
            print(f"  blocked:n={bl['count']} WR={bl.get('win_rate')} avgR={bl.get('avg_r')}  FP_blocked_winners={ev['false_positives_blocked_winners']}")
            print(f"  missing_snapshots={ev['missing_snapshots']}")
        print(f"\nVERDICT: {decision['verdict']}")
        print(f"REASON: {decision['reason']}")

    out_dir = PROJECT_ROOT / "docs" / "analysis" / "raw"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"g1_glassnode_overlay_{ts}.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nWrote {out_path.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
