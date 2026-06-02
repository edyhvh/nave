"""Fetch max-available Hyperliquid historical candles and persist Parquet snapshots.

Example:
    source .venv/bin/activate
    PYTHONPATH=. python scripts/fetch_hyperliquid_snapshots.py \
        --coins BTC ETH SOL --intervals 1h 4h --max-history --out-dir data/hyperliquid_snapshots
"""

from __future__ import annotations

import argparse
from pathlib import Path
from datetime import datetime, timezone
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from trading.crypto.client import HyperliquidClient  # noqa: E402


def _to_dataframe(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df = df.drop_duplicates(
        subset=["coin", "interval", "timestamp_ms"]).sort_values("timestamp_ms")
    df["timestamp"] = pd.to_datetime(df["timestamp_ms"], unit="ms", utc=True)
    return df


def _save_parquet(df: pd.DataFrame, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)


def _fetch_symbol_interval(
    client: HyperliquidClient,
    coin: str,
    interval: str,
    max_pages: int,
    max_history: bool,
) -> pd.DataFrame:
    if max_history:
        start_ms = 0
    else:
        now_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
        start_ms = now_ms - (365 * 24 * 60 * 60 * 1000)

    rows = client.get_historical_candles(
        coin=coin,
        interval=interval,
        start_time_ms=start_ms,
        end_time_ms=None,
        max_pages=max_pages,
    )
    return _to_dataframe(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch Hyperliquid historical candle snapshots")
    parser.add_argument("--coins", nargs="+", default=["BTC", "ETH", "SOL"])
    parser.add_argument("--intervals", nargs="+", default=["1h", "4h"])
    parser.add_argument("--out-dir", default="data/hyperliquid_snapshots")
    parser.add_argument("--max-pages", type=int, default=250)
    parser.add_argument(
        "--max-history",
        action="store_true",
        help="Fetch max available history (default is last 1 year if omitted)",
    )
    parser.add_argument(
        "--mainnet",
        action="store_true",
        help="Use mainnet candles (recommended). If omitted, testnet is used.",
    )
    parser.add_argument(
        "--wallet",
        default="",
        help="Optional wallet label (not required for candle snapshots)",
    )
    args = parser.parse_args()

    wallet_name = args.wallet or None
    client = HyperliquidClient(
        wallet_name=wallet_name, testnet=not args.mainnet)
    out_dir = Path(args.out_dir)
    fetched_at = datetime.now(tz=timezone.utc)

    print(f"Source: Hyperliquid {'MAINNET' if args.mainnet else 'TESTNET'}")
    print(f"Output: {out_dir}")

    summaries: list[str] = []
    for coin in [c.upper() for c in args.coins]:
        for interval in args.intervals:
            df = _fetch_symbol_interval(
                client=client,
                coin=coin,
                interval=interval,
                max_pages=args.max_pages,
                max_history=args.max_history,
            )

            if df.empty:
                summaries.append(f"{coin} {interval}: 0 rows")
                print(f"[WARN] {coin} {interval}: no candles returned")
                continue

            df["fetched_at"] = fetched_at
            out_path = out_dir / f"{coin}_{interval}.parquet"
            _save_parquet(df, out_path)

            first_ts = df["timestamp"].iloc[0]
            last_ts = df["timestamp"].iloc[-1]
            msg = (
                f"{coin} {interval}: rows={len(df):,} "
                f"range={first_ts.isoformat()} -> {last_ts.isoformat()} file={out_path}"
            )
            summaries.append(msg)
            print(f"[OK] {msg}")

    print("\nSummary")
    for line in summaries:
        print(f"- {line}")


if __name__ == "__main__":
    main()
