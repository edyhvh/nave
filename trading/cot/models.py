"""Data models for COT analysis and weekly planning."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Bias = Literal["bullish", "bearish", "neutral"]


@dataclass(slots=True)
class COTSectionMetrics:
    """Normalized COT section metrics for one report slice."""

    net_non_commercial: int = 0
    net_non_commercial_delta: int = 0
    net_commercial: int = 0
    net_commercial_delta: int = 0
    open_interest: int = 0
    open_interest_delta: int = 0
    pct_oi: float = 0.0
    traders_non_commercial: int | None = None
    traders_commercial: int | None = None


@dataclass(slots=True)
class TradeSetup:
    """One actionable setup recommendation in the weekly plan."""

    name: str
    direction: Literal["long", "short"]
    entry_zone: dict[str, float]
    entry_reference: float
    stop_loss: float
    take_profit_levels: list[dict[str, float | str]]
    recommended_risk_pct: float
    position_size_usd: float
    position_size_coin: float
    notional_usd_10x: float
    rationale: str


@dataclass(slots=True)
class WeeklyAssetPlan:
    """Weekly execution plan for a single asset."""

    asset: str
    bias: Bias
    confidence: float
    bias_explanation: str
    key_levels: dict[str, float] = field(default_factory=dict)
    setups: list[TradeSetup] = field(default_factory=list)
    cot_summary: dict[str, Any] = field(default_factory=dict)
    risk_management_notes: list[str] = field(default_factory=list)
