"""Run a descriptive integration proof through the existing M3 layer."""

from __future__ import annotations

import argparse
import json
from datetime import timedelta
from pathlib import Path

from research.dune.panel import dune_rows, normalize_proof_events
from trading.memecoin.m3_dual_horizon import build_trajectory


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", default="data/research/dune/raw/2026-08-27/proof_token_lifecycle.json")
    parser.add_argument("--output", default="data/research/dune/integration_proof.json")
    args = parser.parse_args()
    events = normalize_proof_events(dune_rows(args.raw))
    launch_ts = next(e["event_ts"] for e in events if e.get("event_type") == "CREATE")
    m3_events = [{**event, "event_ts": event["event_ts"].isoformat() if event.get("event_ts") else None} for event in events]
    trajectory = build_trajectory(
        events[0]["mint"], m3_events, launch_ts=launch_ts,
        coverage_end=launch_ts + timedelta(hours=72),
    )
    horizons = {"60m": "60m", "24h": "24h", "72h": "72h"}
    output = {
        "pipeline": "Dune canonical proof -> existing m3_dual_horizon.build_trajectory",
        "strategy_research_run": False,
        "eligible_tokens": 1,
        "complete_60m_trajectories": int(trajectory["intervals"].get("60m", {}).get("coverage") == "RESOLVED"),
        "complete_24h_trajectories": int(trajectory["intervals"].get("24h", {}).get("coverage") == "RESOLVED"),
        "complete_72h_trajectories": int(trajectory["intervals"].get("72h", {}).get("coverage") == "RESOLVED"),
        "trajectory_horizons": {key: trajectory["intervals"].get(value, {}).get("coverage") for key, value in horizons.items()},
        "max_return_descriptive": {
            key: max((trajectory["intervals"].get(key, {}).get("price") or 0) / (trajectory["intervals"].get("30s", {}).get("price") or 1) - 1, 0) * 100
            if trajectory["intervals"].get(key, {}).get("price") and trajectory["intervals"].get("30s", {}).get("price") else None
            for key in ("60m", "24h", "72h")
        },
        "note": "Descriptive wiring proof only; no Burst/Runner label or edge claim is made.",
    }
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
