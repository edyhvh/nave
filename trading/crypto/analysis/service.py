"""Single entry point for live BTC/ETH derivatives analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from trading.crypto.analysis.review import review_positions
from trading.crypto.momentum.service import MomentumMarketService, MomentumTimeframes


@dataclass
class CryptoAnalysisService:
    """Orchestrates momentum scans and unified position review."""

    momentum: MomentumMarketService = field(default_factory=MomentumMarketService)

    def review(
        self,
        coins: list[str] | str = "BTC ETH",
        *,
        account_equity: float = 10_000.0,
        risk_pct: float = 0.005,
        timeframes: MomentumTimeframes | None = None,
        include_options: bool = True,
        options_days_to_exp: int = 30,
        options_source: str = "deribit",
    ) -> dict[str, Any]:
        if isinstance(coins, str):
            coin_list = [part.strip().upper() for part in coins.replace(",", " ").split() if part.strip()]
        else:
            coin_list = [coin.upper() for coin in coins]
        return review_positions(
            coin_list,
            account_equity=account_equity,
            risk_pct=risk_pct,
            timeframes=timeframes,
            momentum_service=self.momentum,
            include_options=include_options,
            options_days_to_exp=options_days_to_exp,
            options_source=options_source,
        )

    def scan(
        self,
        symbols: str | list[str] = "BTCUSDT,ETHUSDT",
        *,
        tf: str = "4h,1h",
        account_equity: float = 10_000.0,
        risk_pct: float = 0.005,
        score_threshold: int | None = None,
        apply_cadence_policy: bool = False,
    ) -> dict[str, Any]:
        parsed = self.momentum.parse_symbols(symbols)
        return self.momentum.scan_live(
            symbols=parsed,
            timeframes=self.momentum.parse_timeframes(tf),
            account_equity=account_equity,
            risk_pct=risk_pct,
            score_threshold=score_threshold,
            apply_cadence_policy=apply_cadence_policy,
        )

    def playbook(
        self,
        *,
        symbol: str,
        side: str,
        tf: str = "4h,1h",
        account_equity: float = 10_000.0,
        risk_pct: float = 0.005,
        score_threshold: int | None = None,
    ) -> dict[str, Any]:
        return self.momentum.playbook_live(
            symbol=self.momentum.parse_symbols(symbol)[0],
            side=side.lower(),
            timeframes=self.momentum.parse_timeframes(tf),
            account_equity=account_equity,
            risk_pct=risk_pct,
            score_threshold=score_threshold,
        )