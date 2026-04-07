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
                context={"market_regime": self.regime or "all"},
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
        if isinstance(raw, dict) and (
            "net_non_commercial" in raw or "noncomm_net" in raw
        ):
            # Mock/simplified data case
            net = raw.get("net_non_commercial", raw.get("noncomm_net", 0))
            pct = raw.get("pct_oi_non_com", raw.get("noncomm_pct_oi", 20.0))
            change = raw.get("change", raw.get("change_noncomm_net", 0))
            # Sanitise NaN/None from real CSV rows missing change data
            import math
            if net is None or (isinstance(net, float) and math.isnan(net)):
                net = 0
            if pct is None or (isinstance(pct, float) and math.isnan(pct)):
                pct = 0.0
            if change is None or (isinstance(change, float) and math.isnan(change)):
                change = 0
            change = int(change)
        else:
            # From real DF or records
            df = pd.DataFrame(raw.get("raw", []))
            long_col = self._first_existing(
                df, ["noncomm_positions_long_all",
                     "Noncommercial_Positions_Long"]
            )
            short_col = self._first_existing(
                df, ["noncomm_positions_short_all",
                     "Noncommercial_Positions_Short"]
            )
            oi_col = self._first_existing(
                df, ["open_interest_all", "Open_Interest_All"])

            if not df.empty and long_col:
                latest_long = float(df[long_col].iloc[-1] or 0.0)
                latest_short = float(
                    df[short_col].iloc[-1] or 0.0) if short_col else 0.0
                net = latest_long - latest_short
            else:
                net = 0

            if not df.empty and oi_col:
                total_oi = float(df[oi_col].iloc[-1] or 0.0)
                pct = round(float(abs(net) / total_oi * 100),
                            2) if total_oi else 0.0
            else:
                pct = 0.0

            if not df.empty and len(df) >= 2 and long_col:
                prev_long = float(df[long_col].iloc[-2] or 0.0)
                prev_short = float(df[short_col].iloc[-2]
                                   or 0.0) if short_col else 0.0
                prev_net = prev_long - prev_short
                change = int(net - prev_net)
            else:
                change = 0

        # Advanced F.I.T.S. weighting (from PR #7): Sentiment (COT commercials) 40%, Fundamental 30%, Technical stub 30%
        # Bias score 0-100 for overall setup quality
        # Use pct_oi (scale-independent) for bias detection.
        # Real CFTC BTC data: pct_oi ranges ~ -32 to +8.
        # Contrarian logic: specs heavily long at extremes = bearish reversal,
        # specs heavily short at extremes = bullish reversal.
        pct_extreme = abs(pct) / 20.0  # normalise: 20% OI is a strong signal
        spec_extreme = abs(net) / max(abs(net) + 1, 1)  # fallback scale
        score = min(100, int(40 * min(pct_extreme, 1.0) + 30 *
                    (abs(change) / 2000) + 30 * 0.7))  # technical stub
        if pct > 5.0:
            # specs heavily long (rare, above P95) → potential reversal (contrarian)
            bias = "bearish"
            conf = 0.75
        elif pct < -15.0:
            # specs heavily short (below P30) → bullish reversal
            bias = "bullish"
            conf = 0.8
        elif pct > 0:
            # specs mildly long → lean bearish
            bias = "bearish"
            conf = 0.6
        elif pct < -8.0:
            # specs moderately short → lean bullish
            bias = "bullish"
            conf = 0.65
        else:
            bias = "neutral"
            conf = 0.5

        bias_score = score  # 0-100 overall

        market_regime = self.regime or self._infer_market_regime(
            change=int(change), pct_oi=float(pct))
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
            "bias_strength": "strong" if bias_score > 70 else "medium" if bias_score > 40 else "weak",
            "cot_bias_strength": 1.0 if bias_score > 70 else 0.6 if bias_score > 40 else 0.25,
            "market_regime": market_regime,
            "momentum": float(change),
            "oi_level": float(pct),
            "volatility": 0.02 + (min(abs(change), 2000) / 2000) * 0.03,
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

    def _infer_market_regime(self, change: int, pct_oi: float) -> str:
        if abs(change) > 2500 or abs(pct_oi) > 22:
            return "high_vol"
        if change >= 0:
            return "bull"
        return "bear"

    def _first_existing(self, df: pd.DataFrame, names: list[str]) -> str | None:
        for name in names:
            if name in df.columns:
                return name
        return None


if __name__ == "__main__":
    from trading.cot.cot_fetcher import fetch_latest_cot
    data = fetch_latest_cot()
    analyzer = COTAnalyzer()
    biases = analyzer.analyze(data)
    signals = analyzer.to_signals(biases)
    print("COT Biases:", {k: v.bias for k, v in biases.items()})
    print("Generated Signals:", len(signals))
