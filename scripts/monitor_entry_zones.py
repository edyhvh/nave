#!/usr/bin/env python3
"""Monitor momentum entry zones and emit notifications on first touch.

Intended cadence: every 5 minutes via cron/launchd. This script never places
orders; it only detects zone-entry events and emits alerts.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from trading.alerts.entry_zone_monitor import EntryZoneMonitor, build_zone_watch_candidates
from trading.alerts.telegram import TelegramDispatchError, send_markdown_v2_messages
from trading.alerts.zone_watch_state import ZoneWatchStateStore
from trading.crypto.client import HyperliquidClient
from trading.crypto.momentum.formatters import render_entry_zone_alert_markdown_v2
from trading.crypto.momentum.service import MomentumMarketService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Monitor momentum entry-zone touches")
    parser.add_argument("--symbols", default="BTCUSDT,ETHUSDT", help="Comma-separated symbols")
    parser.add_argument("--tf", default="4h,1h", help="setup,trigger timeframe pair")
    parser.add_argument("--score-threshold", type=int, default=75, help="Minimum score for watch candidates")
    parser.add_argument("--account-equity", type=float, default=10000.0, help="Sizing context passed to scan")
    parser.add_argument("--risk-pct", type=float, default=0.005, help="Risk per trade decimal")
    parser.add_argument("--state-path", type=Path, default=None, help="Override state JSON path")
    parser.add_argument("--json", action="store_true", help="Emit JSON payload")
    parser.add_argument("--send-telegram", action="store_true", help="Send alerts to Telegram if token/chat configured")
    return parser.parse_args()


def run_monitor(args: argparse.Namespace) -> dict:
    service = MomentumMarketService()
    payload = service.scan_live(
        symbols=service.parse_symbols(args.symbols),
        timeframes=service.parse_timeframes(args.tf),
        account_equity=args.account_equity,
        risk_pct=args.risk_pct,
        score_threshold=args.score_threshold,
    )

    candidates = build_zone_watch_candidates(payload, min_score=args.score_threshold)
    state_store = ZoneWatchStateStore(path=args.state_path)
    monitor = EntryZoneMonitor(state_store)
    market = HyperliquidClient(wallet_name=None, testnet=False)

    result = monitor.evaluate(
        candidates,
        price_lookup=lambda symbol: market.get_mid(symbol.replace("USDT", "")),
    )

    messages = [render_entry_zone_alert_markdown_v2(alert) for alert in result["alerts"]]
    result["telegram_markdown_v2"] = messages

    if args.send_telegram and messages:
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        responses = send_markdown_v2_messages(messages, token=token, chat_id=chat_id)
        result["telegram_deliveries"] = len(responses)

    result["scan_summary"] = payload.get("summary")
    result["watch_candidates"] = [
        {
            "symbol": candidate.symbol,
            "side": candidate.side,
            "entry_zone": [candidate.entry_zone[0], candidate.entry_zone[1]],
            "invalidation": candidate.invalidation,
            "tp1": candidate.tp1,
            "tp2": candidate.tp2,
            "tp3": candidate.tp3,
            "expected_move_pct": candidate.expected_move_pct,
            "confidence_score": candidate.confidence_score,
            "rr_estimated": candidate.rr_estimated,
            "setup_status": candidate.setup_status,
            "tradeable": candidate.tradeable,
        }
        for candidate in candidates
    ]
    return result


def main() -> int:
    args = parse_args()
    try:
        result = run_monitor(args)
    except TelegramDispatchError as exc:
        print(f"telegram dispatch failed: {exc}", file=sys.stderr)
        return 3
    except Exception as exc:  # noqa: BLE001
        print(f"entry-zone monitor failed: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    print(
        f"entry-zone monitor: candidates={len(result['watch_candidates'])} "
        f"alerts={result['alert_count']}"
    )
    for alert in result["alerts"]:
        print(
            f"  ALERT {alert['symbol']} {alert['side']} "
            f"price={alert['price']:.2f} zone={alert['entry_zone'][0]:.2f}-{alert['entry_zone'][1]:.2f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
