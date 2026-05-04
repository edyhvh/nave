from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from trading.crypto.momentum.config import MomentumConfig


@dataclass(frozen=True)
class PositionSizing:
    account_equity: float
    risk_pct: float
    risk_usd: float
    stop_pct: float
    notional_usd: float
    recommended_leverage: float
    max_leverage: float

    def to_dict(self) -> dict[str, float]:
        return {
            "account_equity": round(self.account_equity, 2),
            "risk_pct": round(self.risk_pct, 4),
            "risk_usd": round(self.risk_usd, 2),
            "stop_pct": round(self.stop_pct, 4),
            "notional_usd": round(self.notional_usd, 2),
            "recommended_leverage": round(self.recommended_leverage, 2),
            "max_leverage": round(self.max_leverage, 2),
        }


@dataclass(frozen=True)
class TradePlan:
    symbol: str
    side: str
    setup_status: str
    entry_zone: list[float]
    invalidation: float
    tp1: float
    tp2: float
    tp3: float
    expected_move_pct: float
    rr_estimated: float
    holding_horizon_estimate: str
    confidence_score: int
    tradeable: bool
    score_breakdown: dict[str, int]
    reasoning: dict[str, list[Any]]
    sizing: dict[str, float]
    leverage_constraints: dict[str, float]
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "setup_status": self.setup_status,
            "entry_zone": [round(value, 6) for value in self.entry_zone],
            "invalidation": round(self.invalidation, 6),
            "tp1": round(self.tp1, 6),
            "tp2": round(self.tp2, 6),
            "tp3": round(self.tp3, 6),
            "expected_move_pct": round(self.expected_move_pct, 4),
            "rr_estimated": round(self.rr_estimated, 3),
            "holding_horizon_estimate": self.holding_horizon_estimate,
            "confidence_score": self.confidence_score,
            "tradeable": self.tradeable,
            "score_breakdown": self.score_breakdown,
            "reasoning": self.reasoning,
            "sizing": self.sizing,
            "leverage_constraints": self.leverage_constraints,
            "diagnostics": self.diagnostics,
        }


def recommend_position_sizing(
    *,
    symbol: str,
    entry_price: float,
    invalidation: float,
    account_equity: float,
    risk_pct: float,
    config: MomentumConfig,
) -> PositionSizing:
    if account_equity <= 0:
        raise ValueError("account_equity must be positive")
    bounded_risk_pct = min(max(risk_pct, config.risk.min_risk_pct), config.risk.max_risk_pct)
    stop_pct = abs(entry_price - invalidation) / entry_price if entry_price else 0.0
    if stop_pct <= 0:
        raise ValueError("entry_price and invalidation must produce a positive stop distance")
    risk_usd = account_equity * bounded_risk_pct
    notional = risk_usd / stop_pct
    default_leverage, max_leverage = config.risk.leverage_profile(symbol)
    suggested = min(max(max(notional / account_equity, 1.0), default_leverage), max_leverage)
    return PositionSizing(
        account_equity=account_equity,
        risk_pct=bounded_risk_pct,
        risk_usd=risk_usd,
        stop_pct=stop_pct,
        notional_usd=notional,
        recommended_leverage=suggested,
        max_leverage=max_leverage,
    )


def holding_horizon(expected_move_pct: float) -> str:
    if expected_move_pct < 0.1:
        return "intraday"
    if expected_move_pct < 0.18:
        return "1-3 days"
    return "3-5 days"