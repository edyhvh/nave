"""Historical COT data fetcher for backtesting."""

from typing import Dict, Any, Optional, Union
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd


class HistoricalCotFetcher:
    """
    Replays historical COT data for backtesting.

    Usage:
        fetcher = HistoricalCotFetcher('tests/backtest/fixtures/cot_historical.csv')
        fetcher.set_date(datetime(2023, 6, 1))
        data = fetcher.latest_btc()  # Returns COT data as of that date
    """

    BTC_CODE = '133741'
    ETH_CODE = '138741'

    def __init__(self, data_path: Optional[Union[str, Path]] = None):
        """
        Initialize with historical COT data.

        Args:
            data_path: Path to CSV with COT data. If None, uses default fixture path.
        """
        if data_path is None:
            resolved_data_path: Union[str, Path] = Path(
                __file__).parent.parent / 'fixtures' / 'cot_historical.csv'
        else:
            resolved_data_path = data_path

        try:
            self.data = pd.read_csv(
                resolved_data_path, parse_dates=['report_date'])
        except (FileNotFoundError, pd.errors.EmptyDataError):
            # Synthetic fallback for tests/manual runs without fixtures (no account needed)
            self.data = self._generate_synthetic_data()
        self.data = self.data.sort_values('report_date').reset_index(drop=True)
        self.current_idx = 0
        self._current_date: Optional[datetime] = None

    def _generate_synthetic_data(self) -> pd.DataFrame:
        """Generate synthetic COT data for tests/backtests when CSV missing.

        Generates separate columns for BTC and ETH with distinct profiles
        to avoid the duplication bug where both assets show the same values.
        """
        import numpy as np
        dates = pd.date_range(start='2022-01-01',
                              end='2025-03-31', freq='W-TUE')
        np.random.seed(42)
        data = []
        for i, date in enumerate(dates):
            # BTC: larger contracts, specs tend net short
            btc_net_pct = np.clip(15 * np.sin(i / 10) +
                                  np.random.normal(0, 5), -30, 30)
            btc_change = np.random.normal(0, 1000)
            if btc_net_pct > 10:
                btc_change += 500
            elif btc_net_pct < -10:
                btc_change -= 500

            # ETH: different cycle, smaller scale, phase-shifted
            eth_net_pct = np.clip(
                12 * np.sin(i / 8 + 2) + np.random.normal(0, 4), -25, 25)
            eth_change = np.random.normal(0, 600)
            if eth_net_pct > 8:
                eth_change += 300
            elif eth_net_pct < -8:
                eth_change -= 300

            data.append({
                'report_date': date,
                # BTC columns
                'btc_noncomm_long': 50000 + btc_net_pct * 500,
                'btc_noncomm_short': 50000 - btc_net_pct * 500,
                'btc_noncomm_net': btc_net_pct * 1000,
                'btc_open_interest': 100000,
                'btc_noncomm_pct_oi': btc_net_pct,
                'btc_change_noncomm_net': btc_change,
                'btc_comm_long': 30000 - btc_net_pct * 300,
                'btc_comm_short': 30000 + btc_net_pct * 300,
                # ETH columns
                'eth_noncomm_long': 12000 + eth_net_pct * 200,
                'eth_noncomm_short': 12000 - eth_net_pct * 200,
                'eth_noncomm_net': eth_net_pct * 400,
                'eth_open_interest': 25000,
                'eth_noncomm_pct_oi': eth_net_pct,
                'eth_change_noncomm_net': eth_change,
                'eth_comm_long': 8000 - eth_net_pct * 120,
                'eth_comm_short': 8000 + eth_net_pct * 120,
                # Legacy fallback columns (BTC as default)
                'noncomm_long': 50000 + btc_net_pct * 500,
                'noncomm_short': 50000 - btc_net_pct * 500,
                'noncomm_net': btc_net_pct * 1000,
                'open_interest': 100000,
                'noncomm_pct_oi': btc_net_pct,
                'change_noncomm_net': btc_change,
            })
        return pd.DataFrame(data)

    def set_date(self, date: datetime):
        """Set current backtest date. Returns data as of most recent COT report."""
        self._current_date = date
        # Find most recent report date <= current date
        mask = self.data['report_date'] <= date
        if mask.any():
            self.current_idx = self.data[mask].index[-1]
        else:
            self.current_idx = 0

    def advance(self, weeks: int = 1):
        """Advance time by N weeks (COT reports are weekly)."""
        self.current_idx = min(self.current_idx + weeks, len(self.data) - 1)
        self._current_date = self.data.iloc[self.current_idx]['report_date']

    def latest_btc(self) -> Dict[str, Any]:
        """Return BTC COT data as of current backtest date."""
        row = self.data.iloc[self.current_idx]
        return self._parse_row(row, 'BTC')

    def latest_eth(self) -> Dict[str, Any]:
        """Return ETH COT data as of current backtest date."""
        # ETH data would be in separate file or filtered column
        # For now, assume separate file or add asset column
        row = self.data.iloc[self.current_idx]
        return self._parse_row(row, 'ETH')

    def _parse_row(self, row: pd.Series, asset: str) -> Dict[str, Any]:
        """Parse COT row to standardized dict."""
        prefix = 'btc_' if asset == 'BTC' else 'eth_'

        return {
            'report_date': row.get('report_date', self._current_date),
            'asset': asset,
            'noncomm_long': row.get(f'{prefix}noncomm_long', row.get('noncomm_long', 0)),
            'noncomm_short': row.get(f'{prefix}noncomm_short', row.get('noncomm_short', 0)),
            'noncomm_net': row.get(f'{prefix}noncomm_net', row.get('noncomm_net', 0)),
            'open_interest': row.get(f'{prefix}open_interest', row.get('open_interest', 0)),
            'noncomm_pct_oi': row.get(f'{prefix}noncomm_pct_oi', row.get('noncomm_pct_oi', 0)),
            'change_noncomm_long': row.get(f'{prefix}change_noncomm_long', row.get('change_noncomm_long', 0)),
            'change_noncomm_short': row.get(f'{prefix}change_noncomm_short', row.get('change_noncomm_short', 0)),
            'change_noncomm_net': row.get(f'{prefix}change_noncomm_net', row.get('change_noncomm_net', 0)),
        }

    def get_historical_range(self, start: datetime, end: datetime, asset: str = 'BTC') -> pd.DataFrame:
        """Get COT data for a date range."""
        mask = (self.data['report_date'] >= start) & (
            self.data['report_date'] <= end)
        return self.data[mask].copy()

    @property
    def current_date(self) -> datetime:
        """Return current backtest date."""
        if self._current_date:
            return self._current_date
        return self.data.iloc[self.current_idx]['report_date']

    @property
    def total_weeks(self) -> int:
        """Return total weeks of data available."""
        return len(self.data)
