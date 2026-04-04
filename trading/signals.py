"""
Nave Trading Signals - Signal generation framework with COT integration.

Implements F.I.T.S. framework:
- Fundamental (macro, ETF flows)
- Intermarket (RRP, VIX, yields)
- Technical (IPDA, 75% retrace, FVG, confluence)
- Sentiment (COT as primary driver)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol
import statistics


class Direction(Enum):
    """Trade direction enumeration."""
    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"


@dataclass
class Signal:
    """
    Trading signal with Nave philosophy alignment.
    
    Attributes:
        coin: Asset symbol (BTC, ETH, etc.)
        direction: LONG, SHORT, or NEUTRAL
        confidence: 0.0-1.0 score
        source: Signal origin (cot/sentiment, macro, technical, perp-scan)
        timeframe: Primary timeframe (4H, 1H, etc.)
        metadata: Additional context (COT data, levels, etc.)
        timestamp: Signal generation time
    """
    coin: str
    direction: Direction
    confidence: float  # 0.0-1.0
    source: str
    timeframe: str = "4H"
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def __post_init__(self):
        self.confidence = max(0.0, min(1.0, self.confidence))


class SignalProducer(Protocol):
    """Protocol for signal generation components."""
    def produce(self) -> List[Signal]: ...


class SignalAggregator:
    """
    Aggregates signals across sources for consensus decision-making.
    Implements confluence scoring per Nave philosophy.
    """
    
    def __init__(self, signals: List[Signal]):
        self.signals = signals
    
    def by_coin(self, coin: str) -> List[Signal]:
        """Get all signals for a specific coin."""
        return [s for s in self.signals if s.coin.upper() == coin.upper()]
    
    def net_direction(self, coin: str) -> Direction:
        """
        Calculate net directional bias for a coin.
        Weights by confidence and source reliability.
        """
        coin_sigs = self.by_coin(coin)
        if not coin_sigs:
            return Direction.NEUTRAL
        
        # Weight by confidence
        long_score = sum(s.confidence for s in coin_sigs if s.direction == Direction.LONG)
        short_score = sum(s.confidence for s in coin_sigs if s.direction == Direction.SHORT)
        
        threshold = 0.3
        if long_score - short_score > threshold:
            return Direction.LONG
        elif short_score - long_score > threshold:
            return Direction.SHORT
        return Direction.NEUTRAL
    
    def confluence_score(self, coin: str) -> float:
        """
        Calculate confluence score (0-1) based on signal alignment.
        High confluence = multiple sources agreeing.
        """
        coin_sigs = self.by_coin(coin)
        if len(coin_sigs) < 2:
            return coin_sigs[0].confidence if coin_sigs else 0.0
        
        directions = [s.direction for s in coin_sigs]
        confidences = [s.confidence for s in coin_sigs]
        
        # Check alignment
        if len(set(directions)) == 1:
            # All agree - boost confluence
            return min(1.0, statistics.mean(confidences) * 1.2)
        
        # Mixed signals - reduce confluence
        return statistics.mean(confidences) * 0.7
    
    def best_setup(self) -> Optional[Signal]:
        """Return the highest-confidence signal with best confluence."""
        if not self.signals:
            return None
        
        # Score each signal by confidence + confluence boost
        scored = []
        for sig in self.signals:
            conf = self.confluence_score(sig.coin)
            scored.append((sig.confidence * conf, sig))
        
        scored.sort(key=lambda x: -x[0])
        return scored[0][1] if scored else None
    
    def summary(self) -> Dict[str, Any]:
        """Generate summary statistics for all signals."""
        coins = set(s.coin for s in self.signals)
        return {
            'total_signals': len(self.signals),
            'coins': list(coins),
            'by_direction': {
                'long': len([s for s in self.signals if s.direction == Direction.LONG]),
                'short': len([s for s in self.signals if s.direction == Direction.SHORT]),
                'neutral': len([s for s in self.signals if s.direction == Direction.NEUTRAL]),
            },
            'best_setup': self.best_setup(),
            'avg_confidence': statistics.mean([s.confidence for s in self.signals]) if self.signals else 0,
        }


class MacroSignalProducer:
    """
    Produces macro-based signals (Fundamental + Intermarket in FITS).
    
    Integrates:
    - TGA (Treasury General Account) - liquidity drain/injection
    - RRP (Reverse Repo) - liquidity conditions
    - VIX - volatility regime
    - ETF flows - institutional demand
    - Yields curve - risk-on/off
    """
    
    def __init__(self, openbb_client=None):
        self.openbb = openbb_client
    
    def produce(self, indicators: Optional[Dict] = None) -> List[Signal]:
        """
        Generate macro signals from indicator data.
        
        Args:
            indicators: Dict with keys like 'vix', 'tga_change', 'rrp', 'etf_flows'
        """
        signals = []
        indicators = indicators or {}
        
        # VIX regime signal
        vix = indicators.get('vix', 20)
        if vix > 30:
            # High vol - risk off, favor shorts or options
            signals.append(Signal(
                coin='MARKET',
                direction=Direction.SHORT,
                confidence=min(0.8, vix / 50),
                source='macro/vix',
                metadata={'vix': vix, 'regime': 'high_vol'}
            ))
        elif vix < 15:
            # Low vol - complacency warning
            signals.append(Signal(
                coin='MARKET',
                direction=Direction.NEUTRAL,
                confidence=0.5,
                source='macro/vix',
                metadata={'vix': vix, 'regime': 'low_vol_complacency'}
            ))
        
        # TGA liquidity signal
        tga_change = indicators.get('tga_change', 0)
        if tga_change < -50:  # TGA draining = liquidity injection
            signals.append(Signal(
                coin='CRYPTO',
                direction=Direction.LONG,
                confidence=min(0.7, abs(tga_change) / 200),
                source='macro/tga',
                metadata={'tga_change': tga_change, 'liquidity': 'injection'}
            ))
        elif tga_change > 50:  # TGA filling = liquidity drain
            signals.append(Signal(
                coin='CRYPTO',
                direction=Direction.SHORT,
                confidence=min(0.7, tga_change / 200),
                source='macro/tga',
                metadata={'tga_change': tga_change, 'liquidity': 'drain'}
            ))
        
        # ETF flows (BTC specific)
        etf_flows = indicators.get('etf_flows_btc', 0)
        if etf_flows > 100:  # $100M+ inflows
            signals.append(Signal(
                coin='BTC',
                direction=Direction.LONG,
                confidence=min(0.85, etf_flows / 500),
                source='macro/etf',
                metadata={'etf_flows': etf_flows, 'institutional_demand': 'strong'}
            ))
        elif etf_flows < -100:
            signals.append(Signal(
                coin='BTC',
                direction=Direction.SHORT,
                confidence=min(0.75, abs(etf_flows) / 500),
                source='macro/etf',
                metadata={'etf_flows': etf_flows, 'institutional_demand': 'weak'}
            ))
        
        return signals


class TechnicalSignalProducer:
    """
    Produces technical signals based on Nave philosophy.
    
    Key concepts:
    - IPDA phases (expansion, retracement, regression, consolidation)
    - 75% retracement setups
    - Mitigation blocks, Order blocks, FVG
    - Confluence zones (institutional levels + swings + FVG)
    """
    
    def __init__(self, openbb_client=None):
        self.openbb = openbb_client
    
    def produce(self, market_data: Optional[Dict] = None) -> List[Signal]:
        """
        Generate technical signals from market structure data.
        
        Args:
            market_data: Dict with OHLCV, swing highs/lows, FVGs, etc.
        """
        signals = []
        market_data = market_data or {}
        
        # This is a stub - real implementation would integrate with
        # OpenBB technical analysis or custom IPDA detection
        for coin in ['BTC', 'ETH']:
            data = market_data.get(coin, {})
            
            # Check for 75% retracement setup
            retracement = data.get('retracement_pct', 0)
            trend = data.get('trend', 'neutral')
            
            if 0.70 <= retracement <= 0.80 and trend in ['bullish', 'bearish']:
                direction = Direction.LONG if trend == 'bullish' else Direction.SHORT
                signals.append(Signal(
                    coin=coin,
                    direction=direction,
                    confidence=0.75,
                    source='technical/75retrace',
                    timeframe=data.get('timeframe', '4H'),
                    metadata={
                        'retracement_pct': retracement,
                        'trend': trend,
                        'setup': '75%_retracement',
                        'confluence': data.get('confluence_score', 0)
                    }
                ))
            
            # Check for FVG fill setup
            if data.get('fvg_fill', False):
                direction = Direction.LONG if data.get('fvg_type') == 'bullish' else Direction.SHORT
                signals.append(Signal(
                    coin=coin,
                    direction=direction,
                    confidence=0.65,
                    source='technical/fvg',
                    timeframe=data.get('timeframe', '1H'),
                    metadata={'setup': 'fvg_fill', 'fvg_size': data.get('fvg_size', 0)}
                ))
        
        return signals


# Import COT components at end to avoid circular imports
from trading.cot.cot_analyzer import CotAnalyzer


class CotSignalProducer:
    """
    Produces COT-based signals integrated with Nave FITS Sentiment.
    
    This is the PRIMARY weekly driver - COT is the Sentiment pillar.
    Compares BTC/ETH and scans Hyperliquid perps for opportunities.
    """
    
    def __init__(self, client=None):
        self.analyzer = CotAnalyzer()
        self.client = client  # HyperliquidClient for perp scan
        self.macro = MacroSignalProducer()
        self.technical = TechnicalSignalProducer()
    
    def produce(self, include_macro: bool = True, include_technical: bool = True) -> List[Signal]:
        """
        Generate complete signal set for weekly COT analysis.
        
        Flow:
        1. COT signals (BTC/ETH comparison)
        2. Macro signals (if enabled)
        3. Technical signals (if enabled)
        4. Perp scan for alt opportunities
        """
        signals = []
        
        # 1. COT as primary sentiment driver
        cot_compare = self.analyzer.compare_btc_eth()
        if cot_compare['btc_signal']:
            signals.append(cot_compare['btc_signal'])
        if cot_compare['eth_signal']:
            signals.append(cot_compare['eth_signal'])
        
        # 2. Macro context (FITS Fundamental + Intermarket)
        if include_macro:
            macro_signals = self.macro.produce(self._fetch_macro_indicators())
            signals.extend(macro_signals)
        
        # 3. Technical confluence (FITS Technical)
        if include_technical:
            tech_signals = self.technical.produce(self._fetch_technical_data())
            signals.extend(tech_signals)
        
        # 4. Scan other Hyperliquid perps (extensible)
        if self.client:
            signals.extend(self._scan_perps())
        
        return signals
    
    def compare_assets(self) -> Dict[str, Any]:
        """
        Compare BTC vs ETH setups and return recommendation.
        
        Returns:
            Dict with best_asset, scores, and allocation recommendation.
        """
        cot_compare = self.analyzer.compare_btc_eth()
        
        # Get aggregated signals for each
        btc_signals = [s for s in self.produce() if s.coin == 'BTC']
        eth_signals = [s for s in self.produce() if s.coin == 'ETH']
        
        btc_agg = SignalAggregator(btc_signals)
        eth_agg = SignalAggregator(eth_signals)
        
        btc_confluence = btc_agg.confluence_score('BTC')
        eth_confluence = eth_agg.confluence_score('ETH')
        
        # COT score + confluence boost
        btc_total = cot_compare['btc_score'] * (1 + btc_confluence)
        eth_total = cot_compare['eth_score'] * (1 + eth_confluence)
        
        best = 'BTC' if btc_total > eth_total else 'ETH'
        
        return {
            'btc_score': cot_compare['btc_score'],
            'eth_score': cot_compare['eth_score'],
            'btc_confluence': btc_confluence,
            'eth_confluence': eth_confluence,
            'btc_total': btc_total,
            'eth_total': eth_total,
            'best_asset': best,
            'btc_signal': cot_compare['btc_signal'],
            'eth_signal': cot_compare['eth_signal'],
        }
    
    def _fetch_macro_indicators(self) -> Dict[str, Any]:
        """Fetch macro indicators (stub - integrate with OpenBB)."""
        # TODO: Integrate real nave indicators via OpenBB
        # - VIX from openbb.index
        # - TGA from openbb.treasury
        # - ETF flows from openbb.etf or custom scraper
        return {
            'vix': 20,  # Placeholder
            'tga_change': 0,
            'rrp': 0,
            'etf_flows_btc': 0,
        }
    
    def _fetch_technical_data(self) -> Dict[str, Any]:
        """Fetch technical data (stub - integrate with OpenBB TA)."""
        # TODO: Integrate with openbb.crypto or custom IPDA detection
        return {
            'BTC': {'trend': 'bullish', 'retracement_pct': 0.75},
            'ETH': {'trend': 'bullish', 'retracement_pct': 0.72},
        }
    
    def _scan_perps(self) -> List[Signal]:
        """
        Scan Hyperliquid perps for high-quality opportunities.
        
        Filters:
        - Liquidity: >$1M daily volume
        - Funding: Favorable direction
        - Volatility: Suitable for setup
        - Margin efficiency: Good leverage available
        """
        signals = []
        
        if not self.client:
            return signals
        
        try:
            markets = self.client.get_markets()
            
            for coin in markets:
                if coin in ['BTC', 'ETH']:
                    continue
                
                # Stub: Real implementation would fetch:
                # - 24h volume (liquidity check)
                # - Funding rate (direction bias)
                # - Volatility metrics
                # - Order book depth (slippage estimate)
                
                # Scoring rubric for alts
                liquidity_score = 0.5  # Placeholder
                funding_bias = 0.0     # Placeholder
                vol_score = 0.5        # Placeholder
                
                # Only generate signals for quality setups
                overall_score = (liquidity_score + abs(funding_bias) + vol_score) / 3
                
                if overall_score > 0.6:
                    direction = Direction.LONG if funding_bias > 0 else Direction.SHORT
                    signals.append(Signal(
                        coin=coin,
                        direction=direction,
                        confidence=min(0.7, overall_score),
                        source='perp-scan',
                        timeframe='4H',
                        metadata={
                            'liquidity_score': liquidity_score,
                            'funding_bias': funding_bias,
                            'vol_score': vol_score,
                            'scan_reason': 'high_liquidity_favorable_funding'
                        }
                    ))
        
        except Exception as e:
            # Log error but don't fail entire signal generation
            print(f"Perp scan error: {e}")
        
        return signals


# Convenience function for CLI usage
def generate_weekly_signals(client=None, full_analysis: bool = True) -> Dict[str, Any]:
    """
    Generate complete weekly signal set with COT as primary driver.
    
    Usage:
        from trading.signals import generate_weekly_signals
        result = generate_weekly_signals(client)
        print(result['recommendation'])
    """
    producer = CotSignalProducer(client)
    
    if full_analysis:
        comparison = producer.compare_assets()
        signals = producer.produce()
    else:
        signals = producer.produce(include_macro=False, include_technical=False)
        comparison = producer.analyzer.compare_btc_eth()
    
    aggregator = SignalAggregator(signals)
    
    return {
        'signals': signals,
        'comparison': comparison,
        'summary': aggregator.summary(),
        'best_setup': aggregator.best_setup(),
    }