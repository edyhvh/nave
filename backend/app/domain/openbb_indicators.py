"""OpenBB indicator definitions for the Nave API.

Each entry maps a frontend slug to the OpenBB call parameters required to
fetch that indicator.  The ``type`` field controls which fetcher function is
used in ``app.services.openbb``.
"""
from __future__ import annotations

from typing import Any, Dict

# Mapping of frontend slug → OpenBB call spec
OPENBB_INDICATORS: Dict[str, Dict[str, Any]] = {
    # FRED series ─────────────────────────────────────────────────────────────
    "tga": {
        "type": "fred_series",
        "series_id": "WDTGAL",
        "label": "Treasury General Account",
        "description": "US Treasury cash balance held at the Federal Reserve.",
    },
    "rrp": {
        "type": "fred_series",
        "series_id": "RRPONTSYD",
        "label": "Reverse Repo Facility",
        "description": "Overnight reverse repo facility usage (Fed liquidity drain).",
    },
    "cpi": {
        "type": "fred_series",
        "series_id": "CPIAUCSL",
        "label": "Consumer Price Index (CPI)",
        "description": "All-items CPI for all urban consumers.",
    },
    "pce": {
        "type": "fred_series",
        "series_id": "PCE",
        "label": "Personal Consumption Expenditures",
        "description": "Fed's preferred inflation gauge.",
    },
    "unrate": {
        "type": "fred_series",
        "series_id": "UNRATE",
        "label": "Unemployment Rate",
        "description": "US civilian unemployment rate (%).",
    },
    "payems": {
        "type": "fred_series",
        "series_id": "PAYEMS",
        "label": "Non-farm Payrolls",
        "description": "Total non-farm employees (thousands).",
    },
    "real_gdp": {
        "type": "fred_series",
        "series_id": "GDPC1",
        "label": "Real GDP",
        "description": "Real US GDP, quarterly.",
    },
    "pce_price_index": {
        "type": "fred_series",
        "series_id": "PCEPI",
        "label": "PCE Price Index",
        "description": "Personal consumption expenditures price index.",
    },
    "fed_balance_sheet": {
        "type": "fred_series",
        "series_id": "WALCL",
        "label": "Federal Reserve Total Assets",
        "description": "Weekly Fed balance-sheet total assets.",
    },
    "gold_history": {
        "type": "equity_history",
        "symbol": "GC=F",
        "label": "Gold Futures (USD)",
        "description": "Historical gold futures OHLCV observations via OpenBB/yfinance.",
    },
    "btc_usd": {
        "type": "fred_series",
        "series_id": "CBBTCUSD",
        "label": "Bitcoin Price (USD)",
        "description": "Coinbase Bitcoin price in US dollars.",
    },
    "wti": {
        "type": "fred_series",
        "series_id": "DCOILWTICO",
        "label": "WTI Crude Oil",
        "description": "Daily Cushing, Oklahoma WTI spot price.",
    },
    # Fixed income rates ───────────────────────────────────────────────────────
    "fed_funds": {
        "type": "fixedincome_rate",
        "symbol": "EFFR",
        "label": "Federal Funds Rate",
        "description": "Effective federal funds rate (%).",
    },
    "dgs10": {
        "type": "fixedincome_rate",
        "symbol": "DGS10",
        "label": "10-Year Treasury Rate",
        "description": "US 10-year Treasury constant maturity rate (%).",
    },
    # Yield curve spreads ─────────────────────────────────────────────────────
    "yield_curve_10y_2y": {
        "type": "yield_curve_spread",
        "long_symbol": "DGS10",
        "short_symbol": "DGS2",
        "label": "10Y-2Y Yield Spread",
        "description": "Spread between 10-year and 2-year Treasury rates. "
        "Negative = inverted curve (recession indicator).",
    },
    # Market history. These use the configured OpenBB equity provider and fail
    # explicitly if that provider is unavailable; no fallback/mock is allowed.
    "spy_history": {
        "type": "equity_history",
        "symbol": "SPY",
        "label": "S&P 500 ETF",
        "description": "Historical SPY OHLCV observations.",
    },
    "xle_history": {
        "type": "equity_history",
        "symbol": "XLE",
        "label": "Energy Select Sector ETF",
        "description": "Historical XLE OHLCV observations.",
    },
    "nvda_history": {
        "type": "equity_history",
        "symbol": "NVDA",
        "label": "NVIDIA",
        "description": "Historical NVIDIA OHLCV observations.",
    },
}
