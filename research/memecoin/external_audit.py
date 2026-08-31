"""Reproducible local audit for the external-research iteration.

This script reads only the existing targeted Parquet panel and the small
RED-COHORT reproducibility archive. It intentionally does not download or
query a provider.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from research.memecoin.research_primitives import (
    build_cooccurrence_cohorts,
    participant_excluded_outcomes,
    validate_feature_derivability,
)


ROOT = Path(__file__).resolve().parents[2]
DUNE = ROOT / "data/research/dune"
EXTERNAL = ROOT / "data/research/external"


def _rows(path: Path) -> list[dict[str, Any]]:
    return pq.read_table(path).to_pylist()


def _local_first_buyer_ranks(events: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    ranks: dict[str, dict[str, int]] = defaultdict(dict)
    ordered = sorted(events, key=lambda row: (
        row["mint"], row["event_ts"], row.get("slot", 2**63),
        row.get("tx_index", 2**31), row.get("outer_instruction_index", 2**31),
        row.get("inner_instruction_index", 2**31), row.get("transaction", ""),
    ))
    for row in ordered:
        if row.get("side") != "buy":
            continue
        mint, wallet = str(row["mint"]), str(row["wallet"])
        ranks[mint].setdefault(wallet, len(ranks[mint]) + 1)
    return ranks


def _red_cohort_summary(path: Path) -> dict[str, Any]:
    catalogue = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    wallets = {wallet for cohort in catalogue for wallet in cohort.get("wallets", [])}
    sizes = [int(cohort["cohort_size"]) for cohort in catalogue]
    return {
        "catalogue_rows": len(catalogue),
        "unique_wallets": len(wallets),
        "cohort_size_min": min(sizes) if sizes else None,
        "cohort_size_max": max(sizes) if sizes else None,
        "size_distribution": {str(size): sizes.count(size) for size in sorted(set(sizes))},
        "published_structure_reproduced": False,
        "reproduction_limit": "released intra file contains co-fire groups, not the complete buyer-event input expected by the detector",
    }


def run() -> dict[str, Any]:
    events = _rows(DUNE / "pumpfun_first_hour_events.parquet")
    ranks = _local_first_buyer_ranks(events)
    for row in events:
        row["buyer_rank"] = ranks[str(row["mint"])].get(str(row["wallet"]))
    triggers = {
        mint: {wallet for wallet, rank in wallet_ranks.items() if rank <= 10}
        for mint, wallet_ranks in ranks.items()
    }
    bounded = [
        row for row in events
        if (row["event_ts"] - row["launch_ts"]).total_seconds() < 1800
    ]
    contamination = {
        mint: participant_excluded_outcomes(
            [row for row in bounded if row["mint"] == mint], {mint: wallets}
        )
        for mint, wallets in sorted(triggers.items())
    }
    aggregate = {}
    for category in ("raw", "exogenous", "participant_self_flow"):
        fields = contamination[next(iter(contamination))][category]
        aggregate[category] = {
            field: sum(result[category][field] for result in contamination.values())
            for field in fields
        }
    cohort = build_cooccurrence_cohorts(events, min_shared_launches=2)
    derivability = validate_feature_derivability([
        {"feature": "on_chain_event", "available_at": row["event_ts"], "decision_time": row["event_ts"]}
        for row in events[:20]
    ])
    red_path = EXTERNAL / "red_cohort/release/RED-COHORT-2026-v1/sniper_cohorts.jsonl"
    return {
        "local_panel": {
            "events": len(events),
            "mints": len({row["mint"] for row in events}),
            "first_buyer_trigger_wallets": sum(len(wallets) for wallets in triggers.values()),
            "cooccurrence_cohorts_min_shared_2": len(cohort["cohorts"]),
            "cooccurrence_edges_min_shared_2": len(cohort["edges"]),
        },
        "contamination_30m": aggregate,
        "derivability_sample": {key: value for key, value in derivability.items() if key != "rows"},
        "red_cohort": _red_cohort_summary(red_path) if red_path.exists() else {"status": "not_downloaded"},
        "interpretation": "methodology proof only; no participant signal or causal claim from one day and seven targeted mints",
    }


if __name__ == "__main__":
    output = EXTERNAL / "external_audit_summary.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    summary = run()
    encoded = json.dumps(summary, indent=2, sort_keys=True, default=str)
    output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
