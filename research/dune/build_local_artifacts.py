"""Build compact local artifacts from bounded Dune CLI result files."""

from __future__ import annotations

import argparse
import json
from datetime import timezone
from pathlib import Path

from research.dune.panel import (
    dune_rows,
    normalize_proof_events,
    participant_episodes,
    proof_summary,
    write_parquet,
)

UTC = timezone.utc


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", default="data/research/dune/raw/2026-08-27")
    parser.add_argument("--output-root", default="data/research/dune")
    args = parser.parse_args()
    raw = Path(args.raw_root)
    out = Path(args.output_root)
    out.mkdir(parents=True, exist_ok=True)

    launch_rows = dune_rows(raw / "launches.json")
    write_parquet(launch_rows, out / "launches.parquet")
    completeness = dune_rows(raw / "cohort_completeness.json")
    (out / "completeness.json").write_text(json.dumps(completeness[0], indent=2, sort_keys=True) + "\n")

    proof = normalize_proof_events(dune_rows(raw / "proof_token_lifecycle.json"))
    write_parquet(proof, out / "proof_token_lifecycle.parquet")
    launch_ts = next(e["event_ts"] for e in proof if e.get("event_type") == "CREATE")
    summary = proof_summary(proof, launch_ts)
    (out / "proof_token_lifecycle_summary.json").write_text(json.dumps(summary, indent=2, default=str, sort_keys=True) + "\n")

    episodes = participant_episodes(proof, launch_ts)
    write_parquet(episodes, out / "participant_episodes.parquet")
    pnl = {
        "episodes_tested": min(10, len(episodes)),
        "fully_reconstructible": 0,
        "partially_reconstructible": min(10, len(episodes)),
        "not_reconstructible": 0,
        "sample_scope": "10 wallets from one migrated token proof; not a multi-token validation sample",
        "reasons": [
            "Dune proof rows expose token and quote amounts but the selected normalized proof did not carry fee fields into the local FIFO sample.",
            "Open inventory is separated from realized PnL; no unrealized mark is used as profit.",
            "A representative multi-token cohort PnL query was not run after the 500-credit hard stop was exceeded.",
        ],
    }
    (out / "participant_pnl_validation.json").write_text(json.dumps(pnl, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
