#!/usr/bin/env python3
"""Record or mark forward outcomes for ``nave options daily`` recommendations."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from options.forward_tracker import (  # noqa: E402
    mark_open_recommendations,
    record_daily_recommendations,
    render_tracker_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    rec = sub.add_parser("record", help="Record picks from a saved daily JSON report")
    rec.add_argument(
        "report",
        type=Path,
        nargs="?",
        help="Path to hidden_gems / options daily JSON (default: latest in reports/)",
    )

    mark = sub.add_parser("mark", help="Mark open recommendations through today")
    mark.add_argument(
        "--offsets",
        default="1,3,5,7",
        help="Comma-separated days since entry to mark",
    )
    mark.add_argument("--as-of", type=str, default=None, help="YYYY-MM-DD exit date")

    args = parser.parse_args()

    if args.command == "record":
        path = args.report
        if path is None:
            reports = sorted(
                (PROJECT_ROOT / "data" / "options_cache" / "reports").glob(
                    "hidden_gems_*_options_report_*.json"
                ),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if not reports:
                print("No hidden_gems report found under data/options_cache/reports/")
                return 1
            path = reports[0]
            print(f"Using latest report: {path}")

        payload = json.loads(path.read_text(encoding="utf-8"))
        result = record_daily_recommendations(payload)
        print(
            f"Recorded {result['recommendation_count']} recommendations → {result['path']}"
        )
        return 0

    offsets = [int(part.strip()) for part in args.offsets.split(",") if part.strip()]
    as_of = (
        date.fromisoformat(args.as_of)
        if args.as_of
        else datetime.now(timezone.utc).date()
    )
    summary = mark_open_recommendations(as_of=as_of, offsets_days=offsets)
    print(render_tracker_report(summary))
    if args.as_of is None:
        print(f"\nMarks log: {summary.get('marks_path')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
