"""Performance metrics calculation for backtests."""

from typing import List, Dict, Any, cast
from dataclasses import dataclass
from datetime import datetime
import numpy as np
import pandas as pd


@dataclass
class PerformanceMetrics:
    """Comprehensive performance metrics for strategy evaluation."""

    # Returns
    total_return: float
    cagr: float
    annualized_volatility: float

    # Risk-adjusted
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float

    # Drawdown
    max_drawdown: float
    avg_drawdown: float
    max_drawdown_duration: int  # days

    # Trade stats
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    profit_factor: float
    avg_win: float
    avg_loss: float
    avg_trade: float
    largest_win: float
    largest_loss: float
    max_consecutive_wins: int
    max_consecutive_losses: int

    # Time
    avg_trade_duration: float  # days
    avg_time_to_profit: float  # days

    # Additional
    skewness: float
    kurtosis: float
    var_95: float  # 95% Value at Risk
    cvar_95: float  # Conditional VaR

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'total_return': self.total_return,
            'cagr': self.cagr,
            'sharpe_ratio': self.sharpe_ratio,
            'max_drawdown': self.max_drawdown,
            'win_rate': self.win_rate,
            'profit_factor': self.profit_factor,
            'total_trades': self.total_trades,
        }

    def __str__(self) -> str:
        """Pretty print metrics."""
        return f"""
Performance Metrics:
===================
Returns:
  Total Return:     {self.total_return:.2%}
  CAGR:             {self.cagr:.2%}
  Volatility:       {self.annualized_volatility:.2%}

Risk-Adjusted:
  Sharpe Ratio:     {self.sharpe_ratio:.2f}
  Sortino Ratio:    {self.sortino_ratio:.2f}
  Calmar Ratio:     {self.calmar_ratio:.2f}

Drawdown:
  Max Drawdown:     {self.max_drawdown:.2%}
  Avg Drawdown:     {self.avg_drawdown:.2%}
  Max DD Duration:  {self.max_drawdown_duration} days

Trade Stats:
  Total Trades:     {self.total_trades}
  Win Rate:         {self.win_rate:.1%}
  Profit Factor:    {self.profit_factor:.2f}
  Avg Win:          ${self.avg_win:,.2f}
  Avg Loss:         ${self.avg_loss:,.2f}
  Max Consec Loss:  {self.max_consecutive_losses}
"""


def calculate_metrics(
    equity_curve: pd.Series,
    trades: List[Any],
    risk_free_rate: float = 0.02
) -> PerformanceMetrics:
    """
    Calculate comprehensive performance metrics.

    Args:
        equity_curve: Series of portfolio values indexed by date
        trades: List of trade objects with pnl, entry_date, exit_date
        risk_free_rate: Annual risk-free rate (default 2%)

    Returns:
        PerformanceMetrics object
    """
    # Returns
    total_return = (equity_curve.iloc[-1] / equity_curve.iloc[0]) - 1

    # Time period
    days = (equity_curve.index[-1] - equity_curve.index[0]).days
    years = days / 365.25
    cagr = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0

    # Returns series
    returns = equity_curve.pct_change().dropna()
    annualized_vol = returns.std() * np.sqrt(252)

    # Risk-adjusted metrics
    excess_returns = returns - risk_free_rate / 252
    sharpe = excess_returns.mean() / excess_returns.std() * \
        np.sqrt(252) if excess_returns.std() > 0 else 0

    # Sortino (downside deviation)
    downside_returns = returns[returns < 0]
    downside_std = downside_returns.std() * np.sqrt(252) if len(downside_returns) > 0 else 0
    sortino = (returns.mean() * 252 - risk_free_rate) / \
        downside_std if downside_std > 0 else 0

    # Drawdown
    peak = equity_curve.cummax()
    drawdown = (equity_curve - peak) / peak
    max_drawdown = drawdown.min()
    avg_drawdown = drawdown[drawdown < 0].mean() if (drawdown < 0).any() else 0

    # Max drawdown duration
    is_drawdown = drawdown < 0
    max_duration = 0
    current_duration = 0
    for in_dd in is_drawdown:
        if in_dd:
            current_duration += 1
            max_duration = max(max_duration, current_duration)
        else:
            current_duration = 0

    # Calmar
    calmar = cagr / abs(max_drawdown) if max_drawdown != 0 else 0

    # Trade statistics
    if trades:
        pnls = [t.pnl for t in trades if t.pnl is not None]
        winning = [p for p in pnls if p > 0]
        losing = [p for p in pnls if p < 0]

        total_trades = len(pnls)
        winning_trades = len(winning)
        losing_trades = len(losing)
        win_rate = winning_trades / total_trades if total_trades > 0 else 0

        gross_profit = sum(winning) if winning else 0
        gross_loss = abs(sum(losing)) if losing else 0
        profit_factor = gross_profit / \
            gross_loss if gross_loss > 0 else float('inf')

        avg_win = np.mean(winning) if winning else 0
        avg_loss = np.mean(losing) if losing else 0
        avg_trade = np.mean(pnls) if pnls else 0

        largest_win = max(winning) if winning else 0
        largest_loss = min(losing) if losing else 0

        # Consecutive wins/losses
        max_consec_wins = 0
        max_consec_losses = 0
        current_wins = 0
        current_losses = 0
        for pnl in pnls:
            if pnl > 0:
                current_wins += 1
                current_losses = 0
                max_consec_wins = max(max_consec_wins, current_wins)
            else:
                current_losses += 1
                current_wins = 0
                max_consec_losses = max(max_consec_losses, current_losses)

        # Durations
        durations = []
        for t in trades:
            if t.exit_date and t.entry_date:
                durations.append((t.exit_date - t.entry_date).days)
        avg_duration = np.mean(durations) if durations else 0

        # Time to profit (for winners)
        # Simplified: assume held until exit
        avg_time_to_profit = avg_duration  # Placeholder
    else:
        total_trades = winning_trades = losing_trades = 0
        win_rate = profit_factor = avg_win = avg_loss = avg_trade = 0
        largest_win = largest_loss = max_consec_wins = max_consec_losses = 0
        avg_duration = avg_time_to_profit = 0

    # Distribution stats
    skewness = cast(float, returns.skew())
    kurtosis = cast(float, returns.kurtosis())
    var_95 = np.percentile(returns, 5)
    cvar_95 = returns[returns <= var_95].mean()

    return PerformanceMetrics(
        total_return=float(total_return),
        cagr=float(cagr),
        annualized_volatility=float(annualized_vol),
        sharpe_ratio=float(sharpe),
        sortino_ratio=float(sortino),
        calmar_ratio=float(calmar),
        max_drawdown=float(max_drawdown),
        avg_drawdown=float(avg_drawdown),
        max_drawdown_duration=max_duration,
        total_trades=total_trades,
        winning_trades=winning_trades,
        losing_trades=losing_trades,
        win_rate=float(win_rate),
        profit_factor=float(profit_factor),
        avg_win=float(avg_win),
        avg_loss=float(avg_loss),
        avg_trade=float(avg_trade),
        largest_win=float(largest_win),
        largest_loss=float(largest_loss),
        max_consecutive_wins=max_consec_wins,
        max_consecutive_losses=max_consec_losses,
        avg_trade_duration=float(avg_duration),
        avg_time_to_profit=float(avg_time_to_profit),
        skewness=float(skewness),
        kurtosis=float(kurtosis),
        var_95=float(var_95),
        cvar_95=float(cvar_95)
    )


def calculate_regime_metrics(
    equity_curve: pd.Series,
    trades: List[Any],
    price_data: pd.Series
) -> Dict[str, PerformanceMetrics]:
    """
    Calculate metrics segmented by market regime.

    Regimes:
    - bull_trend: Price > 50-day MA, rising
    - bear_trend: Price < 50-day MA, falling
    - range: Sideways, within bands
    """
    # Calculate regime for each date
    ma50 = price_data.rolling(50).mean()
    regime = pd.Series(index=price_data.index, dtype='object')

    for i in range(50, len(price_data)):
        if price_data.iloc[i] > ma50.iloc[i] and price_data.iloc[i] > price_data.iloc[i-20]:
            regime.iloc[i] = 'bull_trend'
        elif price_data.iloc[i] < ma50.iloc[i] and price_data.iloc[i] < price_data.iloc[i-20]:
            regime.iloc[i] = 'bear_trend'
        else:
            regime.iloc[i] = 'range'

    # Segment trades by regime
    regime_metrics = {}
    for r in ['bull_trend', 'bear_trend', 'range']:
        regime_trades = [t for t in trades if regime.get(t.entry_date) == r]
        if regime_trades:
            # Create sub-equity curve (simplified)
            regime_metrics[r] = calculate_metrics(equity_curve, regime_trades)

    return regime_metrics
