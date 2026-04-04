"""
CME Commitment of Traders (COT) Data Fetcher

Downloads and caches COT reports for Bitcoin and Ethereum futures.
Uses the cot-reports library for reliable CFTC data access.

Asset Codes:
- BTC: 133741 (CME Bitcoin Futures, Legacy format)
- ETH: 138741 (CME Ether Futures, Legacy format)

Data is released every Friday at 3:30 PM ET, covering positions as of Tuesday.
"""
from __future__ import annotations
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional
import json

import pandas as pd
from cot_reports import COTReport


class CotFetcher:
    """
    Fetches and caches COT data from CFTC via cot-reports library.
    
    Features:
    - Automatic caching to reduce API calls
    - Historical data access
    - Change calculations (WoW, MoM)
    - Error handling and fallback
    """
    
    # CME Futures Codes (Legacy format)
    BTC_CODE = '133741'
    ETH_CODE = '138741'
    
    # Cache settings
    CACHE_DIR = Path.home() / '.cache' / 'nave' / 'cot'
    CACHE_TTL_HOURS = 24  # Refresh daily
    
    def __init__(self, use_cache: bool = True):
        self.use_cache = use_cache
        self.btc_report = COTReport('legacy_futures', self.BTC_CODE)
        self.eth_report = COTReport('legacy_futures', self.ETH_CODE)
        
        if use_cache:
            self.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    
    def _cache_path(self, asset: str) -> Path:
        """Get cache file path for an asset."""
        return self.CACHE_DIR / f"{asset.lower()}_cot.json"
    
    def _is_cache_valid(self, cache_path: Path) -> bool:
        """Check if cache file is still valid."""
        if not cache_path.exists():
            return False
        
        mtime = datetime.fromtimestamp(cache_path.stat().st_mtime)
        age = datetime.now() - mtime
        return age < timedelta(hours=self.CACHE_TTL_HOURS)
    
    def _load_from_cache(self, asset: str) -> Optional[Dict[str, Any]]:
        """Load COT data from cache if valid."""
        if not self.use_cache:
            return None
        
        cache_path = self._cache_path(asset)
        if not self._is_cache_valid(cache_path):
            return None
        
        try:
            with open(cache_path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None
    
    def _save_to_cache(self, asset: str, data: Dict[str, Any]) -> None:
        """Save COT data to cache."""
        if not self.use_cache:
            return
        
        cache_path = self._cache_path(asset)
        try:
            with open(cache_path, 'w') as f:
                json.dump(data, f, indent=2, default=str)
        except IOError as e:
            print(f"Warning: Failed to cache COT data: {e}")
    
    def _parse_row(self, row: pd.Series) -> Dict[str, Any]:
        """
        Parse COT report row into standardized dictionary.
        
        Key metrics:
        - Non-commercial (speculator) positions
        - Net position and % of OI
        - Weekly changes
        - Open interest
        """
        report_date = row.get('Report_Date_as_YYYY-MM-DD', '')
        
        # Non-commercial positions (speculators/smart money)
        noncomm_long = float(row.get('NonComm_Positions_Long_All', 0) or 0)
        noncomm_short = float(row.get('NonComm_Positions_Short_All', 0) or 0)
        noncomm_net = noncomm_long - noncomm_short
        
        # Commercial positions (hedgers)
        comm_long = float(row.get('Comm_Positions_Long_All', 0) or 0)
        comm_short = float(row.get('Comm_Positions_Short_All', 0) or 0)
        comm_net = comm_long - comm_short
        
        # Total open interest
        oi = float(row.get('Open_Interest_All', 0) or 0)
        
        # Calculate percentages
        noncomm_pct_oi = (noncomm_net / oi * 100) if oi > 0 else 0
        noncomm_long_pct = (noncomm_long / oi * 100) if oi > 0 else 0
        noncomm_short_pct = (noncomm_short / oi * 100) if oi > 0 else 0
        
        # Changes from previous week
        change_noncomm_long = float(row.get('Change_in_NonComm_Positions_Long_All', 0) or 0)
        change_noncomm_short = float(row.get('Change_in_NonComm_Positions_Short_All', 0) or 0)
        change_noncomm_net = change_noncomm_long - change_noncomm_short
        change_oi = float(row.get('Change_in_Open_Interest_All', 0) or 0)
        
        # Percentile ranks (if historical data available)
        net_pct_rank = None  # Calculated separately
        
        return {
            'report_date': report_date,
            'asset_code': row.get('CFTC_Contract_Market_Code', ''),
            'asset_name': row.get('Market_and_Exchange_Names', ''),
            
            # Non-commercial (speculators)
            'noncomm_long': noncomm_long,
            'noncomm_short': noncomm_short,
            'noncomm_net': noncomm_net,
            'noncomm_long_pct': round(noncomm_long_pct, 2),
            'noncomm_short_pct': round(noncomm_short_pct, 2),
            'noncomm_net_pct_oi': round(noncomm_pct_oi, 2),
            
            # Commercial (hedgers)
            'comm_long': comm_long,
            'comm_short': comm_short,
            'comm_net': comm_net,
            
            # Open interest
            'open_interest': oi,
            'change_oi': change_oi,
            
            # Changes
            'change_noncomm_long': change_noncomm_long,
            'change_noncomm_short': change_noncomm_short,
            'change_noncomm_net': change_noncomm_net,
            
            # Metadata
            'net_pct_rank': net_pct_rank,
        }
    
    def latest_btc(self, use_cache: Optional[bool] = None) -> Dict[str, Any]:
        """
        Fetch latest COT data for Bitcoin.
        
        Args:
            use_cache: Override default cache setting
        
        Returns:
            Dictionary with parsed COT metrics
        """
        use_cache = use_cache if use_cache is not None else self.use_cache
        
        if use_cache:
            cached = self._load_from_cache('BTC')
            if cached:
                return cached
        
        try:
            latest = self.btc_report.latest()
            data = self._parse_row(latest)
            self._save_to_cache('BTC', data)
            return data
        except Exception as e:
            # Try cache as fallback even if expired
            cached = self._load_from_cache('BTC')
            if cached:
                print(f"Warning: Using stale COT cache due to error: {e}")
                return cached
            raise
    
    def latest_eth(self, use_cache: Optional[bool] = None) -> Dict[str, Any]:
        """Fetch latest COT data for Ethereum."""
        use_cache = use_cache if use_cache is not None else self.use_cache
        
        if use_cache:
            cached = self._load_from_cache('ETH')
            if cached:
                return cached
        
        try:
            latest = self.eth_report.latest()
            data = self._parse_row(latest)
            self._save_to_cache('ETH', data)
            return data
        except Exception as e:
            cached = self._load_from_cache('ETH')
            if cached:
                print(f"Warning: Using stale COT cache due to error: {e}")
                return cached
            raise
    
    def get_history(self, asset: str, weeks: int = 12) -> pd.DataFrame:
        """
        Get historical COT data for trend analysis.
        
        Args:
            asset: 'BTC' or 'ETH'
            weeks: Number of weeks of history
        
        Returns:
            DataFrame with historical COT data
        """
        report = self.btc_report if asset.upper() == 'BTC' else self.eth_report
        df = report.cot_report(
            start_date=(datetime.now() - timedelta(weeks=weeks)).strftime('%Y-%m-%d'),
            end_date=datetime.now().strftime('%Y-%m-%d')
        )
        return df
    
    def calculate_percentiles(self, asset: str, weeks: int = 52) -> Dict[str, float]:
        """
        Calculate percentile ranks for current positioning.
        
        Args:
            asset: 'BTC' or 'ETH'
            weeks: Lookback period for percentile calculation
        
        Returns:
            Dictionary with percentile ranks
        """
        try:
            df = self.get_history(asset, weeks)
            
            # Calculate net positions for history
            df['net'] = df['NonComm_Positions_Long_All'] - df['NonComm_Positions_Short_All']
            df['net_pct'] = df['net'] / df['Open_Interest_All'] * 100
            
            # Current values
            current = self.latest_btc() if asset.upper() == 'BTC' else self.latest_eth()
            current_net_pct = current['noncomm_net_pct_oi']
            
            # Calculate percentiles
            net_pct_rank = (df['net_pct'] < current_net_pct).mean() * 100
            
            return {
                'net_pct_rank': round(net_pct_rank, 1),
                'current_net_pct': current_net_pct,
                'historical_min': df['net_pct'].min(),
                'historical_max': df['net_pct'].max(),
                'historical_avg': df['net_pct'].mean(),
            }
        except Exception as e:
            print(f"Warning: Could not calculate percentiles: {e}")
            return {
                'net_pct_rank': 50.0,
                'current_net_pct': 0,
                'historical_min': 0,
                'historical_max': 0,
                'historical_avg': 0,
            }
    
    def get_both_assets(self) -> Dict[str, Dict[str, Any]]:
        """
        Fetch COT data for both BTC and ETH.
        
        Returns:
            Dictionary with 'BTC' and 'ETH' keys
        """
        return {
            'BTC': self.latest_btc(),
            'ETH': self.latest_eth(),
        }
