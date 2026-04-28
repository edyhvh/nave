"""
Data models for the trade journaling system.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, List, Any
import uuid


class TradeStatus(Enum):
    """Status of a trade."""
    PENDING = "pending"          # Order submitted, not filled
    OPEN = "open"                # Position active
    CLOSED = "closed"            # Position closed
    CANCELLED = "cancelled"      # Order cancelled
    EXPIRED = "expired"          # Order expired


class TradeEnvironment(Enum):
    """Trading environment - affects risk and recording behavior."""
    BACKTEST = "backtest"        # Simulated historical data
    PAPER = "paper"              # Real-time simulation
    LIVE = "live"                # Real money


class AssetClass(Enum):
    """Asset class for a trade. Used for filtering, reporting, and broker routing."""
    CRYPTO = "crypto"            # Hyperliquid perps (default — historical trades)
    STOCK = "stock"              # Alpaca / Ondo equities


class TradeOutcome(Enum):
    """Outcome classification for closed trades."""
    WIN = "win"
    LOSS = "loss"
    BREAKEVEN = "breakeven"
    UNKNOWN = "unknown"


@dataclass
class Trade:
    """
    Core trade record.

    Tracks all essential information about a trade from entry to exit.
    Supports both spot and leveraged positions.
    """
    # Identification
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    strategy_name: str = "unknown"

    # Market info
    coin: str = ""
    direction: str = ""  # "long" or "short"

    # Position sizing
    size_usd: float = 0.0
    leverage: float = 1.0

    # Pricing
    entry_price: float = 0.0
    exit_price: Optional[float] = None

    # Fees
    entry_fee: float = 0.0
    exit_fee: float = 0.0
    funding_fees: float = 0.0  # Accumulated funding payments

    # Timing
    entry_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    exit_time: Optional[datetime] = None

    # Trade lifecycle
    status: TradeStatus = TradeStatus.PENDING
    environment: TradeEnvironment = TradeEnvironment.BACKTEST
    asset_class: AssetClass = AssetClass.CRYPTO  # default preserves back-compat for existing rows

    # Risk management
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None

    # Context
    entry_signals: Dict[str, Any] = field(default_factory=dict)
    exit_signals: Dict[str, Any] = field(default_factory=dict)

    # Metadata
    tags: List[str] = field(default_factory=list)
    notes: str = ""

    # Computed fields (set on exit)
    pnl_absolute: Optional[float] = None
    pnl_percent: Optional[float] = None
    outcome: TradeOutcome = TradeOutcome.UNKNOWN

    def __post_init__(self):
        """Ensure proper types after initialization."""
        if isinstance(self.status, str):
            self.status = TradeStatus(self.status)
        if isinstance(self.environment, str):
            self.environment = TradeEnvironment(self.environment)
        if isinstance(self.asset_class, str):
            self.asset_class = AssetClass(self.asset_class)
        if isinstance(self.outcome, str):
            self.outcome = TradeOutcome(self.outcome)
        if isinstance(self.entry_time, str):
            self.entry_time = datetime.fromisoformat(self.entry_time)
        if isinstance(self.exit_time, str):
            self.exit_time = datetime.fromisoformat(self.exit_time)

    @property
    def symbol(self) -> str:
        """Alias for :attr:`coin`. Preferred when the asset class is a stock."""
        return self.coin

    @property
    def is_crypto(self) -> bool:
        return self.asset_class == AssetClass.CRYPTO

    @property
    def is_stock(self) -> bool:
        return self.asset_class == AssetClass.STOCK

    @property
    def is_closed(self) -> bool:
        """Check if trade is closed."""
        return self.status == TradeStatus.CLOSED

    @property
    def is_long(self) -> bool:
        """Check if long position."""
        return self.direction.lower() == "long"

    @property
    def position_value(self) -> float:
        """Current position value in USD."""
        return self.size_usd * self.leverage

    @property
    def notional_size(self) -> float:
        """Notional position size (size * leverage)."""
        return self.size_usd * self.leverage

    @property
    def total_fees(self) -> float:
        """Total fees paid."""
        return self.entry_fee + self.exit_fee + self.funding_fees

    @property
    def duration(self) -> Optional[float]:
        """Trade duration in hours."""
        if self.exit_time and self.entry_time:
            return (self.exit_time - self.entry_time).total_seconds() / 3600
        return None

    def calculate_pnl(self, current_price: Optional[float] = None) -> float:
        """
        Calculate P&L.

        Args:
            current_price: Current market price (for open trades)

        Returns:
            P&L in USD
        """
        if self.is_closed and self.exit_price is not None:
            exit_p = self.exit_price
        elif current_price is not None:
            exit_p = current_price
        else:
            return 0.0

        price_diff = exit_p - self.entry_price
        if not self.is_long:
            price_diff = -price_diff

        gross_pnl = price_diff * (self.notional_size / self.entry_price)
        return gross_pnl - self.total_fees

    def close(self, exit_price: float, exit_time: Optional[datetime] = None):
        """
        Close the trade.

        Args:
            exit_price: Exit price
            exit_time: Exit timestamp (defaults to now)
        """
        self.exit_price = exit_price
        self.exit_time = exit_time or datetime.now(timezone.utc).replace(tzinfo=None)
        self.status = TradeStatus.CLOSED

        # Calculate P&L
        self.pnl_absolute = self.calculate_pnl()

        if self.notional_size > 0:
            self.pnl_percent = (self.pnl_absolute / self.size_usd) * 100

        # Determine outcome
        if self.pnl_absolute is not None:
            if self.pnl_absolute > 0:
                self.outcome = TradeOutcome.WIN
            elif self.pnl_absolute < 0:
                self.outcome = TradeOutcome.LOSS
            else:
                self.outcome = TradeOutcome.BREAKEVEN

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = asdict(self)
        # Convert enums to strings
        data['status'] = self.status.value
        data['environment'] = self.environment.value
        data['asset_class'] = self.asset_class.value
        data['outcome'] = self.outcome.value
        data['entry_time'] = self.entry_time.isoformat()
        data['exit_time'] = self.exit_time.isoformat() if self.exit_time else None
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Trade":
        """Create from dictionary."""
        return cls(**data)

    def __repr__(self) -> str:
        return (f"Trade({self.id} {self.coin} {self.direction} "
                f"${self.size_usd:.2f}@{self.entry_price:.2f} "
                f"[{self.environment.value}])")


@dataclass
class PositionUpdate:
    """Snapshot of position state at a point in time."""
    trade_id: str
    timestamp: datetime
    current_price: float
    unrealized_pnl: float
    funding_paid: float = 0.0
    margin_used: float = 0.0
    liquidation_price: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            'trade_id': self.trade_id,
            'timestamp': self.timestamp.isoformat(),
            'current_price': self.current_price,
            'unrealized_pnl': self.unrealized_pnl,
            'funding_paid': self.funding_paid,
            'margin_used': self.margin_used,
            'liquidation_price': self.liquidation_price,
        }


@dataclass
class TradeReview:
    """Post-trade review and lessons learned."""
    trade_id: str
    reviewed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    # Analysis
    setup_quality: int = 0  # 1-10 rating
    entry_quality: int = 0
    exit_quality: int = 0
    risk_management: int = 0

    # Review content
    what_went_well: str = ""
    what_went_wrong: str = ""
    lessons_learned: str = ""

    # Improvements
    would_take_again: bool = True
    improvements: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TradeJournalEntry:
    """Complete journal entry combining trade, updates, and review."""
    trade: Trade
    position_updates: List[PositionUpdate] = field(default_factory=list)
    review: Optional[TradeReview] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            'trade': self.trade.to_dict(),
            'position_updates': [u.to_dict() for u in self.position_updates],
            'review': self.review.to_dict() if self.review else None,
        }
