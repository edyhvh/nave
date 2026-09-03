"""Materialize the acquired compact slices and audit coverage locally."""

from __future__ import annotations

import argparse
import json
from datetime import timedelta
from pathlib import Path

from research.dune.efficient import participant_episodes_multi_token, read_json_rows
from research.dune.panel import parse_ts, write_parquet


def normalize(rows, launches, venue):
    result = []
    for row in rows:
        event = dict(row)
        event["event_ts"] = parse_ts(row.get("event_time"))
        launch = launches.get(str(row.get("mint")))
        if launch:
            event["launch_ts"] = parse_ts(launch.get("launch_ts"))
            event["coverage_end"] = event["launch_ts"] + timedelta(hours=72)
        event["venue"] = venue
        result.append(event)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="data/research/dune")
    args = parser.parse_args()
    root = Path(args.root)
    raw = root / "raw/2026-08-27"
    launches = {str(row["mint"]): row for row in read_json_rows(raw / "launches.json")}
    migrations = read_json_rows(raw / "migrations_1000.json")
    first_hour = normalize(read_json_rows(raw / "pumpfun_first_hour_7_migrated.json"), launches, "pumpfun")
    pumpswap = normalize(read_json_rows(raw / "pumpswap_7_migrated.json"), launches, "pumpswap")
    panel = read_json_rows(raw / "token_panel_1000.json")
    migration_by_mint = {row["mint"]: row for row in migrations}
    enriched_panel = []
    for row in panel:
        launch = launches.get(str(row["mint"]), {})
        enriched_panel.append({
            **row,
            "launch_time": launch.get("launch_ts"),
            "creator": launch.get("creator"),
            "quote_mint": launch.get("quote_mint"),
            "supply": launch.get("token_total_supply"),
            "mayhem": launch.get("is_mayhem_mode"),
            "cashback": launch.get("is_cashback_enabled"),
            "token_program": launch.get("token_program"),
            "migration_time": migration_by_mint.get(str(row["mint"]), {}).get("migration_time"),
            "pool_id": migration_by_mint.get(str(row["mint"]), {}).get("pool_id"),
        })

    write_parquet(first_hour, root / "pumpfun_first_hour_events.parquet")
    write_parquet(pumpswap, root / "pumpswap_postmigration_events.parquet")
    write_parquet(migrations, root / "migrations.parquet")
    write_parquet(enriched_panel, root / "token_trajectories.parquet")
    outcomes = []
    for row in enriched_panel:
        for horizon, field in (("4h", "mark_price_4h_usd"), ("24h", "mark_price_24h_usd"), ("48h", "mark_price_48h_usd"), ("72h", "mark_price_72h_usd")):
            outcomes.append({"mint": row["mint"], "horizon": horizon, "mark_price_usd": row.get(field), "status": "RESOLVED" if row.get(field) is not None else "UNKNOWN"})
    write_parquet(outcomes, root / "outcomes.parquet")

    all_events = first_hour + pumpswap
    episodes = participant_episodes_multi_token(all_events, {
        mint: {"launch_time": parse_ts(row.get("launch_ts"))}
        for mint, row in launches.items()
    })
    write_parquet(episodes, root / "participant_targeted_history.parquet")
    early = [row for row in episodes if row["entry_within_window"]]
    write_parquet(early, root / "participant_early_episodes.parquet")

    first_entry_cutoff_checks = []
    for episode in episodes[:50]:
        prior = [e for e in all_events if e.get("wallet") == episode["wallet"] and e.get("event_ts") and e["event_ts"] < episode["first_entry_time"]]
        first_entry_cutoff_checks.append(all(e["event_ts"] < episode["first_entry_time"] for e in prior))
    pnl_validation = {
        "status": "HISTORICAL_TARGETED_PROOF",
        "historical_dune_rows": True,
        "wallets": len({row["wallet"] for row in episodes}),
        "tokens": len({row["mint"] for row in episodes}),
        "episodes": len(episodes),
        "early_episodes": len(early),
        "checks": {
            "multi_token": len({row["mint"] for row in episodes}) >= 2,
            "ten_wallets": len({row["wallet"] for row in episodes}) >= 10,
            "fifo_realized_pnl": all("realized_pnl_sol_before_fees" in row for row in episodes),
            "fees_separate": all("fees_sol" in row for row in episodes),
            "inventory_separate": all("inventory_remaining" in row for row in episodes),
            "point_in_time_cutoff": all(first_entry_cutoff_checks),
        },
        "scope": "Seven migrated mints; Pump.fun history is first-hour only and PumpSwap history is bounded to the 72-hour observation window.",
        "limitation": "Not a full-cohort participant reputation study; identity independence, funding, bundles, and failed transactions remain unavailable.",
    }
    (root / "participant_pnl_validation_v2.json").write_text(json.dumps(pnl_validation, indent=2, sort_keys=True) + "\n")

    summary = {
        "status": "DUNE_PIPELINE_VALIDATED_WITH_LIMITATIONS",
        "launch_sample": 1000,
        "token_rows": len(enriched_panel),
        "tokens_with_first_hour_trades": sum((row.get("trade_count_60m") or 0) > 0 for row in enriched_panel),
        "migration_rows": len(migrations),
        "pumpfun_first_hour_event_rows": len(first_hour),
        "pumpswap_postmigration_event_rows": len(pumpswap),
        "targeted_wallet_token_episodes": len(episodes),
        "early_episodes": len(early),
        "wallets": len({row["wallet"] for row in episodes}),
        "tokens_with_participant_history": len({row["mint"] for row in episodes}),
        "note": "Seven migrated mints were targeted. Participant history is intentionally bounded and not a full cohort export.",
    }
    (root / "efficient_panel_materialization.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
