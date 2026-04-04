"""Tests for strategy module."""
import pytest
from unittest.mock import MagicMock, patch
from trading.strategy import PositionSizing, CotWeeklyStrategy
from trading.signals import Signal, Direction


class TestPositionSizing:
    """Test cases for PositionSizing dataclass."""
    
    def test_position_sizing_creation(self):
        """Test position sizing can be created."""
        sizing = PositionSizing(
            size_usd=1000.0,
            leverage=5.0,
            risk_usd=100.0,
            risk_pct=0.10,
            stop_price=40000.0,
            target_price=45000.0,
            expected_rr=2.5,
            direction=Direction.LONG,
            instrument="BTC-PERP"
        )
        
        assert sizing.size_usd == 1000.0
        assert sizing.leverage == 5.0
        assert sizing.risk_usd == 100.0


class TestCotWeeklyStrategy:
    """Test cases for CotWeeklyStrategy."""
    
    def test_strategy_initialization(self):
        """Test strategy initializes correctly."""
        mock_client = MagicMock()
        strategy = CotWeeklyStrategy(
            client=mock_client,
            capital_usd=2000.0,
            risk_pct=0.10,
            dry_run=True
        )
        
        assert strategy is not None
        assert strategy.capital_usd == 2000.0
        assert strategy.risk_pct == 0.10
        assert strategy.dry_run is True
    
    def test_calculate_leverage_from_confidence(self):
        """Test leverage scales with confidence."""
        mock_client = MagicMock()
        strategy = CotWeeklyStrategy(
            client=mock_client,
            capital_usd=2000.0,
            risk_pct=0.10,
            dry_run=True
        )
        
        # High confidence should give higher leverage
        high_lev = strategy._calculate_leverage(0.8)
        low_lev = strategy._calculate_leverage(0.4)
        
        assert high_lev > low_lev
        assert high_lev <= 10.0  # Max leverage cap
        assert low_lev >= 1.0    # Min leverage floor
    
    def test_calculate_position_sizing(self):
        """Test position sizing calculation."""
        mock_client = MagicMock()
        strategy = CotWeeklyStrategy(
            client=mock_client,
            capital_usd=2000.0,
            risk_pct=0.10,
            dry_run=True
        )
        
        signal = Signal(
            asset="BTC",
            direction=Direction.LONG,
            confidence=0.75,
            rationale="Test"
        )
        
        sizing = strategy._calculate_position_sizing(signal, 40000.0)
        
        assert sizing is not None
        assert sizing.size_usd > 0
        assert sizing.risk_usd == 200.0  # 10% of 2000
        assert sizing.direction == Direction.LONG
