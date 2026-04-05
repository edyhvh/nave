"""Onchain crypto metrics service."""

from datetime import datetime, timezone
from typing import Any, Dict


def fetch_onchain_metrics(coin_id: str) -> Dict[str, Any]:
    """Fetch onchain metrics for a given coin (mock for now)."""
    # TODO: Implement real onchain data from blockchain or API
    return {
        "coin_id": coin_id,
        "active_addresses": 125000,
        "transaction_volume": 450000000,
        "tvl": 1250000000,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "source": "onchain",
    }
