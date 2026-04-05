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

        # Bias logic: extreme spec long = potential top (contrarian bearish), but respect commercials
        # Per philosophy: commercials move market -> inverse extreme specs somewhat
        if net > 10000:
            bias = "bearish"  # specs heavily long -> potential reversal
            conf = 0.75
        elif net < -5000:
            bias = "bullish"
            conf = 0.8
        else:
            bias = "neutral"
            conf = 0.5

        metadata = {
            "net_non_commercial": int(net),
            "pct_oi": round(pct, 1),
            "weekly_change": int(change),
            "report_date": raw.get("latest_date", "N/A"),
            "source": "cftc_cot",
            "philosophy_ref": "F.I.T.S. sentiment - commercials as makers"
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


if __name__ == "__main__":
    from trading.cot.cot_fetcher import fetch_latest_cot
    data = fetch_latest_cot()
    analyzer = COTAnalyzer()
    biases = analyzer.analyze(data)
    signals = analyzer.to_signals(biases)
    print("COT Biases:", {k: v.bias for k, v in biases.items()})
    print("Generated Signals:", len(signals))
