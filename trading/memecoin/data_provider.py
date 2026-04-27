"""
Data layer for the Solana memecoin scanner.

Thin, rate-limited clients with a persistent JSON cache under
``var/memecoin_cache/``. The :class:`MemecoinDataProvider` is the only
class the rest of the pipeline (safety_check, scoring, scanner) needs to
import — it composes the four underlying clients and exposes typed
accessors.

Providers:
    * :class:`HeliusClient`     — RPC + DAS API. Token metadata, mint info,
                                  largest holders, parsed accounts.
                                  Auth: HELIUS_API_KEY (free / starter tier).
    * :class:`PumpFunClient`    — Public Pump.fun frontend API. New launches,
                                  bonding-curve state, basic mcap/liquidity.
                                  No auth required.
    * :class:`DexScreenerClient` — Free public market-data API. Price, 24h
                                  volume, liquidity in USD. No auth required.
    * :class:`JupiterClient`    — Jupiter v6 ``/quote`` endpoint. Used as a
                                  honeypot probe (does a sell route exist
                                  for a tiny amount?). No auth required.

All clients share a sliding-window rate limiter and 429-retry loop. The
provider never raises on a single failed downstream call: it returns
``None`` / empty fields and lets ``safety_check`` decide the verdict.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Solana wrapped SOL mint — used as the quote token for Jupiter honeypot
# probes (try to swap 1000 lamports of TOKEN → wSOL).
WSOL_MINT = "So11111111111111111111111111111111111111112"

DEFAULT_CACHE_TTL_SECONDS = 60 * 5  # 5 min — memecoin state moves fast
DEFAULT_TIMEOUT_SECONDS = 12.0
DEFAULT_RPM = 60  # be polite on free tiers
RATE_WINDOW_SECONDS = 60.0
DEFAULT_429_RETRIES = 2

_DOTENV_ATTEMPTED = False


# ── Public dataclasses ────────────────────────────────────────────────────────


@dataclass
class TokenMetadata:
    """Subset of Helius DAS / mint account fields the safety check needs."""

    mint: str
    name: str | None = None
    symbol: str | None = None
    decimals: int | None = None
    supply: float | None = None  # ui amount (already divided by 10**decimals)
    mint_authority: str | None = None  # None if renounced
    freeze_authority: str | None = None  # None if revoked
    update_authority: str | None = None
    is_mutable: bool | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class TokenHolder:
    address: str
    amount: float  # ui amount
    pct_of_supply: float  # 0-100


@dataclass
class TokenMarket:
    """Aggregated market snapshot — DexScreener for graduated tokens, Pump.fun
    for tokens still on the bonding curve."""

    mint: str
    price_usd: float | None = None
    liquidity_usd: float | None = None
    fdv_usd: float | None = None
    market_cap_usd: float | None = None
    volume_24h_usd: float | None = None
    pair_address: str | None = None
    dex: str | None = None  # "raydium" | "pump" | "meteora" | ...
    age_minutes: int | None = None
    price_change_5m_pct: float | None = None
    price_change_1h_pct: float | None = None
    holder_count: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class PumpFunLaunch:
    """A single new launch row from Pump.fun."""

    mint: str
    name: str | None
    symbol: str | None
    creator: str | None
    created_at: str | None
    bonding_curve_progress: float | None  # 0-100
    market_cap_usd: float | None
    liquidity_usd: float | None
    raw: dict[str, Any] = field(default_factory=dict)


# ── Errors ────────────────────────────────────────────────────────────────────


class MemecoinRateLimitError(RuntimeError):
    """Raised when the local rate limiter couldn't drain in time."""


# ── Helpers ───────────────────────────────────────────────────────────────────


def _maybe_load_repo_dotenv_once() -> None:
    """Best-effort .env bootstrap so CLI/MCP/Hermes share local credentials."""
    global _DOTENV_ATTEMPTED
    if _DOTENV_ATTEMPTED:
        return
    _DOTENV_ATTEMPTED = True

    if os.getenv("HELIUS_API_KEY"):
        return

    try:
        from dotenv import load_dotenv
    except Exception:
        return

    env_path = Path(__file__).resolve().parents[2] / ".env"
    if env_path.exists():
        load_dotenv(env_path)


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class _TokenBucket:
    """Sliding-window rate limiter: at most ``rpm`` calls per 60 seconds."""

    def __init__(self, rpm: int):
        self.rpm = max(1, rpm)
        self._calls: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self, *, max_wait_seconds: float = 90.0) -> None:
        deadline = time.monotonic() + max_wait_seconds
        while True:
            with self._lock:
                now = time.monotonic()
                while self._calls and (now - self._calls[0]) >= RATE_WINDOW_SECONDS:
                    self._calls.popleft()
                if len(self._calls) < self.rpm:
                    self._calls.append(now)
                    return
                sleep_for = RATE_WINDOW_SECONDS - (now - self._calls[0]) + 0.05
            if time.monotonic() + sleep_for > deadline:
                raise MemecoinRateLimitError(
                    f"Rate limit not drained after {max_wait_seconds:.0f}s "
                    f"(limit={self.rpm} rpm)"
                )
            time.sleep(sleep_for)


# ── Base client with shared cache + rate-limit + 429 retry ────────────────────


class _BaseClient:
    """Shared transport layer for the four memecoin data providers."""

    name: str = "base"
    default_base_url: str = ""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        rpm: int = DEFAULT_RPM,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        cache_dir: Path | None = None,
        cache_ttl_seconds: int | None = None,
        http: httpx.Client | None = None,
    ):
        self.base_url = (base_url or self.default_base_url).rstrip("/")
        self._bucket = _TokenBucket(rpm=rpm)
        self.timeout_seconds = timeout_seconds
        self._http = http
        self.cache_ttl_seconds = int(
            cache_ttl_seconds
            or os.getenv("MEMECOIN_CACHE_TTL_SECONDS")
            or DEFAULT_CACHE_TTL_SECONDS
        )
        self.cache_dir: Path | None = None
        if http is None:
            default_cache_dir = (
                Path(__file__).resolve().parents[2] / "var" / "memecoin_cache" / self.name
            )
            self.cache_dir = Path(
                cache_dir or os.getenv("MEMECOIN_CACHE_DIR") or default_cache_dir
            )
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _client(self) -> httpx.Client:
        if self._http is not None:
            return self._http
        self._http = httpx.Client(
            base_url=self.base_url,
            headers={"Accept": "application/json"},
            timeout=self.timeout_seconds,
        )
        return self._http

    def _cache_path(self, namespace: str, key: str) -> Path:
        assert self.cache_dir is not None
        safe_key = "".join(
            ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in key.lower()
        )
        return self.cache_dir / f"{namespace}_{safe_key}.json"

    def _cache_get(self, namespace: str, key: str) -> Any | None:
        if self.cache_dir is None:
            return None
        path = self._cache_path(namespace, key)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text())
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        expires_at = _to_float(payload.get("expires_at"))
        if expires_at is not None and time.time() > expires_at:
            return None
        return payload.get("value")

    def _cache_put(
        self, namespace: str, key: str, value: Any, *, ttl_seconds: int | None = None
    ) -> None:
        if self.cache_dir is None:
            return
        path = self._cache_path(namespace, key)
        payload = {
            "expires_at": time.time() + float(ttl_seconds or self.cache_ttl_seconds),
            "value": value,
        }
        try:
            path.write_text(json.dumps(payload, default=str))
        except Exception:
            logger.debug(
                "Failed to persist %s cache for %s:%s",
                self.name,
                namespace,
                key,
                exc_info=True,
            )

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        max_retries: int = DEFAULT_429_RETRIES,
    ) -> dict[str, Any] | list[Any] | None:
        for attempt in range(max_retries + 1):
            self._bucket.acquire()
            try:
                resp = self._client().request(
                    method, path, params=params, json=json_body
                )
            except httpx.HTTPError as exc:
                logger.debug("%s %s failed: %s", method, path, exc, exc_info=True)
                return None
            if resp.status_code == 429:
                if attempt >= max_retries:
                    logger.warning(
                        "%s rate-limited after %d attempts on %s",
                        self.name,
                        attempt + 1,
                        path,
                    )
                    return None
                retry_after = _to_float(resp.headers.get("Retry-After")) or 5.0
                time.sleep(min(retry_after, RATE_WINDOW_SECONDS))
                continue
            if resp.status_code in {404, 400}:
                logger.debug("%s %s -> %s", method, path, resp.status_code)
                return None
            if resp.status_code >= 500:
                logger.warning("%s %s -> %s", method, path, resp.status_code)
                return None
            try:
                return resp.json()
            except Exception:
                return None
        return None


# ── Helius (RPC + DAS API) ────────────────────────────────────────────────────


class HeliusClient(_BaseClient):
    """Helius RPC + DAS API for token metadata, mint state, and holders.

    Uses HELIUS_API_KEY appended as ``?api-key=...``. Compatible with the
    free / starter tier.
    """

    name = "helius"
    default_base_url = "https://mainnet.helius-rpc.com"

    def __init__(self, api_key: str | None = None, **kwargs: Any):
        _maybe_load_repo_dotenv_once()
        self.api_key = api_key or os.getenv("HELIUS_API_KEY")
        if not self.api_key:
            logger.warning(
                "HELIUS_API_KEY is not set. HeliusClient calls will fail at runtime."
            )
        super().__init__(**kwargs)

    def _rpc(self, method: str, params: list[Any]) -> Any:
        if not self.api_key:
            return None
        body = {
            "jsonrpc": "2.0",
            "id": "nave-memecoin",
            "method": method,
            "params": params,
        }
        path = f"/?api-key={self.api_key}"
        payload = self._request_json("POST", path, json_body=body)
        if isinstance(payload, dict):
            if "error" in payload:
                logger.debug("Helius RPC error on %s: %s", method, payload["error"])
                return None
            return payload.get("result")
        return None

    # ── Public API ----------------------------------------------------

    def get_token_metadata(self, mint: str) -> TokenMetadata | None:
        """Pull DAS asset details + parsed mint account in one logical call."""
        cached = self._cache_get("token_metadata", mint)
        if isinstance(cached, dict):
            try:
                return TokenMetadata(**cached)
            except TypeError:
                pass

        asset = self._rpc("getAsset", [mint]) or {}
        mint_account = self._rpc(
            "getAccountInfo", [mint, {"encoding": "jsonParsed"}]
        ) or {}

        parsed = (
            mint_account.get("value", {})
            .get("data", {})
            .get("parsed", {})
            .get("info", {})
            if isinstance(mint_account, dict)
            else {}
        )

        token_info = asset.get("token_info") or {}
        content = asset.get("content") or {}
        metadata = content.get("metadata") or {}
        authorities = asset.get("authorities") or []
        update_authority = authorities[0].get("address") if authorities else None

        decimals = _to_int(parsed.get("decimals") or token_info.get("decimals"))
        raw_supply = _to_float(parsed.get("supply") or token_info.get("supply"))
        ui_supply = (
            raw_supply / (10 ** decimals)
            if (raw_supply is not None and decimals is not None and decimals > 0)
            else raw_supply
        )

        meta = TokenMetadata(
            mint=mint,
            name=metadata.get("name") or asset.get("name"),
            symbol=metadata.get("symbol") or asset.get("symbol"),
            decimals=decimals,
            supply=ui_supply,
            mint_authority=parsed.get("mintAuthority"),
            freeze_authority=parsed.get("freezeAuthority"),
            update_authority=update_authority,
            is_mutable=asset.get("mutable"),
            raw={"asset": asset, "mint_account": parsed},
        )

        self._cache_put(
            "token_metadata",
            mint,
            {
                "mint": meta.mint,
                "name": meta.name,
                "symbol": meta.symbol,
                "decimals": meta.decimals,
                "supply": meta.supply,
                "mint_authority": meta.mint_authority,
                "freeze_authority": meta.freeze_authority,
                "update_authority": meta.update_authority,
                "is_mutable": meta.is_mutable,
                "raw": meta.raw,
            },
        )
        return meta

    def get_largest_holders(self, mint: str, limit: int = 20) -> list[TokenHolder]:
        """Returns the top ``limit`` holders sorted by balance, with %-of-supply."""
        cached = self._cache_get("largest_holders", f"{mint}_{limit}")
        if isinstance(cached, list):
            return [TokenHolder(**row) for row in cached]

        result = self._rpc("getTokenLargestAccounts", [mint])
        if not isinstance(result, dict):
            return []

        meta = self.get_token_metadata(mint)
        supply = meta.supply if meta else None

        holders: list[TokenHolder] = []
        for row in (result.get("value") or [])[:limit]:
            ui_amount = _to_float(row.get("uiAmount"))
            if ui_amount is None:
                amount_str = row.get("amount")
                decimals = meta.decimals if meta else None
                if amount_str is not None and decimals is not None and decimals > 0:
                    ui_amount = _to_float(amount_str) / (10 ** decimals)
            ui_amount = ui_amount or 0.0
            pct = (ui_amount / supply * 100.0) if (supply and supply > 0) else 0.0
            holders.append(
                TokenHolder(
                    address=row.get("address", ""),
                    amount=ui_amount,
                    pct_of_supply=round(pct, 4),
                )
            )

        self._cache_put(
            "largest_holders",
            f"{mint}_{limit}",
            [h.__dict__ for h in holders],
        )
        return holders


# ── Pump.fun (no auth) ────────────────────────────────────────────────────────


class PumpFunClient(_BaseClient):
    """Public Pump.fun frontend API. No auth required.

    The frontend API is community-documented and stable enough for a
    scanner: ``/coins`` for new launches, ``/coins/<mint>`` for one row.
    Fields surface bonding-curve progress, mcap, and a coarse liquidity
    estimate while the token is still on the bonding curve.
    """

    name = "pumpfun"
    default_base_url = "https://frontend-api.pump.fun"

    def list_new_launches(self, limit: int = 50) -> list[PumpFunLaunch]:
        cached = self._cache_get("new_launches", str(limit))
        if isinstance(cached, list):
            return [PumpFunLaunch(**row) for row in cached]

        # /coins?offset=0&limit=N&sort=created_timestamp&order=DESC&includeNsfw=false
        payload = self._request_json(
            "GET",
            "/coins",
            params={
                "offset": 0,
                "limit": limit,
                "sort": "created_timestamp",
                "order": "DESC",
                "includeNsfw": "false",
            },
        )
        if not isinstance(payload, list):
            return []

        launches = [self._parse_launch(row) for row in payload]
        launches = [lx for lx in launches if lx is not None]
        self._cache_put(
            "new_launches",
            str(limit),
            [
                {
                    "mint": lx.mint,
                    "name": lx.name,
                    "symbol": lx.symbol,
                    "creator": lx.creator,
                    "created_at": lx.created_at,
                    "bonding_curve_progress": lx.bonding_curve_progress,
                    "market_cap_usd": lx.market_cap_usd,
                    "liquidity_usd": lx.liquidity_usd,
                    "raw": lx.raw,
                }
                for lx in launches
            ],
            ttl_seconds=60,  # new-launches feed turns over fast
        )
        return launches

    def get_launch(self, mint: str) -> PumpFunLaunch | None:
        cached = self._cache_get("launch", mint)
        if isinstance(cached, dict):
            try:
                return PumpFunLaunch(**cached)
            except TypeError:
                pass
        payload = self._request_json("GET", f"/coins/{mint}")
        if not isinstance(payload, dict):
            return None
        launch = self._parse_launch(payload)
        if launch is not None:
            self._cache_put(
                "launch",
                mint,
                {
                    "mint": launch.mint,
                    "name": launch.name,
                    "symbol": launch.symbol,
                    "creator": launch.creator,
                    "created_at": launch.created_at,
                    "bonding_curve_progress": launch.bonding_curve_progress,
                    "market_cap_usd": launch.market_cap_usd,
                    "liquidity_usd": launch.liquidity_usd,
                    "raw": launch.raw,
                },
            )
        return launch

    @staticmethod
    def _parse_launch(row: dict[str, Any]) -> PumpFunLaunch | None:
        mint = row.get("mint") or row.get("address")
        if not mint:
            return None
        # Bonding-curve progress is roughly virtual_sol_reserves / completion target.
        progress = _to_float(row.get("complete_progress"))
        if progress is None:
            v_sol = _to_float(row.get("virtual_sol_reserves"))
            if v_sol is not None:
                # Pump.fun graduates around ~85 SOL of real reserves; use 100 SOL as
                # a coarse 100% mark for display-only progress.
                progress = min(100.0, (v_sol / 1e9) / 100.0 * 100.0)
        return PumpFunLaunch(
            mint=mint,
            name=row.get("name"),
            symbol=row.get("symbol"),
            creator=row.get("creator") or row.get("dev"),
            created_at=row.get("created_timestamp") or row.get("created_at"),
            bonding_curve_progress=progress,
            market_cap_usd=_to_float(row.get("usd_market_cap")),
            liquidity_usd=_to_float(row.get("liquidity"))
            or _to_float(row.get("usd_liquidity")),
            raw=row,
        )


# ── DexScreener (free, no auth) ───────────────────────────────────────────────


class DexScreenerClient(_BaseClient):
    """DexScreener public API for graduated tokens.

    Once a Pump.fun token graduates onto Raydium / Meteora / etc., the
    richest market data (price, FDV, 24h volume, deep liquidity) lives
    on DexScreener. Free, no auth, no quota beyond reasonable use.
    """

    name = "dexscreener"
    default_base_url = "https://api.dexscreener.com"

    def get_token_market(self, mint: str) -> TokenMarket | None:
        cached = self._cache_get("token_market", mint)
        if isinstance(cached, dict):
            try:
                return TokenMarket(**cached)
            except TypeError:
                pass

        payload = self._request_json("GET", f"/latest/dex/tokens/{mint}")
        if not isinstance(payload, dict):
            return None
        pairs = payload.get("pairs") or []
        if not pairs:
            return None
        # Pick the pair with the deepest USD liquidity — that's the venue
        # we'd actually trade through.
        best = max(
            pairs,
            key=lambda p: _to_float((p.get("liquidity") or {}).get("usd")) or 0.0,
        )
        liquidity = (best.get("liquidity") or {})
        price_change = best.get("priceChange") or {}
        created_ms = _to_float(best.get("pairCreatedAt"))
        age_minutes = (
            int((time.time() * 1000 - created_ms) / 60000.0)
            if created_ms is not None
            else None
        )

        market = TokenMarket(
            mint=mint,
            price_usd=_to_float(best.get("priceUsd")),
            liquidity_usd=_to_float(liquidity.get("usd")),
            fdv_usd=_to_float(best.get("fdv")),
            market_cap_usd=_to_float(best.get("marketCap")),
            volume_24h_usd=_to_float((best.get("volume") or {}).get("h24")),
            pair_address=best.get("pairAddress"),
            dex=best.get("dexId"),
            age_minutes=age_minutes,
            price_change_5m_pct=_to_float(price_change.get("m5")),
            price_change_1h_pct=_to_float(price_change.get("h1")),
            holder_count=None,  # DexScreener doesn't ship holder count
            raw={"best_pair": best, "all_pairs": pairs},
        )
        self._cache_put(
            "token_market",
            mint,
            {
                "mint": market.mint,
                "price_usd": market.price_usd,
                "liquidity_usd": market.liquidity_usd,
                "fdv_usd": market.fdv_usd,
                "market_cap_usd": market.market_cap_usd,
                "volume_24h_usd": market.volume_24h_usd,
                "pair_address": market.pair_address,
                "dex": market.dex,
                "age_minutes": market.age_minutes,
                "price_change_5m_pct": market.price_change_5m_pct,
                "price_change_1h_pct": market.price_change_1h_pct,
                "holder_count": market.holder_count,
                "raw": market.raw,
            },
        )
        return market


# ── Jupiter v6 (free, no auth) ────────────────────────────────────────────────


class JupiterClient(_BaseClient):
    """Jupiter v6 quote API — used as a sell-route honeypot probe.

    A token is a likely honeypot when buying succeeds but selling does
    not. We probe with a tiny notional: ask for a quote of N base units
    of TOKEN → wSOL. If no route is returned, flag the token.
    """

    name = "jupiter"
    default_base_url = "https://quote-api.jup.ag"

    def has_sell_route(
        self,
        mint: str,
        *,
        amount: int = 1000,
        slippage_bps: int = 500,
    ) -> bool:
        """Returns True iff Jupiter can route ``amount`` base units of
        ``mint`` into wSOL within ``slippage_bps``."""
        cached = self._cache_get("sell_route", f"{mint}_{amount}_{slippage_bps}")
        if isinstance(cached, dict):
            return bool(cached.get("ok"))

        payload = self._request_json(
            "GET",
            "/v6/quote",
            params={
                "inputMint": mint,
                "outputMint": WSOL_MINT,
                "amount": amount,
                "slippageBps": slippage_bps,
                "onlyDirectRoutes": "false",
                "asLegacyTransaction": "false",
            },
        )
        ok = (
            isinstance(payload, dict)
            and payload.get("outAmount")
            and _to_float(payload.get("outAmount"))
            and _to_float(payload.get("outAmount")) > 0
        )
        self._cache_put(
            "sell_route",
            f"{mint}_{amount}_{slippage_bps}",
            {"ok": bool(ok), "payload": payload if isinstance(payload, dict) else None},
            ttl_seconds=60,
        )
        return bool(ok)


# ── Composite provider ────────────────────────────────────────────────────────


class MemecoinDataProvider:
    """One-stop façade combining the four downstream clients.

    The rest of the pipeline (safety_check, scoring, scanner) takes a
    single ``MemecoinDataProvider`` instance so wiring tests / fakes is
    a single substitution.
    """

    def __init__(
        self,
        *,
        helius: HeliusClient | None = None,
        pumpfun: PumpFunClient | None = None,
        dexscreener: DexScreenerClient | None = None,
        jupiter: JupiterClient | None = None,
    ):
        self.helius = helius or HeliusClient()
        self.pumpfun = pumpfun or PumpFunClient()
        self.dexscreener = dexscreener or DexScreenerClient()
        self.jupiter = jupiter or JupiterClient()

    # Convenience accessors so call sites don't need to know which sub-
    # provider owns each piece of data.

    def metadata(self, mint: str) -> TokenMetadata | None:
        return self.helius.get_token_metadata(mint)

    def holders(self, mint: str, limit: int = 20) -> list[TokenHolder]:
        return self.helius.get_largest_holders(mint, limit=limit)

    def market(self, mint: str) -> TokenMarket | None:
        """Prefer DexScreener (graduated), fall back to Pump.fun (still on curve)."""
        market = self.dexscreener.get_token_market(mint)
        if market is not None and (market.liquidity_usd or 0) > 0:
            return market
        launch = self.pumpfun.get_launch(mint)
        if launch is None:
            return market
        return TokenMarket(
            mint=mint,
            price_usd=None,
            liquidity_usd=launch.liquidity_usd,
            fdv_usd=None,
            market_cap_usd=launch.market_cap_usd,
            volume_24h_usd=None,
            pair_address=None,
            dex="pump",
            age_minutes=None,
            price_change_5m_pct=None,
            price_change_1h_pct=None,
            holder_count=None,
            raw={"pumpfun": launch.raw},
        )

    def new_launches(self, limit: int = 50) -> list[PumpFunLaunch]:
        return self.pumpfun.list_new_launches(limit=limit)

    def has_sell_route(self, mint: str, *, amount: int = 1000) -> bool:
        return self.jupiter.has_sell_route(mint, amount=amount)
