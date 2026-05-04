from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import pandas as pd

from trading.crypto.momentum.config import MomentumConfig, load_momentum_config
from trading.crypto.momentum.engine import MomentumSetupEngine
from trading.crypto.momentum.execution_plan import TradePlan
from trading.crypto.momentum.filters import normalize_frame


@dataclass(frozen=True)
class BacktestTrade:
    symbol: str
    side: str
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    entry_price: float
    exit_price: float
    stop_price: float
    tp2_price: float
    realized_move_pct: float
    r_multiple: float
    confidence_score: int
    expected_move_pct: float
    rr_estimated: float
    holding_horizon_estimate: str
    reached_8_pct: bool
    reached_12_pct: bool
    reached_20_pct: bool
    best_move_pct: float
    worst_move_pct: float
    score_breakdown: dict[str, int]
    diagnostics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "entry_time": self.entry_time.isoformat(),
            "exit_time": self.exit_time.isoformat(),
            "entry_price": round(self.entry_price, 6),
            "exit_price": round(self.exit_price, 6),
            "stop_price": round(self.stop_price, 6),
            "tp2_price": round(self.tp2_price, 6),
            "realized_move_pct": round(self.realized_move_pct, 4),
            "r_multiple": round(self.r_multiple, 3),
            "confidence_score": self.confidence_score,
            "expected_move_pct": round(self.expected_move_pct, 4),
            "rr_estimated": round(self.rr_estimated, 3),
            "holding_horizon_estimate": self.holding_horizon_estimate,
            "reached_8_pct": self.reached_8_pct,
            "reached_12_pct": self.reached_12_pct,
            "reached_20_pct": self.reached_20_pct,
            "best_move_pct": round(self.best_move_pct, 4),
            "worst_move_pct": round(self.worst_move_pct, 4),
            "score_breakdown": self.score_breakdown,
            "diagnostics": self.diagnostics,
        }


class MomentumBacktester:
    def __init__(self, config: MomentumConfig | None = None):
        self.config = config or load_momentum_config()
        self.engine = MomentumSetupEngine(self.config)

    def evaluate(
        self,
        *,
        symbol: str,
        daily_frame: pd.DataFrame,
        setup_frame: pd.DataFrame,
        trigger_frame: pd.DataFrame,
        funding_rate: float | None = None,
        open_interest: pd.DataFrame | pd.Series | None = None,
        baseline: bool = False,
    ) -> dict[str, Any]:
        daily = normalize_frame(daily_frame)
        setup = normalize_frame(setup_frame)
        trigger = normalize_frame(trigger_frame)
        trades: list[BacktestTrade] = []
        active_until: pd.Timestamp | None = None

        warmup = max(60, self.config.breakout.lookback_bars + 10)
        for stop in range(warmup, len(setup)):
            setup_slice = setup.iloc[: stop + 1]
            end_time = setup_slice.index[-1]
            if active_until is not None and end_time < active_until:
                continue
            trigger_slice = trigger.loc[trigger.index <= end_time]
            if len(trigger_slice) < warmup:
                continue
            plans = self.engine.evaluate_symbol(
                symbol=symbol,
                daily_frame=daily.loc[daily.index <= end_time],
                setup_frame=setup_slice,
                trigger_frame=trigger_slice,
                funding_rate=None if baseline else funding_rate,
                open_interest=None if baseline else open_interest,
            )
            for plan in plans:
                if not self._should_enter(plan, baseline=baseline):
                    continue
                trade = self._simulate_trade(
                    plan, trigger.loc[trigger.index > end_time])
                if trade is not None:
                    trades.append(trade)
                    active_until = trade.exit_time
                    break

        strategy_metrics = self._metrics(trades)
        baseline_metrics = None
        if not baseline:
            baseline_metrics = self.evaluate(
                symbol=symbol,
                daily_frame=daily,
                setup_frame=setup,
                trigger_frame=trigger,
                funding_rate=funding_rate,
                open_interest=open_interest,
                baseline=True,
            )["metrics"]
        payload = {
            "symbol": symbol,
            "strategy": "momentum_baseline" if baseline else "momentum_breakout_retest",
            "trade_count": len(trades),
            "metrics": strategy_metrics,
            "trades": [trade.to_dict() for trade in trades],
        }
        if baseline_metrics is not None:
            payload["baseline"] = {
                "name": "simple_breakout_alignment",
                "metrics": baseline_metrics,
                "delta": self._delta(strategy_metrics, baseline_metrics),
            }
        return payload

    def _should_enter(self, plan: TradePlan, *, baseline: bool) -> bool:
        if baseline:
            return plan.setup_status in {"confirmed", "pending"}
        return plan.tradeable

    def _simulate_trade(self, plan: TradePlan, future_trigger: pd.DataFrame) -> BacktestTrade | None:
        if future_trigger.empty:
            return None
        horizon = future_trigger.head(self.config.execution.max_holding_bars)
        entry_price = float(
            plan.entry_zone[-1] if plan.side == "long" else plan.entry_zone[0])
        stop_distance = abs(entry_price - plan.invalidation)
        best_move = 0.0
        worst_move = 0.0
        exit_price = float(horizon["close"].iloc[-1])
        exit_time = cast(pd.Timestamp, horizon.index[-1])

        for timestamp, row in horizon.iterrows():
            low = float(row["low"])
            high = float(row["high"])
            close = float(row["close"])
            if plan.side == "long":
                best_move = max(best_move, (high - entry_price) / entry_price)
                worst_move = min(worst_move, (low - entry_price) / entry_price)
                if low <= plan.invalidation:
                    exit_price = plan.invalidation
                    exit_time = cast(pd.Timestamp, timestamp)
                    break
                if high >= plan.tp2:
                    exit_price = plan.tp2
                    exit_time = cast(pd.Timestamp, timestamp)
                    break
            else:
                best_move = max(best_move, (entry_price - low) / entry_price)
                worst_move = min(worst_move, (entry_price - high) / entry_price)
                if high >= plan.invalidation:
                    exit_price = plan.invalidation
                    exit_time = cast(pd.Timestamp, timestamp)
                    break
                if low <= plan.tp2:
                    exit_price = plan.tp2
                    exit_time = cast(pd.Timestamp, timestamp)
                    break
            exit_price = close
            exit_time = cast(pd.Timestamp, timestamp)

        realized_move_pct = ((exit_price - entry_price) / entry_price) if plan.side == "long" else (
            (entry_price - exit_price) / entry_price)
        r_multiple = ((exit_price - entry_price) / stop_distance) if plan.side == "long" else (
            (entry_price - exit_price) / stop_distance)
        return BacktestTrade(
            symbol=plan.symbol,
            side=plan.side,
            entry_time=cast(pd.Timestamp, future_trigger.index[0]),
            exit_time=exit_time,
            entry_price=entry_price,
            exit_price=exit_price,
            stop_price=plan.invalidation,
            tp2_price=plan.tp2,
            realized_move_pct=realized_move_pct,
            r_multiple=r_multiple,
            confidence_score=plan.confidence_score,
            expected_move_pct=plan.expected_move_pct,
            rr_estimated=plan.rr_estimated,
            holding_horizon_estimate=plan.holding_horizon_estimate,
            reached_8_pct=best_move >= 0.08,
            reached_12_pct=best_move >= 0.12,
            reached_20_pct=best_move >= 0.20,
            best_move_pct=best_move,
            worst_move_pct=worst_move,
            score_breakdown=plan.score_breakdown,
            diagnostics=plan.diagnostics,
        )

    def _metrics(self, trades: list[BacktestTrade]) -> dict[str, Any]:
        if not trades:
            return {
                "win_rate": 0.0,
                "expectancy": 0.0,
                "max_drawdown": 0.0,
                "average_realized_move": 0.0,
                "pct_reaching_8": 0.0,
                "pct_reaching_12": 0.0,
                "pct_reaching_20": 0.0,
            }
        winners = [trade for trade in trades if trade.r_multiple > 0]
        cumulative_r = 0.0
        peak = 0.0
        max_drawdown = 0.0
        for trade in trades:
            cumulative_r += trade.r_multiple
            peak = max(peak, cumulative_r)
            max_drawdown = min(max_drawdown, cumulative_r - peak)
        count = len(trades)
        return {
            "win_rate": round(len(winners) / count, 4),
            "expectancy": round(sum(trade.r_multiple for trade in trades) / count, 4),
            "max_drawdown": round(abs(max_drawdown), 4),
            "average_realized_move": round(sum(trade.realized_move_pct for trade in trades) / count, 4),
            "pct_reaching_8": round(sum(1 for trade in trades if trade.reached_8_pct) / count, 4),
            "pct_reaching_12": round(sum(1 for trade in trades if trade.reached_12_pct) / count, 4),
            "pct_reaching_20": round(sum(1 for trade in trades if trade.reached_20_pct) / count, 4),
        }

    def _delta(self, strategy: dict[str, Any], baseline: dict[str, Any]) -> dict[str, float]:
        delta: dict[str, float] = {}
        for key, value in strategy.items():
            baseline_value = baseline.get(key)
            if isinstance(value, (int, float)) and isinstance(baseline_value, (int, float)):
                delta[key] = round(value - baseline_value, 4)
        return delta
