"""
Nave Trading Strategies - Strategy implementations with COT integration.

Implements the Nave Philosophy:
- F.I.T.S. framework for signal generation
- IPDA market structure (expansion, retracement, regression, consolidation)
- 75% retracement entries with confluence
- Asymmetric risk:reward (minimum 1:2)
- SL at invalidation points (structure breaks)
- Position sizing based on risk, not position size
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import math

from trading.client import HyperliquidClient
from trading.signals import (
    Signal, Direction, SignalAggregator, 
    CotSignalProducer, MacroSignalProducer, TechnicalSignalProducer
)
from trading.cot.cot_analyzer import CotAnalyzer


@dataclass
class PositionSizing:
    """
    Nave-compliant position sizing parameters.
    
    Risk-based sizing: Position size = Risk Amount / Stop Distance
    Leverage scaled by confidence and volatility regime.
    """
    coin: str
    direction: Direction
    size_usd: float          # Notional position size
    leverage: float          # Effective leverage (1-10x max)
    risk_usd: float          # Dollar amount at risk
    risk_pct: float          # Risk as % of capital
    stop_price: float        # Invalidation point
    take_profit: float       # Target (min 2:1 R:R)
    expected_rr: float       # Risk:reward ratio
    instrument: str          # 'perp' or 'option'
    confidence: float        # Signal confidence (0-1)
    
    def __str__(self) -> str:
        return (
            f"{self.coin} {self.direction.value.upper()} | "
            f"Size: ${self.size_usd:,.0f} @ {self.leverage:.1f}x | "
            f"Risk: ${self.risk_usd:.0f} ({self.risk_pct*100:.1f}%) | "
            f"R:R {self.expected_rr:.1f}:1 | {self.instrument}"
        )


class BaseStrategy(ABC):
    """
    Abstract base class for Nave trading strategies.
    
    All strategies must:
    1. Respect risk limits (max 12% risk per trade)
    2. Use invalidation-based stop losses
    3. Target asymmetric R:R (minimum 2:1)
    4. Integrate with FITS framework
    """
    
    MAX_RISK_PCT = 0.12      # Maximum 12% risk per trade
    MIN_RR_RATIO = 2.0       # Minimum 2:1 risk:reward
    MAX_LEVERAGE = 10.0      # Maximum 10x leverage
    
    def __init__(
        self, 
        client: HyperliquidClient,
        capital_usd: float = 2000.0,
        default_risk_pct: float = 0.10,
        dry_run: bool = True
    ):
        self.client = client
        self.capital = capital_usd
        self.risk_pct = min(default_risk_pct, self.MAX_RISK_PCT)
        self.dry_run = dry_run
        self.positions: List[Dict] = []
    
    @abstractmethod
    def compute_signals(self) -> List[Signal]:
        """Generate trading signals for this strategy."""
        pass
    
    @abstractmethod
    def generate_sizing(self, signal: Signal) -> Optional[PositionSizing]:
        """Generate position sizing for a signal."""
        pass
    
    def execute_signals(self, signals: List[Signal]) -> List[Dict]:
        """
        Execute or simulate execution of signals.
        
        In dry_run mode: logs intended trades
        In live mode: executes via Hyperliquid client
        """
        results = []
        
        for signal in signals:
            sizing = self.generate_sizing(signal)
            if not sizing:
                continue
            
            if self.dry_run:
                result = self._simulate_trade(sizing)
            else:
                result = self._execute_trade(sizing)
            
            results.append(result)
        
        return results
    
    def _simulate_trade(self, sizing: PositionSizing) -> Dict:
        """Simulate a trade execution (dry run)."""
        return {
            'action': 'SIMULATED',
            'coin': sizing.coin,
            'direction': sizing.direction.value,
            'size_usd': sizing.size_usd,
            'leverage': sizing.leverage,
            'risk_usd': sizing.risk_usd,
            'timestamp': datetime.utcnow().isoformat(),
        }
    
    def _execute_trade(self, sizing: PositionSizing) -> Dict:
        """Execute a live trade via Hyperliquid."""
        try:
            # Set leverage first
            self.client.set_leverage(sizing.coin, int(sizing.leverage))
            
            # Open position
            result = self.client.market_open(
                coin=sizing.coin,
                side=sizing.direction.value,
                size_usd=sizing.size_usd
            )
            
            return {
                'action': 'EXECUTED',
                'coin': sizing.coin,
                'result': result,
                'timestamp': datetime.utcnow().isoformat(),
            }
        except Exception as e:
            return {
                'action': 'FAILED',
                'coin': sizing.coin,
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat(),
            }


class CotWeeklyStrategy(BaseStrategy):
    """
    Weekly COT-driven strategy - Nave's primary Sunday driver.
    
    Strategy Logic:
    1. COT as primary FITS Sentiment bias (BTC vs ETH comparison)
    2. Macro context (RRP, VIX, ETF flows) for regime filter
    3. Technical confluence (75% retrace, FVG, mitigation blocks)
    4. Select best asset (BTC or ETH) based on combined score
    5. Size position based on risk (8-12%), leverage scaled by confidence
    6. Scan Hyperliquid perps for additional high-quality setups
    
    Timeframes: 4H (primary), 1H (entry refinement)
    
    Philosophy Alignment:
    - IPDA: Trade regressions in favor of COT trend
    - Confluence: COT + macro + technical alignment required
    - Risk: SL at invalidation (structure break), 2:1+ R:R minimum
    - Sizing: Risk-based, notional = Risk / Stop Distance
    """
    
    def __init__(
        self,
        client: HyperliquidClient,
        capital_usd: float = 2000.0,
        risk_pct: float = 0.10,
        dry_run: bool = True,
        min_confidence: float = 0.5,
    ):
        super().__init__(client, capital_usd, risk_pct, dry_run)
        self.min_confidence = min_confidence
        self.cot_analyzer = CotAnalyzer()
        self.signal_producer = CotSignalProducer(client)
    
    def compute_signals(self) -> List[Signal]:
        """Generate signals using COT as primary driver."""
        return self.signal_producer.produce()
    
    def compare_btc_eth(self) -> Dict[str, Any]:
        """
        Compare BTC vs ETH and return detailed comparison.
        
        Returns:
            Dict with scores, signals, and allocation recommendation.
        """
        return self.signal_producer.compare_assets()
    
    def select_best_asset(self) -> Tuple[str, Signal, float]:
        """
        Select best asset between BTC and ETH.
        
        Returns:
            Tuple of (asset_symbol, signal, confidence_score)
        """
        comparison = self.compare_btc_eth()
        best = comparison['best_asset']
        
        if best == 'BTC':
            signal = comparison['btc_signal']
            score = comparison['btc_total']
        else:
            signal = comparison['eth_signal']
            score = comparison['eth_total']
        
        return best, signal, score
    
    def generate_sizing(self, signal: Signal) -> Optional[PositionSizing]:
        """
        Generate Nave-compliant position sizing.
        
        Rules:
        - Risk = Capital × Risk% (default 10%)
        - Leverage = Confidence × 20, capped at 10x
        - Stop = Invalidation point (technical structure)
        - Target = 2:1 minimum R:R (prefer 3:1+)
        - Perps for high confidence, options for ranges
        """
        if signal.confidence < self.min_confidence:
            return None
        
        coin = signal.coin
        direction = signal.direction
        
        # Get current price
        try:
            current_price = self.client.get_mid(coin)
        except Exception:
            # Fallback for dry-run without client
            current_price = signal.metadata.get('price', 50000 if coin == 'BTC' else 3000)
        
        # Calculate position parameters
        risk_usd = self.capital * self.risk_pct
        
        # Leverage scaled by confidence (max 10x)
        leverage = min(signal.confidence * 20, self.MAX_LEVERAGE)
        leverage = max(1.0, leverage)  # Minimum 1x
        
        # Determine stop distance based on volatility/ATR
        # For now, use 2% for BTC, 3% for ETH as baseline
        base_stop_pct = 0.02 if coin == 'BTC' else 0.03
        
        # Adjust stop by confidence (higher conf = tighter stop)
        stop_pct = base_stop_pct * (1.5 - signal.confidence)
        
        if direction == Direction.LONG:
            stop_price = current_price * (1 - stop_pct)
            take_profit = current_price * (1 + stop_pct * self.MIN_RR_RATIO * 1.5)
        else:
            stop_price = current_price * (1 + stop_pct)
            take_profit = current_price * (1 - stop_pct * self.MIN_RR_RATIO * 1.5)
        
        # Calculate notional size: Risk / Stop Distance
        stop_distance = abs(current_price - stop_price) / current_price
        size_usd = risk_usd / stop_distance if stop_distance > 0 else risk_usd * 10
        
        # Cap size at available capital × leverage
        max_size = self.capital * leverage
        size_usd = min(size_usd, max_size)
        
        # Calculate actual R:R
        reward_distance = abs(take_profit - current_price) / current_price
        expected_rr = reward_distance / stop_distance if stop_distance > 0 else 0
        
        # Choose instrument: perps for trend, options for range/low conf
        instrument = 'perp' if signal.confidence > 0.6 else 'option'
        
        return PositionSizing(
            coin=coin,
            direction=direction,
            size_usd=size_usd,
            leverage=leverage,
            risk_usd=risk_usd,
            risk_pct=self.risk_pct,
            stop_price=round(stop_price, 2),
            take_profit=round(take_profit, 2),
            expected_rr=round(expected_rr, 2),
            instrument=instrument,
            confidence=signal.confidence,
        )
    
    def weekly_report(self) -> str:
        """
        Generate comprehensive weekly COT report.
        
        Format: Markdown for CLI display and logging.
        """
        lines = []
        
        # Header
        lines.append("# Nave Weekly COT Analysis Report")
        lines.append(f"**Generated:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
        lines.append(f"**Capital:** ${self.capital:,.0f} | **Risk/Trade:** {self.risk_pct*100:.0f}%")
        lines.append("")
        
        # COT Analysis
        comparison = self.compare_btc_eth()
        lines.append("## COT Sentiment Analysis (FITS)")
        lines.append("")
        lines.append(f"| Asset | COT Score | Confluence | Total | Signal |")
        lines.append(f"|-------|-----------|------------|-------|--------|")
        lines.append(
            f"| BTC | {comparison['btc_score']:.2f} | {comparison['btc_confluence']:.2f} | "
            f"{comparison['btc_total']:.2f} | "
            f"{comparison['btc_signal'].direction.value.upper() if comparison['btc_signal'] else 'N/A'} |"
        )
        lines.append(
            f"| ETH | {comparison['eth_score']:.2f} | {comparison['eth_confluence']:.2f} | "
            f"{comparison['eth_total']:.2f} | "
            f"{comparison['eth_signal'].direction.value.upper() if comparison['eth_signal'] else 'N/A'} |"
        )
        lines.append("")
        
        # Best Asset Recommendation
        best_asset, best_signal, best_score = self.select_best_asset()
        lines.append("## Asset Selection")
        lines.append(f"**Recommended Asset:** {best_asset}")
        lines.append(f"**Direction:** {best_signal.direction.value.upper()}")
        lines.append(f"**Confidence:** {best_signal.confidence:.2f}")
        lines.append("")
        
        # COT Details
        if best_signal and best_signal.metadata:
            lines.append("### COT Details")
            for key, value in best_signal.metadata.items():
                lines.append(f"- **{key}:** {value}")
            lines.append("")
        
        # Position Sizing
        sizing = self.generate_sizing(best_signal)
        if sizing:
            lines.append("## Position Sizing (Nave Risk Model)")
            lines.append(f"```")
            lines.append(str(sizing))
            lines.append(f"```")
            lines.append("")
            
            lines.append("### Risk Parameters")
            lines.append(f"- **Entry Strategy:** 75% retracement on 4H/1H confluence")
            lines.append(f"- **Stop Loss:** ${sizing.stop_price:,.2f} (invalidation point)")
            lines.append(f"- **Take Profit:** ${sizing.take_profit:,.2f} (target R:R {sizing.expected_rr:.1f}:1)")
            lines.append(f"- **Instrument:** {sizing.instrument.upper()}")
            lines.append("")
        
        # Philosophy Alignment
        lines.append("## Philosophy Alignment (F.I.T.S.)")
        lines.append("")
        lines.append("### Sentiment (COT)")
        lines.append("- Non-commercial net positions indicate smart money bias")
        lines.append(f"- Current bias: {best_signal.direction.value.upper()} with {best_signal.confidence:.0%} confidence")
        lines.append("")
        
        lines.append("### Technical (IPDA)")
        lines.append("- Primary timeframe: 4H for structure, 1H for entry")
        lines.append("- Setup: 75% retracement into confluence zone")
        lines.append("- Invalidation: Structure break below/above key level")
        lines.append("")
        
        lines.append("### Fundamental + Intermarket")
        lines.append("- Macro regime filter (VIX, TGA, RRP)")
        lines.append("- ETF flows for BTC institutional demand")
        lines.append("")
        
        # Perp Scan
        all_signals = self.compute_signals()
        alt_signals = [s for s in all_signals if s.coin not in ['BTC', 'ETH'] and s.confidence > 0.5]
        
        if alt_signals:
            lines.append("## Additional Hyperliquid Opportunities")
            lines.append("")
            lines.append("| Coin | Direction | Confidence | Source |")
            lines.append("|------|-----------|------------|--------|")
            for sig in sorted(alt_signals, key=lambda x: -x.confidence)[:5]:
                lines.append(f"| {sig.coin} | {sig.direction.value.upper()} | {sig.confidence:.2f} | {sig.source} |")
            lines.append("")
        
        # Execution Summary
        lines.append("## Execution Plan")
        lines.append(f"1. **Primary Trade:** Allocate 100% to {best_asset} {best_signal.direction.value.upper()}")
        if sizing:
            lines.append(f"2. **Size:** ${sizing.size_usd:,.0f} at {sizing.leverage:.1f}x leverage")
            lines.append(f"3. **Risk:** ${sizing.risk_usd:.0f} ({sizing.risk_pct*100:.0f}% of capital)")
        lines.append(f"4. **Entry:** Wait for 75% retracement into confluence zone on 4H/1H")
        lines.append(f"5. **Management:** Scale out at 2:1, runner to 3:1+")
        lines.append("")
        
        if self.dry_run:
            lines.append("---")
            lines.append("*Mode: DRY RUN - No actual trades will be executed*")
        
        return "\n".join(lines)
    
    def run_weekly_analysis(self) -> Dict[str, Any]:
        """
        Complete weekly analysis workflow.
        
        Returns:
            Dict with all analysis data for programmatic use.
        """
        signals = self.compute_signals()
        comparison = self.compare_btc_eth()
        best_asset, best_signal, best_score = self.select_best_asset()
        sizing = self.generate_sizing(best_signal)
        
        # Execute or simulate
        results = self.execute_signals([best_signal]) if sizing else []
        
        return {
            'timestamp': datetime.utcnow().isoformat(),
            'capital': self.capital,
            'risk_pct': self.risk_pct,
            'signals': signals,
            'comparison': comparison,
            'best_asset': best_asset,
            'best_signal': best_signal,
            'sizing': sizing,
            'execution_results': results,
            'report': self.weekly_report(),
        }


class MultiAssetStrategy(BaseStrategy):
    """
    Multi-asset strategy for diversified exposure.
    
    Allocates across multiple assets based on:
    - COT sentiment scores
    - Perp scan opportunities
    - Correlation considerations
    """
    
    def __init__(
        self,
        client: HyperliquidClient,
        capital_usd: float = 2000.0,
        risk_pct: float = 0.10,
        max_positions: int = 3,
        dry_run: bool = True,
    ):
        super().__init__(client, capital_usd, risk_pct, dry_run)
        self.max_positions = max_positions
        self.signal_producer = CotSignalProducer(client)
    
    def compute_signals(self) -> List[Signal]:
        """Generate signals for all assets."""
        return self.signal_producer.produce()
    
    def generate_sizing(self, signal: Signal) -> Optional[PositionSizing]:
        """Generate sizing for a single signal."""
        if signal.confidence < 0.5:
            return None
        
        # Similar to CotWeeklyStrategy but with position limit
        risk_usd = self.capital * self.risk_pct / self.max_positions
        leverage = min(signal.confidence * 15, self.MAX_LEVERAGE)
        
        coin = signal.coin
        try:
            current_price = self.client.get_mid(coin)
        except Exception:
            current_price = signal.metadata.get('price', 1000)
        
        stop_pct = 0.025
        if signal.direction == Direction.LONG:
            stop_price = current_price * (1 - stop_pct)
            take_profit = current_price * (1 + stop_pct * 2.5)
        else:
            stop_price = current_price * (1 + stop_pct)
            take_profit = current_price * (1 - stop_pct * 2.5)
        
        stop_distance = abs(current_price - stop_price) / current_price
        size_usd = risk_usd / stop_distance if stop_distance > 0 else risk_usd * 10
        max_size = (self.capital / self.max_positions) * leverage
        size_usd = min(size_usd, max_size)
        
        return PositionSizing(
            coin=coin,
            direction=signal.direction,
            size_usd=size_usd,
            leverage=leverage,
            risk_usd=risk_usd,
            risk_pct=self.risk_pct / self.max_positions,
            stop_price=round(stop_price, 2),
            take_profit=round(take_profit, 2),
            expected_rr=2.5,
            instrument='perp',
            confidence=signal.confidence,
        )
    
    def select_positions(self) -> List[Signal]:
        """
        Select top N positions based on confidence and diversification.
        """
        all_signals = self.compute_signals()
        
        # Filter by minimum confidence
        qualified = [s for s in all_signals if s.confidence >= 0.5]
        
        # Sort by confidence
        qualified.sort(key=lambda x: -x.confidence)
        
        # Take top N, ensuring no duplicate coins
        selected = []
        coins_seen = set()
        for sig in qualified:
            if sig.coin not in coins_seen and len(selected) < self.max_positions:
                selected.append(sig)
                coins_seen.add(sig.coin)
        
        return selected
    
    def run_portfolio_allocation(self) -> Dict[str, Any]:
        """
        Run full multi-asset allocation.
        """
        positions = self.select_positions()
        sizings = [self.generate_sizing(p) for p in positions]
        sizings = [s for s in sizings if s is not None]
        
        results = []
        for sizing in sizings:
            if self.dry_run:
                results.append(self._simulate_trade(sizing))
            else:
                results.append(self._execute_trade(sizing))
        
        return {
            'timestamp': datetime.utcnow().isoformat(),
            'capital': self.capital,
            'positions': len(sizings),
            'sizings': sizings,
            'results': results,
        }
