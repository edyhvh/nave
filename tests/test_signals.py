"""Tests for signals module."""
import pytest
from unittest.mock import MagicMock, patch
from trading.signals import Signal, Direction, CotSignalProducer


class TestSignal:
    """Test cases for Signal dataclass."""
    
    def test_signal_creation(self):
        """Test signal can be created."""
        signal = Signal(
            asset="BTC",
            direction=Direction.LONG,
            confidence=0.75,
            rationale="Test signal"
        )
        
        assert signal.asset == "BTC"
        assert signal.direction == Direction.LONG
        assert signal.confidence == 0.75
        assert signal.rationale == "Test signal"
    
    def test_signal_direction_enum(self):
        """Test Direction enum values."""
        assert Direction.LONG.value == "long"
        assert Direction.SHORT.value == "short"
        assert Direction.NEUTRAL.value == "neutral"


class TestCotSignalProducer:
    """Test cases for CotSignalProducer."""
    
    def test_producer_initialization(self):
        """Test producer initializes correctly."""
        producer = CotSignalProducer()
        assert producer is not None
    
    @patch('trading.cot.CotFetcher')
    def test_generate_signal_returns_signal(self, mock_fetcher_class):
        """Test generate_signal returns a Signal."""
        # Mock fetcher
        mock_fetcher = MagicMock()
        mock_fetcher_class.return_value = mock_fetcher
        
        # Mock data
        mock_data = MagicMock()
        mock_data.empty = False
        mock_data.iloc = [{
            'Noncommercial Longs': 1000,
            'Noncommercial Shorts': 400,
            'Open Interest': 5000,
            'As of Date in Form YYYY-MM-DD': '2024-01-01'
        }]
        mock_fetcher.latest_btc.return_value = mock_data
        
        producer = CotSignalProducer()
        signal = producer.generate_signal("BTC")
        
        assert signal is not None
        assert signal.asset == "BTC"
    
    def test_compare_signals_prefers_higher_confidence(self):
        """Test compare signals prefers higher confidence."""
        producer = CotSignalProducer()
        
        signal_btc = Signal(
            asset="BTC",
            direction=Direction.LONG,
            confidence=0.8,
            rationale="Strong bullish"
        )
        
        signal_eth = Signal(
            asset="ETH",
            direction=Direction.LONG,
            confidence=0.6,
            rationale="Moderate bullish"
        )
        
        best = producer.compare_signals(signal_btc, signal_eth)
        assert best.asset == "BTC"
