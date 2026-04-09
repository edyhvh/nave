"""
data_loader — crypto OHLCV loading for the theory_refinement workflow.

Public API:
    load(coin, timeframe, start, end) -> pandas.DataFrame

On first import, scans the project-level ``data/`` directory recursively and
prints an inventory of the files it finds. Later calls to ``load`` consult
this inventory to decide whether to read a local file, gap-fill from OpenBB,
or fetch the whole range from OpenBB.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #


class DataNotFoundError(RuntimeError):
    """Raised when neither local files nor OpenBB can satisfy a load request."""


# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"

# Ticker aliases — all stored lowercase for case-insensitive matching.
COIN_ALIASES: dict[str, list[str]] = {
    "BTC": ["btc", "btcusdt", "btcusd", "btc-usd", "bitcoin", "xbt"],
    "ETH": ["eth", "ethusdt", "ethusd", "eth-usd", "ethereum"],
}

# Timeframe canonical names mapped to pandas offset aliases and minute counts.
TIMEFRAME_MINUTES: dict[str, int] = {
    "1H": 60,
    "4H": 240,
    "1D": 60 * 24,
    "1W": 60 * 24 * 7,
}

TIMEFRAME_PANDAS_RULE: dict[str, str] = {
    "1H": "1h",
    "4H": "4h",
    "1D": "1D",
    "1W": "1W",
}

# Filename tokens → canonical timeframe.
TIMEFRAME_FILENAME_TOKENS: dict[str, str] = {
    "1h": "1H",
    "60m": "1H",
    "hourly": "1H",
    "4h": "4H",
    "240m": "4H",
    "1d": "1D",
    "daily": "1D",
    "day": "1D",
    "1w": "1W",
    "weekly": "1W",
    "week": "1W",
}

COLUMN_ALIASES: dict[str, str] = {
    "date": "timestamp",
    "time": "timestamp",
    "datetime": "timestamp",
    "timestamp": "timestamp",
    "open": "open",
    "o": "open",
    "high": "high",
    "h": "high",
    "low": "low",
    "l": "low",
    "close": "close",
    "c": "close",
    "adj close": "close",
    "volume": "volume",
    "vol": "volume",
    "v": "volume",
}

REQUIRED_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]


# --------------------------------------------------------------------------- #
# Inventory
# --------------------------------------------------------------------------- #


@dataclass
class LocalFile:
    path: Path
    coin: str
    timeframe: str
    start: pd.Timestamp
    end: pd.Timestamp
    rows: int


@dataclass
class Inventory:
    # { coin: { timeframe: LocalFile } }
    files: dict[str, dict[str, LocalFile]] = field(default_factory=dict)

    def add(self, entry: LocalFile) -> None:
        self.files.setdefault(entry.coin, {})
        # Prefer the file with the longest coverage if duplicates exist.
        existing = self.files[entry.coin].get(entry.timeframe)
        if existing is None or (entry.end - entry.start) > (existing.end - existing.start):
            self.files[entry.coin][entry.timeframe] = entry

    def get(self, coin: str, timeframe: str) -> LocalFile | None:
        return self.files.get(coin, {}).get(timeframe)

    def lowest_available(self, coin: str, target_tf: str) -> LocalFile | None:
        """Return the highest-resolution local file that can resample to target_tf."""
        target_minutes = TIMEFRAME_MINUTES[target_tf]
        candidates = [
            f
            for tf, f in self.files.get(coin, {}).items()
            if TIMEFRAME_MINUTES[tf] < target_minutes
        ]
        if not candidates:
            return None
        # Pick the closest lower timeframe to avoid oversampling.
        candidates.sort(key=lambda f: TIMEFRAME_MINUTES[f.timeframe], reverse=True)
        return candidates[0]


_INVENTORY: Inventory | None = None


# --------------------------------------------------------------------------- #
# File scanning
# --------------------------------------------------------------------------- #


def _detect_coin(filename: str) -> str | None:
    name = filename.lower()
    # Sort aliases by length, longest first, so "btcusdt" beats "btc".
    for canonical, aliases in COIN_ALIASES.items():
        for alias in sorted(aliases, key=len, reverse=True):
            # Match as a contiguous token (allow separators around it).
            if re.search(rf"(?:^|[^a-z0-9]){re.escape(alias)}(?:[^a-z0-9]|$)", name):
                return canonical
    return None


def _detect_timeframe_from_filename(filename: str) -> str | None:
    name = filename.lower()
    # Sort tokens longest-first to avoid "1w" matching inside "1week".
    for token in sorted(TIMEFRAME_FILENAME_TOKENS, key=len, reverse=True):
        if re.search(rf"(?:^|[^a-z0-9]){re.escape(token)}(?:[^a-z0-9]|$)", name):
            return TIMEFRAME_FILENAME_TOKENS[token]
    return None


def _infer_timeframe_from_index(ts: pd.Series) -> str | None:
    if len(ts) < 3:
        return None
    diffs = ts.sort_values().diff().dropna()
    if diffs.empty:
        return None
    median_minutes = diffs.median().total_seconds() / 60
    # Snap to the closest canonical timeframe by log-distance.
    best, best_ratio = None, None
    for tf, minutes in TIMEFRAME_MINUTES.items():
        ratio = max(minutes, median_minutes) / min(minutes, median_minutes)
        if best_ratio is None or ratio < best_ratio:
            best, best_ratio = tf, ratio
    # Only accept if within 15% of a canonical timeframe.
    if best_ratio is not None and best_ratio <= 1.15:
        return best
    return None


def _read_raw(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path)


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    renamed = {}
    for col in df.columns:
        key = col.strip().lower()
        if key in COLUMN_ALIASES:
            renamed[col] = COLUMN_ALIASES[key]
    df = df.rename(columns=renamed)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"missing required columns: {missing}")
    df = df[REQUIRED_COLUMNS].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.dropna(subset=["timestamp"])
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"])
    df = df.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)
    return df


def _scan(data_dir: Path) -> Inventory:
    inventory = Inventory()
    if not data_dir.exists():
        print(f"[data_loader] data directory not found: {data_dir}")
        return inventory

    files = sorted(
        [p for p in data_dir.rglob("*") if p.suffix.lower() in (".csv", ".parquet")]
    )
    for path in files:
        coin = _detect_coin(path.name)
        if coin is None:
            continue
        try:
            raw = _read_raw(path)
            df = _normalize(raw)
        except Exception as exc:  # noqa: BLE001
            print(f"[data_loader] skip {path.relative_to(PROJECT_ROOT)}: {exc}")
            continue
        if df.empty:
            continue
        tf = _detect_timeframe_from_filename(path.name) or _infer_timeframe_from_index(
            df["timestamp"]
        )
        if tf is None:
            print(
                f"[data_loader] skip {path.relative_to(PROJECT_ROOT)}: "
                "cannot determine timeframe"
            )
            continue
        entry = LocalFile(
            path=path,
            coin=coin,
            timeframe=tf,
            start=df["timestamp"].iloc[0],
            end=df["timestamp"].iloc[-1],
            rows=len(df),
        )
        inventory.add(entry)

    _print_inventory(inventory)
    return inventory


def _print_inventory(inventory: Inventory) -> None:
    if not inventory.files:
        print("[data_loader] no local OHLCV files discovered under data/")
        return

    for coin in sorted(inventory.files):
        tf_map = inventory.files[coin]
        for tf in sorted(tf_map, key=lambda t: TIMEFRAME_MINUTES[t]):
            entry = tf_map[tf]
            rel = entry.path.relative_to(PROJECT_ROOT)
            start_s = entry.start.strftime("%Y-%m-%d")
            end_s = entry.end.strftime("%Y-%m-%d")
            print(
                f"[data_loader] found: {coin} {tf} — {rel} "
                f"({start_s} → {end_s}, {entry.rows} rows)"
            )
        # Note which higher timeframes will be resampled.
        available_tfs = set(tf_map.keys())
        for tf in TIMEFRAME_MINUTES:
            if tf in available_tfs:
                continue
            if inventory.lowest_available(coin, tf) is not None:
                source = inventory.lowest_available(coin, tf)
                assert source is not None
                print(
                    f"[data_loader] note: {coin} {tf} will be resampled "
                    f"from {coin} {source.timeframe}"
                )


def _get_inventory() -> Inventory:
    global _INVENTORY
    if _INVENTORY is None:
        _INVENTORY = _scan(DATA_DIR)
    return _INVENTORY


# --------------------------------------------------------------------------- #
# Resampling
# --------------------------------------------------------------------------- #


def _resample(df: pd.DataFrame, target_tf: str) -> pd.DataFrame:
    rule = TIMEFRAME_PANDAS_RULE[target_tf]
    indexed = df.set_index("timestamp")
    agg = indexed.resample(rule, label="left", closed="left").agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
    )
    agg = agg.dropna(subset=["open", "high", "low", "close"])
    return agg.reset_index()


# --------------------------------------------------------------------------- #
# OpenBB fetcher
# --------------------------------------------------------------------------- #


def _openbb_symbol(coin: str) -> str:
    return {"BTC": "BTC-USD", "ETH": "ETH-USD"}.get(coin, f"{coin}-USD")


def _openbb_interval(timeframe: str) -> str:
    return {"1H": "1h", "4H": "4h", "1D": "1d", "1W": "1W"}[timeframe]


def _fetch_openbb(
    coin: str, timeframe: str, start: pd.Timestamp, end: pd.Timestamp
) -> pd.DataFrame | None:
    try:
        from openbb import obb  # type: ignore
    except Exception as exc:  # noqa: BLE001
        print(f"[data_loader] OpenBB unavailable: {exc}")
        return None

    symbol = _openbb_symbol(coin)
    interval = _openbb_interval(timeframe)
    try:
        result: Any = obb.crypto.price.historical(  # type: ignore[attr-defined]
            symbol=symbol,
            start_date=start.strftime("%Y-%m-%d"),
            end_date=end.strftime("%Y-%m-%d"),
            interval=interval,
        )
        df = result.to_df().reset_index()
    except Exception as exc:  # noqa: BLE001
        print(f"[data_loader] OpenBB fetch failed for {coin} {timeframe}: {exc}")
        return None

    try:
        df = _normalize(df)
    except Exception as exc:  # noqa: BLE001
        print(f"[data_loader] OpenBB response normalization failed: {exc}")
        return None

    if df.empty:
        return None
    # If the caller asked for a non-native interval (e.g. 4H but OpenBB only
    # returned 1H), resample so the contract holds.
    inferred = _infer_timeframe_from_index(df["timestamp"])
    if inferred is not None and TIMEFRAME_MINUTES[inferred] < TIMEFRAME_MINUTES[timeframe]:
        df = _resample(df, timeframe)
    return df


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def _to_ts(value: Any) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    return ts


def _slice(df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    mask = (df["timestamp"] >= start) & (df["timestamp"] <= end)
    return df.loc[mask].reset_index(drop=True)


def _available_files_summary() -> str:
    inv = _get_inventory()
    if not inv.files:
        return "  (none)"
    lines = []
    for coin, tf_map in inv.files.items():
        for tf, entry in tf_map.items():
            rel = entry.path.relative_to(PROJECT_ROOT)
            lines.append(f"  - {coin} {tf}: {rel}")
    return "\n".join(lines)


def _load_local(entry: LocalFile) -> pd.DataFrame:
    return _normalize(_read_raw(entry.path))


def load(
    coin: str,
    timeframe: str,
    start: Any,
    end: Any,
) -> pd.DataFrame:
    """Load OHLCV for ``coin`` at ``timeframe`` between ``start`` and ``end``.

    Resolution order:
        1. Local file covering the full range.
        2. Local file + OpenBB gap-fill.
        3. OpenBB only.

    Raises :class:`DataNotFoundError` if none of those succeed.
    """
    coin = coin.upper()
    timeframe = timeframe.upper().replace("H", "H").replace("D", "D").replace("W", "W")
    if timeframe not in TIMEFRAME_MINUTES:
        # Accept a few common spellings.
        aliased = {
            "HOURLY": "1H",
            "DAILY": "1D",
            "WEEKLY": "1W",
            "H1": "1H",
            "H4": "4H",
            "D1": "1D",
            "W1": "1W",
        }.get(timeframe)
        if aliased is None:
            raise ValueError(f"unsupported timeframe: {timeframe}")
        timeframe = aliased

    start_ts = _to_ts(start)
    end_ts = _to_ts(end)
    if end_ts < start_ts:
        raise ValueError(f"end ({end_ts}) is before start ({start_ts})")

    inventory = _get_inventory()

    # ------------------------------------------------------------------ #
    # Find a local source for the requested timeframe (native or resampled)
    # ------------------------------------------------------------------ #
    local_df: pd.DataFrame | None = None
    local_label: str | None = None
    native = inventory.get(coin, timeframe)
    if native is not None:
        local_df = _load_local(native)
        local_label = str(native.path.relative_to(PROJECT_ROOT))
    else:
        source = inventory.lowest_available(coin, timeframe)
        if source is not None:
            base = _load_local(source)
            local_df = _resample(base, timeframe)
            local_label = (
                f"{source.path.relative_to(PROJECT_ROOT)} "
                f"(resampled {source.timeframe}→{timeframe})"
            )

    # ------------------------------------------------------------------ #
    # Case 1 / 2: local file exists
    # ------------------------------------------------------------------ #
    if local_df is not None and not local_df.empty:
        local_start = local_df["timestamp"].iloc[0]
        local_end = local_df["timestamp"].iloc[-1]

        covers_start = local_start <= start_ts
        covers_end = local_end >= end_ts

        if covers_start and covers_end:
            print(f"[{coin} {timeframe}] source: local — {local_label}")
            return _slice(local_df, start_ts, end_ts)

        # Gap fill with OpenBB for anything missing at either end.
        gap_frames: list[pd.DataFrame] = []
        gap_notes: list[str] = []

        if not covers_start:
            gap_start = start_ts
            gap_end = min(end_ts, local_start - pd.Timedelta(minutes=1))
            if gap_end >= gap_start:
                fetched = _fetch_openbb(coin, timeframe, gap_start, gap_end)
                if fetched is not None and not fetched.empty:
                    gap_frames.append(fetched)
                    gap_notes.append(
                        f"{gap_start.strftime('%Y-%m-%d')} → "
                        f"{gap_end.strftime('%Y-%m-%d')}"
                    )

        gap_frames.append(_slice(local_df, start_ts, end_ts))

        if not covers_end:
            gap_start = max(start_ts, local_end + pd.Timedelta(minutes=1))
            gap_end = end_ts
            if gap_end >= gap_start:
                fetched = _fetch_openbb(coin, timeframe, gap_start, gap_end)
                if fetched is not None and not fetched.empty:
                    gap_frames.append(fetched)
                    gap_notes.append(
                        f"{gap_start.strftime('%Y-%m-%d')} → "
                        f"{gap_end.strftime('%Y-%m-%d')}"
                    )

        merged = (
            pd.concat(gap_frames, ignore_index=True)
            .drop_duplicates("timestamp")
            .sort_values("timestamp")
            .reset_index(drop=True)
        )
        if merged.empty:
            raise DataNotFoundError(
                f"local file {local_label} did not cover {start_ts.date()} → "
                f"{end_ts.date()} and OpenBB gap-fill returned nothing"
            )

        if gap_notes:
            print(
                f"[{coin} {timeframe}] source: local ({local_label}) + "
                f"OpenBB gap-fill ({'; '.join(gap_notes)})"
            )
        else:
            print(
                f"[{coin} {timeframe}] source: local — {local_label} "
                f"(partial; OpenBB gap-fill unavailable)"
            )
        return _slice(merged, start_ts, end_ts)

    # ------------------------------------------------------------------ #
    # Case 3: no local file — OpenBB only
    # ------------------------------------------------------------------ #
    fetched = _fetch_openbb(coin, timeframe, start_ts, end_ts)
    if fetched is not None and not fetched.empty:
        print(f"[{coin} {timeframe}] source: OpenBB (no local file found)")
        return _slice(fetched, start_ts, end_ts)

    raise DataNotFoundError(
        f"no data available for {coin} {timeframe} between "
        f"{start_ts.date()} and {end_ts.date()}.\n"
        f"Available local files:\n{_available_files_summary()}"
    )


# --------------------------------------------------------------------------- #
# Run the inventory scan at import time so the first `load()` call is ready.
# --------------------------------------------------------------------------- #

_get_inventory()
