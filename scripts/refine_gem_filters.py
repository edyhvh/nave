#!/usr/bin/env python3
"""Tune hidden-gem filters against yearly options replay JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from options.gem_finder import GemFilterConfig, score_replay_row, summarize_filter_experiment  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "yearly_json",
        type=Path,
        nargs="?",
        default=None,
        help="Path to options_yearly_*.json (defaults to latest in docs/analysis/raw)",
    )
    args = parser.parse_args()

    path = args.yearly_json
    if path is None:
        raw = PROJECT_ROOT / "docs/analysis/raw"
        candidates = sorted(raw.glob("options_yearly_*.json"))
        if not candidates:
            print("No yearly JSON found", file=sys.stderr)
            return 1
        path = candidates[-1]

    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("rows") or []
    print(f"Loaded {path.name} — {len(rows)} replay rows")

    configs = [
        ("baseline_all_actionable", GemFilterConfig(
            require_open_recommended=False,
            require_bias_aligned=False,
            allow_bear_calls=True,
            block_high_vol=False,
            min_structure=0.0,
            min_gem_score=0.0,
        )),
        ("v2_bullish_bull_put", GemFilterConfig(
            allow_bear_calls=False,
            require_bias_aligned=True,
            block_high_vol=True,
        )),
        ("v3_production", GemFilterConfig()),
        ("v4_strict_pop", GemFilterConfig(min_pop=65.0, max_touch=68.0, min_structure=55.0)),
    ]

    print("\n=== Filter experiment (yearly replay) ===\n")
    best_name, best_stats = "", {"win_rate": 0.0, "avg_pnl": -99999.0, "trades": 0}
    for name, cfg in configs:
        stats = summarize_filter_experiment(rows, cfg)
        print(
            f"{name:22} trades={stats['trades']:4d} "
            f"win={stats['win_rate']:.1%} avg_pnl=${stats['avg_pnl']:.0f} "
            f"gems={stats['gem_tier_count']}"
        )
        if stats["trades"] >= 15 and (
            stats["win_rate"] > best_stats["win_rate"]
            or (stats["win_rate"] == best_stats["win_rate"] and stats["avg_pnl"] > best_stats["avg_pnl"])
        ):
            best_name, best_stats = name, stats

    print(f"\nRecommended config: {best_name}")
    out = PROJECT_ROOT / "docs/analysis/raw" / "gem_filter_experiment.json"
    out.write_text(
        json.dumps({"source": str(path), "configs": {n: summarize_filter_experiment(rows, c) for n, c in configs}}, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())