#!/usr/bin/env python3
"""Check active BTC/ETH regime theses vs latest price and position review."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from trading.crypto.analysis.regime_thesis import RegimeThesisStore  # noqa: E402
from trading.crypto.analysis.review import review_positions  # noqa: E402


def _load_spot(coin: str) -> float | None:
    try:
        import pandas as pd

        path = PROJECT_ROOT / "data" / "binance_cache" / f"{coin}_1d.parquet"
        if not path.is_file():
            return None
        df = pd.read_parquet(path)
        if "close" in df.columns:
            return float(df["close"].iloc[-1])
        return float(df.iloc[-1]["close"])
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coins", default="BTC ETH")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    coins = [c.strip().upper() for c in args.coins.replace(",", " ").split() if c.strip()]
    store = RegimeThesisStore()
    review = review_positions(coins, include_options=True)
    theses = (store.payload.get("theses") or {})

    lines: list[str] = []
    payload: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "coins": {},
    }

    for rec in review.get("recommendations") or []:
        coin = rec["coin"]
        spot = _load_spot(coin)
        key = f"{coin}:bearish" if rec.get("direction") == "short" else f"{coin}:bullish"
        thesis = theses.get(key) or {}
        inv = thesis.get("invalidation") or rec.get("invalidation")
        status = "ok"
        notes: list[str] = []

        if spot is not None and inv is not None:
            if rec.get("direction") == "short" and spot > float(inv):
                status = "invalidated"
                notes.append(f"spot {spot:,.2f} above invalidation {float(inv):,.2f}")
            elif rec.get("direction") == "long" and spot < float(inv):
                status = "invalidated"
                notes.append(f"spot {spot:,.2f} below invalidation {float(inv):,.2f}")

        entry = rec.get("entry_zone")
        if spot is not None and entry and rec.get("action") == "enter":
            if len(entry) == 1 and spot > float(entry[0]) and rec.get("direction") == "short":
                notes.append("price above single entry — stalk or scale planned")
            elif len(entry) == 1 and spot < float(entry[0]) and rec.get("direction") == "long":
                notes.append("price below single entry — not filled yet")

        coin_out = {
            "spot": spot,
            "action": rec.get("action"),
            "direction": rec.get("direction"),
            "invalidation": inv,
            "thesis": thesis,
            "status": status,
            "notes": notes,
        }
        payload["coins"][coin] = coin_out
        lines.append(f"{coin}: {rec.get('action')} {rec.get('direction')} — thesis {status}")
        if spot is not None:
            lines.append(f"  spot ${spot:,.2f}")
        if inv is not None:
            lines.append(f"  invalidation ${float(inv):,.2f}")
        for note in notes:
            lines.append(f"  • {note}")
        opts = rec.get("options") or {}
        if opts.get("execution_lane"):
            lines.append(f"  options: {opts['execution_lane']}")

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
