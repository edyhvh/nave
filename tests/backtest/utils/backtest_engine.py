"""Core backtest engine for strategy validation."""

from typing import List, Dict, Any, Optional, cast
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
import pandas as pd
import numpy as np

from .metrics import calculate_metrics, PerformanceMetrics

logger = logging.getLogger(__name__)


@dataclass
class BacktestConfig:
    """Configuration for backtest run."""
    start_date: datetime
    end_date: datetime
    initial_capital: float = 10000.0
    slippage_pct: float = 0.001  # 0.1%
    trading_fee_pct: float = 0.0005  # 0.05%
    risk_free_rate: float = 0.02  # 2%

    # Risk limits
    max_leverage: float = 10.0
    max_drawdown_pct: float = 0.30
    max_risk_per_trade: float = 0.12


@dataclass
class BacktestResult:
    """Results from a backtest run."""
    config: BacktestConfig
    equity_curve: pd.Series
    trades: List[Any]
    metrics: PerformanceMetrics
    regime_metrics: Dict[str, PerformanceMetrics] = field(default_factory=dict)
    best_params: Dict[str, Any] = field(default_factory=dict)

    def summary(self) -> str:
        """Generate summary report."""
        return f"""
Backtest Summary
===============
Period: {self.config.start_date.date()} to {self.config.end_date.date()}
Initial Capital: ${self.config.initial_capital:,.2f}
Final Equity: ${self.equity_curve.iloc[-1]:,.2f}

{self.metrics}

Regime Performance:
{self._regime_summary()}
"""

    def _regime_summary(self) -> str:
        """Summarize regime metrics."""
        if not self.regime_metrics:
            return "  No regime analysis performed"

        lines = []
        for regime, metrics in self.regime_metrics.items():
            lines.append(f"  {regime}:")
            lines.append(f"    Win Rate: {metrics.win_rate:.1%}")
            lines.append(f"    Trades: {metrics.total_trades}")
            lines.append(f"    Avg Trade: ${metrics.avg_trade:,.2f}")
        return '\n'.join(lines)


class BacktestEngine:
    """
    Core backtest engine for running strategy simulations.

    Usage:
        engine = BacktestEngine(
            start_date=datetime(2022, 1, 1),
            end_date=datetime(2025, 3, 31),
            initial_capital=10000
        )
        result = engine.run(strategy)
        print(result.metrics)
    """

    def __init__(
        self,
        start_date: datetime,
        end_date: datetime,
        initial_capital: float = 10000.0,
        config: Optional[BacktestConfig] = None,
        journal_enabled: bool = False,
        journal: Optional[Any] = None,
    ):
        """
        Initialize backtest engine.

        Args:
            start_date: Backtest start date
            end_date: Backtest end date
            initial_capital: Starting portfolio value
            config: Optional custom configuration
        """
        self.config = config or BacktestConfig(
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital
        )
        self.current_date = start_date
        self.equity = initial_capital
        self.equity_curve: Dict[datetime, float] = {}
        self.trades: List[Any] = []
        self.positions: Dict[str, Any] = {}
        self.journal_enabled = journal_enabled
        self.journal = journal
        self._backtest_trade_ids: List[str] = []
        if self.journal_enabled and self.journal is None:
            from trading.journal import TradeJournal
            self.journal = TradeJournal()

    def run(self, strategy: Any, price_data: Optional[pd.DataFrame] = None) -> BacktestResult:
        """
        Run backtest for a strategy.

        Args:
            strategy: Strategy object with compute_signals() and execute_signals()
            price_data: Optional price data for regime analysis

        Returns:
            BacktestResult with metrics and equity curve
        """
        # Reset state
        self.equity = self.config.initial_capital
        self.equity_curve = {self.current_date: self.equity}
        self.trades = []
        self.positions = {}

        # Walk-forward ML: activate model gating earlier to reduce warmup bleed.
        warmup_trades = 8  # minimum trades before ML gating activates

        # Iterate through time (weekly for COT)
        current = self.config.start_date
        while current <= self.config.end_date:
            self.current_date = current

            # Update strategy with current date
            if hasattr(strategy, 'set_date'):
                strategy.set_date(current)

            # Walk-forward: retrain SetupLearner on accumulated trades
            setup_learner = getattr(strategy, "setup_learner", None)
            if (
                setup_learner is not None
                and hasattr(setup_learner, "fit")
                and len(self.trades) >= warmup_trades
            ):
                # Create a lightweight result object for incremental fit
                _interim = type("InterimResult", (), {
                                "trades": list(self.trades)})()
                setup_learner.fit(_interim)

            # Check intraweek stop losses / take profits on open positions
            if hasattr(strategy, "client") and hasattr(strategy.client, "check_stops_intraweek"):
                client = strategy.client
                for coin in list(getattr(client, "positions", {}).keys()):
                    stopped_trade = client.check_stops_intraweek(coin)
                    if stopped_trade is not None:
                        self.trades.append(stopped_trade)
                        if self.journal_enabled and self.journal is not None:
                            self._record_journal_trade(
                                stopped_trade, strategy_name=strategy.__class__.__name__)

            # Generate signals
            signals = strategy.compute_signals()

            # Execute signals
            if hasattr(strategy, 'execute_signals'):
                executed = strategy.execute_signals(signals, self)
                self.trades.extend(executed)
                if self.journal_enabled and self.journal is not None:
                    for trade in executed:
                        self._record_journal_trade(
                            trade, strategy_name=strategy.__class__.__name__)

            # Update equity (mark to market)
            self._update_equity()
            self.equity_curve[current] = self.equity

            # Advance time (weekly for COT reports)
            current += timedelta(weeks=1)

        # Close client-side backtest positions (mock client path) at final timestamp.
        if hasattr(strategy, "client") and hasattr(strategy.client, "close_all_positions"):
            # type: ignore[attr-defined]
            closed = strategy.client.close_all_positions()
            self.trades.extend(closed)
            if self.journal_enabled and self.journal is not None:
                for trade in closed:
                    self._record_journal_trade(
                        trade, strategy_name=strategy.__class__.__name__)

        # Close any remaining positions
        self._close_all_positions()

        # Calculate metrics
        equity_series = pd.Series(self.equity_curve)
        metrics = calculate_metrics(
            equity_series,
            self.trades,
            self.config.risk_free_rate
        )

        # Regime analysis
        regime_metrics = {}
        if price_data is not None:
            from .metrics import calculate_regime_metrics
            # Ensure price_data has a DatetimeIndex for regime matching
            close_series = price_data['close']
            if not isinstance(close_series.index, pd.DatetimeIndex) and 'timestamp' in price_data.columns:
                close_series = price_data.set_index('timestamp')['close']
            regime_metrics = calculate_regime_metrics(
                equity_series,
                self.trades,
                close_series
            )

        result = BacktestResult(
            config=self.config,
            equity_curve=equity_series,
            trades=self.trades,
            metrics=metrics,
            regime_metrics=regime_metrics
        )

        # Final fit for report generation (full dataset)
        setup_learner = getattr(strategy, "setup_learner", None)
        if setup_learner is not None and hasattr(setup_learner, "fit"):
            setup_learner.fit(result)

        return result

    def _record_journal_trade(self, trade: Any, strategy_name: str) -> None:
        """Persist executed backtest trade in TradeJournal storage."""
        from trading.journal import Trade, TradeEnvironment, TradeOutcome, TradeStatus

        if isinstance(trade, Trade):
            trade.environment = TradeEnvironment.BACKTEST
            to_save = trade
        else:
            coin = str(getattr(trade, "coin", "UNKNOWN") or "UNKNOWN")
            direction = str(getattr(trade, "direction", "long") or "long")
            if direction not in {"long", "short"}:
                direction = "long" if str(direction).lower() in {
                    "buy", "bullish"} else "short"

            entry_price = float(getattr(trade, "entry_price", 1.0) or 1.0)
            exit_price = float(getattr(trade, "exit_price",
                               entry_price) or entry_price)
            explicit_size_usd = getattr(trade, "size_usd", None)
            if explicit_size_usd is None:
                units = float(getattr(trade, "size", 0.0) or 0.0)
                size_usd = units * entry_price
            else:
                size_usd = float(explicit_size_usd or 0.0)
            if size_usd <= 0:
                size_usd = self.config.initial_capital * 0.1
            leverage = float(getattr(trade, "leverage", 1.0) or 1.0)
            pnl = float(getattr(trade, "pnl", 0.0) or 0.0)
            metadata = dict(getattr(trade, "metadata", {}) or {})

            to_save = Trade(
                strategy_name=strategy_name,
                coin=coin,
                direction=direction,
                size_usd=size_usd,
                leverage=leverage,
                entry_price=entry_price,
                environment=TradeEnvironment.BACKTEST,
                entry_signals=metadata,
                notes="Recorded by BacktestEngine",
            )
            to_save.status = TradeStatus.CLOSED
            to_save.entry_time = getattr(
                trade, "entry_date", self.current_date)
            to_save.exit_time = getattr(trade, "exit_date", self.current_date)
            to_save.exit_price = exit_price
            to_save.pnl_absolute = pnl
            if size_usd:
                to_save.pnl_percent = (pnl / size_usd) * 100
            to_save.outcome = (
                TradeOutcome.WIN if pnl > 0 else TradeOutcome.LOSS if pnl < 0 else TradeOutcome.BREAKEVEN
            )

        self.journal.storage.save_trade(to_save)
        self._backtest_trade_ids.append(to_save.id)

    def get_journal_trades(self) -> List[Any]:
        """Return journal-backed trades for this backtest run."""
        if not self.journal_enabled or self.journal is None:
            return []
        trades = []
        for trade_id in self._backtest_trade_ids:
            loaded = self.journal.get_trade(trade_id)
            if loaded is not None:
                trades.append(loaded)
        return trades

    def _update_equity(self):
        """Mark positions to market."""
        unrealized_pnl = 0
        for coin, position in self.positions.items():
            if hasattr(position, 'mark_to_market'):
                unrealized_pnl += position.mark_to_market(self.current_date)
        self.equity = self.config.initial_capital + sum(
            t.pnl for t in self.trades if t.pnl is not None
        ) + unrealized_pnl

    def _close_all_positions(self):
        """Close all open positions at end of backtest."""
        for coin in list(self.positions.keys()):
            self._close_position(coin)

    def _close_position(self, coin: str):
        """Close a position and record PnL."""
        if coin in self.positions:
            position = self.positions.pop(coin)
            # Calculate final PnL
            if hasattr(position, 'close'):
                position.close(self.current_date)
                self.trades.append(position)

    def simulate_drawdown(self, drawdown_pct: float):
        """Simulate a drawdown scenario for risk testing."""
        self.equity *= (1 - drawdown_pct)
        self.equity_curve[self.current_date] = self.equity

    def simulate_recovery(self):
        """Simulate recovery to initial capital."""
        self.equity = self.config.initial_capital
        self.equity_curve[self.current_date] = self.equity

    def identify_regimes(self, price_data: pd.Series) -> Dict[str, List[Any]]:
        """
        Identify market regimes and segment trades.

        Returns:
            Dict mapping regime names to lists of trades
        """
        # Calculate 50-day moving average
        ma50 = price_data.rolling(50).mean()

        regimes = {'bull_trend': [], 'bear_trend': [], 'range': []}

        for trade in self.trades:
            if not hasattr(trade, 'entry_date'):
                continue

            entry_price_raw = price_data.asof(trade.entry_date)
            ma_price_raw = ma50.asof(trade.entry_date)

            if not np.isscalar(entry_price_raw) or not np.isscalar(ma_price_raw):
                continue

            try:
                entry_price = float(cast(Any, entry_price_raw))
                ma_price = float(cast(Any, ma_price_raw))
            except (TypeError, ValueError):
                continue

            if np.isnan(entry_price) or np.isnan(ma_price):
                continue

            if entry_price > ma_price:
                regimes['bull_trend'].append(trade)
            elif entry_price < ma_price:
                regimes['bear_trend'].append(trade)
            else:
                regimes['range'].append(trade)

        return regimes


class WalkForwardOptimizer:
    """
    Walk-forward optimization for parameter stability testing.

    Usage:
        wfo = WalkForwardOptimizer(
            train_weeks=52,
            test_weeks=13
        )
        results = wfo.run(strategy_class, param_grid)
    """

    def __init__(
        self,
        train_weeks: int = 52,
        test_weeks: int = 13,
        step_weeks: int = 13
    ):
        """
        Initialize walk-forward optimizer.

        Args:
            train_weeks: Weeks for in-sample training
            test_weeks: Weeks for out-of-sample testing
            step_weeks: Weeks to roll forward each iteration
        """
        self.train_weeks = train_weeks
        self.test_weeks = test_weeks
        self.step_weeks = step_weeks

    def run(
        self,
        strategy_class: type,
        param_grid: Dict[str, List[Any]],
        start_date: datetime,
        end_date: datetime,
        initial_capital: float = 10000.0,
        setup_learning: bool = False,
        setup_model_path: Optional[str] = None,
    ) -> List[BacktestResult]:
        """
        Run walk-forward optimization.

        Args:
            strategy_class: Strategy class to instantiate
            param_grid: Dict of parameter names to lists of values
            start_date: Overall start date
            end_date: Overall end date
            initial_capital: Starting capital

        Returns:
            List of BacktestResults for each test period
        """
        results = []
        current = start_date

        while current + timedelta(weeks=self.train_weeks + self.test_weeks) <= end_date:
            train_start = current
            train_end = current + timedelta(weeks=self.train_weeks)
            test_start = train_end
            test_end = test_start + timedelta(weeks=self.test_weeks)

            # Optimize on training data
            best_params = self._optimize_params(
                strategy_class,
                param_grid,
                train_start,
                train_end,
                initial_capital
            )

            train_strategy = strategy_class(**best_params)
            train_engine = BacktestEngine(
                train_start, train_end, initial_capital)
            train_result = train_engine.run(train_strategy)
            setup_learner = getattr(train_strategy, "setup_learner", None)

            if setup_learning and setup_learner is not None:
                model_path = setup_model_path or "tests/backtest/artifacts/setup_learner.joblib"
                if hasattr(setup_learner, "save_model"):
                    saved = setup_learner.save_model(model_path)
                    logger.info("Saved setup learner model: %s", saved)

            # Test on out-of-sample data
            test_engine = BacktestEngine(
                test_start,
                test_end,
                initial_capital
            )
            test_strategy = strategy_class(**best_params)
            if setup_learning and setup_learner is not None:
                if hasattr(setup_learner, "save_model") and hasattr(test_strategy, "setup_learner"):
                    getattr(test_strategy, "setup_learner").load_model(
                        setup_model_path or "tests/backtest/artifacts/setup_learner.joblib"
                    )
            test_result = test_engine.run(test_strategy)
            test_result.best_params = best_params
            if setup_learning:
                test_result.best_params["objective"] = "setup-learning"
            train_result.best_params = best_params
            results.append(test_result)

            # Roll forward
            current += timedelta(weeks=self.step_weeks)

        return results

    def _optimize_params(
        self,
        strategy_class: type,
        param_grid: Dict[str, List[Any]],
        start: datetime,
        end: datetime,
        capital: float
    ) -> Dict[str, Any]:
        """Grid search for best parameters on training data."""
        from itertools import product

        best_sharpe = -float('inf')
        best_params = {}

        # Generate all parameter combinations
        keys = list(param_grid.keys())
        values = [param_grid[k] for k in keys]

        for combo in product(*values):
            params = dict(zip(keys, combo))

            engine = BacktestEngine(start, end, capital)
            strategy = strategy_class(**params)
            result = engine.run(strategy)

            if result.metrics.sharpe_ratio > best_sharpe:
                best_sharpe = result.metrics.sharpe_ratio
                best_params = params

        return best_params

    def analyze_stability(self, results: List[BacktestResult]) -> Dict[str, Any]:
        """
        Analyze parameter stability across walk-forward periods.

        Returns:
            Dict with stability metrics
        """
        sharpes = [r.metrics.sharpe_ratio for r in results]
        win_rates = [r.metrics.win_rate for r in results]
        max_dds = [r.metrics.max_drawdown for r in results]

        return {
            'avg_sharpe': np.mean(sharpes),
            'sharpe_std': np.std(sharpes),
            'sharpe_min': min(sharpes),
            'sharpe_max': max(sharpes),
            'consistency_score': 1 - (np.std(sharpes) / abs(np.mean(sharpes))) if np.mean(sharpes) != 0 else 0,
            'avg_win_rate': np.mean(win_rates),
            'avg_max_dd': np.mean(max_dds),
            'profitable_periods': sum(1 for r in results if r.metrics.total_return > 0),
            'total_periods': len(results)
        }
