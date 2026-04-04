"""Tests for COT fetcher module."""
import pytest
from unittest.mock import patch, MagicMock
from trading.cot import CotFetcher


class TestCotFetcher:
    """Test cases for CotFetcher."""
    
    def test_fetcher_initialization(self):
        """Test fetcher initializes correctly."""
        fetcher = CotFetcher()
        assert fetcher is not None
        assert fetcher.btc_code == "133741"
        assert fetcher.eth_code == "138741"
    
    def test_btc_code_property(self):
        """Test BTC code property."""
        fetcher = CotFetcher()
        assert fetcher.btc_code == "133741"
    
    def test_eth_code_property(self):
        """Test ETH code property."""
        fetcher = CotFetcher()
        assert fetcher.eth_code == "138741"
    
    @patch('cot_reports.cot_reports.cot_hist')
    def test_latest_btc_returns_data(self, mock_cot_hist):
        """Test latest_btc returns data."""
        # Mock return data
        mock_data = MagicMock()
        mock_data.empty = False
        mock_cot_hist.return_value = mock_data
        
        fetcher = CotFetcher()
        result = fetcher.latest_btc()
        
        assert result is not None
        mock_cot_hist.assert_called_once()
    
    @patch('cot_reports.cot_reports.cot_hist')
    def test_latest_eth_returns_data(self, mock_cot_hist):
        """Test latest_eth returns data."""
        mock_data = MagicMock()
        mock_data.empty = False
        mock_cot_hist.return_value = mock_data
        
        fetcher = CotFetcher()
        result = fetcher.latest_eth()
        
        assert result is not None
        mock_cot_hist.assert_called_once()
    
    @patch('cot_reports.cot_reports.cot_hist')
    def test_fetch_both_returns_tuple(self, mock_cot_hist):
        """Test fetch_both returns tuple of data."""
        mock_data = MagicMock()
        mock_data.empty = False
        mock_cot_hist.return_value = mock_data
        
        fetcher = CotFetcher()
        btc_data, eth_data = fetcher.fetch_both()
        
        assert btc_data is not None
        assert eth_data is not None
