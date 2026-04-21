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


class Timeframe(str, Enum):
    WEEKLY = "1W"
    DAILY = "1D"
    H4 = "4H"
    H1 = "1H"


class Direction(str, Enum):
    LONG = "long"
    SHORT = "short"
    CLOSE = "close"  # close any existing position
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
        bias_timeframe: Weekly bias timeframe used to frame the idea.
        setup_timeframe: Timeframe that produced the setup.
        trigger_timeframe: Timeframe that produced the entry trigger.
        size_usd:   Optional suggested notional size. Strategy may override.
        invalidation: Optional invalidation price for the setup.
        targets:    Optional take-profit ladder.
        metadata:   Optional dict for diagnostic context (never contains secrets).
    """

    coin: str
    direction: Direction
    confidence: float  # 0..1
    source: str
    bias_timeframe: Timeframe | None = None
    setup_timeframe: Timeframe | None = None
    trigger_timeframe: Timeframe | None = None
    size_usd: float | None = None
    invalidation: float | None = None
    targets: list[float] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def __init__(
        self,
        coin: str,
        direction: Direction | str,
        confidence: float,
        source: str,
        bias_timeframe: Timeframe | str | None = None,
        setup_timeframe: Timeframe | str | None = None,
        trigger_timeframe: Timeframe | str | None = None,
        size_usd: float | None = None,
        invalidation: float | None = None,
        targets: list[float] | None = None,
        metadata: dict | None = None,
    ):
        self.coin = coin
        self.direction = Direction(direction) if isinstance(direction, str) else direction
        self.confidence = confidence
        self.source = source
        self.bias_timeframe = (
            Timeframe(bias_timeframe) if isinstance(bias_timeframe, str) else bias_timeframe
        )
        self.setup_timeframe = (
            Timeframe(setup_timeframe)
            if isinstance(setup_timeframe, str)
            else setup_timeframe
        )
        self.trigger_timeframe = (
            Timeframe(trigger_timeframe)
            if isinstance(trigger_timeframe, str)
            else trigger_timeframe
        )
        self.size_usd = size_usd
        self.invalidation = invalidation
        self.targets = list(targets or [])
        self.metadata = metadata or {}
        self.__post_init__()

    def __post_init__(self):
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1], got {self.confidence}")
        if isinstance(self.direction, str):
            self.direction = Direction(self.direction)
        for attr in ("bias_timeframe", "setup_timeframe", "trigger_timeframe"):
            value = getattr(self, attr)
            if isinstance(value, str):
                setattr(self, attr, Timeframe(value))

    @property
    def is_actionable(self) -> bool:
        return self.direction not in (Direction.NEUTRAL,)

    @property
    def is_timeframe_aware(self) -> bool:
        return self.setup_timeframe is not None or self.trigger_timeframe is not None

    def __repr__(self) -> str:
        tf_parts = []
        if self.bias_timeframe:
            tf_parts.append(f"bias={self.bias_timeframe.value}")
        if self.setup_timeframe:
            tf_parts.append(f"setup={self.setup_timeframe.value}")
        if self.trigger_timeframe:
            tf_parts.append(f"trigger={self.trigger_timeframe.value}")
        tf_suffix = f" {' '.join(tf_parts)}" if tf_parts else ""
        return (
            f"Signal({self.coin} {self.direction.value} "
            f"conf={self.confidence:.2f} src={self.source!r}{tf_suffix})"
        )


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
                print(f"           {s.direction.value:<8} conf={s.confidence:.2f}  [{s.source}]")


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

    def __init__(
        self,
        coins: list[str] | None = None,
    ):
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
            Signal(
                coin=c,
                direction=direction,
                confidence=confidence,
                source="macro/rrp",
                metadata={"rrp_change_bn": rrp_weekly_change_bn},
            )
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
            Signal(
                coin=c,
                direction=direction,
                confidence=confidence,
                source="sentiment/aaii",
                metadata={"bull_pct": bull_pct, "bear_pct": bear_pct},
            )
            for c in self.coins
        ]

    def from_vix(self, vix: float) -> list[Signal]:
        """VIX spike → close or reduce positions."""
        if vix < 25:
            return []
        confidence = min((vix - 25) / 30, 0.9)
        return [
            Signal(
                coin=c,
                direction=Direction.CLOSE,
                confidence=confidence,
                source="risk/vix",
                metadata={"vix": vix},
            )
            for c in self.coins
        ]

    def from_cot(self, cot_biases: dict, setups: list[str] | None = None) -> list[Signal]:
        """
        COT (Commitment of Traders) as primary weekly driver.
        Uses non-commercial positioning (specs vs commercials per philosophy).
        Integrates with F.I.T.S. sentiment layer.
        """
        from trading.cot.cot_analyzer import COTAnalyzer

        analyzer = COTAnalyzer(setups=setups)
        # If data isn't already COTBias objects, analyze raw dict payload first.
        is_bias_object_map = all(
            hasattr(v, "bias") and hasattr(v, "confidence") for v in cot_biases.values()
        )
        biases = cot_biases if is_bias_object_map else analyzer.analyze(cot_biases)
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
            signals.extend(self.from_rrp_delta(indicators["rrp_weekly_change_bn"]))
        if "aaii_bull_pct" in indicators and "aaii_bear_pct" in indicators:
            signals.extend(
                self.from_aaii_sentiment(indicators["aaii_bull_pct"], indicators["aaii_bear_pct"])
            )
        if "vix" in indicators:
            signals.extend(self.from_vix(indicators["vix"]))
        if "cot_data" in indicators:
            # COT is the MAIN weekly driver
            signals.extend(
                self.from_cot(
                    indicators["cot_data"],
                    setups=indicators.get("setups"),
                )
            )
        return signals
