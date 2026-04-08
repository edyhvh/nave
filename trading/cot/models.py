"""Data models for COT analysis and weekly planning.

Philosophy (per CriptoPana):
    The COT report is ONLY a record of past positioning — it is NOT a
    predictive tool.  Commercials are hedgers (defensive), non-commercials
    are speculators (offensive).  The COT should never be used in isolation;
    it must always require strong confluence with 4H price structure before
    any setup is generated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Bias = Literal["bullish", "bearish", "neutral"]
Confluence = Literal["strong", "partial", "none"]

COT_DISCLAIMER = (
    "COT data is a lagging report of past trader positioning (released with "
    "a 3-day delay). It is NOT a predictive signal. All setups require live "
    "4H price structure confirmation before execution. Never trade COT in "
    "isolation."
)


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
    """One conditional setup recommendation — only valid with structure confluence."""

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
    """Weekly directional context and conditional execution plan for one asset.

    ``structure_confluence`` determines whether setups are emitted:
        - ``"strong"``  — 4H trend aligns with COT context AND price is near
          a key IPDA level.  2-3 setups are generated.
        - ``"partial"`` — 4H trend aligns but price is mid-range.  1
          conservative setup is generated.
        - ``"none"``    — 4H opposes COT context or structure is unknown.
          No setups are generated.
    """

    asset: str
    bias: Bias
    confidence: float
    bias_explanation: str
    structure_confluence: Confluence = "none"
    disclaimer: str = COT_DISCLAIMER
    key_levels: dict[str, float] = field(default_factory=dict)
    setups: list[TradeSetup] = field(default_factory=list)
    cot_summary: dict[str, Any] = field(default_factory=dict)
    risk_management_notes: list[str] = field(default_factory=list)
