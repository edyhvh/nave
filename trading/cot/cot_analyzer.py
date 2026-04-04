"""
CME Commitment of Traders (COT) Analyzer

Analyzes COT data to generate trading signals aligned with Nave philosophy.

Key Concepts:
- Non-commercial (speculator) positions = "Smart Money" sentiment
- Net positioning as % of Open Interest = conviction level
- Changes in positioning = momentum/acceleration
- Extreme positioning = potential reversal (contrarian signal)

Nave FITS Integration:
- COT is the Sentiment pillar
- Combined with Fundamental (macro), Intermarket (RRP/VIX), Technical (IPDA)
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any, Optional, List
from datetime import datetime
import statistics

from trading.signals import Signal, Direction
from .cot_fetcher import CotFetcher


@dataclass
class CotAnalysis:
    """Structured COT analysis result."""
    asset: str
    net_position: float
    net_pct_oi: float
    net_change: float
    confidence: float
    bias: Direction
    strength: str  # 'extreme', 'strong', 'moderate', 'weak', 'neutral'
    percentile: Optional[float] = None
    signal: Optional[Signal] = None


class CotAnalyzer:
    """
    Analyzes COT data for trading bias using Nave FITS framework.
    
    Signal Generation Rules:
    - Net long >20% OI + increasing: Strong BULL (high conf)
    - Net long >10% OI + stable/increasing: Bull
    - Net short >20% OI + increasing: Strong BEAR
    - Net short >10% OI + stable/increasing: Bear
    - Extreme positioning (>90th percentile): Caution/Reversal risk
    - Divergence (net extreme but price against): Close signal
    
    Scoring:
    - Base score from net %OI
    - Boost from change momentum
    - Reduction from extreme percentiles (contrarian)
    """
    
    # Thresholds for signal generation
    STRONG_BULL_THRESHOLD = 20.0   # Net long %OI
    MODERATE_BULL_THRESHOLD = 10.0
    STRONG_BEAR_THRESHOLD = -20.0  # Net short %OI
    MODERATE_BEAR_THRESHOLD = -10.0
    
    # Confidence scaling
    MAX_CONFIDENCE = 0.95
    MIN_CONFIDENCE = 0.3
    
    def __init__(self, fetcher: Optional[CotFetcher] = None):
        self.fetcher = fetcher or CotFetcher()
    
    def _calculate_strength(self, net_pct: float, change: float, percentile: Optional[float]) -> str:
        """
        Determine signal strength category.
        
        Categories:
        - extreme: >90th percentile (contrarian warning)
        - strong: Clear directional bias with momentum
        - moderate: Directional but less conviction
        - weak: Marginal signal
        - neutral: No clear bias
        """
        if percentile and (percentile > 90 or percentile < 10):
            return 'extreme'
        
        abs_net = abs(net_pct)
        
        if abs_net > 25:
            return 'strong' if (net_pct > 0 and change > 0) or (net_pct < 0 and change < 0) else 'moderate'
        elif abs_net > 15:
            return 'moderate'
        elif abs_net > 5:
            return 'weak'
        else:
            return 'neutral'
    
    def _calculate_confidence(self, net_pct: float, change: float, oi: float, percentile: Optional[float]) -> float:
        """
        Calculate confidence score (0-1) for the signal.
        
        Factors:
        - Magnitude of net positioning
        - Momentum (change direction aligned with net)
        - Open interest (liquidity confirmation)
        - Percentile (extreme = reduce confidence)
        """
        # Base confidence from net %OI
        base_conf = min(abs(net_pct) / 30, 0.7)  # Max 0.7 from net alone
        
        # Momentum boost (change aligned with net direction)
        momentum_boost = 0
        if (net_pct > 0 and change > 0) or (net_pct < 0 and change < 0):
            momentum_boost = min(abs(change) / oi * 500, 0.2)  # Max 0.2 boost
        elif (net_pct > 0 and change < 0) or (net_pct < 0 and change > 0):
            # Divergence penalty
            momentum_boost = -0.15
        
        # Liquidity confirmation
        liquidity_boost = 0
        if oi > 10000:  # High OI = more reliable
            liquidity_boost = 0.05
        
        # Extreme positioning adjustment (contrarian caution)
        extreme_adjust = 0
        if percentile:
            if percentile > 95 or percentile < 5:
                extreme_adjust = -0.2  # Strong contrarian warning
            elif percentile > 90 or percentile < 10:
                extreme_adjust = -0.1  # Moderate caution
        
        confidence = base_conf + momentum_boost + liquidity_boost + extreme_adjust
        return max(self.MIN_CONFIDENCE, min(self.MAX_CONFIDENCE, confidence))
    
    def _generate_direction(self, net_pct: float, change: float) -> Direction:
        """Generate directional bias from COT data."""
        if net_pct > self.MODERATE_BULL_THRESHOLD and change >= -1000:
            return Direction.LONG
        elif net_pct < self.MODERATE_BEAR_THRESHOLD and change <= 1000:
            return Direction.SHORT
        else:
            return Direction.NEUTRAL
    
    def analyze(self, asset: str, data: Optional[Dict[str, Any]] = None) -> CotAnalysis:
        """
        Analyze COT data for a single asset.
        
        Args:
            asset: 'BTC' or 'ETH'
            data: Pre-fetched COT data (optional)
        
        Returns:
            CotAnalysis with signal and metadata
        """
        if data is None:
            data = self.fetcher.latest_btc() if asset == 'BTC' else self.fetcher.latest_eth()
        
        net_pct = data['noncomm_net_pct_oi']
        net_change = data['change_noncomm_net']
        oi = data['open_interest']
        
        # Get percentile data for context
        percentiles = self.fetcher.calculate_percentiles(asset)
        percentile = percentiles.get('net_pct_rank')
        
        # Calculate metrics
        direction = self._generate_direction(net_pct, net_change)
        strength = self._calculate_strength(net_pct, net_change, percentile)
        confidence = self._calculate_confidence(net_pct, net_change, oi, percentile)
        
        # Generate Signal object
        signal = None
        if direction != Direction.NEUTRAL and confidence >= self.MIN_CONFIDENCE:
            signal = Signal(
                coin=asset,
                direction=direction,
                confidence=confidence,
                source='cot/sentiment',
                timeframe='1W',  # COT is weekly
                metadata={
                    'report_date': data['report_date'],
                    'net_pct_oi': round(net_pct, 2),
                    'net_change': net_change,
                    'open_interest': oi,
                    'strength': strength,
                    'percentile': percentile,
                    'noncomm_long': data['noncomm_long'],
                    'noncomm_short': data['noncomm_short'],
                }
            )
        
        return CotAnalysis(
            asset=asset,
            net_position=data['noncomm_net'],
            net_pct_oi=net_pct,
            net_change=net_change,
            confidence=confidence,
            bias=direction,
            strength=strength,
            percentile=percentile,
            signal=signal
        )
    
    def analyze_btc(self) -> Optional[Signal]:
        """Analyze BTC COT data and return Signal."""
        analysis = self.analyze('BTC')
        return analysis.signal
    
    def analyze_eth(self) -> Optional[Signal]:
        """Analyze ETH COT data and return Signal."""
        analysis = self.analyze('ETH')
        return analysis.signal
    
    def compare_btc_eth(self) -> Dict[str, Any]:
        """
        Compare BTC and ETH setups and determine best opportunity.
        
        Scoring:
        - COT confidence (primary)
        - Positioning momentum
        - Extreme positioning penalty
        
        Returns:
            Dict with comparison metrics and recommendation
        """
        btc_analysis = self.analyze('BTC')
        eth_analysis = self.analyze('ETH')
        
        btc_signal = btc_analysis.signal
        eth_signal = eth_analysis.signal
        
        # Calculate composite scores
        def calc_score(analysis: CotAnalysis) -> float:
            """Calculate composite score for ranking."""
            score = analysis.confidence
            
            # Boost for strong momentum
            if abs(analysis.net_change) > 1000:
                score += 0.05
            
            # Penalty for extreme positioning (contrarian risk)
            if analysis.percentile:
                if analysis.percentile > 90 or analysis.percentile < 10:
                    score -= 0.1
            
            # Penalty for neutral bias
            if analysis.bias == Direction.NEUTRAL:
                score *= 0.5
            
            return max(0, score)
        
        btc_score = calc_score(btc_analysis)
        eth_score = calc_score(eth_analysis)
        
        # Determine best asset
        if btc_score > eth_score:
            best_asset = 'BTC'
            best_score = btc_score
            best_signal = btc_signal
        else:
            best_asset = 'ETH'
            best_score = eth_score
            best_signal = eth_signal
        
        return {
            'btc_analysis': btc_analysis,
            'eth_analysis': eth_analysis,
            'btc_signal': btc_signal,
            'eth_signal': eth_signal,
            'btc_score': round(btc_score, 3),
            'eth_score': round(eth_score, 3),
            'best_asset': best_asset,
            'best_score': round(best_score, 3),
            'recommendation': f"Allocate to {best_asset}" if best_signal else "No clear signal",
            'timestamp': datetime.utcnow().isoformat(),
        }
    
    def get_trend_alignment(self, asset: str, price_trend: str) -> Dict[str, Any]:
        """
        Check if COT positioning aligns with price trend.
        
        Args:
            asset: 'BTC' or 'ETH'
            price_trend: 'bullish', 'bearish', or 'neutral'
        
        Returns:
            Dict with alignment analysis
        """
        analysis = self.analyze(asset)
        
        cot_bias = analysis.bias.value
        aligned = (
            (cot_bias == 'long' and price_trend == 'bullish') or
            (cot_bias == 'short' and price_trend == 'bearish')
        )
        
        divergence = (
            (cot_bias == 'long' and price_trend == 'bearish') or
            (cot_bias == 'short' and price_trend == 'bullish')
        )
        
        return {
            'asset': asset,
            'cot_bias': cot_bias,
            'price_trend': price_trend,
            'aligned': aligned,
            'divergence': divergence,
            'confidence': analysis.confidence,
            'recommendation': (
                'Strong setup' if aligned and analysis.confidence > 0.7
                else 'Caution - divergence' if divergence
                else 'Moderate setup'
            )
        }
    
    def detect_extremes(self, threshold_pct: float = 90.0) -> List[Dict[str, Any]]:
        """
        Detect assets with extreme positioning (potential reversals).
        
        Args:
            threshold_pct: Percentile threshold for extreme detection
        
        Returns:
            List of extreme positioning alerts
        """
        alerts = []
        
        for asset in ['BTC', 'ETH']:
            analysis = self.analyze(asset)
            
            if analysis.percentile and (analysis.percentile > threshold_pct or analysis.percentile < (100 - threshold_pct)):
                alerts.append({
                    'asset': asset,
                    'percentile': analysis.percentile,
                    'net_pct_oi': analysis.net_pct_oi,
                    'bias': analysis.bias.value,
                    'alert_type': 'extreme_long' if analysis.percentile > threshold_pct else 'extreme_short',
                    'suggestion': 'Consider contrarian position or wait for reversal confirmation'
                })
        
        return alerts
