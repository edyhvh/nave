from typing import Dict, Any
from trading.signals import Signal, Direction
from .cot_fetcher import CotFetcher

class CotAnalyzer:
    \"\"\"
    Analyzes COT data for trading bias using Nave FITS (Sentiment component).
    
    Rules (non-commercial net positions):
    - Net long >20% OI + increasing: Strong BULL (high conf)
    - Net long >10% OI + stable/increasing: Bull
    - Net short >20% OI + increasing: Strong BEAR
    - Net short >10% OI + stable/increasing: Bear
    - Divergence (net extreme but macro against): Caution/CLOSE
    \"\"\"
    
    def __init__(self):
        self.fetcher = CotFetcher()
    
    def analyze_btc(self) -> Signal:
        data = self.fetcher.latest_btc()
        return self._generate_signal('BTC', data)
    
    def analyze_eth(self) -> Signal:
        data = self.fetcher.latest_eth()
        return self._generate_signal('ETH', data)
    
    def compare_btc_eth(self) -> Dict[str, Any]:
        btc_sig = self.analyze_btc()
        eth_sig = self.analyze_eth()
        btc_score = btc_sig.confidence if btc_sig else 0
        eth_score = eth_sig.confidence if eth_sig else 0
        best = 'BTC' if btc_score > eth_score else 'ETH'
        return {
            'btc_signal': btc_sig,
            'eth_signal': eth_sig,
            'best_asset': best,
            'btc_score': btc_score,
            'eth_score': eth_score,
        }
    
    def _generate_signal(self, symbol: str, data: Dict[str, Any]) -> Signal | None:
        net_pct = data['noncomm_pct_oi']
        net_change = data['change_noncomm_net']
        oi = data['open_interest']
        
        if oi < 1000:  # Low liquidity filter
            return None
        
        conf = 0.0
        dir_str = Direction.NEUTRAL
        
        if net_pct > 20 and net_change > 0:
            conf = min(0.9, net_pct / 50 + abs(net_change) / oi * 100)
            dir_str = Direction.LONG
        elif net_pct > 10 and net_change >= -500:
            conf = min(0.7, net_pct / 30)
            dir_str = Direction.LONG
        elif net_pct < -20 and net_change < 0:
            conf = min(0.9, abs(net_pct) / 50 + abs(net_change) / oi * 100)
            dir_str = Direction.SHORT
        elif net_pct < -10 and net_change <= 500:
            conf = min(0.7, abs(net_pct) / 30)
            dir_str = Direction.SHORT
        else:
            return None
        
        metadata = {
            'report_date': data['report_date'],
            'net_pct_oi': round(net_pct, 1),
            'net_change': net_change,
        }
        
        return Signal(
            coin=symbol,
            direction=dir_str,
            confidence=conf,
            source='cot/sentiment',
            metadata=metadata
        )