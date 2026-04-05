"""AAII sentiment service for investor sentiment data."""

from datetime import datetime, timezone
from typing import Any, Dict


def fetch_aaii_sentiment() -> Dict[str, Any]:
    """Fetch AAII investor sentiment data (mock for now)."""
    # TODO: Implement real data fetch from AAII or proxy
    return {
        "bullish": 0.45,
        "neutral": 0.30,
        "bearish": 0.25,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "source": "aaii",
    }
