"""
Execution planning for refined 4H / 1H theory-aligned entries.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from trading.crypto.signals import Direction, Signal, Timeframe


@dataclass
class ExecutionPlan:
    coin: str
    direction: Direction
    bias_timeframe: Timeframe
    setup_timeframe: Timeframe
    trigger_timeframe: Timeframe
    entry_price: float
    invalidation_price: float
    targets: list[float] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def risk_distance(self) -> float:
        if self.direction == Direction.LONG:
            return self.entry_price - self.invalidation_price
        return self.invalidation_price - self.entry_price


def build_execution_plan(signal: Signal) -> ExecutionPlan | None:
    """
    Convert a timeframe-aware signal into a concrete 4H/1H execution plan.

    Long/short entries require:
      - weekly or daily bias context
      - 4H setup declaration
      - 1H trigger declaration
      - entry price in metadata["entry_price"]
      - invalidation price on the signal
    """
    if signal.direction not in (Direction.LONG, Direction.SHORT):
        return None
    if signal.setup_timeframe != Timeframe.H4:
        raise ValueError("execution entries must declare a 4H setup timeframe")
    if signal.trigger_timeframe != Timeframe.H1:
        raise ValueError("execution entries must declare a 1H trigger timeframe")
    if signal.bias_timeframe not in (Timeframe.WEEKLY, Timeframe.DAILY):
        raise ValueError("execution entries must declare weekly or daily bias context")

    entry_price = signal.metadata.get("entry_price")
    if entry_price is None:
        raise ValueError("execution entries require metadata['entry_price']")
    if signal.invalidation is None:
        raise ValueError("execution entries require an invalidation price")

    plan = ExecutionPlan(
        coin=signal.coin,
        direction=signal.direction,
        bias_timeframe=signal.bias_timeframe,
        setup_timeframe=signal.setup_timeframe,
        trigger_timeframe=signal.trigger_timeframe,
        entry_price=float(entry_price),
        invalidation_price=float(signal.invalidation),
        targets=[float(target) for target in signal.targets],
        notes=list(signal.metadata.get("notes", [])),
    )
    if plan.risk_distance <= 0:
        raise ValueError("execution entry must have a positive risk distance")
    return plan
