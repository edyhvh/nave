"""Typed domain models for options analysis."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class OptionContract:
    """Normalized option contract row."""

    ticker: str
    contract_symbol: str
    option_type: str
    expiration: str
    strike: float
    last_price: float
    bid: float
    ask: float
    mid_price: float
    volume: int
    open_interest: int
    implied_volatility: float
    in_the_money: bool
    last_trade_date: str | None
    spread_pct: float
    liquidity_score: float
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None


@dataclass(frozen=True)
class StrategyLeg:
    """One strategy leg (option or stock)."""

    instrument_type: str
    side: str
    quantity: int
    premium: float
    strike: float | None = None
    option_type: str | None = None


@dataclass(frozen=True)
class StrategyCandidate:
    """A fully specified options strategy candidate."""

    name: str
    expiration: str
    days_to_expiration: int
    legs: list[StrategyLeg]
    net_premium: float
    max_profit: float | None
    max_loss: float | None
    breakeven_points: list[float]
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class StrategyMetrics:
    """Quantitative scoring metrics for a strategy."""

    pop: float
    expected_value: float
    expected_profit: float
    expected_loss: float
    risk_reward: float
    max_loss: float
    theta_per_day: float
    vega_exposure: float
    probability_of_touch: float
    profit_range_low: float
    profit_range_high: float
    composite_score: float


@dataclass(frozen=True)
class StrategyRecommendation:
    """Strategy candidate with computed metrics."""

    strategy: StrategyCandidate
    metrics: StrategyMetrics
    pnl_samples: list[float]
    tradeoff_comment: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["pnl_samples"] = self.pnl_samples[:250]
        return payload


@dataclass(frozen=True)
class CacheSnapshotMetadata:
    """Persistent metadata for a parquet chain snapshot."""

    ticker: str
    fetched_at: datetime
    path: str
    underlying_price: float
    expirations: list[str]
    row_count: int
    source: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["fetched_at"] = self.fetched_at.isoformat()
        return data
