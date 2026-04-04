from abc import ABC
from trading.client import HyperliquidClient
from trading.signals import CotSignalProducer, SignalAggregator
from trading.cot.cot_analyzer import CotAnalyzer

class CotWeeklyStrategy(BaseStrategy):
    \"\"\"
    Weekly COT-driven strategy respecting Nave philosophy.
    
    1. COT as primary FITS Sentiment bias (BTC vs ETH comparison).
    2. Combine with macro (RRP, VIX, etc.).
    3. Check 4H/1H setups (75% retrace, FVG, confluence).
    4. Recommend best asset + sizing/leverage.
    5. Scan Hyperliquid perps for alts.
    \"\"\"
    
    def __init__(self, client: HyperliquidClient, capital_usd: float = 2000.0, **kwargs):
        super().__init__(client, **kwargs)
        self.capital = capital_usd
        self.risk_pct = 0.10  # 8-12% risk per trade
    
    def compute_signals(self) -> list[Signal]:
        producer = CotSignalProducer(self.client)
        return producer.produce()
    
    def weekly_report(self) -> str:
        signals = self.compute_signals()
        agg = SignalAggregator(signals)
        
        report = [\"## Nave Weekly COT Report (Sunday)\"]
        report.append(f\"Capital: ${self.capital:,.0f} | Risk/Trade: {self.risk_pct*100:.0f}%\\n\")
        
        btc_net = agg.net_direction('BTC')
        eth_net = agg.net_direction('ETH')
        cot = CotAnalyzer()
        compare = cot.compare_btc_eth()
        
        best = compare['best_asset']
        best_sig = getattr(compare[f'{best.lower()}_signal'], 'confidence', 0)
        
        report.append(f\"### COT Bias: {compare['btc_score']:.2f} BTC | {compare['eth_score']:.2f} ETH\")
        report.append(f\"**Best Setup: {best} ({best_net.value.upper()}) Conf: {best_sig:.2f}\"\\n\")
        
        # Sizing example (Nave risk mgmt)
        leverage = min(20 * best_sig, 10)  # Max 10x, scaled by conf
        size_usd = self.capital * self.risk_pct / 0.02  # Assume 2% SL dist
        report.append(f\"Recommendation: Allocate 100% to {best}-{best_net.value.upper()}\\n\")
        report.append(f\"Size: ${size_usd:,.0f} | Leverage: {leverage:.0f}x | SL: Invalidation point\\n\")
        
        # Philosophy tie-in
        report.append(\"### FITS Alignment:\")
        report.append(\"- **Sentiment (COT)**: Smart money net positions.\")
        report.append(\"- **Technical**: 75% retrace + confluence zones on 4H/1H.\")
        report.append(\"- **Fundamental/Intermarket**: Macro bias (TGA/RRP/VIX).\")\n\n\")
        
        # Perp scan
        report.append(\"### Other Hyperliquid Opportunities:\")
        alts = [s for s in signals if s.coin not in ['BTC', 'ETH']]
        for s in sorted(alts, key=lambda x: -x.confidence)[:5]:
            report.append(f\"- {s.coin} {s.direction.value} ({s.confidence:.2f}): Good liq/funding\")
        
        return '\\n'.join(report)