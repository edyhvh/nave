"""Tests for COT analyzer module."""
import pytest
from unittest.mock import MagicMock
from trading.cot import CotAnalyzer


class TestCotAnalyzer:
    """Test cases for CotAnalyzer."""
    
    def test_analyzer_initialization(self):
        """Test analyzer initializes correctly."""
        analyzer = CotAnalyzer()
        assert analyzer is not None
    
    def test_calculate_net_position(self):
        """Test net position calculation."""
        analyzer = CotAnalyzer()
        
        # Mock row data
        row = {
            'Noncommercial Longs': 1000,
            'Noncommercial Shorts': 400
        }
        
        net = analyzer.calculate_net_position(row)
        assert net == 600
    
    def test_calculate_net_pct_oi(self):
        """Test net position as % of OI."""
        analyzer = CotAnalyzer()
        
        row = {
            'Noncommercial Longs': 1000,
            'Noncommercial Shorts': 400,
            'Open Interest': 5000
        }
        
        net_pct = analyzer.calculate_net_pct_oi(row)
        assert net_pct == 12.0  # (600/5000)*100
    
    def test_classify_sentiment_strong_bull(self):
        """Test sentiment classification for strong bullish."""
        analyzer = CotAnalyzer()
        
        sentiment = analyzer.classify_sentiment(25.0)
        assert sentiment == "strong_bull"
    
    def test_classify_sentiment_strong_bear(self):
        """Test sentiment classification for strong bearish."""
        analyzer = CotAnalyzer()
        
        sentiment = analyzer.classify_sentiment(-25.0)
        assert sentiment == "strong_bear"
    
    def test_classify_sentiment_neutral(self):
        """Test sentiment classification for neutral."""
        analyzer = CotAnalyzer()
        
        sentiment = analyzer.classify_sentiment(0.0)
        assert sentiment == "neutral"
    
    def test_calculate_confidence(self):
        """Test confidence calculation."""
        analyzer = CotAnalyzer()
        
        row = {
            'Noncommercial Longs': 1000,
            'Noncommercial Shorts': 400,
            'Open Interest': 5000
        }
        
        confidence = analyzer.calculate_confidence(row)
        assert 0.0 <= confidence <= 1.0
