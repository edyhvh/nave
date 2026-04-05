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
                # Try different calls based on API (dynamic extension)
                result = obb.regulators.cftc.cot(
                    symbol=symbol)  # type: ignore[attr-defined]
                df = result.to_df() if hasattr(result, "to_df") else pd.DataFrame(result)
                data[asset] = {
                    "raw": df.to_dict("records") if not df.empty else [],
                    "latest_date": str(df["Report_Date_as_of"].iloc[-1]) if not df.empty and "Report_Date_as_of" in df.columns else str(today.date()),
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


if __name__ == "__main__":
    data = fetch_latest_cot()
    print("COT Data keys:", list(data.keys()))
    for k, v in data.items():
        print(
            f"{k}: {v.get('bias', 'N/A')} (net: {v.get('net_non_commercial', 'N/A')})")
