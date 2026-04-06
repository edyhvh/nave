"""COT Fetcher for CME Commitment of Traders reports.

Downloads latest COT data for BTC (code 133741) and ETH using OpenBB CFTC extension.
Caches weekly reports (released Fridays, analyzed Sundays).
"""
from __future__ import annotations

import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
import json

from openbb import obb

CACHE_DIR = Path.home() / ".cache" / "nave" / "cot"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def fetch_latest_cot() -> Dict[str, Any]:
    """Fetch latest COT for BTC and ETH, with caching."""
    cache_file = CACHE_DIR / "latest_cot.json"
    today = datetime.now()

    # Check cache (valid for 7 days)
    if cache_file.exists():
        with open(cache_file) as f:
            cached = json.load(f)
        cache_date = datetime.fromisoformat(
            cached.get("fetch_date", "2000-01-01"))
        if (today - cache_date).days < 7:
            print("✅ Using cached COT data")
            return cached["data"]

    print("📥 Fetching latest COT reports via OpenBB...")

    data = {}
    try:
        # Use obb.regulators.cftc.cot - adapt for BTC/ETH futures
        # BTC futures COT code ~133741, ETH similar
        for asset, symbol in [("BTC", "BTC"), ("ETH", "ETH")]:
            try:
                # OpenBB extension APIs are dynamically attached; resolve callables safely.
                regulators = getattr(obb, "regulators", None)
                cftc = getattr(regulators, "cftc", None)
                cot = getattr(cftc, "cot", None)
                if not callable(cot):
                    raise AttributeError("OpenBB CFTC COT endpoint is unavailable")

                result: Any = cot(symbol=symbol)
                to_df = getattr(result, "to_df", None)
                df: pd.DataFrame
                if callable(to_df):
                    converted = to_df()
                    if isinstance(converted, pd.DataFrame):
                        df = converted
                    elif isinstance(converted, (list, tuple, dict)):
                        df = pd.DataFrame(converted)
                    else:
                        df = pd.DataFrame()
                elif isinstance(result, pd.DataFrame):
                    df = result
                elif isinstance(result, (list, tuple, dict)):
                    df = pd.DataFrame(result)
                else:
                    df = pd.DataFrame()
                filtered = _filter_asset_rows(df, asset)
                latest_date = str(today.date())
                if not filtered.empty:
                    for date_col in ("report_date_as_yyyy_mm_dd", "Report_Date_as_of"):
                        if date_col in filtered.columns:
                            latest_date = str(filtered[date_col].iloc[-1])
                            break
                data[asset] = {
                    "raw": filtered.to_dict("records") if not filtered.empty else [],
                    "latest_date": latest_date,
                    "symbol": symbol
                }
                print(f"✅ Fetched COT for {asset}")
            except Exception as e_asset:
                print(
                    f"⚠️  COT fetch for {asset} failed: {e_asset}. Using mock for demo.")
                data[asset] = _mock_cot_data(asset)

    except Exception as e:
        print(f"⚠️ OpenBB COT fetch failed: {e}. Using mock data.")
        data = {a: _mock_cot_data(a) for a in ["BTC", "ETH"]}

    # Cache
    cache_data = {
        "fetch_date": today.isoformat(),
        "data": data
    }
    with open(cache_file, "w") as f:
        json.dump(cache_data, f, default=str, indent=2)

    return data


def _mock_cot_data(asset: str) -> Dict:
    """Mock data for development/demo when API fails."""
    is_bullish = asset == "ETH"  # example
    return {
        "raw": [],
        "latest_date": str(datetime.now().date()),
        "symbol": asset,
        "net_non_commercial": 5000 if is_bullish else -3000,
        "pct_oi_non_com": 25.5 if is_bullish else 15.2,
        "change": 1200 if is_bullish else -800,
        "bias": "bullish" if is_bullish else "bearish"
    }


def _filter_asset_rows(df: pd.DataFrame, asset: str) -> pd.DataFrame:
    """Keep only rows relevant to the requested crypto asset."""
    if df.empty:
        return df

    market_col = None
    for candidate in ("market_and_exchange_names", "Market_and_Exchange_Names"):
        if candidate in df.columns:
            market_col = candidate
            break

    if market_col is None:
        return df.tail(260).copy()

    keyword = "BITCOIN" if asset.upper() == "BTC" else "ETHER"
    mask = df[market_col].astype(str).str.upper().str.contains(keyword, na=False)
    filtered = df[mask].copy()
    if filtered.empty:
        return df.tail(260).copy()
    return filtered


if __name__ == "__main__":
    data = fetch_latest_cot()
    print("COT Data keys:", list(data.keys()))
    for k, v in data.items():
        print(
            f"{k}: {v.get('bias', 'N/A')} (net: {v.get('net_non_commercial', 'N/A')})")
