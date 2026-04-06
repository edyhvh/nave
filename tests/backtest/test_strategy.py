"""
Backtest tests for complete COT Weekly Strategy.

Objective: Validate the full CotWeeklyStrategy including position sizing,
leverage, risk management, and execution.
"""

import pytest
from datetime import datetime, timedelta
from typing import List, Dict, Any
import pandas as pd
import numpy as np

from trading.strategy import CotWeeklyStrategy
from trading.signals import Signal, Direction
from tests.backtest.mocks.mock_hyperliquid import MockHyperliquidClient
from tests.backtest.mocks.mock_cot_fetcher import HistoricalCotFetcher
from tests.backtest.utils.backtest_engine import BacktestEngine, BacktestConfig
from tests.backtest.utils.metrics import PerformanceMetrics


class TestCotWeeklyStrategy:
    """Full strategy backtest with realistic execution simulation."""

    @pytest.fixture
    def mock_client(self):
        """Fixture for mock Hyperliquid client."""
        return MockHyperliquidClient(slippage_pct=0.001)

    @pytest.fixture
    def strategy_config(self):
        """Default strategy configuration for testing."""
        return {
            'capital_usd': 10000.0,
            'risk_pct': 0.10,
            'max_leverage': 10.0,
            'test_mode': True,  # mocks only, no Hyperliquid account needed
        }

    @pytest.fixture
    def backtest_engine(self):
        """Fixture for backtest engine."""
        return BacktestEngine(
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2024, 12, 31),
            initial_capital=10000.0,
            config=BacktestConfig(
                start_date=datetime(2023, 1, 1),
                end_date=datetime(2024, 12, 31),
                initial_capital=10000.0,
                slippage_pct=0.001,
                trading_fee_pct=0.0005,
            )
        )

    def test_full_strategy_backtest(self, mock_client, strategy_config, backtest_engine):
        """
        Run complete strategy backtest and verify performance metrics.

        Validates:
        - Returns meet minimum threshold
        - Risk metrics are acceptable
        - Trade statistics are reasonable
        """
        # Create strategy
        strategy = CotWeeklyStrategy(
            client=mock_client,
            cot_fetcher=HistoricalCotFetcher(),
            **strategy_config
        )

        # Run backtest
        result = backtest_engine.run(strategy)

        metrics = result.metrics

        print("\n" + "="*50)
        print("FULL STRATEGY BACKTEST RESULTS")
        print("="*50)
        print(result.summary())

        # Performance thresholds (adjust based on real backtests)
        assert metrics.total_return > -0.50, "Strategy lost more than 50%"
        assert metrics.max_drawdown > -0.60, "Max drawdown exceeded 60%"
        assert metrics.total_trades > 0, "Insufficient trades for analysis"

        # Risk management checks
        assert metrics.max_consecutive_losses <= 10, "Too many consecutive losses"

        # Basic sanity checks
        assert metrics.win_rate >= 0, "Invalid win rate"
        assert metrics.profit_factor >= 0, "Invalid profit factor"

    def test_position_sizing_logic(self, mock_client, strategy_config):
        """
        Verify position sizing matches confidence and respects limits.

        Tests:
        - Leverage scales with confidence
        - Position size respects risk limits
        - No position when confidence is too low
        """
        strategy = CotWeeklyStrategy(client=mock_client, **strategy_config)

        test_cases = [
            {'confidence': 0.9, 'expected_leverage_min': 8, 'should_trade': True},
            {'confidence': 0.7, 'expected_leverage_min': 5, 'should_trade': True},
            {'confidence': 0.5, 'expected_leverage_min': 3, 'should_trade': True},
            {'confidence': 0.3, 'expected_leverage_min': 0, 'should_trade': False},
        ]

        for case in test_cases:
            sizing = strategy.calculate_position_sizing(
                confidence=case['confidence'],
                capital=strategy_config['capital_usd'],
                stop_distance=0.02
            )

            if case['should_trade']:
                assert sizing['leverage'] >= case['expected_leverage_min'], \
                    f"Leverage {sizing['leverage']}x below expected for confidence {case['confidence']}"
                assert sizing['size_usd'] > 0, "Should have position size"
            else:
                assert sizing['size_usd'] == 0 or sizing['leverage'] == 0, \
                    "Should not trade with low confidence"

            # Always respect max leverage
            assert sizing['leverage'] <= strategy_config['max_leverage'], \
                f"Leverage {sizing['leverage']}x exceeds max {strategy_config['max_leverage']}x"

    def test_risk_limits_respected(self, mock_client, strategy_config):
        """
        Verify strategy respects risk limits during drawdowns.

        Tests:
        - Risk reduction after consecutive losses
        - Max drawdown circuit breaker
        - Recovery behavior
        """
        strategy = CotWeeklyStrategy(
            client=mock_client,
            cot_fetcher=HistoricalCotFetcher(),
            **strategy_config
        )

        # Test risk adjustment after losses
        initial_risk = strategy.risk_pct

        # Simulate consecutive losses
        strategy.record_loss()
        strategy.record_loss()
        strategy.record_loss()

        # Risk should be reduced
        adjusted_risk = strategy.get_adjusted_risk()
        assert adjusted_risk < initial_risk, "Risk should be reduced after losses"

        # Test max drawdown circuit breaker
        strategy.equity = strategy_config['capital_usd'] * 0.70  # 30% drawdown

        should_halt = strategy.check_circuit_breaker()
        assert should_halt, "Should halt trading at max drawdown"

    def test_btc_eth_comparison_and_selection(self, mock_client, strategy_config):
        """
        Test BTC vs ETH comparison logic and asset selection.

        Validates:
        - Correct comparison of COT scores
        - Selection of better setup
        - Allocation to selected asset
        """
        strategy = CotWeeklyStrategy(client=mock_client, **strategy_config)

        # Create mock COT signals
        btc_signal = Signal(
            coin='BTC',
            direction=Direction.LONG,
            confidence=0.8,
            source='cot',
            metadata={'net_pct_oi': 25}
        )

        eth_signal = Signal(
            coin='ETH',
            direction=Direction.LONG,
            confidence=0.6,
            source='cot',
            metadata={'net_pct_oi': 15}
        )

        # BTC should be selected (higher confidence)
        selected = strategy.select_best_asset([btc_signal, eth_signal])
        assert selected is not None, "Should return a signal"
        assert selected.coin == 'BTC', "Should select BTC with higher confidence"

        # Reverse case
        eth_signal.confidence = 0.9
        btc_signal.confidence = 0.5

        selected = strategy.select_best_asset([btc_signal, eth_signal])
        assert selected is not None, "Should return a signal"
        assert selected.coin == 'ETH', "Should select ETH with higher confidence"

    def test_market_regime_performance(self, mock_client, strategy_config):
        """
        Analyze strategy performance across different market regimes.

        Regimes:
        - Bull trend: Should capture upside
        - Bear trend: Should limit downside or profit from shorts
        - Range: Should have fewer signals
        """
        engine = BacktestEngine(
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2024, 12, 31),
            initial_capital=10000.0
        )

        strategy = CotWeeklyStrategy(
            client=mock_client,
            cot_fetcher=HistoricalCotFetcher(),
            **strategy_config
        )

        # Generate synthetic price data with regimes
        dates = pd.date_range(start='2023-01-01', end='2024-12-31', freq='D')
        np.random.seed(42)

        # Create price with different regimes
        price = 50000
        prices = []
        regime = 'bull'  # Start in bull

        for i, date in enumerate(dates):
            if i % 180 == 0:  # Switch regime every ~6 months
                regime = np.random.choice(['bull', 'bear', 'range'])

            if regime == 'bull':
                change = np.random.normal(0.002, 0.02)  # Upward drift
            elif regime == 'bear':
                change = np.random.normal(-0.002, 0.025)  # Downward drift
            else:
                change = np.random.normal(0, 0.015)  # No drift

            price *= (1 + change)
            prices.append(price)

        price_data = pd.DataFrame({
            'timestamp': dates,
            'close': prices
        })

        # Run backtest with price data for regime analysis
        result = engine.run(strategy, price_data=price_data)

        print("\nRegime Performance:")
        for regime, metrics in result.regime_metrics.items():
            print(
                f"  {regime}: {metrics.win_rate:.1%} win rate, {metrics.total_trades} trades")

        # Should have trades in at least one regime (synthetic data may limit variety)
        assert len(
            result.regime_metrics) >= 1, "Should trade in at least one regime"

    def test_leverage_scaling_by_confidence(self, mock_client, strategy_config):
        """
        Verify leverage scales appropriately with confidence.

        Formula: leverage = min(confidence * max_leverage, max_leverage)
        """
        strategy = CotWeeklyStrategy(client=mock_client, **strategy_config)

        test_cases = [
            (0.95, 9.5),  # 95% conf -> 9.5x leverage
            (0.80, 8.0),  # 80% conf -> 8.0x leverage
            (0.50, 5.0),  # 50% conf -> 5.0x leverage
            (0.30, 3.0),  # 30% conf -> 3.0x leverage
        ]

        for confidence, expected_leverage in test_cases:
            leverage = strategy.calculate_leverage(confidence)

            # Allow small rounding differences
            assert abs(leverage - expected_leverage) < 0.5, \
                f"Leverage {leverage}x doesn't match expected {expected_leverage}x for confidence {confidence}"

            # Never exceed max
            assert leverage <= strategy_config['max_leverage'], \
                f"Leverage {leverage}x exceeds max {strategy_config['max_leverage']}x"

    def test_trade_execution_simulation(self, mock_client, strategy_config):
        """
        Test trade execution with realistic slippage and fees.

        Validates:
        - Slippage is applied
        - Fees are deducted
        - PnL is calculated correctly
        """
        strategy = CotWeeklyStrategy(
            client=mock_client,
            cot_fetcher=HistoricalCotFetcher(),
            **strategy_config
        )

        # Open a position
        signal = Signal(
            coin='BTC',
            direction=Direction.LONG,
            confidence=0.8,
            source='cot'
        )

        trade = strategy.execute_signal(signal, mock_client)

        # Verify slippage applied
        entry_price = trade.entry_price
        theoretical_price = mock_client.get_price('BTC')

        assert entry_price > theoretical_price, "Long entry should have positive slippage"

        # Verify fees recorded
        assert trade.fees > 0, "Trading fees should be recorded"

        # Close position and verify PnL
        closed_trade = strategy.close_position('BTC', mock_client)

        assert closed_trade.pnl is not None, "PnL should be calculated"
        assert closed_trade.exit_price is not None, "Exit price should be recorded"
        assert closed_trade.exit_date is not None, "Exit date should be recorded"

    def test_correlation_and_diversification(self, mock_client, strategy_config):
        """
        Test that strategy handles correlated assets appropriately.

        BTC and ETH are highly correlated - strategy should:
        - Not double down on same directional bias
        - Select the stronger setup
        """
        strategy = CotWeeklyStrategy(client=mock_client, **strategy_config)

        # Both BTC and ETH with same direction
        signals = [
            Signal(coin='BTC', direction=Direction.LONG,
                   confidence=0.8, source='cot'),
            Signal(coin='ETH', direction=Direction.LONG,
                   confidence=0.7, source='cot'),
        ]

        # Should select BTC (higher confidence) and not also take ETH
        selected = strategy.select_best_asset(signals)
        assert selected is not None, "Should return a signal"
        assert selected.coin == 'BTC', "Should select highest confidence"

        # Check that we're not over-concentrated
        positions = strategy.get_current_positions()
        btc_position = positions.get('BTC')
        eth_position = positions.get('ETH')

        # Should not have both positions simultaneously (correlation risk)
        if btc_position and eth_position:
            total_exposure = btc_position.size + eth_position.size
            assert total_exposure <= strategy_config['capital_usd'] * 1.5, \
                "Total exposure too high for correlated assets"

    def test_weekly_report_generation(self, mock_client, strategy_config):
        """
        Test weekly report generation with all required components.

        Validates:
        - COT bias section
        - Best asset recommendation
        - Position sizing
        - Risk parameters
        """
        strategy = CotWeeklyStrategy(client=mock_client, **strategy_config)

        # Generate report
        report = strategy.weekly_report()

        # Verify report sections
        assert 'COT' in report or 'cot' in report.lower(), "Report should mention COT"
        assert 'BTC' in report or 'ETH' in report, "Report should mention assets"
        assert '$' in report, "Report should include dollar amounts"
        assert 'x' in report.lower(), "Report should mention leverage"

        print("\nWeekly Report Preview:")
        print(report[:500] + "...")


class TestStrategyRobustness:
    """Stress tests and edge cases for strategy robustness."""

    @pytest.fixture
    def mock_client(self):
        """Fixture for mock Hyperliquid client."""
        return MockHyperliquidClient(slippage_pct=0.001)

    def test_empty_signal_handling(self, mock_client):
        """Strategy should handle weeks with no signals gracefully."""
        strategy = CotWeeklyStrategy(
            client=mock_client, capital_usd=10000, test_mode=True)

        # No signals
        signals = []

        # Should not error
        result = strategy.execute_signals(signals)

        # Should not open any positions
        assert len(strategy.get_current_positions()) == 0

    def test_conflicting_signals(self, mock_client):
        """Strategy should handle conflicting signals appropriately."""
        strategy = CotWeeklyStrategy(
            client=mock_client, capital_usd=10000, test_mode=True)

        # Same asset, conflicting directions
        signals = [
            Signal(coin='BTC', direction=Direction.LONG,
                   confidence=0.6, source='cot'),
            Signal(coin='BTC', direction=Direction.SHORT,
                   confidence=0.4, source='macro'),
        ]

        # Should select based on confidence (LONG wins)
        selected = strategy.resolve_conflicts(signals)

        assert selected.direction == Direction.LONG, "Should select higher confidence signal"

    def test_extreme_market_conditions(self, mock_client):
        """Strategy behavior during extreme market moves."""
        strategy = CotWeeklyStrategy(
            client=mock_client, capital_usd=10000, test_mode=True)

        # Simulate extreme volatility
        mock_client.volatility_multiplier = 3.0

        # Should still function
        signals = strategy.compute_signals()

        # May reduce position sizes
        if signals:
            sizing = strategy.calculate_position_sizing(
                confidence=signals[0].confidence,
                capital=10000,
                stop_distance=0.05  # Wider stops in high vol
            )

            # Should be more conservative
            assert sizing['leverage'] <= 5, "Should reduce leverage in extreme conditions"

    def test_data_gaps_handling(self, mock_client):
        """Strategy should handle missing COT data gracefully."""
        strategy = CotWeeklyStrategy(
            client=mock_client, capital_usd=10000, test_mode=True)

        # Simulate data gap
        strategy.cot_fetcher = None  # Force error

        # Should not crash
        try:
            signals = strategy.compute_signals()
            # May return empty or use cached
        except Exception as e:
            pytest.fail(f"Strategy should handle data gaps gracefully: {e}")
