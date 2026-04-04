from trading.signals import Signal, Direction, SignalAggregator, MacroSignalProducer
from trading.cot.cot_analyzer import CotAnalyzer

class CotSignalProducer:
    \"\"\"
    Produces COT-based signals integrated with Nave FITS Sentiment.
    Compares BTC/ETH and scans Hyperliquid perps for opportunities.
    \"\"\"
    
    def __init__(self, client=None):
        self.analyzer = CotAnalyzer()
        self.client = client  # HyperliquidClient for perp scan
    
    def produce(self) -> list[Signal]:
        cot_compare = self.analyzer.compare_btc_eth()
        signals = []
        if cot_compare['btc_signal']:
            signals.append(cot_compare['btc_signal'])
        if cot_compare['eth_signal']:
            signals.append(cot_compare['eth_signal'])
        
        # Integrate macro (stub - replace with real OpenBB pulls)
        macro = MacroSignalProducer()
        macro_signals = macro.produce(self._stub_macro())
        signals += macro_signals
        
        # Scan other Hyperliquid perps (extensible)
        if self.client:
            signals += self._scan_perps()
        
        return signals
    
    def _stub_macro(self) -> dict:
        # TODO: Integrate real nave indicators (RRP, VIX, etc.)
        return {}
    
    def _scan_perps(self) -> list[Signal]:
        signals = []
        markets = self.client.get_markets()[:20]  # Top 20 by name
        for coin in markets:
            if coin in ['BTC', 'ETH']:
                continue
            # Stub: Funding rate, liquidity filter (extend with vol, funding)
            conf = 0.4  # Low conf for alts
            dir_ = Direction.LONG  # Stub
            sig = Signal(coin=coin, direction=dir_, confidence=conf, source='perp-scan')
            signals.append(sig)
        return signals

# Update existing MacroSignalProducer to use COT
def cot_producer_example():
    producer = CotSignalProducer()
    signals = producer.produce()
    agg = SignalAggregator(signals)
    agg.summary()
    return agg