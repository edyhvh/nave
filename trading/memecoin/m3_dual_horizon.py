"""Read-only M3 dual-horizon research primitives.

This module deliberately contains no provider clients and no execution hooks.  It
operates on already archived events so that a replay can be audited, replayed,
and tested without touching a wallet or a live market endpoint.

The public corpus is useful for discovery only.  Callers must retain the raw
quality flags returned here and must not turn ``UNKNOWN`` into a loss or a gain.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import isfinite, log1p, sqrt
from statistics import median
from typing import Any, Iterable, Sequence

UTC = timezone.utc

RESOLVED = "RESOLVED"
DEAD = "DEAD"
UNEXITABLE = "UNEXITABLE"
PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
UNKNOWN = "UNKNOWN"
OUTCOME_STATUSES = frozenset({RESOLVED, DEAD, UNEXITABLE, PROVIDER_UNAVAILABLE, UNKNOWN})
TRAJECTORY_LABELS = frozenset({
    "NO_START", "FAST_BURST", "FALSE_RUNNER", "SUSTAINED_RUNNER",
    "MINOR_PUMP", "SLOW_BLEED", "UNKNOWN",
})

SYSTEM_PROGRAM = "BwWK17cbHxwWBKZKUYvzxLcNQ1YVyaFezduWbtm2de6s"  # corpus-documented contamination address
SYNTHETIC_POOLS = frozenset({"synthetic_graduation_queue", "backfilled_from_pumpswap_trade"})
HORIZONS_SECONDS = {
    "30s": 30,
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "10m": 600,
    "30m": 1800,
    "60m": 3600,
    "2h": 7200,
    "4h": 14400,
    "8h": 28800,
    "12h": 43200,
    "24h": 86400,
    "48h": 172800,
    "72h": 259200,
}


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _time(value: Any) -> datetime | None:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000 if value > 10_000_000_000 else value, UTC)
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _first(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value is not None and value != "":
            return value
    return None


def _boolean(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str) and value.strip().lower() in {"true", "false"}:
        return value.strip().lower() == "true"
    return None


def _side(row: dict[str, Any]) -> str | None:
    value = str(_first(row, "side", "direction", "trade_side") or "").lower()
    if value in {"buy", "sell"}:
        return value
    flag = _first(row, "is_buy", "isBuy")
    return "buy" if flag is True else "sell" if flag is False else None


def _wallet(row: dict[str, Any]) -> str | None:
    value = _first(row, "trader", "wallet", "user", "buyer", "seller", "owner")
    return str(value) if value else None


def event_timestamp(row: dict[str, Any]) -> datetime | None:
    return _time(_first(row, "event_ts", "timestamp", "time", "created_at", "createdAt", "blockTime"))


def classify_protocol_state(row: dict[str, Any]) -> dict[str, Any]:
    """Return explicit protocol state; absence is ``UNKNOWN``, never false."""
    extensions = _first(row, "token2022_extensions", "token_2022_extensions", "extensions")
    if isinstance(extensions, str):
        extensions = [extensions]
    if extensions is not None and not isinstance(extensions, list):
        extensions = [str(extensions)]
    venue = _first(row, "venue", "dex", "platform")
    pool = _first(row, "pool_address", "poolAddress", "pair_address", "pairAddress")
    protocol_generated = _boolean(_first(row, "protocol_generated", "is_protocol_trade"))
    mayhem = _boolean(_first(row, "mayhem_mode", "mayhem", "is_mayhem"))
    return {
        "mayhem_mode": mayhem,
        "mayhem_agent_state": _first(row, "mayhem_agent_state", "agent_state"),
        "cashback_enabled": _first(row, "cashback_enabled", "cashback"),
        "tokenized_agent": _first(row, "tokenized_agent", "automated_buyback"),
        "boost": _first(row, "boost", "boost_active", "boost_buy_and_burn"),
        "protocol_generated": protocol_generated,
        "quote_asset": _first(row, "quote_asset", "quote_mint", "quoteSymbol"),
        "launch_variant": _first(row, "launch_variant", "create_variant", "instruction_variant"),
        "token2022": bool(extensions) if extensions is not None else None,
        "token2022_extensions": extensions,
        "venue": venue,
        "pool_address": pool,
        "canonical_pool": bool(pool and pool not in SYNTHETIC_POOLS)
        if pool is not None
        else None,
        "migration_state": _first(row, "migration_state", "graduation_state"),
        "fee_bps": _number(_first(row, "fee_bps", "lp_fee_bps", "protocol_fee_bps")),
    }


def clean_trade(row: dict[str, Any]) -> dict[str, Any]:
    """Annotate a trade for safe research aggregation.

    Values are not repaired.  A corrupted SOL amount is excluded from SOL
    computations, while a missing amount remains explicit missingness.
    """
    side = _side(row)
    wallet = _wallet(row)
    token_amount = _number(_first(row, "token_amount", "tokenAmount", "amount_tokens"))
    sol_amount = _number(_first(row, "sol_amount", "solAmount", "quote_amount"))
    price_sol = _number(_first(row, "price_sol", "priceSol"))
    ratio = sol_amount / (token_amount * price_sol) if sol_amount and token_amount and price_sol else None
    quality: list[str] = []
    if wallet == SYSTEM_PROGRAM:
        quality.append("SYSTEM_PROGRAM_WALLET")
    if sol_amount is None or price_sol is None:
        quality.append("SOL_PRICE_MISSING")
    elif token_amount is None or token_amount <= 0 or ratio is None or not 0.01 <= ratio <= 100:
        quality.append("SOL_AMOUNT_SUSPECT")
    curve_pct = _number(_first(row, "curve_pct_depleted", "curve_pct_depleted_eob"))
    if curve_pct is not None and not 0 <= curve_pct <= 100:
        quality.append("CURVE_DEPLETION_OUT_OF_RANGE")
    return {
        **row,
        "event_ts": event_timestamp(row),
        "side": side,
        "wallet": wallet,
        "protocol_state": classify_protocol_state(row),
        "sol_amount_valid": not any(flag in quality for flag in {"SOL_PRICE_MISSING", "SOL_AMOUNT_SUSPECT"}),
        "wallet_valid": wallet is not None and wallet != SYSTEM_PROGRAM,
        "quality_flags": quality,
    }


def mayhem_supply(row: dict[str, Any]) -> float | None:
    """Select protocol-consistent supply, preferring corrected corpus fields."""
    corrected = _number(_first(row, "supply_corrected", "total_supply_corrected"))
    if corrected and corrected > 0:
        return corrected
    explicit = _number(_first(row, "total_supply", "supply", "token_supply"))
    if explicit and explicit > 0:
        return explicit
    mayhem = _boolean(_first(row, "mayhem_mode", "mayhem", "is_mayhem"))
    return 2_000_000_000.0 if mayhem is True else 1_000_000_000.0 if mayhem is False else None


def market_cap_from_price(price: float | None, supply_row: dict[str, Any]) -> float | None:
    supply = mayhem_supply(supply_row)
    return price * supply if price is not None and supply else None


@dataclass(frozen=True)
class Outcome:
    status: str
    observed_ts: datetime | None = None
    mark_price: float | None = None
    gross_return_pct: float | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.status not in OUTCOME_STATUSES:
            raise ValueError(f"invalid outcome status: {self.status}")
        if self.status != RESOLVED and self.gross_return_pct is not None:
            raise ValueError("non-resolved outcomes cannot have a return")


def resolve_outcome(
    *,
    entry_ts: datetime,
    entry_price: float | None,
    events: Sequence[dict[str, Any]],
    horizon_seconds: int,
    coverage_end: datetime,
    provider_outage: bool = False,
    pool_disappeared: bool = False,
    route_available: bool | None = True,
) -> Outcome:
    """Resolve one horizon without turning right censoring into death."""
    target = entry_ts + timedelta(seconds=horizon_seconds)
    if provider_outage:
        return Outcome(PROVIDER_UNAVAILABLE, reason="provider_outage")
    if coverage_end < target:
        return Outcome(UNKNOWN, reason="right_censored_at_collection_end")
    if pool_disappeared:
        return Outcome(DEAD, reason="verified_pool_disappeared")
    if route_available is False:
        return Outcome(UNEXITABLE, reason="historical_exit_route_unavailable")
    future = [e for e in events if (event_timestamp(e) or entry_ts) >= target]
    marked = next((e for e in future if _number(_first(e, "price_usd", "priceUsd", "price")) is not None), None)
    mark = _number(_first(marked or {}, "price_usd", "priceUsd", "price"))
    if entry_price is None or entry_price <= 0 or mark is None:
        return Outcome(UNKNOWN, reason="missing_entry_or_horizon_price")
    return Outcome(RESOLVED, event_timestamp(marked), mark, (mark / entry_price - 1) * 100)


def _event_price(event: dict[str, Any]) -> float | None:
    direct = _number(_first(event, "price_usd", "priceUsd", "price", "token_price"))
    if direct is not None and direct >= 0:
        return direct
    token = _number(_first(event, "token_amount", "tokenAmount", "amount_tokens"))
    sol = _number(_first(event, "sol_amount", "solAmount", "quote_amount"))
    return sol / token if sol is not None and token and token > 0 else None


def _eligible_wallet(event: dict[str, Any]) -> bool:
    clean = clean_trade(event)
    return clean["wallet_valid"] and not clean["protocol_state"]["protocol_generated"]


def build_trajectory(
    mint: str,
    events: Iterable[dict[str, Any]],
    *,
    launch_ts: datetime | None = None,
    migration_ts: datetime | None = None,
    coverage_end: datetime | None = None,
) -> dict[str, Any]:
    """Build point-in-time interval features from event-ordered trades."""
    normalized = [clean_trade(e) for e in events if event_timestamp(e) is not None]
    normalized.sort(key=lambda e: (e["event_ts"], _number(_first(e, "provider_sequence", "sequence")) or 0))
    if not normalized:
        return {"mint": mint, "intervals": {}, "status": UNKNOWN, "missingness": ["NO_EVENTS"]}
    first_ts = launch_ts or normalized[0]["event_ts"]
    coverage = coverage_end or normalized[-1]["event_ts"]
    buyers: set[str] = set()
    sellers: set[str] = set()
    buyer_first_seen: dict[str, datetime] = {}
    rows: dict[str, dict[str, Any]] = {}
    previous_seconds = 0
    for label, seconds in HORIZONS_SECONDS.items():
        until = first_ts + timedelta(seconds=seconds)
        visible = [e for e in normalized if e["event_ts"] <= until]
        eligible = [
            e for e in visible
            if e["wallet_valid"] and e["sol_amount_valid"] and not e["protocol_state"]["protocol_generated"]
        ]
        buys = [e for e in eligible if e["side"] == "buy"]
        sells = [e for e in eligible if e["side"] == "sell"]
        buyers = {e["wallet"] for e in buys if e["wallet"]}
        sellers = {e["wallet"] for e in sells if e["wallet"]}
        for e in buys:
            buyer_first_seen.setdefault(e["wallet"], e["event_ts"])
        new_buyers = {
            w for w, ts in buyer_first_seen.items()
            if first_ts + timedelta(seconds=previous_seconds) < ts <= until
        }
        prices = [_event_price(e) for e in visible]
        prices = [p for p in prices if p is not None and p > 0]
        buy_sol = sum(_number(_first(e, "sol_amount", "solAmount", "quote_amount")) or 0 for e in buys)
        sell_sol = sum(_number(_first(e, "sol_amount", "solAmount", "quote_amount")) or 0 for e in sells)
        buy_usd = sum(_number(_first(e, "notional_usd", "notionalUsd")) or 0 for e in buys)
        sell_usd = sum(_number(_first(e, "notional_usd", "notionalUsd")) or 0 for e in sells)
        liquidity = _number(_first(visible[-1], "liquidity_usd", "liquidityUsd")) if visible else None
        market_cap = _number(_first(visible[-1], "market_cap_usd", "marketCapUsd")) if visible else None
        if market_cap is None and prices:
            market_cap = market_cap_from_price(prices[-1], visible[-1])
        buyer_amounts: dict[str, float] = defaultdict(float)
        cluster_amounts: dict[str, float] = defaultdict(float)
        for e in buys:
            amount = _number(_first(e, "notional_usd", "notionalUsd"))
            if amount is None:
                continue
            if e["wallet"]:
                buyer_amounts[e["wallet"]] += amount
            cluster = str(_first(e, "economic_cluster", "cluster_id", "bundle_cluster_id") or e["wallet"])
            if cluster:
                cluster_amounts[cluster] += amount
        largest_buyer_share = max(buyer_amounts.values(), default=0) / buy_usd if buy_usd else None
        largest_cluster_share = max(cluster_amounts.values(), default=0) / buy_usd if buy_usd else None
        prior_prices = prices[:-1] or prices
        prior_liquidity = [
            _number(_first(e, "liquidity_usd", "liquidityUsd"))
            for e in visible
        ]
        prior_liquidity = [value for value in prior_liquidity if value is not None and value > 0]
        price_peak = max(prior_prices, default=None)
        liquidity_peak = max(prior_liquidity, default=None)
        rows[label] = {
            "observed_ts": until.isoformat(),
            "price": prices[-1] if prices else None,
            "quoted_market_cap": market_cap,
            "liquidity_usd": liquidity,
            "buy_volume_sol": buy_sol,
            "sell_volume_sol": sell_sol,
            "net_flow_sol": buy_sol - sell_sol,
            "cumulative_real_volume_sol": buy_sol + sell_sol,
            "buy_volume_usd": buy_usd or None,
            "sell_volume_usd": sell_usd or None,
            "net_flow_usd": buy_usd - sell_usd if buy_usd or sell_usd else None,
            "cumulative_real_volume_usd": buy_usd + sell_usd or None,
            "unique_buyers": len(buyers),
            "unique_sellers": len(sellers),
            "new_buyers": len(new_buyers),
            "returning_buyers": max(0, len(buyers) - len(new_buyers)),
            "cluster_adjusted_buyers": len({
                str(_first(e, "economic_cluster", "cluster_id", "bundle_cluster_id") or e["wallet"])
                for e in buys if e["wallet"]
            }),
            "largest_buyer_share": largest_buyer_share,
            "largest_cluster_share": largest_cluster_share,
            "creator_linked_trade_count": sum(bool(e.get("creator_linked")) for e in eligible),
            "price_drawdown": (prices[-1] / price_peak - 1) if price_peak else None,
            "liquidity_drawdown": (liquidity / liquidity_peak - 1) if liquidity and liquidity_peak else None,
            "reserve_base": _number(_first(visible[-1], "reserve_base", "reserveBase")) if visible else None,
            "reserve_quote": _number(_first(visible[-1], "reserve_quote", "reserveQuote")) if visible else None,
            "protocol_generated_buy_volume_sol": sum(
                _number(_first(e, "sol_amount", "solAmount", "quote_amount")) or 0
                for e in visible
                if e["side"] == "buy" and e["wallet_valid"] and e["sol_amount_valid"]
                and e["protocol_state"]["protocol_generated"]
            ),
            "coverage": RESOLVED if coverage >= until else UNKNOWN,
        }
        previous_seconds = seconds
    return {
        "mint": mint,
        "launch_ts": first_ts.isoformat(),
        "migration_ts": migration_ts.isoformat() if migration_ts else None,
        "coverage_end": coverage.isoformat(),
        "intervals": rows,
        "status": RESOLVED,
        "protocol_state": normalized[0]["protocol_state"],
        "quality_flags": sorted({flag for e in normalized for flag in e["quality_flags"]}),
    }


def trajectory_vector(trajectory: dict[str, Any], labels: Sequence[str] = ("5m", "30m", "4h", "24h", "48h")) -> list[float] | None:
    """Small interpretable normalized vector for exploratory clustering only."""
    values: list[float] = []
    intervals = trajectory.get("intervals", {})
    base = intervals.get("5m", {}).get("price")
    if not base:
        return None
    for label in labels:
        row = intervals.get(label, {})
        price = row.get("price")
        liq = row.get("liquidity_usd")
        values.extend([
            log1p(max(price / base - 1, -0.999)) if price else 0.0,
            log1p(max((row.get("cumulative_real_volume_usd") or row.get("cumulative_real_volume_sol") or 0), 0)),
            log1p(max((row.get("unique_buyers") or 0), 0)),
            log1p(max((liq or 0), 0)),
        ])
    return values


def trajectory_quality(trajectory: dict[str, Any], *, notionals: Sequence[float] = (100, 500, 1000)) -> dict[str, Any]:
    """Derive market-quality diagnostics; peak quoted value is never sufficient."""
    intervals = trajectory.get("intervals", {})
    peak = max((row.get("quoted_market_cap") or 0 for row in intervals.values()), default=0)
    peak_row = max(intervals.values(), key=lambda row: row.get("quoted_market_cap") or 0, default={})
    liquidity = peak_row.get("liquidity_usd")
    return {
        "peak_quoted_market_cap": peak or None,
        "peak_liquidity_usd": liquidity,
        "peak_market_cap_to_liquidity": peak / liquidity if peak and liquidity else None,
        "quality_by_horizon": {
            label: {
                "liquidity_to_market_cap": (
                    row.get("liquidity_usd") / row["quoted_market_cap"]
                    if row.get("liquidity_usd") and row.get("quoted_market_cap") else None
                ),
                "volume_to_market_cap": (
                    (row.get("cumulative_real_volume_usd") or row.get("cumulative_real_volume_sol")) /
                    row["quoted_market_cap"]
                    if (row.get("cumulative_real_volume_usd") or row.get("cumulative_real_volume_sol"))
                    and row.get("quoted_market_cap") else None
                ),
                "new_buyer_share": (
                    row.get("new_buyers") / row["unique_buyers"]
                    if row.get("unique_buyers") else None
                ),
                "protocol_buy_share": (
                    row.get("protocol_generated_buy_volume_sol") /
                    (row.get("buy_volume_sol") + row.get("protocol_generated_buy_volume_sol"))
                    if row.get("buy_volume_sol") is not None and
                    row.get("protocol_generated_buy_volume_sol") is not None and
                    (row.get("buy_volume_sol") + row.get("protocol_generated_buy_volume_sol")) > 0 else None
                ),
            }
            for label, row in intervals.items()
        },
        "fixed_notional_exit_values": {str(n): None for n in notionals},
        "market_cap_alone_is_qualification": False,
    }


def classify_trajectory(
    trajectory: dict[str, Any], *, peak_return_threshold: float = 1.0,
    retracement_threshold: float = 0.5, runner_horizons: Sequence[str] = ("24h", "48h"),
) -> str:
    """Apply a predeclared descriptive taxonomy after trajectory discovery.

    This is intentionally conservative: incomplete horizons return UNKNOWN and
    a large peak without market-quality evidence cannot become a runner.
    """
    intervals = trajectory.get("intervals", {})
    first = intervals.get("5m", {}).get("price")
    if not first:
        return "NO_START"
    complete = [intervals.get(h, {}) for h in runner_horizons]
    if any(row.get("coverage") != RESOLVED for row in complete):
        return "UNKNOWN"
    prices = [row.get("price") for row in intervals.values() if row.get("price")]
    if not prices:
        return "NO_START"
    peak = max(prices)
    peak_return = peak / first - 1
    last = complete[-1].get("price")
    if peak_return >= peak_return_threshold and last is not None and last / peak - 1 <= -retracement_threshold:
        return "FAST_BURST"
    quality = trajectory_quality(trajectory)["quality_by_horizon"]
    sustained = all(
        row.get("price") is not None and
        quality.get(h, {}).get("liquidity_to_market_cap") is not None and
        (row.get("new_buyers") or 0) > 0
        for h, row in zip(runner_horizons, complete)
    )
    if sustained and peak_return >= peak_return_threshold:
        return "SUSTAINED_RUNNER"
    if peak_return >= peak_return_threshold and any(
        quality.get(h, {}).get("liquidity_to_market_cap") is None for h in runner_horizons
    ):
        return "FALSE_RUNNER"
    return "MINOR_PUMP" if peak_return > 0.2 else "SLOW_BLEED"


def simulate_fast_burst_exit(
    entry_ts: datetime, entry_price: float, events: Sequence[dict[str, Any]], *,
    target_pct: float = 0.20, stop_pct: float = -0.15, time_stop_seconds: int = 3600,
) -> dict[str, Any]:
    """Simulate the legacy comparable head with stop-first ambiguity handling."""
    target = entry_price * (1 + target_pct)
    stop = entry_price * (1 + stop_pct)
    end = entry_ts + timedelta(seconds=time_stop_seconds)
    for event in sorted(events, key=lambda e: event_timestamp(e) or end):
        ts = event_timestamp(event)
        price = _event_price(event)
        if ts is None or price is None or ts < entry_ts or ts > end:
            continue
        # One event/bar has no order information; conservative stop-first.
        if price <= stop:
            return {"exit_reason": "STOP", "exit_ts": ts, "gross_return_pct": stop_pct * 100}
        if price >= target:
            return {"exit_reason": "TARGET", "exit_ts": ts, "gross_return_pct": target_pct * 100}
    return {"exit_reason": "TIME_STOP", "exit_ts": end, "gross_return_pct": None}


def runner_exit_families(
    entry_ts: datetime, entry_price: float, events: Sequence[dict[str, Any]], *,
    fixed_horizons: Sequence[int] = (4 * 3600, 8 * 3600, 24 * 3600, 48 * 3600),
    trailing_drawdowns: Sequence[float] = (0.20, 0.30, 0.40),
) -> dict[str, Any]:
    """Evaluate predetermined runner exits without selecting a best rule."""
    ordered = sorted(((event_timestamp(e), _event_price(e)) for e in events), key=lambda x: x[0] or entry_ts)
    ordered = [(ts, price) for ts, price in ordered if ts and price and ts >= entry_ts]
    result: dict[str, Any] = {"fixed": {}, "trailing": {}}
    for seconds in fixed_horizons:
        target = entry_ts + timedelta(seconds=seconds)
        mark = next((price for ts, price in ordered if ts >= target), None)
        result["fixed"][f"{seconds}s"] = (mark / entry_price - 1) * 100 if mark else None
    for drawdown in trailing_drawdowns:
        high = entry_price
        exit_price = None
        for ts, price in ordered:
            high = max(high, price)
            if price <= high * (1 - drawdown):
                exit_price = price
                break
        result["trailing"][str(drawdown)] = (exit_price / entry_price - 1) * 100 if exit_price else None
    return result


def entry_timing_bucket(*, age_seconds: float | None, curve_progress: float | None, market_cap_fraction_of_peak: float | None) -> str:
    """Classify entry timing descriptively; no outcome data is used."""
    if age_seconds is None or curve_progress is None or market_cap_fraction_of_peak is None:
        return "UNKNOWN"
    if age_seconds <= 30 and curve_progress <= 0.25 and market_cap_fraction_of_peak <= 0.10:
        return "ULTRA_EARLY"
    if age_seconds <= 300 and curve_progress <= 0.50 and market_cap_fraction_of_peak <= 0.30:
        return "EARLY"
    if market_cap_fraction_of_peak <= 0.70:
        return "MID"
    return "LATE"


def leave_one_participant_out(results: Sequence[dict[str, Any]], participant_key: str = "participant") -> list[dict[str, Any]]:
    """Return robustness summaries with each participant removed once."""
    participants = sorted({row.get(participant_key) for row in results if row.get(participant_key)})
    summaries = []
    for participant in participants:
        kept = [row for row in results if row.get(participant_key) != participant]
        returns = [_number(row.get("net_return_pct")) for row in kept]
        returns = [value for value in returns if value is not None]
        summaries.append({
            "removed_participant": participant,
            "n": len(returns),
            "mean_net_return_pct": sum(returns) / len(returns) if returns else None,
        })
    return summaries


def _distance(a: Sequence[float], b: Sequence[float]) -> float:
    return sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def cluster_trajectories(trajectories: Sequence[dict[str, Any]], k: int) -> dict[str, Any]:
    """Deterministic, feature-based k-means for discovery, not optimization."""
    if not 2 <= k <= 6:
        raise ValueError("k must be between 2 and 6")
    items = [(t, trajectory_vector(t)) for t in trajectories]
    items = [(t, v) for t, v in items if v is not None]
    if len(items) < k:
        return {"k": k, "status": "INSUFFICIENT_DATA", "assignments": []}
    vectors = [v for _, v in items]
    centers = [vectors[(i * len(vectors)) // k] for i in range(k)]
    assignments = [0] * len(vectors)
    for _ in range(30):
        new_assignments = [min(range(k), key=lambda j: _distance(v, centers[j])) for v in vectors]
        if new_assignments == assignments:
            break
        assignments = new_assignments
        for j in range(k):
            members = [v for v, a in zip(vectors, assignments) if a == j]
            if members:
                centers[j] = [sum(row[d] for row in members) / len(members) for d in range(len(members[0]))]
    sizes = Counter(assignments)
    within = sum(_distance(v, centers[a]) for v, a in zip(vectors, assignments)) / len(vectors)
    return {
        "k": k,
        "status": "OK",
        "n": len(vectors),
        "cluster_sizes": dict(sorted(sizes.items())),
        "within_cluster_distance": within,
        "assignments": [{"mint": t["mint"], "cluster": a} for (t, _), a in zip(items, assignments)],
        "centers": centers,
    }


def chronological_splits(
    timestamps: Sequence[datetime], *, horizon_seconds: int = 0, development: float = 0.6, validation: float = 0.2
) -> dict[str, datetime]:
    """Return chronological boundaries with a purge embargo after development."""
    ordered = sorted(timestamps)
    if not ordered or not (0 < development < 1) or not (0 < validation < 1) or development + validation >= 1:
        raise ValueError("timestamps and fractions are invalid")
    dev = ordered[min(len(ordered) - 1, max(0, int(len(ordered) * development) - 1))]
    val = ordered[min(len(ordered) - 1, max(0, int(len(ordered) * (development + validation)) - 1))]
    return {
        "development_end": dev,
        "validation_start": dev + timedelta(seconds=horizon_seconds),
        "validation_end": val,
        "holdout_start": val + timedelta(seconds=horizon_seconds),
        "holdout_end": ordered[-1],
    }


def assign_split(ts: datetime, boundaries: dict[str, datetime]) -> str:
    if ts <= boundaries["development_end"]:
        return "development"
    if ts <= boundaries["validation_end"]:
        return "validation"
    return "holdout" if ts >= boundaries["holdout_start"] else "purged"


def detect_sell_shocks(events: Sequence[dict[str, Any]], *, multiplier: float = 3.0, min_history: int = 3) -> list[dict[str, Any]]:
    """Detect relative sell shocks using only earlier valid sells."""
    ordered = sorted((clean_trade(e) for e in events), key=lambda e: e["event_ts"] or datetime.min.replace(tzinfo=UTC))
    history: list[float] = []
    shocks: list[dict[str, Any]] = []
    for event in ordered:
        amount = _number(_first(event, "sol_amount", "solAmount", "quote_amount"))
        if event["side"] != "sell" or not event["sol_amount_valid"] or amount is None:
            continue
        baseline = median(history) if history else None
        if baseline and len(history) >= min_history and amount >= baseline * multiplier:
            shocks.append({
                "event_ts": event["event_ts"],
                "sell_amount": amount,
                "prior_median_sell_amount": baseline,
                "relative_size": amount / baseline,
                "protocol_generated": event["protocol_state"]["protocol_generated"],
            })
        history.append(amount)
    return shocks


def execution_price_constant_product(
    *, input_amount: float, reserve_in: float, reserve_out: float, fee_bps: float = 30
) -> float | None:
    """Return output amount for a constant-product swap, or ``None`` if invalid."""
    if min(input_amount, reserve_in, reserve_out) <= 0 or fee_bps < 0 or fee_bps >= 10_000:
        return None
    effective = input_amount * (1 - fee_bps / 10_000)
    return reserve_out * effective / (reserve_in + effective)


def executable_return_pct(
    *, entry_price: float, exit_price: float, notional_usd: float, liquidity_usd: float,
    fee_bps_round_trip: float, impact_bps_round_trip: float, max_liquidity_fraction: float = 0.0025,
) -> float | None:
    """Simple paper execution haircut with an explicit size gate."""
    if min(entry_price, exit_price, notional_usd, liquidity_usd) <= 0:
        return None
    if notional_usd > liquidity_usd * max_liquidity_fraction:
        return None
    haircut = (fee_bps_round_trip + impact_bps_round_trip) / 10_000
    return ((exit_price / entry_price) * (1 - haircut) - 1) * 100


@dataclass(frozen=True)
class ParticipantProfile:
    participant: str
    prior_episodes: int
    prior_eligible: int
    burst_hits: int
    runner_hits: int
    realized_wins: int
    realized_losses: int
    median_realized_return: float | None
    discovery_hit_rate: float
    runner_rate: float
    uncertainty_low: float
    uncertainty_high: float

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def reconstruct_episode(
    participant: str, mint: str, trades: Sequence[dict[str, Any]], *, fee_bps: float = 30
) -> dict[str, Any]:
    """FIFO realized P&L; open inventory is never marked as realized profit."""
    inventory: list[list[float]] = []  # quantity, cost per unit
    realized = 0.0
    buys = sells = 0
    for raw in sorted((clean_trade(t) for t in trades if _wallet(t) == participant), key=lambda e: e["event_ts"] or datetime.min.replace(tzinfo=UTC)):
        price = _event_price(raw)
        qty = _number(_first(raw, "token_amount", "tokenAmount", "amount_tokens"))
        if not price or not qty or raw["side"] not in {"buy", "sell"}:
            continue
        if raw["side"] == "buy":
            buys += 1
            inventory.append([qty, price * (1 + fee_bps / 10_000)])
            continue
        sells += 1
        proceeds = price * (1 - fee_bps / 10_000)
        remaining = qty
        while remaining > 0 and inventory:
            lot_qty, cost = inventory[0]
            used = min(remaining, lot_qty)
            realized += used * (proceeds - cost)
            remaining -= used
            lot_qty -= used
            if lot_qty <= 1e-12:
                inventory.pop(0)
            else:
                inventory[0][0] = lot_qty
    return {
        "participant": participant, "mint": mint, "buy_count": buys, "sell_count": sells,
        "realized_pnl": realized, "remaining_inventory": sum(row[0] for row in inventory),
        "state": "REALIZED_WIN" if realized > 0 and not inventory else "PARTIAL_REALIZATION" if realized > 0 else "OPEN / UNKNOWN" if inventory else "REALIZED_LOSS",
    }


def build_participant_profile(
    participant: str, episodes: Sequence[dict[str, Any]], *, as_of: datetime
) -> ParticipantProfile:
    """Use only completed episode outcomes strictly before the signal timestamp."""
    prior = [e for e in episodes if _time(e.get("outcome_ts")) and _time(e["outcome_ts"]) < as_of and e.get("participant") == participant]
    eligible = [e for e in prior if e.get("eligible", True)]
    burst = [e for e in eligible if e.get("outcome") == "FAST_BURST"]
    runner = [e for e in eligible if e.get("outcome") == "SUSTAINED_RUNNER"]
    realized = [_number(e.get("realized_return_pct")) for e in eligible]
    realized = [v for v in realized if v is not None]
    wins = sum(v > 0 for v in realized)
    losses = sum(v <= 0 for v in realized)
    # Laplace smoothing is descriptive shrinkage, not a claim of calibrated probability.
    hit_rate = (len(burst) + 1) / (len(eligible) + 2)
    runner_rate = (len(runner) + 1) / (len(eligible) + 2)
    uncertainty = 1.96 / sqrt(max(1, len(eligible)))
    return ParticipantProfile(
        participant, len(prior), len(eligible), len(burst), len(runner), wins, losses,
        median(realized) if realized else None, hit_rate, runner_rate,
        max(0.0, hit_rate - uncertainty), min(1.0, hit_rate + uncertainty),
    )


def convergence_features(entries: Sequence[dict[str, Any]], *, window_seconds: int = 60) -> dict[str, Any]:
    """Count distinct economic clusters, not raw wallet addresses."""
    timestamps = [event_timestamp(e) for e in entries]
    timestamps = [t for t in timestamps if t]
    if not timestamps:
        return {"informative_participants": 0, "independent_clusters": 0, "window_seconds": window_seconds}
    start = min(timestamps)
    selected = [e for e in entries if (event_timestamp(e) or start) <= start + timedelta(seconds=window_seconds)]
    clusters = {str(_first(e, "economic_cluster", "cluster_id", "bundle_cluster_id") or _wallet(e)) for e in selected}
    return {
        "informative_participants": len({_wallet(e) for e in selected if _wallet(e)}),
        "independent_clusters": len({c for c in clusters if c and c != "None"}),
        "window_seconds": window_seconds,
    }
