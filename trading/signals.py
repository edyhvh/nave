"""
Trade signals — the bridge between nave's macro analysis and Hyperliquid orders.

A Signal is a directional opinion on a market with a confidence score.
Strategies combine multiple signals to decide whether to trade.

Usage:
    from trading.signals import Signal, Direction, SignalAggregator

    # Produce signals from your analysis:
    signal = Signal(coin="ETH", direction=Direction.LONG, confidence=0.75, source="macro")

    # Combine signals:
    agg = SignalAggregator([signal1, signal2])
    final = agg.dominant()  # highest-confidence signal for a coin
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal


class Direction(str, Enum):
    LONG = "long"
    SHORT = "short"
    CLOSE = "close"    # close any existing position
    NEUTRAL = "neutral"  # no action


@dataclass
class Signal:
    """
    A single directional opinion on a tradeable market.

    Attributes:
        coin:       Hyperliquid symbol, e.g. "ETH", "BTC"
        direction:  Trade direction or action.
        confidence: Conviction score in [0, 1]. 1 = maximum conviction.
        source:     Label for the signal source ("macro", "momentum", "sentiment", …)
        size_usd:   Optional suggested notional size. Strategy may override.
        metadata:   Optional dict for diagnostic context (never contains secrets).
    """
    coin: str
    direction: Direction
    confidence: float  # 0..1
    source: str
    size_usd: float | None = None
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"confidence must be in [0, 1], got {self.confidence}")
        if isinstance(self.direction, str):
            self.direction = Direction(self.direction)

    @property
    def is_actionable(self) -> bool:
        return self.direction not in (Direction.NEUTRAL,)

    def __repr__(self) -> str:
        return (f"Signal({self.coin} {self.direction.value} "
                f"conf={self.confidence:.2f} src={self.source!r})")


class SignalAggregator:
    """
    Combines multiple signals for the same coin into a single trade decision.

    Aggregation method: confidence-weighted vote across directions.
    """

    def __init__(self, signals: list[Signal]):
        self.signals = signals

    def for_coin(self, coin: str) -> list[Signal]:
        return [s for s in self.signals if s.coin == coin]

    def dominant(self, coin: str) -> Signal | None:
        """Return the highest-confidence actionable signal for a coin."""
        candidates = [s for s in self.for_coin(coin) if s.is_actionable]
        if not candidates:
            return None
        return max(candidates, key=lambda s: s.confidence)

    def net_direction(self, coin: str, threshold: float = 0.6) -> Direction:
        """
        Compute net direction via confidence-weighted vote.

        Returns NEUTRAL if net conviction is below threshold.
        """
        long_weight = sum(
            s.confidence for s in self.for_coin(coin) if s.direction == Direction.LONG
        )
        short_weight = sum(
            s.confidence for s in self.for_coin(coin) if s.direction == Direction.SHORT
        )
        close_weight = sum(
            s.confidence for s in self.for_coin(coin) if s.direction == Direction.CLOSE
        )
        if close_weight > max(long_weight, short_weight):
            return Direction.CLOSE
        if long_weight >= short_weight and long_weight >= threshold:
            return Direction.LONG
        if short_weight > long_weight and short_weight >= threshold:
            return Direction.SHORT
        return Direction.NEUTRAL

    def all_coins(self) -> list[str]:
        return sorted({s.coin for s in self.signals})

    def summary(self) -> None:
        for coin in self.all_coins():
            sigs = self.for_coin(coin)
            net = self.net_direction(coin)
            print(f"  {coin:<8} net={net.value:<8} ({len(sigs)} signal(s)):")
            for s in sorted(sigs, key=lambda x: -x.confidence):
                print(
                    f"           {s.direction.value:<8} conf={s.confidence:.2f}  [{s.source}]")


# ── Macro signal producers ────────────────────────────────────────────────────

class MacroSignalProducer:
    """
    Converts nave's macro indicator data into trade signals.

    This is intentionally simple — override produce() in a subclass to
    implement your own macro-to-signal logic.

    Example nave indicators that can drive signals:
      - RRP / TGA (Fed liquidity drain → risk-off → short)
      - AAII sentiment (extreme fear → contrarian long)
      - VIX spike (volatility → reduce size or close)
      - BTC ETF net flows (positive → long BTC)
    """

    def __init__(self, coins: list[str] | None = None):
        self.coins = coins or ["BTC", "ETH"]

    def from_rrp_delta(self, rrp_weekly_change_bn: float) -> list[Signal]:
        """
        RRP (Reverse Repo): rising RRP drains liquidity → bearish crypto.
        Falling RRP releases liquidity → bullish crypto.
        rrp_weekly_change_bn: change in RRP balance in billions USD.
        """
        if abs(rrp_weekly_change_bn) < 10:
            return []  # not significant
        confidence = min(abs(rrp_weekly_change_bn) / 100, 0.9)
        direction = Direction.SHORT if rrp_weekly_change_bn > 0 else Direction.LONG
        return [
            Signal(coin=c, direction=direction, confidence=confidence,
                   source="macro/rrp",
                   metadata={"rrp_change_bn": rrp_weekly_change_bn})
            for c in self.coins
        ]

    def from_aaii_sentiment(self, bull_pct: float, bear_pct: float) -> list[Signal]:
        """
        AAII survey: extreme bearishness is a contrarian long signal.
        bull_pct, bear_pct: percentage of bulls/bears in the survey.
        """
        spread = bull_pct - bear_pct
        if abs(spread) < 15:
            return []
        confidence = min(abs(spread) / 40, 0.8)
        # Contrarian: extreme bears → long, extreme bulls → short
        direction = Direction.LONG if spread < -15 else Direction.SHORT
        return [
            Signal(coin=c, direction=direction, confidence=confidence,
                   source="sentiment/aaii",
                   metadata={"bull_pct": bull_pct, "bear_pct": bear_pct})
            for c in self.coins
        ]

    def from_vix(self, vix: float) -> list[Signal]:
        """VIX spike → close or reduce positions."""
        if vix < 25:
            return []
        confidence = min((vix - 25) / 30, 0.9)
        return [
            Signal(coin=c, direction=Direction.CLOSE, confidence=confidence,
                   source="risk/vix", metadata={"vix": vix})
            for c in self.coins
        ]

    def from_cot(self, cot_biases: dict) -> list[Signal]:
        """
        COT (Commitment of Traders) as primary weekly driver.
        Uses non-commercial positioning (specs vs commercials per philosophy).
        Integrates with F.I.T.S. sentiment layer.
        """
        from trading.cot.cot_analyzer import COTAnalyzer
        analyzer = COTAnalyzer()
        # If raw data, analyze first
        if "BTC" in cot_biases and isinstance(cot_biases["BTC"], dict) and "bias" not in cot_biases["BTC"]:
            biases = analyzer.analyze(cot_biases)
        else:
            biases = cot_biases
        return analyzer.to_signals(biases)

    def produce(self, indicators: dict) -> list[Signal]:
        """
        Produce signals from a dict of nave indicators.

        Expected keys (all optional):
            rrp_weekly_change_bn: float
            aaii_bull_pct: float
            aaii_bear_pct: float
            vix: float
            cot_data: dict  # COT as main weekly driver
        """
        signals: list[Signal] = []
        if "rrp_weekly_change_bn" in indicators:
            signals.extend(self.from_rrp_delta(
                indicators["rrp_weekly_change_bn"]))
        if "aaii_bull_pct" in indicators and "aaii_bear_pct" in indicators:
            signals.extend(self.from_aaii_sentiment(
                indicators["aaii_bull_pct"], indicators["aaii_bear_pct"]
            ))
        if "vix" in indicators:
            signals.extend(self.from_vix(indicators["vix"]))
        if "cot_data" in indicators:
            # COT is the MAIN weekly driver
            signals.extend(self.from_cot(indicators["cot_data"]))
        return signals
