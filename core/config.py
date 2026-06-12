"""Centralized configuration defaults for CLI and integrations."""

from __future__ import annotations

import os
from dataclasses import dataclass

from core.env import load_repo_dotenv


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class HyperliquidSettings:
    """Hyperliquid wallet and execution defaults from .env."""

    wallet: str = "hermes"
    testnet: bool = True
    max_position_usd: float = 100.0
    min_confidence: float = 0.6

    @classmethod
    def from_env(cls) -> HyperliquidSettings:
        load_repo_dotenv()
        return cls(
            wallet=os.getenv("HL_WALLET", "hermes").strip() or "hermes",
            testnet=_env_bool("HL_TESTNET", True),
            max_position_usd=float(os.getenv("HL_MAX_POSITION_USD", "100")),
            min_confidence=float(os.getenv("HL_MIN_CONFIDENCE", "0.6")),
        )


@dataclass(frozen=True)
class CliDefaults:
    """Default values shared by CLI command modules."""

    wallet: str = "hermes"
    capital_usd: float = 2000.0
    coins: str = "BTC ETH"
    host: str = "127.0.0.1"
    api_port: int = 8000

    @classmethod
    def from_env(cls) -> CliDefaults:
        hl = HyperliquidSettings.from_env()
        return cls(wallet=hl.wallet)
