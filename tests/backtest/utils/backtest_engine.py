"""Core backtest engine for strategy validation."""

from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
import numpy as np

from .metrics import calculate_metrics, PerformanceMetrics


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
        config: Optional[BacktestConfig] = None
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
        
        # Iterate through time (weekly for COT)
        current = self.config.start_date
        while current <= self.config.end_date:
            self.current_date = current
            
            # Update strategy with current date
            if hasattr(strategy, 'set_date'):
                strategy.set_date(current)
            
            # Generate signals
            signals = strategy.compute_signals()
            
            # Execute signals
            if hasattr(strategy, 'execute_signals'):
                executed = strategy.execute_signals(signals, self)
                self.trades.extend(executed)
            
            # Update equity (mark to market)
            self._update_equity()
            self.equity_curve[current] = self.equity
            
            # Advance time (weekly for COT reports)
            current += timedelta(weeks=1)
        
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
            regime_metrics = calculate_regime_metrics(
                equity_series,
                self.trades,
                price_data['close']
            )
        
        return BacktestResult(
            config=self.config,
            equity_curve=equity_series,
            trades=self.trades,
            metrics=metrics,
            regime_metrics=regime_metrics
        )
    
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
            
            entry_price = price_data.asof(trade.entry_date)
            ma_price = ma50.asof(trade.entry_date)
            
            if pd.isna(entry_price) or pd.isna(ma_price):
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
        initial_capital: float = 10000.0
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
            
            # Test on out-of-sample data
            test_engine = BacktestEngine(
                test_start,
                test_end,
                initial_capital
            )
            test_strategy = strategy_class(**best_params)
            test_result = test_engine.run(test_strategy)
            test_result.best_params = best_params
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
