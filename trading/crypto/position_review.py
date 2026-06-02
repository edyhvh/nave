"""Deprecated shim — use ``trading.crypto.analysis``."""

from trading.crypto.analysis.review import (  # noqa: F401
    PositionRecommendation,
    review_positions,
)

__all__ = ["PositionRecommendation", "review_positions"]

# Back-compat alias
review_coins = review_positions