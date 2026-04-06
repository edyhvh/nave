"""Setup learning helpers used by COT strategies.

This module keeps learning logic lightweight for now while providing a stable
interface for strategy-testing and walk-forward workflows.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Optional

from trading.config import DEFAULT_SETUPS


@dataclass
class SetupScore:
    setup: str
    samples: int = 0
    pnl_total: float = 0.0

    @property
    def avg_pnl(self) -> float:
        return self.pnl_total / self.samples if self.samples else 0.0


class SetupLearner:
    """Learns setup rankings from backtest outcomes.

    Expected trade metadata shape (best effort):
    - trade.metadata["setup"]
    - trade.metadata["regime"] (optional)
    - trade.pnl
    """

    def __init__(self, default_setups: Optional[list[str]] = None):
        self.default_setups = list(default_setups or DEFAULT_SETUPS)
        self._scores: dict[str, dict[str, SetupScore]] = defaultdict(dict)

    def fit(self, backtest_results: Any) -> None:
        """Fit setup scores from a BacktestResult-like object."""
        trades = getattr(backtest_results, "trades", []) or []
        for trade in trades:
            metadata = getattr(trade, "metadata", {}) or {}
            if not isinstance(metadata, dict):
                continue

            setup = metadata.get("setup")
            if not setup:
                continue

            regime = metadata.get("regime", "all")
            pnl = float(getattr(trade, "pnl", 0.0) or 0.0)

            regime_scores = self._scores[regime]
            if setup not in regime_scores:
                regime_scores[setup] = SetupScore(setup=setup)

            score = regime_scores[setup]
            score.samples += 1
            score.pnl_total += pnl

    def rank_setups(self, setups: list[str], regime: Optional[str] = None) -> list[str]:
        """Rank setups by learned average pnl, preserving unknown setup order."""
        regime_key = regime or "all"
        regime_scores = self._scores.get(regime_key, {})

        if not regime_scores:
            return list(setups)

        indexed = {name: idx for idx, name in enumerate(setups)}

        def sort_key(setup_name: str) -> tuple[float, int]:
            score = regime_scores.get(setup_name)
            avg = score.avg_pnl if score else float("-inf")
            return (-avg, indexed.get(setup_name, 10_000))

        return sorted(setups, key=sort_key)