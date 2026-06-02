#!/usr/bin/env python3
"""Run strategy iterations until merge-readiness gates pass (or max rounds)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _load_dotenv() -> None:
    env = PROJECT_ROOT / ".env"
    if not env.is_file():
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(env)


def main() -> int:
    _load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-rounds", type=int, default=5)
    parser.add_argument("--replay-json", type=Path, default=None)
    parser.add_argument("--backtest", action="store_true")
    parser.add_argument("--no-gems", action="store_true")
    args = parser.parse_args()

    from options.strategy_loop import run_strategy_iteration

    replay = args.replay_json
    if replay is None:
        raw = PROJECT_ROOT / "docs" / "analysis" / "raw"
        candidates = sorted(raw.glob("options_yearly_*.json"))
        replay = candidates[-1] if candidates else None

    for round_num in range(1, args.max_rounds + 1):
        print(f"\n========== Iteration round {round_num}/{args.max_rounds} ==========")
        result = run_strategy_iteration(
            replay_json=replay,
            run_backtest=args.backtest and round_num == 1,
            run_gems=not args.no_gems,
        )
        merge = result.get("merge_readiness") or {}
        counts = merge.get("counts") or {}
        print(
            f"Merge: ready={merge.get('ready_to_merge')} "
            f"approved={counts.get('approved')} watch={counts.get('watch')} "
            f"reject={counts.get('reject')}"
        )
        print(f"Report: {result['report_md']}")
        if merge.get("ready_to_merge"):
            print("\n✓ Strategy is merge-ready.")
            ready_path = PROJECT_ROOT / "docs" / "analysis" / "MERGE_READY.md"
            ready_path.write_text(
                "\n".join(
                    [
                        "# Per-ticker strategy — merge ready",
                        "",
                        f"Verified in round {round_num}.",
                        f"Report: `{result['report_md']}`",
                        "",
                        "## Approved for production playbook",
                        "",
                        ", ".join(merge.get("approved_tickers") or []),
                        "",
                        "## Watch (half size / paper)",
                        "",
                        ", ".join(merge.get("watch_tickers") or []),
                    ]
                ),
                encoding="utf-8",
            )
            print(f"Wrote {ready_path}")
            return 0
        for blocker in merge.get("blockers") or []:
            print(f"  blocker: {blocker}")

    print("\nNot merge-ready after max rounds — review latest iteration report.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())