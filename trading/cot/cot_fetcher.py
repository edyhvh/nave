from cot_reports import COTReport
import pandas as pd
from typing import Dict, Any
from datetime import datetime

class CotFetcher:
    """
    Fetches latest COT data using cot-reports library.
    
    BTC: CME Bitcoin Futures (133741 - legacy futures)
    ETH: CME Ether Futures (138741 - legacy futures)
    """
    BTC_CODE = '133741'
    ETH_CODE = '138741'
    
    def __init__(self):
        self.btc_report = COTReport('legacy_futures', self.BTC_CODE)
        self.eth_report = COTReport('legacy_futures', self.ETH_CODE)
    
    def latest_btc(self) -> Dict[str, Any]:
        latest = self.btc_report.latest()
        return self._parse_row(latest)
    
    def latest_eth(self) -> Dict[str, Any]:
        latest = self.eth_report.latest()
        return self._parse_row(latest)
    
    def _parse_row(self, row: pd.Series) -> Dict[str, Any]:
        """Parse COT row to dict with key metrics."""
        return {
            'report_date': row.get('Report_Date_as_YYYY-MM-DD', ''),
            'noncomm_long': row.get('NonComm_Positions_Long_All', 0),
            'noncomm_short': row.get('NonComm_Positions_Short_All', 0),
            'noncomm_net': row.get('NonComm_Positions_Long_All', 0) - row.get('NonComm_Positions_Short_All', 0),
            'open_interest': row.get('Open_Interest', 0),
            'noncomm_pct_oi': (row.get('NonComm_Positions_Long_All', 0) - row.get('NonComm_Positions_Short_All', 0)) / row.get('Open_Interest', 1) * 100,
            'change_noncomm_long': row.get('Change_in_NonComm_Positions_Long_All', 0),
            'change_noncomm_short': row.get('Change_in_NonComm_Positions_Short_All', 0),
            'change_noncomm_net': row.get('Change_in_NonComm_Positions_Long_All', 0) - row.get('Change_in_NonComm_Positions_Short_All', 0),
        }