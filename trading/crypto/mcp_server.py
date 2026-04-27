"""
Nave Trading MCP Server

Exposes the nave trading integration as an MCP (Model Context Protocol) server.
Both ironclaw and openfang can call these tools via stdio transport.

Tools provided:
  - account_summary     Show wallet balance, equity, open positions
  - get_price           Current mid price for any Hyperliquid market
  - list_markets        All tradeable perpetual markets
  - open_position       Open a market position (dry_run=true by default)
  - close_position      Close an open position (dry_run=true by default)
  - list_positions      All currently open positions
  - list_orders         All open orders

SECURITY:
  - Private keys are never exposed via MCP tools.
  - Trading tools default to dry_run=true — the AI must explicitly pass
    dry_run=false AND testnet=false to place real orders.
  - All wallet data comes from the encrypted vault only.

Run standalone (for testing):
    python trading/mcp_server.py

Register with ironclaw:
    ironclaw mcp add nave-trading --command "python /root/nave/trading/mcp_server.py" --description "Hyperliquid trading tools"

Register with openfang:
    Add [[mcp_servers]] block to ~/.openfang/config.toml (see docs/web3-setup.md)
"""

import sys
from pathlib import Path

# Ensure nave root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
from mcp.server.fastmcp import FastMCP
from hermes.integration import HermesNaveIntegration
from trading.crypto.client import HyperliquidClient
from trading.crypto.services import COTService
from trading.crypto.vault import WalletVault

mcp = FastMCP(
    name="nave-trading",
    instructions=(
        "Hyperliquid perpetual futures trading tools. "
        "All write operations default to dry_run=True — no real orders are placed "
        "unless the user explicitly requests live trading with dry_run=False. "
        "Never expose private keys or seed phrases."
    ),
)

vault = WalletVault()
hermes = HermesNaveIntegration()
cot_service = COTService()


def _client(wallet: str = "openfang", testnet: bool = True) -> HyperliquidClient:
    return HyperliquidClient(wallet_name=wallet, testnet=testnet)


# ── Read-only tools ───────────────────────────────────────────────────────────


@mcp.tool()
def account_summary(wallet: str = "openfang", testnet: bool = True) -> str:
    """
    Show Hyperliquid account summary: equity, margin used, open positions.

    Args:
        wallet:  Wallet name — 'openfang' or 'ironclaw'
        testnet: True for paper trading (testnet), False for mainnet
    """
    client = _client(wallet, testnet)
    state = client.get_account_state()
    margin = state.get("marginSummary", {})
    positions = client.get_open_positions()
    env = "TESTNET" if testnet else "MAINNET"
    lines = [
        f"Hyperliquid {env} — wallet: {wallet} ({client.address})",
        f"  Equity        : ${float(margin.get('accountValue', 0)):,.2f}",
        f"  Margin used   : ${float(margin.get('totalMarginUsed', 0)):,.2f}",
        f"  Open positions: {len(positions)}",
    ]
    for pos in positions:
        p = pos.get("position", {})
        pnl = float(p.get("unrealizedPnl", 0))
        lines.append(
            f"    {p.get('coin'):>6}  size={p.get('szi')}  "
            f"entry={p.get('entryPx')}  uPnL=${pnl:+.2f}"
        )
    return "\n".join(lines)


@mcp.tool()
def get_price(coin: str, testnet: bool = True) -> str:
    """
    Get the current mid price for a Hyperliquid perpetual market.

    Args:
        coin:    Market symbol, e.g. 'BTC', 'ETH', 'SOL'
        testnet: True for testnet prices (same data, different endpoint)
    """
    client = _client(testnet=testnet)
    price = client.get_mid(coin)
    return f"{coin} mid price: ${price:,.2f} ({'testnet' if testnet else 'mainnet'})"


@mcp.tool()
def list_markets(testnet: bool = True) -> str:
    """
    List all tradeable perpetual markets on Hyperliquid.

    Args:
        testnet: True for testnet market list
    """
    client = _client(testnet=testnet)
    markets = client.get_markets()
    return f"{len(markets)} markets available:\n" + ", ".join(markets)


@mcp.tool()
def list_positions(wallet: str = "openfang", testnet: bool = True) -> str:
    """
    List all open positions for a wallet.

    Args:
        wallet:  Wallet name — 'openfang' or 'ironclaw'
        testnet: True for testnet
    """
    client = _client(wallet, testnet)
    positions = client.get_open_positions()
    if not positions:
        return f"No open positions for {wallet} ({'testnet' if testnet else 'mainnet'})."
    lines = [f"Open positions for {wallet}:"]
    for pos in positions:
        p = pos.get("position", {})
        pnl = float(p.get("unrealizedPnl", 0))
        lines.append(
            f"  {p.get('coin'):>6}  size={p.get('szi')}  entry={p.get('entryPx')}  uPnL=${pnl:+.2f}"
        )
    return "\n".join(lines)


@mcp.tool()
def list_orders(wallet: str = "openfang", testnet: bool = True) -> str:
    """
    List all open orders for a wallet.

    Args:
        wallet:  Wallet name — 'openfang' or 'ironclaw'
        testnet: True for testnet
    """
    client = _client(wallet, testnet)
    orders = client.get_open_orders()
    if not orders:
        return f"No open orders for {wallet}."
    return f"Open orders for {wallet}:\n" + json.dumps(orders, indent=2)


@mcp.tool()
def cot_summary(
    coins: str = "BTC ETH",
    report_type: str = "futures_and_options",
    include_micro: bool = False,
    include_price_context: bool = True,
) -> str:
    """Return the latest structured COT summary as JSON."""
    payload = cot_service.get_latest_summary(
        coins=coins,
        report_type=report_type,
        include_micro=include_micro,
        include_price_context=include_price_context,
    )
    return json.dumps(payload, indent=2)


@mcp.tool()
def cot_weekly_plan(
    coins: str = "BTC ETH",
    capital_usd: float = 2000.0,
    leverage: float = 10.0,
    wallet: str = "openfang",
    testnet: bool = True,
    include_micro: bool = False,
) -> str:
    """Return a structured weekly execution plan generated from live COT + 4H structure."""
    payload = cot_service.get_weekly_plan(
        coins=coins,
        capital_usd=capital_usd,
        leverage=leverage,
        wallet=wallet,
        testnet=testnet,
        include_micro=include_micro,
    )
    return json.dumps(payload, indent=2)


@mcp.tool()
def cot_history(
    months: int = 3,
    coins: str = "BTC ETH",
    report_type: str = "futures_and_options",
    include_micro: bool = False,
) -> str:
    """Return historical COT variation report (structured JSON + markdown)."""
    payload = cot_service.get_historical_variation(
        months=months,
        coins=coins,
        report_type=report_type,
        include_micro=include_micro,
    )
    return json.dumps(payload, indent=2)


# ── Trading tools (default dry_run=True) ─────────────────────────────────────


@mcp.tool()
def open_position(
    coin: str,
    side: str,
    size_usd: float,
    wallet: str = "openfang",
    testnet: bool = True,
    dry_run: bool = True,
) -> str:
    """
    Open a market position on Hyperliquid.

    IMPORTANT: dry_run=True by default — no real order is placed.
    Only set dry_run=False when the user explicitly confirms they want to trade.

    Args:
        coin:     Market symbol, e.g. 'BTC', 'ETH'
        side:     'long' or 'short'
        size_usd: Position size in USD (notional)
        wallet:   Wallet name — 'openfang' or 'ironclaw'
        testnet:  True for paper trading, False for real money
        dry_run:  True = simulate only, False = submit real order
    """
    if side not in ("long", "short"):
        return f"Error: side must be 'long' or 'short', got {side!r}"
    if size_usd <= 0:
        return f"Error: size_usd must be positive, got {size_usd}"

    client = _client(wallet, testnet)
    price = client.get_mid(coin)
    size_coin = round(size_usd / price, 6)
    env = "TESTNET" if testnet else "MAINNET"

    if dry_run:
        return (
            f"[DRY-RUN] Would open {side.upper()} {coin} on {env}\n"
            f"  Wallet  : {wallet} ({client.address})\n"
            f"  Size    : ${size_usd:.2f} ≈ {size_coin} {coin} @ ${price:,.2f}\n"
            f"  (Pass dry_run=False to submit a real order)"
        )

    result = client.market_open(coin, side, size_usd)
    return f"Order submitted [{env}]:\n{json.dumps(result, indent=2)}"


@mcp.tool()
def close_position(
    coin: str,
    wallet: str = "openfang",
    testnet: bool = True,
    dry_run: bool = True,
) -> str:
    """
    Close the entire open position for a coin at market price.

    IMPORTANT: dry_run=True by default — no real order is placed.

    Args:
        coin:    Market symbol to close, e.g. 'ETH'
        wallet:  Wallet name — 'openfang' or 'ironclaw'
        testnet: True for paper trading, False for real money
        dry_run: True = simulate only, False = submit real order
    """
    client = _client(wallet, testnet)
    env = "TESTNET" if testnet else "MAINNET"

    if dry_run:
        positions = client.get_open_positions()
        pos = next((p for p in positions if p.get("position", {}).get("coin") == coin), None)
        if not pos:
            return f"No open {coin} position for {wallet} — nothing to close."
        p = pos["position"]
        return (
            f"[DRY-RUN] Would close {coin} position on {env}\n"
            f"  Wallet : {wallet} ({client.address})\n"
            f"  Size   : {p.get('szi')} {coin}  entry=${p.get('entryPx')}\n"
            f"  (Pass dry_run=False to submit a real order)"
        )

    result = client.market_close(coin)
    return f"Close order submitted [{env}]:\n{json.dumps(result, indent=2)}"


@mcp.tool()
def cot_report(
    coins: str = "BTC ETH",
    include_micro: bool = False,
    report_type: str = "futures_and_options",
) -> str:
    """Return structured COT report JSON for Hermes and other MCP clients."""
    payload = hermes.cot_report(
        coins=coins,
        include_micro=include_micro,
        report_type=report_type,
    )
    return json.dumps(payload, indent=2)


@mcp.tool()
def weekly_plan(
    capital: float = 2000.0,
    wallet: str = "hermes",
    coins: str = "BTC ETH",
    include_micro: bool = False,
) -> str:
    """Return structured weekly trading plan JSON from real COT and 4H data."""
    payload = hermes.weekly_plan(
        capital=capital,
        wallet=wallet,
        coins=coins,
        include_micro=include_micro,
    )
    return json.dumps(payload, indent=2)


@mcp.tool()
def theory_v2_scan(coins: str = "BTC ETH") -> str:
    """Run the daily top-down theory v2 scan (momentum → daily → 4H → 1H).

    Returns per-coin decision trace: at which stage each coin was rejected
    (weekly / weekly_cot / daily / climax_cooldown / chase_gate / 4H / 1H)
    or, if fired, the entry / stop-loss / targets / zc1_rr / velocity.
    The Hermes agent uses this as its primary daily signal source.

    Args:
        coins: Whitespace-separated coin list, e.g. 'BTC ETH SOL'.
    """
    payload = hermes.theory_v2_scan(coins=coins)
    return json.dumps(payload, indent=2)


@mcp.tool()
def strategy_context() -> str:
    """Return the current theory v2 configuration and pooled backtest summary.

    Use alongside theory_v2_scan so the agent can cite the edge
    (iter 14 pooled WR 77.8%, total R +42.54) and the known blind spots
    (iter 16: range-breakouts) when explaining a recommendation.
    """
    payload = hermes.strategy_context()
    return json.dumps(payload, indent=2)


@mcp.tool()
def recommend_position(
    coin_scan: dict,
    capital_usd: float,
    leverage: float = 10.0,
    risk_pct: float = 0.01,
) -> str:
    """Size a concrete position from a theory_v2_scan fired entry.

    Pass in one coin entry from ``theory_v2_scan(...)['coins'][COIN]``.
    Returns risk in USD, coin quantity, notional, margin required, and
    a human-readable order summary. If the scan entry has fired=False,
    returns a stand_aside recommendation with the stage reason.

    Args:
        coin_scan:   Dict from theory_v2_scan['coins'][COIN]
        capital_usd: Total trading capital in USD
        leverage:    Hyperliquid leverage (1-50)
        risk_pct:    Fraction of capital to risk to stop-loss (default 0.01)
    """
    payload = hermes.recommend_position(
        coin_scan=coin_scan,
        capital_usd=capital_usd,
        leverage=leverage,
        risk_pct=risk_pct,
    )
    return json.dumps(payload, indent=2)


@mcp.tool()
def scan_history(days: int = 7) -> str:
    """Return the last N daily-scan reports from var/reports/.

    Lets the agent see whether today's stand-aside is new or the
    continuation of a multi-day regime — important for judging whether
    an extreme-COT block is a one-off or a persistent condition.
    """
    payload = hermes.scan_history(days=days)
    return json.dumps(payload, indent=2)


@mcp.tool()
def stocks_ism_report(
    kind: str = "manufacturing",
    top_n: int = 5,
    min_eps_growth_next_year: float | None = None,
) -> str:
    """Return ISM hottest/worst industries and filtered stock candidates JSON."""
    payload = hermes.stocks_ism_report(
        kind=kind,
        top_n=top_n,
        min_eps_growth_next_year=min_eps_growth_next_year,
    )
    return json.dumps(payload, indent=2)


# ── Memecoin scanner (Solana, read-only) ─────────────────────────────────────


@mcp.tool()
def memecoin_scan(
    limit: int = 50,
    top_n: int = 10,
    keep_skipped: bool = False,
) -> str:
    """Scan recent Pump.fun launches and return safety-filtered ranked candidates.

    Pipeline: Pump.fun new launches → liquidity gate ($25k) → 5 canonical
    SPL safety checks (mint authority, freeze authority, LP, honeypot,
    holder concentration) → transparent FDV/vol/liquidity/momentum/age
    score → ranked top-N. Returns JSON with full breakdown per candidate
    so a human or Hermes can override individual sub-scores.

    Args:
        limit:        How many recent launches to pull from Pump.fun.
        top_n:        Keep the top-N passing candidates by score.
        keep_skipped: Include liquidity-rejected tokens for observability.
    """
    from trading.memecoin.mcp_tools import memecoin_scan_json

    return memecoin_scan_json(limit=limit, top_n=top_n, keep_skipped=keep_skipped)


@mcp.tool()
def memecoin_safety_report(mint: str) -> str:
    """Return the structured 5-check safety report for a single Solana mint.

    Output JSON contract: ``{verdict, rug_score, checks: {mint_authority_renounced,
    freeze_authority_revoked, lp_status, honeypot, holder_concentration},
    dev_wallets, honeypot_flags}``. ``verdict`` is FAIL on any hard check,
    WATCH if all pass but top-1 holder is in the 15-18% flag band, PASS otherwise.
    """
    from trading.memecoin.mcp_tools import memecoin_safety_report_json

    return memecoin_safety_report_json(mint)


@mcp.tool()
def memecoin_score(mint: str, include_safety: bool = False) -> str:
    """Return the transparent rubric score for a single Solana mint.

    All sub-bands (FDV, turnover, liquidity, momentum, age) are returned
    with their numeric inputs and per-band points so callers can override
    a single sub-score without recomputing the rest. Set
    ``include_safety=True`` to additionally run the safety report (a
    failing safety verdict clamps the label to SHILL).
    """
    from trading.memecoin.mcp_tools import memecoin_score_json

    return memecoin_score_json(mint, include_safety=include_safety)


if __name__ == "__main__":
    mcp.run(transport="stdio")
