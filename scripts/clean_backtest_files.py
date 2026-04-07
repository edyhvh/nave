#!/usr/bin/env python3
"""CLI wrapper for cleaning invalid backtest JSON files."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from trading.utils.clean_backtest_files import clean_backtest_outputs


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Clean backtest summary/snapshot JSON files with fake prices."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("trade_journal"),
        help="Directory containing backtest JSON files (default: trade_journal)",
    )
    parser.add_argument(
        "--archive-dir",
        type=Path,
        default=Path("backtest_archive/invalid"),
        help="Archive directory for invalid files (default: backtest_archive/invalid)",
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Delete invalid files instead of moving to archive directory",
    )
    args = parser.parse_args()
    clean_backtest_outputs(
        output_dir=args.output_dir,
        archive_dir=args.archive_dir,
        delete=args.delete,
        verbose=True,
    )


if __name__ == "__main__":
    main()
