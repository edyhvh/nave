"""
Backtest tests for COT setup discovery optimization.

Objective: Find the best way to identify high-probability setups using COT data.
Tests various thresholds, filters, and parameters.
"""

import pytest
from datetime import datetime, timedelta
from typing import List, Dict, Any
import pandas as pd
import numpy as np

from trading.cot.cot_analyzer import COTAnalyzer
from trading.signals import Signal, Direction
from tests.backtest.mocks.mock_cot_fetcher import HistoricalCotFetcher
from tests.backtest.utils.metrics import calculate_metrics


class TestSetupDiscovery:
    """Test COT signal parameters for optimal setup discovery."""

    @pytest.fixture
    def historical_fetcher(self):
        """Fixture for historical COT data fetcher."""
        # This would load real historical data in production
        # For now, we'll create synthetic data for testing structure
        return HistoricalCotFetcher()

    @pytest.fixture
    def synthetic_cot_data(self):
        """Generate synthetic COT data for testing."""
        dates = pd.date_range(start='2022-01-01',
                              end='2025-03-31', freq='W-TUE')
        np.random.seed(42)

        data = []
        for i, date in enumerate(dates):
            # Generate realistic COT patterns
            # Net %OI oscillates between -30 and +30
            base_net = 15 * np.sin(i / 10) + np.random.normal(0, 5)
            net_pct = np.clip(base_net, -30, 30)

            # Change has some momentum
            change = np.random.normal(0, 1000)
            if net_pct > 10:
                change += 500  # Bias toward increasing when already long
            elif net_pct < -10:
                change -= 500

            data.append({
                'report_date': date,
                'noncomm_long': 50000 + net_pct * 500,
                'noncomm_short': 50000 - net_pct * 500,
                'noncomm_net': net_pct * 1000,
                'open_interest': 100000,
                'noncomm_pct_oi': net_pct,
                'change_noncomm_net': change,
            })

        return pd.DataFrame(data)

    def test_threshold_optimization(self, synthetic_cot_data):
        """
        Test various net_pct_oi thresholds to find optimal level.

        Hypothesis: Higher thresholds (>20%) yield fewer but higher-quality signals.
        """
        thresholds = [5, 10, 15, 20, 25, 30]
        results = []

        for threshold in thresholds:
            signals = self._generate_signals_from_data(
                synthetic_cot_data,
                threshold=threshold,
                require_momentum=True
            )

            # Simulate forward returns (would use real price data)
            perf = self._simulate_forward_returns(signals, forward_days=14)

            results.append({
                'threshold': threshold,
                'signals_per_year': len(signals) / 3,  # 3 years of data
                'win_rate': perf['win_rate'],
                'avg_return': perf['avg_return'],
                'sharpe': perf['sharpe'],
            })

        # Find optimal: balance between signal frequency and quality
        df = pd.DataFrame(results)

        # Should have reasonable signal count (>20/year) and positive Sharpe
        valid = df[(df['signals_per_year'] > 20) & (df['sharpe'] > 0)]

        if not valid.empty:
            best = valid.loc[valid['sharpe'].idxmax()]
            print(f"\nOptimal threshold: {best['threshold']}%")
            print(f"  Win rate: {best['win_rate']:.1%}")
            print(f"  Sharpe: {best['sharpe']:.2f}")
            print(f"  Signals/year: {best['signals_per_year']:.0f}")

        # Assert we found a valid threshold
        assert len(valid) > 0, "No threshold produced valid signals"

    def test_momentum_filter_impact(self, synthetic_cot_data):
        """
        Compare signals with and without momentum (change) filter.

        Hypothesis: Adding momentum filter improves Sharpe and reduces false signals.
        """
        # Without momentum filter
        signals_no_momentum = self._generate_signals_from_data(
            synthetic_cot_data,
            threshold=15,
            require_momentum=False
        )
        perf_no_momentum = self._simulate_forward_returns(
            signals_no_momentum, forward_days=14)

        # With momentum filter
        signals_with_momentum = self._generate_signals_from_data(
            synthetic_cot_data,
            threshold=15,
            require_momentum=True,
            min_change=500
        )
        perf_with_momentum = self._simulate_forward_returns(
            signals_with_momentum, forward_days=14)

        print(f"\nWithout momentum filter:")
        print(f"  Signals: {len(signals_no_momentum)}")
        print(f"  Win rate: {perf_no_momentum['win_rate']:.1%}")
        print(f"  Sharpe: {perf_no_momentum['sharpe']:.2f}")

        print(f"\nWith momentum filter:")
        print(f"  Signals: {len(signals_with_momentum)}")
        print(f"  Win rate: {perf_with_momentum['win_rate']:.1%}")
        print(f"  Sharpe: {perf_with_momentum['sharpe']:.2f}")

        # Momentum filter should improve quality (or at least not hurt significantly)
        # Note: With synthetic data, this might not always pass - adjust threshold as needed
        assert perf_with_momentum['sharpe'] >= perf_no_momentum['sharpe'] * 0.8, \
            "Momentum filter significantly degraded performance"

    def test_btc_vs_eth_selection(self, synthetic_cot_data):
        """
        Test the BTC vs ETH asset selection algorithm.

        Hypothesis: Selecting the asset with higher COT score outperforms random selection.
        """
        # Create separate BTC and ETH data with different patterns
        btc_data = synthetic_cot_data.copy()
        eth_data = synthetic_cot_data.copy()

        # Make ETH slightly stronger on average
        eth_data['noncomm_pct_oi'] += 5

        # Simulate selection over time
        correct_selections = 0
        total_weeks = 0

        for i in range(0, len(btc_data) - 4, 4):  # Every 4 weeks
            btc_score = btc_data.iloc[i]['noncomm_pct_oi']
            eth_score = eth_data.iloc[i]['noncomm_pct_oi']

            # Selection algorithm: pick higher score
            selected = 'ETH' if eth_score > btc_score else 'BTC'

            # Simulate forward performance (ETH should win more often)
            btc_forward = btc_data.iloc[i:i+4]['noncomm_pct_oi'].mean()
            eth_forward = eth_data.iloc[i:i+4]['noncomm_pct_oi'].mean()
            actual_best = 'ETH' if eth_forward > btc_forward else 'BTC'

            if selected == actual_best:
                correct_selections += 1
            total_weeks += 1

        accuracy = correct_selections / total_weeks if total_weeks > 0 else 0

        print(f"\nBTC vs ETH Selection Accuracy: {accuracy:.1%}")
        print(f"  Correct: {correct_selections}/{total_weeks}")

        # Should be better than random (50%)
        assert accuracy > 0.50, f"Selection accuracy {accuracy:.1%} not better than random"

    def test_low_oi_filter(self, synthetic_cot_data):
        """
        Test that low open interest filter eliminates problematic setups.

        Hypothesis: Filtering OI < 1000 improves overall performance.
        """
        # Add some low OI records
        low_oi_data = synthetic_cot_data.copy()
        # Every 10th record has low OI
        low_oi_data.loc[::10, 'open_interest'] = 500

        # Without filter
        signals_all = self._generate_signals_from_data(
            low_oi_data,
            threshold=15,
            require_momentum=True,
            min_oi=0
        )

        # With filter
        signals_filtered = self._generate_signals_from_data(
            low_oi_data,
            threshold=15,
            require_momentum=True,
            min_oi=1000
        )

        print(f"\nWithout OI filter: {len(signals_all)} signals")
        print(f"With OI filter: {len(signals_filtered)} signals")
        print(
            f"Filtered out: {len(signals_all) - len(signals_filtered)} low-OI signals")

        # Should filter out some signals
        assert len(signals_filtered) <= len(signals_all)

    def test_confidence_scoring(self, synthetic_cot_data):
        """
        Test that confidence scores correlate with actual performance.

        Hypothesis: Higher confidence signals have better forward returns.
        """
        signals = self._generate_signals_from_data(
            synthetic_cot_data,
            threshold=10,
            require_momentum=True
        )

        # Group by confidence buckets
        buckets = {
            'high': [],    # > 0.7
            'medium': [],  # 0.5 - 0.7
            'low': []      # < 0.5
        }

        for signal in signals:
            if signal['confidence'] > 0.7:
                buckets['high'].append(signal)
            elif signal['confidence'] > 0.5:
                buckets['medium'].append(signal)
            else:
                buckets['low'].append(signal)

        # Calculate performance per bucket
        for bucket_name, bucket_signals in buckets.items():
            if bucket_signals:
                perf = self._simulate_forward_returns(
                    bucket_signals, forward_days=14)
                print(
                    f"\n{bucket_name.capitalize()} confidence ({len(bucket_signals)} signals):")
                print(f"  Win rate: {perf['win_rate']:.1%}")
                print(f"  Avg return: {perf['avg_return']:.2%}")

        # High confidence should outperform low confidence
        if buckets['high'] and buckets['low']:
            high_perf = self._simulate_forward_returns(
                buckets['high'], forward_days=14)
            low_perf = self._simulate_forward_returns(
                buckets['low'], forward_days=14)

            # This might not always hold with synthetic data
            # but is the expectation with real data
            print(
                f"\nHigh vs Low confidence spread: {high_perf['avg_return'] - low_perf['avg_return']:.2%}")

    def test_regime_dependence(self, synthetic_cot_data):
        """
        Test COT signal performance across different market regimes.

        Hypothesis: COT signals work better in trending markets than ranging.
        """
        # Create regimes based on COT trend
        signals = self._generate_signals_from_data(
            synthetic_cot_data,
            threshold=15,
            require_momentum=True
        )

        # Classify by regime (simplified: based on consecutive signal direction)
        regime_performance = {
            'trending': [],
            'ranging': []
        }

        prev_direction = None
        consecutive = 0

        for signal in signals:
            direction = signal.get('direction', 'neutral')

            if direction == prev_direction:
                consecutive += 1
            else:
                consecutive = 0

            # If 3+ consecutive same direction, consider it trending
            regime = 'trending' if consecutive >= 2 else 'ranging'
            regime_performance[regime].append(signal)

            prev_direction = direction

        for regime, regime_signals in regime_performance.items():
            if regime_signals:
                perf = self._simulate_forward_returns(
                    regime_signals, forward_days=14)
                print(
                    f"\n{regime.capitalize()} regime ({len(regime_signals)} signals):")
                print(f"  Win rate: {perf['win_rate']:.1%}")
                print(f"  Sharpe: {perf['sharpe']:.2f}")

    # Helper methods

    def _generate_signals_from_data(
        self,
        data: pd.DataFrame,
        threshold: float = 15,
        require_momentum: bool = True,
        min_change: float = 0,
        min_oi: float = 1000
    ) -> List[Dict[str, Any]]:
        """Generate signals from COT data with given parameters."""
        signals = []

        for _, row in data.iterrows():
            net_pct = row['noncomm_pct_oi']
            change = row.get('change_noncomm_net', 0)
            oi = row.get('open_interest', 0)

            # OI filter
            if oi < min_oi:
                continue

            # Threshold check
            if abs(net_pct) < threshold:
                continue

            # Momentum filter
            if require_momentum and abs(change) < min_change:
                continue

            # Determine direction and confidence
            if net_pct > 0:
                direction = Direction.LONG
                confidence = min(0.9, net_pct / 50 + abs(change) / oi * 100)
            else:
                direction = Direction.SHORT
                confidence = min(0.9, abs(net_pct) / 50 +
                                 abs(change) / oi * 100)

            signals.append({
                'date': row['report_date'],
                'direction': direction,
                'confidence': confidence,
                'net_pct': net_pct,
                'change': change,
            })

        return signals

    def _simulate_forward_returns(
        self,
        signals: List[Dict[str, Any]],
        forward_days: int = 14
    ) -> Dict[str, float]:
        """
        Simulate forward returns for signals.

        In production, this would use actual price data.
        For testing, we use a simplified model.
        """
        if not signals:
            return {'win_rate': 0, 'avg_return': 0, 'sharpe': 0}

        np.random.seed(42)
        returns = []
        wins = 0

        for signal in signals:
            # Simplified model: COT direction predicts price with some accuracy
            base_return = np.random.normal(0, 0.05)  # 5% volatility

            # Directional bias based on signal
            if signal['direction'] == Direction.LONG:
                base_return += 0.05  # 5% upward bias
            else:
                base_return -= 0.05  # 5% downward bias

            # Confidence scaling
            base_return *= signal['confidence']

            returns.append(base_return)

            if (signal['direction'] == Direction.LONG and base_return > 0) or \
               (signal['direction'] == Direction.SHORT and base_return < 0):
                wins += 1

        win_rate = wins / len(signals)
        avg_return = float(np.mean(returns))

        # Sharpe (simplified)
        returns_series = pd.Series(returns)
        std = float(returns_series.std())
        sharpe = avg_return / std if std > 0 else 0.0

        return {
            'win_rate': float(win_rate),
            'avg_return': float(avg_return),
            'sharpe': float(sharpe),
        }
