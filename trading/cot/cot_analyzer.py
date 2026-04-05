"""COT Analyzer - Parses COT data into trading bias per Nave philosophy.

Focuses on non-commercial (speculators) vs commercials positioning.
Commercials (institutions/makers) move the market per technical.yaml.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any, List
import pandas as pd

from trading.signals import Signal, Direction


@dataclass
class COTBias:
    """Structured COT bias for an asset."""
    asset: str
    net_non_commercial: int
    pct_oi_non_com: float
    weekly_change: int
    bias: str  # bullish/bearish/neutral
    confidence: float
    metadata: Dict[str, Any]


class COTAnalyzer:
    """Analyzes COT reports for BTC and ETH, generates Signals."""

    def analyze(self, cot_data: Dict[str, Any]) -> Dict[str, COTBias]:
        """Analyze COT for all assets and return biases."""
        results = {}
        for asset, raw in cot_data.items():
            bias = self._analyze_single(asset, raw)
            results[asset] = bias
        return results

    def _analyze_single(self, asset: str, raw: Dict) -> COTBias:
        """Parse single asset COT into bias (aligned to F.I.T.S. sentiment)."""
        if isinstance(raw, dict) and "net_non_commercial" in raw:
            # Mock data case
            net = raw["net_non_commercial"]
            pct = raw.get("pct_oi_non_com", 20.0)
            change = raw.get("change", 0)
        else:
            # From real DF or records
            df = pd.DataFrame(raw.get("raw", []))
            if not df.empty and "Noncommercial_Positions_Long" in df.columns:
                long = df["Noncommercial_Positions_Long"].sum()
                short = df.get("Noncommercial_Positions_Short",
                               pd.Series([0])).sum()
                net = long - short
            else:
                net = 0
            pct = 22.0  # placeholder
            change = 1000

        # Advanced F.I.T.S. weighting (from PR #7): Sentiment (COT commercials) 40%, Fundamental 30%, Technical stub 30%
        # Bias score 0-100 for overall setup quality
        spec_extreme = abs(net) / 10000
        score = min(100, int(40 * min(spec_extreme, 1.0) + 30 *
                    (abs(change) / 5000) + 30 * 0.7))  # technical stub
        if net > 10000:
            # specs heavily long -> potential reversal (contrarian)
            bias = "bearish"
            conf = 0.75
        elif net < -5000:
            bias = "bullish"
            conf = 0.8
        else:
            bias = "neutral"
            conf = 0.5
        bias_score = score  # 0-100 overall

        metadata = {
            "net_non_commercial": int(net),
            "pct_oi": round(pct, 1),
            "weekly_change": int(change),
            "report_date": raw.get("latest_date", "N/A"),
            "source": "cftc_cot",
            "philosophy_ref": "F.I.T.S. sentiment - commercials as makers",
            "fits_weighted_score": bias_score,
            "bias_strength": "strong" if bias_score > 70 else "medium" if bias_score > 40 else "weak"
        }

        return COTBias(
            asset=asset,
            net_non_commercial=int(net),
            pct_oi_non_com=pct,
            weekly_change=int(change),
            bias=bias,
            confidence=conf,
            metadata=metadata
        )

    def to_signals(self, biases: Dict[str, COTBias]) -> List[Signal]:
        """Convert COT biases to trading Signals for aggregator."""
        signals = []
        for bias in biases.values():
            direction = Direction.LONG if bias.bias == "bullish" else (
                Direction.SHORT if bias.bias == "bearish" else Direction.NEUTRAL
            )
            if direction != Direction.NEUTRAL:
                signals.append(
                    Signal(
                        coin=bias.asset,
                        direction=direction,
                        confidence=bias.confidence,
                        source="macro/cot",
                        metadata=bias.metadata
                    )
                )
        return signals

    def generate_cot_signal(self, asset: str, cot_bias: COTBias, technical_context: dict | None = None) -> Signal:
        """Precise signal generation with 75% retracement + IPDA (from PR #7).
        Stubs technical confluence for 4H/1H setups per philosophy.
        """
        # Stub for 75% retracement detection and IPDA phase (expansion/retracement)
        technical_context = technical_context or {}
        retracement_conf = technical_context.get(
            "has_75_retracement", True)  # stub true for demo
        ipda_phase = technical_context.get("ipda_phase", "retracement")
        overall_conf = min(
            cot_bias.confidence * (cot_bias.metadata.get("fits_weighted_score", 50) / 100), 0.95)

        direction = Direction.LONG if cot_bias.bias == "bullish" else Direction.SHORT
        metadata = {
            **cot_bias.metadata,
            "75_retracement": retracement_conf,
            "ipda_phase": ipda_phase,
            "confluence": "order_block + FVG + institutional level",
            "bias_score_100": cot_bias.metadata.get("fits_weighted_score", 50)
        }
        return Signal(
            coin=asset,
            direction=direction,
            confidence=overall_conf,
            source="macro/cot_75_retrace",
            metadata=metadata
        )


if __name__ == "__main__":
    from trading.cot.cot_fetcher import fetch_latest_cot
    data = fetch_latest_cot()
    analyzer = COTAnalyzer()
    biases = analyzer.analyze(data)
    signals = analyzer.to_signals(biases)
    print("COT Biases:", {k: v.bias for k, v in biases.items()})
    print("Generated Signals:", len(signals))
