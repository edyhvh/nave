#!/usr/bin/env python3
"""
Simple On-Chain Metrics Verification Script

Tests basic API connectivity for BTC, ETH, and SOL on-chain metrics.
Uses only standard library modules.
"""

import json
import urllib.request
import urllib.parse
from datetime import datetime
from typing import Dict, Optional, Any

class SimpleOnChainVerifier:
    """Simple verifier for on-chain metrics APIs."""

    def __init__(self):
        self.timeout = 30.0

    def test_blockchain_info_api(self, chart_name: str) -> Optional[float]:
        """Test Blockchain.com API for a specific chart."""
        try:
            url = f"https://api.blockchain.info/charts/{chart_name}?timespan=1days&format=json"
            print(f"📡 Testing: {url}")

            with urllib.request.urlopen(url, timeout=self.timeout) as response:
                if response.getcode() == 200:
                    data = json.loads(response.read().decode())
                    if 'values' in data and data['values']:
                        latest = data['values'][-1]
                        value = float(latest.get('y', 0))
                        print(f"✅ Got value: {value}")
                        return value
                    else:
                        print("⚠️  No values in response")
                else:
                    print(f"❌ HTTP {response.getcode()}")
        except Exception as e:
            print(f"❌ Error: {e}")

        return None

    def test_coingecko_api(self, coin_id: str) -> Optional[Dict[str, Any]]:
        """Test CoinGecko API for basic coin data."""
        try:
            url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd&include_market_cap=true"
            print(f"📡 Testing: {url}")

            with urllib.request.urlopen(url, timeout=self.timeout) as response:
                if response.getcode() == 200:
                    data = json.loads(response.read().decode())
                    if coin_id in data:
                        coin_data = data[coin_id]
                        print(f"✅ Got data: ${coin_data.get('usd', 'N/A')} market_cap: ${coin_data.get('usd_market_cap', 'N/A')}")
                        return coin_data
                    else:
                        print("⚠️  Coin not in response")
                else:
                    print(f"❌ HTTP {response.getcode()}")
        except Exception as e:
            print(f"❌ Error: {e}")

        return None

    def test_coingecko_market_chart(self, coin_id: str) -> Optional[Dict[str, Any]]:
        """Test CoinGecko market chart API."""
        try:
            url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart?vs_currency=usd&days=1&interval=daily"
            print(f"📡 Testing: {url}")

            with urllib.request.urlopen(url, timeout=self.timeout) as response:
                if response.getcode() == 200:
                    data = json.loads(response.read().decode())
                    if 'prices' in data and data['prices']:
                        latest_price = data['prices'][-1][1]
                        print(f"✅ Got latest price: ${latest_price}")
                        return data
                    else:
                        print("⚠️  No price data")
                else:
                    print(f"❌ HTTP {response.getcode()}")
        except Exception as e:
            print(f"❌ Error: {e}")

        return None

    def calculate_simple_health_score(self, hash_rate: Optional[float],
                                    market_cap: Optional[float],
                                    price_volatility: Optional[float]) -> float:
        """Calculate a simple health score (0-100)."""
        score = 0.0

        if hash_rate and hash_rate > 100e6:  # > 100 EH/s is good
            score += 40

        if market_cap and market_cap > 10e9:  # > $10B market cap is good
            score += 30

        if price_volatility is not None and price_volatility < 0.1:  # Low volatility is stable
            score += 30

        return min(score, 100.0)

def main():
    """Main test function."""
    print("🚀 Simple On-Chain Metrics Verification")
    print("=" * 50)

    verifier = SimpleOnChainVerifier()

    assets = [
        ('bitcoin', 'bitcoin'),
        ('ethereum', 'ethereum'),
        ('solana', 'solana')
    ]

    for asset_name, coin_id in assets:
        print(f"\n{'='*20} Testing {asset_name.upper()} {'='*20}")

        # Test Blockchain.com APIs (for BTC/ETH)
        if asset_name in ['bitcoin', 'ethereum']:
            print("\n🔗 Blockchain.com APIs:")

            # Hash rate (only for BTC/ETH, not SOL which uses PoS)
            if asset_name != 'solana':
                hash_rate = verifier.test_blockchain_info_api('hash-rate')
            else:
                hash_rate = None
                print("ℹ️  SOL uses PoS - no hash rate")

            # Transaction volume
            tx_volume = verifier.test_blockchain_info_api('estimated-transaction-volume-usd')
        else:
            hash_rate = None
            tx_volume = None

        # Test CoinGecko APIs (for all assets)
        print("\n🪙 CoinGecko APIs:")
        coin_data = verifier.test_coingecko_api(coin_id)
        market_cap = coin_data.get('usd_market_cap') if coin_data else None

        chart_data = verifier.test_coingecko_market_chart(coin_id)

        # Calculate simple health score
        # Use price volatility as proxy
        price_volatility = None
        if chart_data and 'prices' in chart_data and len(chart_data['prices']) > 1:
            prices = [p[1] for p in chart_data['prices']]
            if len(prices) > 1:
                mean_price = sum(prices) / len(prices)
                variance = sum((p - mean_price) ** 2 for p in prices) / len(prices)
                price_volatility = (variance ** 0.5) / mean_price if mean_price > 0 else None

        health_score = verifier.calculate_simple_health_score(hash_rate, market_cap, price_volatility)

        print(f"\n🏥 Simple Health Score: {health_score}/100")

        if health_score >= 70:
            print("💡 Interpretation: Strong network health")
        elif health_score >= 50:
            print("💡 Interpretation: Moderate network health")
        elif health_score >= 30:
            print("💡 Interpretation: Weak network health")
        else:
            print("💡 Interpretation: Critical network health")

    print(f"\n✅ Verification complete at {datetime.now().isoformat()}")

if __name__ == "__main__":
    main()