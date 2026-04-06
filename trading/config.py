"""Shared trading configuration constants.

Keep COT setup defaults centralized so strategy/backtest/CLI paths read the
same source of truth before Setup Learning is introduced.
"""

from __future__ import annotations

DEFAULT_SETUPS = [
    "75_retracement",
    "order_block",
]

# Negative-expectancy setups removed from defaults (backtest evidence):
# - fvg: predicted_pnl=-$39.89, win_prob=34.6%
# - liquidity_sweep: avg_pnl=-$41.83, win_rate=44.4%
# - breaker_block: avg_pnl=-$21.67, win_rate=40.6%
ALL_KNOWN_SETUPS = [
    "75_retracement",
    "order_block",
    "fvg",
    "liquidity_sweep",
    "breaker_block",
]

# COT is the main weekly driver; other indicators modulate entries/risk.
COT_PRIMARY_WEIGHT = 0.75
