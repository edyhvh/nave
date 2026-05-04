#!/usr/bin/env python3
"""Run the momentum strategy against one historical regime and persist results.

Usage:
    python scripts/momentum_backtest.py --period 2022-bear --symbols BTC ETH
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def _load_workflow_helpers():
    workflow_path = PROJECT_ROOT / "trading" / "crypto" / "momentum" / "workflow.py"
    module_name = "momentum_workflow_helpers"
    spec = importlib.util.spec_from_file_location(module_name, workflow_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load momentum workflow helpers from {workflow_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return (
        module.render_period_summary,
        module.run_period_backtest,
        module.write_iteration_report,
        module.write_period_artifact,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the momentum backtest for one historical period")
    parser.add_argument("--period", required=True, help="named historical period or TODAY")
    parser.add_argument("--symbols", nargs="+", default=["BTC", "ETH"], help="coins to evaluate")
    parser.add_argument(
        "--trigger-timeframe",
        default="1H",
        choices=["1H", "15m", "15M"],
        help="trigger timeframe used inside the momentum backtester",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit a machine-readable JSON payload to stdout",
    )
    args = parser.parse_args(argv)

    trigger_tf = args.trigger_timeframe.upper()
    if trigger_tf == "15M":
        trigger_tf = "15m"

    render_period_summary, run_period_backtest, write_iteration_report, write_period_artifact = _load_workflow_helpers()

    execution_stream = sys.stderr if args.json else sys.stdout
    with contextlib.redirect_stdout(execution_stream):
        payload = run_period_backtest(
            args.period,
            symbols=args.symbols,
            trigger_timeframe=trigger_tf,
        )
        output = write_period_artifact(payload)
        iteration_path = write_iteration_report(payload, output)
    response = {
        "artifacts": {
            "backtest_json": _display_path(output),
            "iteration_report": _display_path(iteration_path),
        },
        "result": payload,
    }

    if args.json:
        json.dump(response, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    print(render_period_summary(payload))
    print(f"wrote {_display_path(output)}")
    print(f"iteration note {_display_path(iteration_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())