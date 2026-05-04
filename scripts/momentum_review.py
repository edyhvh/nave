#!/usr/bin/env python3
"""Build a cross-regime markdown review from the latest momentum artifacts."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _load_review_helpers():
    review_path = PROJECT_ROOT / "trading" / "crypto" / "momentum" / "review.py"
    module_name = "momentum_review_helpers"
    spec = importlib.util.spec_from_file_location(module_name, review_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load momentum review helpers from {review_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module.build_review_summary, module.write_review_markdown


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the latest cross-regime momentum review")
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit a machine-readable JSON payload to stdout",
    )
    args = parser.parse_args(argv)

    build_review_summary, write_review_markdown = _load_review_helpers()
    raw_dir = PROJECT_ROOT / "docs" / "analysis" / "raw"
    summary = build_review_summary(raw_dir)
    md_path = PROJECT_ROOT / "docs" / "analysis" / "momentum_historical_review.md"
    json_path = raw_dir / "momentum_review_latest.json"
    write_review_markdown(summary, md_path)
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    response = {
        "artifacts": {
            "markdown": str(md_path.relative_to(PROJECT_ROOT)),
            "json": str(json_path.relative_to(PROJECT_ROOT)),
        },
        "summary": summary,
    }

    if args.json:
        json.dump(response, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    print(f"wrote {md_path.relative_to(PROJECT_ROOT)}")
    print(f"wrote {json_path.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())