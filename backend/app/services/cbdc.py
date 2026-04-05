"""CBDC data service."""

from datetime import datetime, timezone
from typing import Any, Dict


def fetch_cbdc_data() -> Dict[str, Any]:
    """Fetch CBDC related data (mock for now)."""
    # TODO: Implement real CBDC data fetch
    return {
        "active_projects": 12,
        "adopted_countries": 5,
        "global_status": "exploratory",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "source": "cbdc",
    }
