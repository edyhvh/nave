#!/usr/bin/env python3
"""Walk-forward tune relief-rally thresholds on BTC Apr–Jun 2025 downtrend."""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import data_loader  # noqa: E402
from trading.crypto.analysis.regime import assess_regime  # noqa: E402
from trading.crypto.analysis.regime_config import RegimeConfig, load_regime_config  # noqa: E402
from trading.crypto.cot.cot_analyzer import COTBias  # noqa: E402


START = pd.Timestamp("2025-04-01", tz="UTC")
END = pd.Timestamp("2025-06-15", tz="UTC")
STEP = pd.Timedelta(days=2)


def _mock_cot_bearish() -> COTBias:
    return COTBias(
        asset="BTC",
        net_non_commercial=5000,
        pct_oi_non_com=0.25,
        weekly_change=200,
        bias="bearish",
        confidence=0.72,
        bias_label="BEARISH",
        historical_percentile=96,
    )


def _forward_return(setup: pd.DataFrame, as_of: pd.Timestamp, days: int = 5) -> float | None:
    future = setup.loc[setup.index > as_of].head(days * 6)
    if future.empty:
        return None
    start = float(setup.loc[setup.index <= as_of]["close"].iloc[-1])
    end = float(future["close"].iloc[-1])
    return (end - start) / start


def _score_config(
    daily: pd.DataFrame,
    setup: pd.DataFrame,
    cfg: RegimeConfig,
) -> dict[str, float]:
    cot = _mock_cot_bearish()
    relief_hits = 0
    relief_good = 0
    leg_hits = 0
    ts = START
    while ts <= END:
        d_slice = daily.loc[daily.index <= ts]
        s_slice = setup.loc[setup.index <= ts]
        if len(d_slice) < 30 or len(s_slice) < 60:
            ts += STEP
            continue
        reg = assess_regime(daily=d_slice, setup=s_slice, cot_bias=cot, best_plan=None, config=cfg)
        fwd = _forward_return(s_slice, ts, days=5)
        if reg.phase == "relief_rally_fade" and fwd is not None:
            relief_hits += 1
            if fwd < 0:
                relief_good += 1
        if reg.phase in {"leg_down", "relief_rally_fade", "breakdown_retest"}:
            leg_hits += 1
        ts += STEP
    precision = relief_good / relief_hits if relief_hits else 0.0
    return {
        "relief_hits": relief_hits,
        "relief_precision": precision,
        "leg_coverage": leg_hits,
        "score": precision * 2 + min(relief_hits, 8) * 0.1 + leg_hits * 0.05,
    }


def main() -> int:
    daily = data_loader.load("BTC", "1D", START - pd.Timedelta(days=60), END)
    setup = data_loader.load("BTC", "4H", START - pd.Timedelta(days=30), END)
    if "timestamp" in daily.columns:
        daily = daily.set_index(pd.to_datetime(daily["timestamp"], utc=True))
    if "timestamp" in setup.columns:
        setup = setup.set_index(pd.to_datetime(setup["timestamp"], utc=True))

    base = load_regime_config()
    candidates: list[tuple[RegimeConfig, dict[str, float]]] = []
    for dd in (0.055, 0.065, 0.075):
        for bmin in (0.015, 0.018, 0.025):
            for bmax in (0.16, 0.20, 0.24):
                cfg = replace(
                    base,
                    min_drawdown_from_high=dd,
                    relief_bounce_min=bmin,
                    relief_bounce_max=bmax,
                )
                stats = _score_config(daily, setup, cfg)
                candidates.append((cfg, stats))

    best_cfg, best_stats = max(candidates, key=lambda row: row[1]["score"])
    out = {
        "window": {"start": str(START.date()), "end": str(END.date())},
        "best": {
            "min_drawdown_from_high": best_cfg.min_drawdown_from_high,
            "relief_bounce_min": best_cfg.relief_bounce_min,
            "relief_bounce_max": best_cfg.relief_bounce_max,
            "stats": best_stats,
        },
        "baseline": _score_config(daily, setup, base),
    }

    defaults_path = PROJECT_ROOT / "trading" / "crypto" / "analysis" / "regime_defaults.json"
    payload = json.loads(defaults_path.read_text())
    payload["min_drawdown_from_high"] = best_cfg.min_drawdown_from_high
    payload["relief_bounce_min"] = best_cfg.relief_bounce_min
    payload["relief_bounce_max"] = best_cfg.relief_bounce_max
    defaults_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(out, indent=2))
    print(f"\nUpdated {defaults_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())