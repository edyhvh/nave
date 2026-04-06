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
    # Fixed income rates ───────────────────────────────────────────────────────
    "fed_funds": {
        "type": "fixedincome_rate",
        "symbol": "effr",
        "label": "Federal Funds Rate",
        "description": "Effective federal funds rate (%).",
    },
    "dgs10": {
        "type": "fixedincome_rate",
        "symbol": "dgs10",
        "label": "10-Year Treasury Rate",
        "description": "US 10-year Treasury constant maturity rate (%).",
    },
    # Yield curve spreads ─────────────────────────────────────────────────────
    "yield_curve_10y_2y": {
        "type": "yield_curve_spread",
        "long_symbol": "dgs10",
        "short_symbol": "dgs2",
        "label": "10Y-2Y Yield Spread",
        "description": "Spread between 10-year and 2-year Treasury rates. "
        "Negative = inverted curve (recession indicator).",
    },
}
