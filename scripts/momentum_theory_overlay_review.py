#!/usr/bin/env python3
"""Replay and tune the momentum theory overlay against latest artifacts."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _load_overlay_review_helpers():
    module_path = PROJECT_ROOT / "trading" / "crypto" / "momentum" / "theory_overlay_review.py"
    module_name = "momentum_theory_overlay_review_helpers"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load overlay review helpers from {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return (
        module.evaluate_overlay_replay,
        module.sweep_overlay_parameters,
        module.write_overlay_review_markdown,
    )


def _parse_float_csv(value: str | None) -> list[float] | None:
    if not value:
        return None
    return [float(chunk.strip()) for chunk in value.split(",") if chunk.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay and tune the momentum theory overlay")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON to stdout")
    parser.add_argument("--sweep", action="store_true", help="run parameter sweep mode")
    parser.add_argument("--periods", nargs="+", help="optional named periods to evaluate")
    parser.add_argument(
        "--chase-min-retrace-values",
        help="comma-separated list for sweep mode (example: 0.1,0.12,0.15,0.18,0.2)",
    )
    parser.add_argument(
        "--chase-min-expected-move-pct-values",
        help="comma-separated list for sweep mode (example: 0.08,0.1,0.12)",
    )
    args = parser.parse_args(argv)

    evaluate_overlay_replay, sweep_overlay_parameters, write_overlay_review_markdown = _load_overlay_review_helpers()
    raw_dir = PROJECT_ROOT / "docs" / "analysis" / "raw"

    if args.sweep:
        payload = sweep_overlay_parameters(
            raw_dir,
            periods=args.periods,
            chase_min_retrace_values=_parse_float_csv(args.chase_min_retrace_values),
            chase_min_expected_move_pct_values=_parse_float_csv(args.chase_min_expected_move_pct_values),
        )
        md_path = PROJECT_ROOT / "docs" / "analysis" / "momentum_theory_overlay_sweep.md"
        json_path = raw_dir / "momentum_theory_overlay_sweep_latest.json"
    else:
        payload = evaluate_overlay_replay(raw_dir, periods=args.periods)
        md_path = PROJECT_ROOT / "docs" / "analysis" / "momentum_theory_overlay_replay.md"
        json_path = raw_dir / "momentum_theory_overlay_replay_latest.json"

    write_overlay_review_markdown(payload, md_path)
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    response = {
        "artifacts": {
            "markdown": str(md_path.relative_to(PROJECT_ROOT)),
            "json": str(json_path.relative_to(PROJECT_ROOT)),
        },
        "summary": payload,
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