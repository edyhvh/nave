"""
Nave COT (Commitment of Traders) Module

Provides CME COT data integration for Nave trading system.

Components:
- CotFetcher: Downloads and caches COT reports
- CotAnalyzer: Generates trading signals from COT data
- COT codes: BTC=133741, ETH=138741

Usage:
    from trading.cot import CotFetcher, CotAnalyzer
    
    fetcher = CotFetcher()
    btc_data = fetcher.latest_btc()
    
    analyzer = CotAnalyzer()
    comparison = analyzer.compare_btc_eth()
"""
from .cot_fetcher import CotFetcher
from .cot_analyzer import CotAnalyzer, CotAnalysis

__all__ = ['CotFetcher', 'CotAnalyzer', 'CotAnalysis']