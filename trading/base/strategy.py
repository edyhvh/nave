"""
Asset-agnostic strategy scaffold.

``AbstractStrategy`` is the smallest useful base for any signal-driven
strategy regardless of asset class. It does not assume a ``SignalAggregator``
or a directional signal model — subclasses choose how to translate their
compute step into broker calls.

The Hyperliquid-specific ``trading.crypto.strategy.BaseStrategy`` predates
this layer and stays unchanged to avoid rewriting its aggregation logic;
new asset classes should prefer this scaffold.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from trading.base.broker import BaseBroker

logger = logging.getLogger(__name__)


class AbstractStrategy(ABC):
    """
    Minimal strategy contract.

    Lifecycle:
        strategy = MyStrategy(broker=...)
        result   = strategy.run_once()  # returns a dict summary

    Subclasses implement:
        compute() — read the world, decide what to do, return a plan
        execute(plan) — route the plan through ``self.broker``
    """

    def __init__(self, broker: BaseBroker, *, dry_run: bool = True):
        self.broker = broker
        self.dry_run = dry_run
        if dry_run:
            logger.warning(
                "%s running in DRY-RUN mode — no orders will be submitted.",
                type(self).__name__,
            )

    @abstractmethod
    def compute(self) -> Any:
        """Return a strategy-specific plan (dict, list, dataclass, …)."""

    @abstractmethod
    def execute(self, plan: Any) -> Any:
        """Route ``plan`` through ``self.broker``. Respect ``self.dry_run``."""

    def run_once(self) -> dict[str, Any]:
        """Compute → execute → return a minimal summary."""
        plan = self.compute()
        result = self.execute(plan)
        return {
            "strategy": type(self).__name__,
            "broker": self.broker.name,
            "dry_run": self.dry_run,
            "plan": plan,
            "result": result,
        }
