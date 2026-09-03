#!/usr/bin/env python3
"""Point-in-time diagnostic replay for the 2026 BTC 64k-to-78k miss.

This script is research-only. It never places orders and its COT/theory
ablations are attribution controls, not candidate strategies.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import queue  # noqa: F401  # preload stdlib before adding the repository root
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

with contextlib.redirect_stdout(io.StringIO()):
    from trading.crypto.cot.cot_gate import evaluate_cot_permission, load_cot_history_frame
    from trading.crypto.momentum.config import load_momentum_config
    from trading.crypto.momentum.engine import MomentumSetupEngine
    from trading.crypto.momentum.theory_overlay import build_weekly_frame
    import trading.crypto.momentum.cot_overlay as cot_overlay_module

API_URL = "https://api.hyperliquid.xyz/info"
COT_CACHE = Path.home() / ".cache" / "nave" / "cot" / "history_cot.json"
CASE_START = pd.Timestamp("2026-02-06T00:00:00Z")
CASE_END = pd.Timestamp("2026-04-30T23:59:59Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Optional JSON output path")
    return parser.parse_args()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_default(value: Any) -> Any:
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def fetch_candles(interval: str) -> pd.DataFrame:
    start = int(datetime(2025, 9, 1, tzinfo=timezone.utc).timestamp() * 1000)
    end = int(datetime(2026, 5, 2, tzinfo=timezone.utc).timestamp() * 1000)
    payload = {
        "type": "candleSnapshot",
        "req": {
            "coin": "BTC",
            "interval": interval,
            "startTime": start,
            "endTime": end,
        },
    }
    request = Request(
        API_URL,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=30) as response:
        rows = json.load(response)
    frame = pd.DataFrame(
        {
            "timestamp": [pd.to_datetime(int(row["t"]), unit="ms", utc=True) for row in rows],
            "close_time": [pd.to_datetime(int(row["T"]), unit="ms", utc=True) for row in rows],
            "open": [float(row["o"]) for row in rows],
            "high": [float(row["h"]) for row in rows],
            "low": [float(row["l"]) for row in rows],
            "close": [float(row["c"]) for row in rows],
            "volume": [float(row["v"]) for row in rows],
        }
    ).set_index("timestamp")
    return frame.sort_index()


def cot_history_with_release_times(cache_path: Path = COT_CACHE) -> pd.DataFrame:
    blob = json.loads(cache_path.read_text())
    frame = load_cot_history_frame(blob["BTC|futures_and_options|micro=0"])
    eastern = ZoneInfo("America/New_York")
    releases = []
    for value in frame["report_date"]:
        report_date = pd.Timestamp(value).date()
        release_date = report_date + timedelta(days=3)
        release_local = datetime(
            release_date.year,
            release_date.month,
            release_date.day,
            15,
            30,
            tzinfo=eastern,
        )
        releases.append(pd.Timestamp(release_local.astimezone(timezone.utc)))
    shifted = frame.copy()
    shifted["report_date"] = releases
    return shifted


def at_time(frame: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    return frame.loc[frame["close_time"] <= as_of].drop(columns=["close_time"])


def completed_weekly(daily: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    weekly = build_weekly_frame(daily)
    completed_at = weekly.index + pd.Timedelta(days=1)
    return weekly.loc[completed_at <= as_of]


def compact_plan(plan: Any) -> dict[str, Any]:
    payload = plan.to_dict()
    machine = {item["code"]: item for item in payload["reasoning"]["machine"]}
    theory = payload["diagnostics"].get("theory_overlay", {})
    cot = payload["diagnostics"].get("cot_overlay", {})
    return {
        "setup_status": payload["setup_status"],
        "tradeable": payload["tradeable"],
        "confidence_score": payload["confidence_score"],
        "entry_zone": payload["entry_zone"],
        "invalidation": payload["invalidation"],
        "expected_move_pct": payload["expected_move_pct"],
        "rr_estimated": payload["rr_estimated"],
        "daily_trend": machine["daily_trend"]["passed"],
        "setup_trend": machine["setup_trend"]["passed"],
        "structure": machine["structure"]["passed"],
        "breakout_retest": machine["breakout_retest"]["passed"],
        "volatility": machine["volatility"]["passed"],
        "participation": machine["participation"]["passed"],
        "volume_ratio": machine["participation"]["value"]["volume_ratio"],
        "theory_passed": theory.get("passed"),
        "theory_stage": theory.get("stage"),
        "theory_bias": theory.get("bias"),
        "cot_passed": cot.get("passed"),
        "cot_permission": cot.get("permission"),
        "cot_percentile": cot.get("historical_percentile"),
        "cot_reason": cot.get("reason"),
    }


def run_replay() -> dict[str, Any]:
    cot_history = cot_history_with_release_times()

    def permission_for_side_released(side: str, coin: str, as_of: pd.Timestamp):
        del coin
        permission = evaluate_cot_permission(side, cot_history, as_of)
        percentile = (
            int(permission.abs_percentile * 100)
            if permission.abs_percentile is not None
            else None
        )
        return permission, percentile

    cot_overlay_module.permission_for_side = permission_for_side_released
    frames = {interval: fetch_candles(interval) for interval in ("1d", "4h", "1h")}
    base_config = load_momentum_config()
    configs = {
        "production_gates": base_config,
        "cot_disabled_attribution_only": replace(
            base_config,
            cot_overlay=replace(base_config.cot_overlay, enabled=False),
        ),
        "theory_disabled_attribution_only": replace(
            base_config,
            theory_overlay=replace(base_config.theory_overlay, enabled=False),
        ),
        "cot_and_theory_disabled_attribution_only": replace(
            base_config,
            cot_overlay=replace(base_config.cot_overlay, enabled=False),
            theory_overlay=replace(base_config.theory_overlay, enabled=False),
        ),
    }
    engines = {name: MomentumSetupEngine(config) for name, config in configs.items()}
    scan_times = [
        pd.Timestamp(value)
        for value in frames["4h"]["close_time"]
        if CASE_START <= value <= CASE_END
    ]
    firsts: dict[str, dict[str, Any]] = {name: {} for name in configs}
    checkpoints: list[dict[str, Any]] = []
    checkpoint_hours = {
        pd.Timestamp("2026-02-06T04:00:00Z"),
        pd.Timestamp("2026-03-31T20:00:00Z"),
        pd.Timestamp("2026-04-06T20:00:00Z"),
        pd.Timestamp("2026-04-13T20:00:00Z"),
        pd.Timestamp("2026-04-20T20:00:00Z"),
        pd.Timestamp("2026-04-22T12:00:00Z"),
    }
    evaluated_rows = 0
    for as_of in scan_times:
        daily = at_time(frames["1d"], as_of)
        setup = at_time(frames["4h"], as_of)
        trigger = at_time(frames["1h"], as_of)
        weekly = completed_weekly(daily, as_of)
        for name, engine in engines.items():
            plan = engine.evaluate_symbol(
                symbol="BTCUSDT",
                daily_frame=daily,
                setup_frame=setup,
                trigger_frame=trigger,
                weekly_frame=weekly,
                funding_rate=None,
                open_interest=None,
                side="long",
                as_of=as_of,
                cot_overlay_mode="historical",
            )[0]
            price = float(trigger["close"].iloc[-1])
            row = {
                "as_of": as_of.isoformat(),
                "variant": name,
                "price": price,
                **compact_plan(plan),
            }
            evaluated_rows += 1
            monitor_candidate = row["confidence_score"] >= 75
            tradeable_watch_candidate = row["tradeable"] and monitor_candidate
            same_scan_zone_touch = (
                monitor_candidate
                and row["entry_zone"][0] <= price <= row["entry_zone"][1]
                and price > row["invalidation"]
            )
            conditions = {
                "first_daily_trend": row["daily_trend"],
                "first_breakout_retest": row["breakout_retest"],
                "first_theory_pass": row["theory_passed"],
                "first_cot_pass": row["cot_passed"],
                "first_confirmed": row["setup_status"] == "confirmed",
                "first_tradeable": row["tradeable"],
                "first_monitor_candidate_clean_branch": monitor_candidate,
                "first_tradeable_watch_candidate": tradeable_watch_candidate,
                "first_same_scan_alert_clean_branch": same_scan_zone_touch,
                "first_same_scan_alert_tradeable_only": (
                    same_scan_zone_touch and row["tradeable"]
                ),
            }
            for key, passed in conditions.items():
                if passed and key not in firsts[name]:
                    firsts[name][key] = {
                        "as_of": as_of.isoformat(),
                        **row,
                    }
            if as_of.ceil("h") in checkpoint_hours:
                checkpoints.append(row)

    case_frame = at_time(frames["4h"], CASE_END)
    case_frame = case_frame.loc[case_frame.index >= pd.Timestamp("2026-02-06T00:00:00Z")]
    low_index = case_frame["low"].idxmin()
    move_frame = case_frame.loc[low_index:]
    high_index = move_frame["high"].idxmax()
    config_path = PROJECT_ROOT / "trading/crypto/momentum/defaults.json"
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "classification": "diagnostic_counterfactual_not_strategy_validation",
        "source": {
            "price": f"{API_URL} candleSnapshot BTC",
            "price_rows": {key: len(value) for key, value in frames.items()},
            "cot": str(COT_CACHE),
            "cot_sha256": _sha256(COT_CACHE),
            "config": str(config_path),
            "config_sha256": _sha256(config_path),
            "cot_availability_rule": (
                "report date Tuesday shifted to official Friday 15:30 "
                "America/New_York release time"
            ),
        },
        "data_limitations": [
            (
                "Funding and open interest are unavailable as point-in-time production "
                "snapshots; replay passes None and is not execution-valid."
            ),
            "The current production engine did not exist for the full move.",
            "Only fully closed 1D/4H/1H bars and completed W-SUN weekly bars are eligible.",
            "Ablations disable one or two gates only to attribute suppression.",
        ],
        "case": {
            "start_reference": "2026-02-06T04:00:00+00:00",
            "start_close": 64133.0,
            "first_close_ge_78000": "2026-04-22T12:00:00+00:00",
            "end_close": 78261.0,
            "close_to_close_move_pct": (78261.0 / 64133.0) - 1,
            "observed_low": {
                "timestamp": low_index.isoformat(),
                "price": float(case_frame.loc[low_index, "low"]),
            },
            "observed_high": {
                "timestamp": high_index.isoformat(),
                "price": float(move_frame.loc[high_index, "high"]),
            },
        },
        "firsts": firsts,
        "checkpoints": checkpoints,
        "evaluated_rows": evaluated_rows,
    }


def main() -> int:
    args = parse_args()
    payload = run_replay()
    rendered = json.dumps(payload, indent=2, sort_keys=True, default=_json_default)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
