"""
Hyperliquid client — wraps the Hyperliquid API for use by nave trading strategies.

Supports:
- Perpetual futures (long/short, market/limit)
- Portfolio info, open positions, order history
- Paper trading via testnet (default until live keys are configured)

Config is loaded from ~/.secrets/nave-wallets/ vault — never from env vars
or hardcoded values.

Usage:
    from scripts.hyperliquid_client import HyperliquidClient

    client = HyperliquidClient(wallet_name="openfang", testnet=True)
    print(client.get_account_info())
    client.market_open("ETH", side="long", size_usd=100)
"""

import sys
import json
from pathlib import Path
from typing import Literal

import requests

sys.path.insert(0, str(Path(__file__).parent))

from wallet_vault import WalletVault


MAINNET_API = "https://api.hyperliquid.xyz"
TESTNET_API = "https://api.hyperliquid-testnet.xyz"


class HyperliquidClient:
    def __init__(self, wallet_name: str = "openfang", testnet: bool = True):
        self.testnet = testnet
        self.base_url = TESTNET_API if testnet else MAINNET_API
        self._wallet_name = wallet_name
        self._vault = WalletVault()
        self._address = self._vault.address(wallet_name)
        self._exchange = None  # lazy-loaded on first trade

    @property
    def address(self) -> str:
        return self._address

    def _get_exchange(self):
        """Lazy-load the exchange client (requires eth_account + hyperliquid SDK)."""
        if self._exchange is not None:
            return self._exchange
        try:
            import eth_account
            from eth_account.signers.local import LocalAccount
            from hyperliquid.exchange import Exchange
            from hyperliquid.utils import constants
        except ImportError as e:
            raise ImportError(
                "Install trading deps: pip install eth-account hyperliquid-python"
            ) from e

        private_key = self._vault.private_key(self._wallet_name)
        account: LocalAccount = eth_account.Account.from_key(private_key)
        base_url = constants.TESTNET_API_URL if self.testnet else constants.MAINNET_API_URL
        self._exchange = Exchange(account, base_url)
        return self._exchange

    # ── Read-only endpoints (no signing required) ────────────────────────────

    def _info_post(self, payload: dict) -> dict:
        resp = requests.post(f"{self.base_url}/info", json=payload, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def get_account_info(self) -> dict:
        """Return portfolio summary: balances, equity, margin usage."""
        return self._info_post({"type": "clearinghouseState", "user": self._address})

    def get_open_positions(self) -> list:
        state = self.get_account_info()
        return state.get("assetPositions", [])

    def get_open_orders(self) -> list:
        return self._info_post({"type": "openOrders", "user": self._address})

    def get_all_mids(self) -> dict:
        """Return mid prices for all perp markets."""
        return self._info_post({"type": "allMids"})

    def get_meta(self) -> dict:
        """Return exchange metadata: available assets, leverage tiers, etc."""
        return self._info_post({"type": "meta"})

    def get_order_history(self, limit: int = 50) -> list:
        result = self._info_post({"type": "userFills", "user": self._address})
        return result[:limit] if isinstance(result, list) else result

    # ── Trading endpoints (requires wallet signing) ───────────────────────────

    def market_open(
        self,
        coin: str,
        side: Literal["long", "short"],
        size_usd: float,
        slippage: float = 0.01,
    ) -> dict:
        """Open a market position. size_usd is the notional in USD."""
        exchange = self._get_exchange()
        is_buy = side == "long"
        mids = self.get_all_mids()
        price = float(mids.get(coin, 0))
        if price == 0:
            raise ValueError(f"No mid price found for {coin}")
        sz = round(size_usd / price, 6)
        result = exchange.market_open(coin, is_buy, sz, slippage=slippage)
        return result

    def market_close(self, coin: str, slippage: float = 0.01) -> dict:
        """Close entire position for a coin at market price."""
        exchange = self._get_exchange()
        result = exchange.market_close(coin, slippage=slippage)
        return result

    def limit_order(
        self,
        coin: str,
        side: Literal["buy", "sell"],
        size: float,
        price: float,
        reduce_only: bool = False,
    ) -> dict:
        exchange = self._get_exchange()
        is_buy = side == "buy"
        order_type = {"limit": {"tif": "Gtc"}}
        result = exchange.order(coin, is_buy, size, price, order_type, reduce_only=reduce_only)
        return result

    def cancel_order(self, coin: str, order_id: int) -> dict:
        exchange = self._get_exchange()
        return exchange.cancel(coin, order_id)

    def set_leverage(self, coin: str, leverage: int, is_cross: bool = True) -> dict:
        exchange = self._get_exchange()
        return exchange.update_leverage(leverage, coin, is_cross)

    def summary(self) -> None:
        """Print a safe account summary (no private data)."""
        info = self.get_account_info()
        margin = info.get("marginSummary", {})
        positions = self.get_open_positions()
        env = "TESTNET" if self.testnet else "MAINNET"
        print(f"[Hyperliquid {env}] wallet={self._wallet_name} addr={self._address}")
        print(f"  Account value : ${float(margin.get('accountValue', 0)):,.2f}")
        print(f"  Total margin  : ${float(margin.get('totalMarginUsed', 0)):,.2f}")
        print(f"  Open positions: {len(positions)}")
        for pos in positions:
            p = pos.get("position", {})
            print(f"    {p.get('coin')}: {p.get('szi')} @ entry {p.get('entryPx')}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Hyperliquid CLI")
    parser.add_argument("--wallet", default="openfang")
    parser.add_argument("--mainnet", action="store_true")
    parser.add_argument("command", choices=["summary", "positions", "orders", "mids"])
    args = parser.parse_args()

    client = HyperliquidClient(wallet_name=args.wallet, testnet=not args.mainnet)

    if args.command == "summary":
        client.summary()
    elif args.command == "positions":
        print(json.dumps(client.get_open_positions(), indent=2))
    elif args.command == "orders":
        print(json.dumps(client.get_open_orders(), indent=2))
    elif args.command == "mids":
        mids = client.get_all_mids()
        for coin, mid in sorted(mids.items()):
            print(f"  {coin}: {mid}")
