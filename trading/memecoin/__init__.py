"""
Solana memecoin asset class — read-only scanner + safety filter.

Pipeline:
    1. ``data_provider`` — thin clients for Helius (RPC + DAS API),
                           Pump.fun (new launches + bonding curve),
                           DexScreener (price/volume/liquidity, free),
                           and Jupiter v6 (route quote for honeypot sim).
                           Persistent JSON cache under ``var/memecoin_cache/``.
    2. ``safety_check``  — 5 canonical SPL checks → :class:`SafetyReport`.
                           rug_score / honeypot_flags / lp_status /
                           holder_concentration / dev_wallets.
    3. ``scoring``       — transparent FDV/vol/liquidity/momentum rubric →
                           ``GOOD`` / ``WATCH`` / ``SHILL`` label.
    4. ``scanner``       — discover (Pump.fun) → liquidity gate ($25k) →
                           safety_check → scoring → ranked candidates.
    5. ``mcp_tools``     — ``memecoin_scan`` / ``memecoin_safety_report`` /
                           ``memecoin_score`` exposed to Hermes.

v1 is read-only: the architecture leaves room for a v2 burner-wallet
swap layer (separate from the existing EVM Hyperliquid vault).
"""

from trading.memecoin.data_provider import (
    DexScreenerClient,
    HeliusClient,
    JupiterClient,
    MemecoinDataProvider,
    PumpFunClient,
    PumpFunLaunch,
    TokenMarket,
    TokenMetadata,
)
from trading.memecoin.safety_check import (
    HOLDER_TOP10_MAX,
    HOLDER_TOP1_FLAG_MIN,
    HOLDER_TOP1_FLAG_MAX,
    SafetyReport,
    SafetyVerdict,
    check_safety,
)
from trading.memecoin.scoring import (
    LIQUIDITY_FLOOR_USD,
    Label,
    ScoreBreakdown,
    score_candidate,
)
from trading.memecoin.scanner import (
    MemecoinCandidate,
    MemecoinScanner,
)

__all__ = [
    "DexScreenerClient",
    "HOLDER_TOP10_MAX",
    "HOLDER_TOP1_FLAG_MAX",
    "HOLDER_TOP1_FLAG_MIN",
    "HeliusClient",
    "JupiterClient",
    "Label",
    "LIQUIDITY_FLOOR_USD",
    "MemecoinCandidate",
    "MemecoinDataProvider",
    "MemecoinScanner",
    "PumpFunClient",
    "PumpFunLaunch",
    "SafetyReport",
    "SafetyVerdict",
    "ScoreBreakdown",
    "TokenMarket",
    "TokenMetadata",
    "check_safety",
    "score_candidate",
]
