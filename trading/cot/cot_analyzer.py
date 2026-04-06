"""COT Analyzer - Parses COT data into trading bias per Nave philosophy.

Focuses on non-commercial (speculators) vs commercials positioning.
Commercials (institutions/makers) move the market per technical.yaml.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any, List, Optional
import pandas as pd

from trading.config import DEFAULT_SETUPS, COT_PRIMARY_WEIGHT
from trading.setup_learning import SetupLearner
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

    def __init__(
        self,
        setups: Optional[List[str]] = None,
        setup_learner: Optional[SetupLearner] = None,
        regime: Optional[str] = None,
    ):
        candidate_setups = setups or list(DEFAULT_SETUPS)
        self.setup_learner = setup_learner
        self.regime = regime
        if self.setup_learner is not None:
            candidate_setups = self.setup_learner.rank_setups(
                candidate_setups,
                regime=self.regime,
            )
        self.setups = candidate_setups

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
                short = (
                    df["Noncommercial_Positions_Short"].sum()
                    if "Noncommercial_Positions_Short" in df.columns
                    else 0
                )
                net = long - short
            else:
                net = 0
            # Compute pct of OI if open-interest column is present
            if not df.empty and "Open_Interest_All" in df.columns:
                total_oi = df["Open_Interest_All"].iloc[-1]
                pct = round(float(abs(net) / total_oi * 100), 2) if total_oi else 0.0
            else:
                pct = 0.0
            # Weekly change: diff of net between latest two rows if available
            if not df.empty and len(df) >= 2 and "Noncommercial_Positions_Long" in df.columns:
                prev_long = df["Noncommercial_Positions_Long"].iloc[-2]
                prev_short = (
                    df["Noncommercial_Positions_Short"].iloc[-2]
                    if "Noncommercial_Positions_Short" in df.columns
                    else 0
                )
                prev_net = prev_long - prev_short
                change = int(net - prev_net)
            else:
                change = 0

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
            "setups": self.setups,
            "cot_weight": COT_PRIMARY_WEIGHT,
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
        """Precise signal generation with setup confluence + IPDA (from PR #7).
        Stubs technical confluence for 4H/1H setups per philosophy.
        """
        # Stub for setup confluence + IPDA phase (expansion/retracement)
        technical_context = technical_context or {}
        retracement_conf = technical_context.get("has_75_retracement", True)
        ipda_phase = technical_context.get("ipda_phase", "retracement")
        overall_conf = min(
            cot_bias.confidence * (cot_bias.metadata.get("fits_weighted_score", 50) / 100), 0.95)

        direction = Direction.LONG if cot_bias.bias == "bullish" else Direction.SHORT
        metadata = {
            **cot_bias.metadata,
            "75_retracement": retracement_conf,
            "ipda_phase": ipda_phase,
            "confluence": " + ".join(self.setups),
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
