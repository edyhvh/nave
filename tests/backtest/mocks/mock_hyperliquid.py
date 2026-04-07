"""Mock Hyperliquid client for backtesting."""

from typing import Dict, Any, List, Optional, cast
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
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
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


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
            self.price_series = self._load_default_price_series()

        # Default markets
        self._markets = ['BTC', 'ETH', 'SOL', 'AVAX', 'ARB', 'OP']

    def set_date(self, date: datetime):
        """Set current backtest date."""
        self.current_date = date

    def get_price(self, coin: str, date: Optional[datetime] = None) -> float:
        """Get price for a coin at a specific date."""
        effective_date = date or self.current_date or datetime.now(
            timezone.utc)

        if self.price_data is not None:
            # Query from price data. If coin column exists, filter by symbol.
            price_df = self.price_data
            if 'coin' in price_df.columns:
                symbol = coin.upper()
                coin_mask = price_df['coin'].astype(str).str.upper() == symbol
                price_df = price_df[coin_mask]
            if not price_df.empty:
                mask = price_df['timestamp'] <= effective_date
                if mask.any():
                    return float(price_df[mask].iloc[-1]['close'])

        series = self.price_series.get(coin.upper())
        if series is not None and not series.empty:
            ts = pd.Timestamp(effective_date)
            if ts.tzinfo is not None:
                ts = ts.tz_convert(None)
            # Align to daily data precision before asof lookup.
            ts = ts.normalize()
            price = series.asof(ts)
            if isinstance(price, pd.Series):
                if price.empty:
                    price = None
                else:
                    price = price.iloc[-1]
            if price is not None and not pd.isna(price):
                return float(cast(float, price))

        # Fallback: generate synthetic price
        return self._synthetic_price(coin, effective_date)

    def _synthetic_price(self, coin: str, date: datetime) -> float:
        """Generate synthetic price for testing."""
        # Deterministic pseudo-random based on date and coin
        np.random.seed(hash(f"{coin}_{date.strftime('%Y%m%d')}") % 2**32)
        base_price = {'BTC': 50000, 'ETH': 3000, 'SOL': 100}.get(coin, 10)
        noise = np.random.normal(0, 0.02)  # 2% daily volatility
        return base_price * (1 + noise)

    def _load_default_price_series(self) -> Dict[str, pd.Series]:
        """Load BTC/ETH daily history for realistic backtest fills."""
        mapping = {"BTC": "BTC-USD", "ETH": "ETH-USD"}
        loaded: Dict[str, pd.Series] = {}
        try:
            import yfinance as yf
            for coin, ticker in mapping.items():
                frame = yf.download(
                    ticker,
                    period="10y",
                    interval="1d",
                    auto_adjust=True,
                    progress=False,
                )
                if frame is None or frame.empty or "Close" not in frame.columns:
                    continue
                close_data = frame["Close"]
                if isinstance(close_data, pd.DataFrame):
                    first_col = close_data.columns[0]
                    series = close_data[first_col].copy()
                else:
                    series = close_data.copy()
                if isinstance(series.index, pd.DatetimeIndex) and series.index.tz is not None:
                    series.index = series.index.tz_localize(None)
                loaded[coin] = series
        except Exception:
            return {}
        return loaded

    def _calculate_atr(self, coin: str, lookback_days: int = 14) -> float:
        """Calculate Average True Range from daily price data for stop/TP sizing."""
        series_map = getattr(self, "price_series", {}) or {}
        series = series_map.get(coin.upper())
        if series is None or series.empty:
            return 0.02  # fallback 2% ATR
        effective_date = self.current_date or datetime.now(timezone.utc)
        ts = pd.Timestamp(effective_date)
        if ts.tzinfo is not None:
            ts = ts.tz_convert(None)
        ts = ts.normalize()
        # Get last N+1 prices for N true ranges
        mask = series.index <= ts
        recent = series[mask].tail(lookback_days + 1)
        if len(recent) < 2:
            return 0.02
        # True range approximation from close-to-close (no H/L available)
        returns = recent.pct_change().abs().dropna()
        return float(returns.mean()) if len(returns) > 0 else 0.02

    def _compute_stop_take_profit(
        self, coin: str, direction: str, entry_price: float,
        atr_stop_mult: float = 2.0, atr_tp_mult: float = 3.0,
    ) -> tuple[float, float]:
        """Compute ATR-based stop loss and take profit levels."""
        atr_pct = self._calculate_atr(coin)
        # Floor at 1% to avoid stops too tight on low-vol days
        atr_pct = max(atr_pct, 0.01)
        stop_distance = entry_price * atr_pct * atr_stop_mult
        tp_distance = entry_price * atr_pct * atr_tp_mult
        if direction == "long":
            stop_loss = entry_price - stop_distance
            take_profit = entry_price + tp_distance
        else:
            stop_loss = entry_price + stop_distance
            take_profit = entry_price - tp_distance
        return stop_loss, take_profit

    def check_stops_intraweek(self, coin: str) -> Optional[MockTrade]:
        """Check if stop loss or take profit was hit during the week.

        Simulates daily price checks between entry and current date.
        Returns the closed MockTrade if stopped/TP'd, else None.
        """
        if coin not in self.positions:
            return None
        trade = self.positions[coin]
        if trade.stop_loss is None and trade.take_profit is None:
            return None

        start = trade.entry_date
        end = self.current_date or datetime.now(timezone.utc)
        # Check each day within the week
        check_date = start + timedelta(days=1)
        while check_date <= end:
            daily_price = self.get_price(coin, date=check_date)
            hit_stop = False
            hit_tp = False

            if trade.direction == "long":
                if trade.stop_loss is not None and daily_price <= trade.stop_loss:
                    hit_stop = True
                if trade.take_profit is not None and daily_price >= trade.take_profit:
                    hit_tp = True
            else:  # short
                if trade.stop_loss is not None and daily_price >= trade.stop_loss:
                    hit_stop = True
                if trade.take_profit is not None and daily_price <= trade.take_profit:
                    hit_tp = True

            if hit_stop or hit_tp:
                # Close at the stop/TP level (not market price)
                exit_price = trade.stop_loss if hit_stop else trade.take_profit
                assert exit_price is not None
                return self._close_at_price(coin, exit_price, check_date)

            check_date += timedelta(days=1)
        return None

    def _close_at_price(self, coin: str, exit_price: float, exit_date: datetime) -> MockTrade:
        """Close a position at a specific price (for stop/TP fills)."""
        trade = self.positions.pop(coin)
        if trade.direction == "long":
            pnl = (exit_price - trade.entry_price) * \
                trade.size * trade.leverage
        else:
            pnl = (trade.entry_price - exit_price) * \
                trade.size * trade.leverage

        # Add exit taker fee (0.035%) and funding estimate
        exit_notional = trade.size * exit_price * trade.leverage
        exit_fee = exit_notional * 0.00035
        hold_hours = max(
            (exit_date - trade.entry_date).total_seconds() / 3600, 1)
        funding_fee = trade.size * trade.entry_price * \
            trade.leverage * 0.0001 * (hold_hours / 8)
        total_fees = trade.fees + exit_fee + funding_fee

        trade.exit_date = exit_date
        trade.exit_price = exit_price
        trade.pnl = pnl - total_fees
        trade.fees = total_fees
        trade.status = "closed"
        self.trade_history.append(trade)
        return trade

    def open_position(
        self,
        coin: str,
        direction: str,
        size_usd: float,
        leverage: float,
        metadata: Optional[Dict[str, Any]] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        atr_stop_mult: float = 2.0,
        atr_tp_mult: float = 3.0,
    ) -> MockTrade:
        """Open a simulated position with ATR-based stop loss and take profit."""
        current_date = self.current_date or datetime.now(timezone.utc)
        entry_price = self.get_price(coin)

        # Apply slippage
        if direction == 'long':
            entry_price *= (1 + self.slippage)
        else:
            entry_price *= (1 - self.slippage)

        # Compute ATR-based stop/TP if not explicitly provided
        if stop_loss is None or take_profit is None:
            computed_sl, computed_tp = self._compute_stop_take_profit(
                coin, direction, entry_price, atr_stop_mult, atr_tp_mult,
            )
            if stop_loss is None:
                stop_loss = computed_sl
            if take_profit is None:
                take_profit = computed_tp

        # Realistic Hyperliquid fees: 0.035% taker on leveraged notional
        entry_notional = size_usd * leverage
        entry_fee = entry_notional * 0.00035

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
            fees=entry_fee,
            status='open',
            stop_loss=stop_loss,
            take_profit=take_profit,
            metadata=metadata or {},
        )

        self.positions[coin] = trade
        return trade

    def close_position(self, coin: str) -> MockTrade:
        """Close a simulated position."""
        if coin not in self.positions:
            raise ValueError(f"No open position for {coin}")

        trade = self.positions.pop(coin)
        exit_price = self.get_price(coin)
        exit_date = self.current_date if self.current_date is not None else datetime.now(
            timezone.utc)

        # Apply slippage
        if trade.direction == 'long':
            exit_price *= (1 - self.slippage)
            pnl = (exit_price - trade.entry_price) * \
                trade.size * trade.leverage
        else:
            exit_price *= (1 + self.slippage)
            pnl = (trade.entry_price - exit_price) * \
                trade.size * trade.leverage

        # Add exit taker fee (0.035%) and funding estimate
        exit_notional = trade.size * exit_price * trade.leverage
        exit_fee = exit_notional * 0.00035
        hold_hours = max(
            (exit_date - trade.entry_date).total_seconds() / 3600, 1)
        funding_fee = trade.size * trade.entry_price * \
            trade.leverage * 0.0001 * (hold_hours / 8)
        total_fees = trade.fees + exit_fee + funding_fee

        trade.exit_date = exit_date
        trade.exit_price = exit_price
        trade.pnl = pnl - total_fees
        trade.fees = total_fees
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

    def market_open(self, coin: str, side: str, size_usd: float) -> Dict[str, Any]:
        """Compatibility wrapper matching live client market_open signature."""
        trade = self.open_position(
            coin=coin,
            direction="long" if str(side).lower() == "long" else "short",
            size_usd=size_usd,
            leverage=1.0,
        )
        return {
            "status": "ok",
            "coin": trade.coin,
            "direction": trade.direction,
            "size_usd": size_usd,
            "entry_price": trade.entry_price,
        }

    def market_close(self, coin: str) -> Dict[str, Any]:
        """Compatibility wrapper matching live client market_close signature."""
        trade = self.close_position(coin)
        return {
            "status": "ok",
            "coin": trade.coin,
            "pnl": trade.pnl,
            "exit_price": trade.exit_price,
        }
