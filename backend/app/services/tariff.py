"""Tariff and trade data service."""

from datetime import datetime, timezone
from typing import Any, Dict


def fetch_tariff_revenue() -> Dict[str, Any]:
    """Fetch tariff revenue data (mock for now)."""
    # TODO: Implement real tariff API integration
    return {
        "revenue": 85000000000,
        "change_pct": 12.5,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "source": "tariff",
    }
