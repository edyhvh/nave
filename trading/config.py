"""Shared trading configuration constants.

Keep COT setup defaults centralized so strategy/backtest/CLI paths read the
same source of truth before Setup Learning is introduced.
"""

from __future__ import annotations

DEFAULT_SETUPS = [
    "75_retracement",
    "order_block",
    "fvg",
    "liquidity_sweep",
    "breaker_block",
]

ALL_KNOWN_SETUPS = list(DEFAULT_SETUPS)

# COT is the main weekly driver; other indicators modulate entries/risk.
COT_PRIMARY_WEIGHT = 0.75
