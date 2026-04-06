"""Mock Hyperliquid client for backtesting."""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime, timezone
import pandas as pd
import numpy as np


@dataclass
class MockTrade:
    """Represents a simulated trade."""
    entry_date: datetime
    exit_date: Optional[datetime]
    coin: str
    direction: str  # 'long' or 'short'
    entry_price: float
    exit_price: Optional[float]
    size: float
    leverage: float
    pnl: Optional[float]
    fees: float
    status: str  # 'open' or 'closed'


class MockHyperliquidClient:
    """
    Mock Hyperliquid client for backtesting.

    Simulates:
    - Market data (OHLCV)
    - Order execution with slippage
    - Position tracking
    - PnL calculation
    """

    def __init__(self, price_data_path: Optional[str] = None, slippage_pct: float = 0.001):
        """
        Initialize mock client.

        Args:
            price_data_path: Path to price data CSV/parquet
            slippage_pct: Slippage to apply to executions (0.001 = 0.1%)
        """
        self.slippage = slippage_pct
        self.positions: Dict[str, MockTrade] = {}
        self.trade_history: List[MockTrade] = []
        self.current_date: Optional[datetime] = None

        # Load price data
        if price_data_path:
            self.price_data = pd.read_parquet(price_data_path)
        else:
            self.price_data = None

        # Default markets
        self._markets = ['BTC', 'ETH', 'SOL', 'AVAX', 'ARB', 'OP']

    def set_date(self, date: datetime):
        """Set current backtest date."""
        self.current_date = date

    def get_price(self, coin: str, date: Optional[datetime] = None) -> float:
        """Get price for a coin at a specific date."""
        effective_date = date or self.current_date or datetime.utcnow()

        if self.price_data is not None:
            # Query from price data
            mask = self.price_data['timestamp'] <= effective_date
            if mask.any():
                return float(self.price_data[mask].iloc[-1]['close'])

        # Fallback: generate synthetic price
        return self._synthetic_price(coin, effective_date)

    def _synthetic_price(self, coin: str, date: datetime) -> float:
        """Generate synthetic price for testing."""
        # Deterministic pseudo-random based on date and coin
        np.random.seed(hash(f"{coin}_{date.strftime('%Y%m%d')}") % 2**32)
        base_price = {'BTC': 50000, 'ETH': 3000, 'SOL': 100}.get(coin, 10)
        noise = np.random.normal(0, 0.02)  # 2% daily volatility
        return base_price * (1 + noise)

    def open_position(
        self,
        coin: str,
        direction: str,
        size_usd: float,
        leverage: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None
    ) -> MockTrade:
        """Open a simulated position."""
        current_date = self.current_date or datetime.utcnow()
        entry_price = self.get_price(coin)

        # Apply slippage
        if direction == 'long':
            entry_price *= (1 + self.slippage)
        else:
            entry_price *= (1 - self.slippage)

        trade = MockTrade(
            entry_date=current_date,
            exit_date=None,
            coin=coin,
            direction=direction,
            entry_price=entry_price,
            exit_price=None,
            size=size_usd / entry_price,
            leverage=leverage,
            pnl=None,
            fees=size_usd * 0.0005,  # 0.05% trading fee
            status='open'
        )

        self.positions[coin] = trade
        return trade

    def close_position(self, coin: str) -> MockTrade:
        """Close a simulated position."""
        if coin not in self.positions:
            raise ValueError(f"No open position for {coin}")

        trade = self.positions.pop(coin)
        exit_price = self.get_price(coin)

        # Apply slippage
        if trade.direction == 'long':
            exit_price *= (1 - self.slippage)
            pnl = (exit_price - trade.entry_price) * trade.size
        else:
            exit_price *= (1 + self.slippage)
            pnl = (trade.entry_price - exit_price) * trade.size

        trade.exit_date = self.current_date if self.current_date is not None else datetime.now(timezone.utc)
        trade.exit_price = exit_price
        trade.pnl = pnl - trade.fees
        trade.status = 'closed'

        self.trade_history.append(trade)
        return trade

    def get_markets(self) -> List[str]:
        """Return list of available markets."""
        return self._markets

    def get_funding_rate(self, coin: str) -> float:
        """Get current funding rate."""
        # Mock funding: slightly positive on average
        np.random.seed(hash(f"funding_{coin}_{self.current_date}") % 2**32)
        return np.random.normal(0.0001, 0.0005)  # Mean 0.01%, std 0.05%

    def get_open_interest(self, coin: str) -> float:
        """Get open interest."""
        return 1000000  # Mock $1M OI

    def get_position(self, coin: str) -> Optional[MockTrade]:
        """Get current position for a coin."""
        return self.positions.get(coin)

    def get_open_positions(self) -> List[MockTrade]:
        """Return open positions (fixes BaseStrategy compatibility per Copilot review)."""
        return list(self.positions.values())

    def close_all_positions(self) -> List[MockTrade]:
        """Close all open positions."""
        closed = []
        for coin in list(self.positions.keys()):
            closed.append(self.close_position(coin))
        return closed
