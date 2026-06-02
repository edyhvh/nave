#!/usr/bin/env python3
"""Daily theory v2 scan — single entry point for the Hermes agent.

Runs the theory v2 engine on the configured coin list, pairs the output
with the current strategy context, and either prints the combined JSON
payload to stdout or writes it to ``--out``.

Invocation patterns:

- Manual:      ``python scripts/daily_scan.py``
- Hermes/MCP:  call tools ``theory_v2_scan`` + ``strategy_context`` directly.
- Cron:        ``python scripts/daily_scan.py --out var/reports/daily_scan.json``

The JSON payload is the contract; the human-readable summary is a
convenience for terminal use.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from hermes.integration import HermesNaveIntegration, _default_reports_dir  # noqa: E402


def build_payload(coins: str) -> dict:
    hermes = HermesNaveIntegration()
    review = hermes.position_review(coins=coins, include_options=True)
    scan = hermes.theory_v2_scan(coins=coins)
    context = hermes.strategy_context()
    return {
        "generated_at": review["generated_at"],
        "coins_requested": coins,
        "position_review": review,
        "scan": scan,
        "context": context,
    }


def default_report_path() -> Path:
    return _default_reports_dir() / f"daily_scan_{date.today().isoformat()}.json"


def format_summary(payload: dict) -> str:
    review = payload.get("position_review") or {}
    scan = payload["scan"]
    fires = scan["summary"]["fires"]
    evaluated = scan["summary"]["evaluated"]
    lines = [
        f"Daily BTC/ETH review — {payload['generated_at']}",
        f"Enter: {review.get('summary', {}).get('actionable_count', 0)}  "
        f"Watch: {review.get('summary', {}).get('watch_count', 0)}  "
        f"Aside: {review.get('summary', {}).get('stand_aside_count', 0)}",
        f"Theory v2 fires: {', '.join(fires) if fires else '(none)'}",
        "",
    ]
    for rec in review.get("recommendations", []):
        lines.append(
            f"  {rec['coin']}: {rec['action']} {rec.get('direction') or '-'} "
            f"— {rec.get('primary_source')} "
            f"[{rec.get('regime_phase', '-')}]"
        )
        for reason in rec.get("reasons", [])[:3]:
            lines.append(f"    + {reason}")
        opts = rec.get("options") or {}
        if opts.get("status") == "ready":
            lines.append(
                f"    options: {opts.get('executable_strategy') or opts.get('top_strategy')}"
            )
    lines.append("")
    lines.extend([
        f"Theory v2 trace — evaluated: {', '.join(evaluated) or '(none)'}",
        "",
    ])
    for coin, entry in scan["coins"].items():
        lines.append(f"  {coin}: {entry['stage']:>16} — {entry['reason']}")
        if entry["fired"]:
            sig = entry["signal"]
            lines.append(
                f"    FIRED {sig['direction'].upper()} "
                f"entry={sig['entry_price']} stop={sig['stop_loss']} "
                f"zc1_rr={sig['zc1_rr']} velocity={sig['weekly_velocity_atr']}"
            )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--coins", default="BTC ETH", help="Whitespace-separated coin list")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Override output path. Default: var/reports/daily_scan_YYYY-MM-DD.json",
    )
    parser.add_argument(
        "--no-persist",
        action="store_true",
        help="Skip writing to disk (scan still prints to stdout)",
    )
    parser.add_argument(
        "--format",
        choices=("json", "human", "both"),
        default="both",
        help="stdout format (json for machines, human for terminal)",
    )
    args = parser.parse_args()

    payload = build_payload(args.coins)

    if not args.no_persist:
        out_path = args.out if args.out is not None else default_report_path()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2))
        payload["persisted_to"] = str(out_path)

    if args.format in ("human", "both"):
        print(format_summary(payload))
        if args.format == "both":
            print()
    if args.format in ("json", "both"):
        print(json.dumps(payload, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
