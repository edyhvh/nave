"""
Base strategy class for nave trading strategies.

A Strategy ties together:
  - A HyperliquidClient (for market data + order execution)
  - One or more signal producers (macro, momentum, sentiment)
  - Position sizing and risk rules

Usage:
    from trading.strategy import BaseStrategy
    from trading.signals import SignalAggregator, Direction

    class MyMacroStrategy(BaseStrategy):
        def compute_signals(self) -> list[Signal]:
            # Pull nave macro data and return signals
            ...

        def run_once(self) -> None:
            self.execute_signals(self.compute_signals())

Example — run from CLI:
    python -m trading.strategy --wallet openfang --dry-run
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from trading.client import HyperliquidClient
from trading.signals import Direction, Signal, SignalAggregator

logger = logging.getLogger(__name__)


class BaseStrategy(ABC):
    """
    Abstract base for all nave trading strategies.

    Subclasses must implement:
        compute_signals() -> list[Signal]

    Risk parameters:
        max_position_usd:   Hard cap per position in USD.
        min_confidence:     Minimum signal confidence to act on.
        dry_run:            If True, log orders but do NOT submit them.
    """

    def __init__(
        self,
        client: HyperliquidClient,
        max_position_usd: float = 100.0,
        min_confidence: float = 0.6,
        dry_run: bool = True,
    ):
        self.client = client
        self.max_position_usd = max_position_usd
        self.min_confidence = min_confidence
        self.dry_run = dry_run

        if dry_run:
            logger.warning("Strategy running in DRY-RUN mode — no orders will be submitted.")

    @abstractmethod
    def compute_signals(self) -> list[Signal]:
        """Compute and return a list of trade signals. No side effects."""
        ...

    def position_size_usd(self, signal: Signal) -> float:
        """Scale position size by confidence. Override to customise."""
        base = signal.size_usd or self.max_position_usd
        return min(base * signal.confidence, self.max_position_usd)

    def _open(self, coin: str, direction: Direction, size_usd: float) -> None:
        side = "long" if direction == Direction.LONG else "short"
        if self.dry_run:
            logger.info("[DRY-RUN] market_open %s %s $%.2f", coin, side, size_usd)
            return
        result = self.client.market_open(coin, side, size_usd)
        logger.info("market_open %s %s $%.2f → %s", coin, side, size_usd, result)

    def _close(self, coin: str) -> None:
        if self.dry_run:
            logger.info("[DRY-RUN] market_close %s", coin)
            return
        result = self.client.market_close(coin)
        logger.info("market_close %s → %s", coin, result)

    def execute_signals(self, signals: list[Signal]) -> None:
        """
        Evaluate aggregated signals and submit orders.

        Logic:
          - CLOSE direction → close any open position for that coin.
          - LONG/SHORT with confidence >= min_confidence → open market position.
          - Coins already in a position and signal unchanged → hold (no action).
        """
        if not signals:
            logger.info("No signals to execute.")
            return

        agg = SignalAggregator(signals)
        open_positions = {
            p["position"]["coin"]
            for p in self.client.get_open_positions()
        }

        for coin in agg.all_coins():
            net = agg.net_direction(coin)
            dominant = agg.dominant(coin)

            if net == Direction.NEUTRAL:
                logger.debug("%s: NEUTRAL — holding", coin)
                continue

            if net == Direction.CLOSE:
                if coin in open_positions:
                    logger.info("%s: closing position", coin)
                    self._close(coin)
                continue

            if dominant and dominant.confidence >= self.min_confidence:
                size_usd = self.position_size_usd(dominant)
                if coin in open_positions:
                    logger.debug("%s: already in position — holding", coin)
                else:
                    self._open(coin, net, size_usd)
            else:
                logger.debug(
                    "%s: below confidence threshold (%.2f < %.2f)",
                    coin,
                    dominant.confidence if dominant else 0,
                    self.min_confidence,
                )

    def run_once(self) -> dict:
        """Compute signals and execute. Returns a summary dict."""
        signals = self.compute_signals()
        logger.info("Computed %d signal(s): %s", len(signals), signals)
        self.execute_signals(signals)
        return {"signals": len(signals), "dry_run": self.dry_run}


# ── Example strategy ──────────────────────────────────────────────────────────

class MacroMomentumStrategy(BaseStrategy):
    """
    Example strategy that combines nave macro indicators with price momentum.

    Extend this with real data from nave's OpenBB scripts.
    """

    def __init__(self, client: HyperliquidClient, coins: list[str] | None = None, **kwargs):
        super().__init__(client, **kwargs)
        self.coins = coins or ["BTC", "ETH"]

    def compute_signals(self) -> list[Signal]:
        from trading.signals import MacroSignalProducer

        # TODO: replace with real nave indicator pulls from OpenBB
        indicators = self._fetch_indicators()
        producer = MacroSignalProducer(coins=self.coins)
        return producer.produce(indicators)

    def _fetch_indicators(self) -> dict:
        """
        Stub — replace with actual nave/OpenBB data fetching.

        Example integration with nave's existing scripts:
            from scripts.openbb_tools import get_rrp, get_aaii, get_vix
            return {
                "rrp_weekly_change_bn": get_rrp()["weekly_change"],
                "aaii_bull_pct": get_aaii()["bull"],
                "aaii_bear_pct": get_aaii()["bear"],
                "vix": get_vix(),
            }
        """
        logger.warning("_fetch_indicators() is using stub data — integrate with nave/OpenBB")
        return {}


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Run MacroMomentumStrategy once")
    parser.add_argument("--wallet", default="openfang")
    parser.add_argument("--mainnet", action="store_true")
    parser.add_argument("--live", action="store_true", help="Disable dry-run (REAL ORDERS)")
    parser.add_argument("--coins", nargs="+", default=["BTC", "ETH"])
    parser.add_argument("--max-usd", type=float, default=50.0)
    args = parser.parse_args()

    if args.live and not args.mainnet:
        parser.error("--live requires --mainnet (testnet is for paper trading)")

    client = HyperliquidClient(wallet_name=args.wallet, testnet=not args.mainnet)
    strategy = MacroMomentumStrategy(
        client,
        coins=args.coins,
        max_position_usd=args.max_usd,
        dry_run=not args.live,
    )
    client.summary()
    result = strategy.run_once()
    print(f"\nStrategy run complete: {result}")
