"""Data-integrity helpers for the read-only M3 forward-observation loop.

The cron driver lives under ``var/`` because its journal is runtime state. The
parser is kept in the governed Nave source tree so a deployment/rebuild cannot
silently lose the malformed-provider-response fix.
"""

RESOLVED = "RESOLVED"
DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
TEMPORARY_FAILURE = "TEMPORARY_FAILURE"
INVALID_RESPONSE = "INVALID_RESPONSE"
UNRESOLVED = "UNRESOLVED"


def best_solana_pair(pairs):
    """Return the most liquid valid Solana pair, skipping malformed elements."""
    best = None
    for pair in pairs or []:
        if not isinstance(pair, dict) or pair.get("chainId") != "solana":
            continue
        liquidity = pair.get("liquidity")
        if not isinstance(liquidity, dict):
            continue
        try:
            amount = float(liquidity.get("usd"))
        except (TypeError, ValueError):
            continue
        if amount < 0:
            continue
        if best is None or amount > best[1]:
            best = (pair, amount)
    return best
