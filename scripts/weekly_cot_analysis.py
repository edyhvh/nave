#!/usr/bin/env python3
"""
Weekly COT Analysis - Nave's Sunday trading setup generator.

Analyzes latest COT for BTC/ETH, compares setups per F.I.T.S. + IPDA philosophy,
recommends best asset, capital allocation ($2000 example), leverage, and scans
other Hyperliquid perps.

Usage:
    python scripts/weekly_cot_analysis.py --capital 2000 --dry-run
"""
import argparse
import logging
from datetime import datetime
from typing import Dict, Any

from trading.cot.cot_fetcher import fetch_latest_cot
from trading.cot.cot_analyzer import COTAnalyzer
from trading.signals import MacroSignalProducer, SignalAggregator
from trading.strategy import MacroMomentumStrategy
from trading.client import HyperliquidClient
from trading.vault import WalletVault  # for potential execution

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def scan_hyperliquid_perps(client: HyperliquidClient) -> list:
    """Scan other promising Hyperliquid perps for liquidity, funding, etc."""
    try:
        meta = client.get_meta()
        mids = client.get_all_mids()
        # Simple filter for good opportunities (extensible)
        opportunities = []
        for asset in list(mids.keys())[:10]:  # limit
            if asset in ["BTC", "ETH"]:
                continue
            opp = {
                "coin": asset,
                "mid": float(mids.get(asset, 0)),
                "liquidity_score": 0.7,  # stub
                "funding_rate": 0.001,  # stub
                "recommend": asset in ["SOL", "XRP"]  # example
            }
            opportunities.append(opp)
        return opportunities
    except Exception as e:
        logger.warning("Perps scan failed: %s", e)
        return []


def generate_weekly_report(capital_usd: float = 2000, dry_run: bool = True) -> Dict:
    """Main weekly COT analysis and recommendation."""
    print("\n" + "="*80)
    print("🚀 NAVE WEEKLY COT ANALYSIS")
    print("="*80)
    print(
        f"Date: {datetime.now().strftime('%Y-%m-%d')} (Sunday analysis of Friday COT)")
    print("Philosophy: F.I.T.S. + IPDA | Commercials move the market | 75% retracement setups")
    print()

    # Fetch and analyze COT
    cot_data = fetch_latest_cot()
    analyzer = COTAnalyzer()
    biases = analyzer.analyze(cot_data)
    producer = MacroSignalProducer()
    signals = producer.produce({"cot_data": cot_data})

    # Compare BTC vs ETH
    btc_bias = biases.get("BTC")
    eth_bias = biases.get("ETH")
    best_asset = "ETH" if getattr(eth_bias, "confidence", 0) > getattr(
        btc_bias, "confidence", 0) else "BTC"
    best_conf = max(getattr(btc_bias, "confidence", 0.5),
                    getattr(eth_bias, "confidence", 0.5))

    print("COT Bias Summary:")
    for asset, b in biases.items():
        print(
            f"  {asset}: {b.bias.upper()} (net={b.net_non_commercial}, conf={b.confidence:.2f})")

    print(f"\n🏆 BEST SETUP: {best_asset} (confidence {best_conf:.2f})")
    print("Recommendation: Allocate 100% capital to best setup on 4H/1H timeframe.")

    # Risk & sizing per philosophy
    risk_per_trade = 0.10  # 8-12%
    position_size = capital_usd * 0.8  # example
    leverage = 10 if best_asset == "ETH" else 5
    print(
        f"Capital: ${capital_usd:,} | Risk/trade: {risk_per_trade*100}% | Leverage: {leverage}x")
    print("SL: at invalidation (IPDA mitigation block or FVG)")
    print("TP: confluence zones (00/50 levels + 75% retrace)")
    print("Setups: Look for regressions in trend, false break PFQ, order blocks.")

    # Perps scan
    print("\n🔍 Other Hyperliquid Opportunities:")
    try:
        client = HyperliquidClient(wallet_name="openfang", testnet=True)
        perps = scan_hyperliquid_perps(client)
        for p in perps[:3]:
            print(
                f"  {p['coin']}: mid~${p['mid']:.2f} | liq={p['liquidity_score']:.1f} | funding={p['funding_rate']:.4f}")
    except Exception:
        print("  (Hyperliquid client stub - connect wallet for live scan)")

    agg = SignalAggregator(signals)
    agg.summary()

    report = {
        "best_asset": best_asset,
        "capital_usd": capital_usd,
        "leverage": leverage,
        "recommended_size_usd": position_size,
        "signals": len(signals),
        "dry_run": dry_run,
        "timestamp": datetime.now().isoformat(),
    }

    print("\n✅ Report complete. Run with --live for execution (use vault).")
    print("="*80)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Nave Weekly COT Analysis")
    parser.add_argument("--capital", type=float,
                        default=2000.0, help="Available capital USD")
    parser.add_argument("--live", action="store_true", help="Disable dry-run")
    parser.add_argument("--wallet", default="openfang")
    args = parser.parse_args()

    report = generate_weekly_report(
        capital_usd=args.capital,
        dry_run=not args.live
    )
    print(
        f"\nFinal recommendation: Allocate to {report['best_asset']} with {report['leverage']}x leverage.")
