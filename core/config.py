"""Centralized configuration defaults for CLI and integrations."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CliDefaults:
    """Default values shared by CLI command modules."""

    wallet: str = "hermes"
    capital_usd: float = 2000.0
    coins: str = "BTC ETH"
    host: str = "127.0.0.1"
    api_port: int = 8000
