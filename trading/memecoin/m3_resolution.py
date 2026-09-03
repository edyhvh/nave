"""Data-integrity helpers for the read-only M3 forward-observation loop.

The cron driver lives under ``var/`` because its journal is runtime state. The
parser is kept in the governed Nave source tree so a deployment/rebuild cannot
silently lose the malformed-provider-response fix.
"""

RESOLVED = "RESOLVED"
DEAD = "DEAD"
UNEXITABLE = "UNEXITABLE"
DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
LEGACY_UNKNOWN = "LEGACY_UNKNOWN"
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


def pair_for_resolution(pairs, expected_pair_address=None):
    """Select the entry pool, never silently replacing it with a new venue.

    A missing expected address is an unexitable outcome, while an absent/invalid
    provider payload remains the caller's data-availability concern.
    """
    valid = [
        pair for pair in (pairs or [])
        if isinstance(pair, dict) and pair.get("chainId") == "solana"
    ]
    if not expected_pair_address:
        return None
    return next(
        (pair for pair in valid if pair.get("pairAddress") == expected_pair_address),
        None,
    )
