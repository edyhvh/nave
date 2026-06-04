#!/usr/bin/env python3
"""Refresh docs/analysis/current_setup.md from the live operator stack."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from trading.crypto.analysis.current_setup_doc import (  # noqa: E402
    build_current_setup_review,
    render_current_setup_markdown,
)

DEFAULT_OUT = PROJECT_ROOT / "docs" / "analysis" / "current_setup.md"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coins", default="BTC ETH")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--no-options", action="store_true")
    args = parser.parse_args()

    review, theory_by_coin = build_current_setup_review(
        args.coins,
        include_options=not args.no_options,
    )
    markdown = render_current_setup_markdown(review, theory_by_coin=theory_by_coin)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(markdown, encoding="utf-8")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
