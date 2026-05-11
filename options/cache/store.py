"""Parquet + sqlite cache manager for options chain snapshots."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from options.config import OptionsConfig
from options.models import CacheSnapshotMetadata


class OptionsCacheStore:
    """Persist and retrieve normalized options chain snapshots."""

    def __init__(self, config: OptionsConfig):
        self.config = config
        self._ensure_dirs()
        self._ensure_schema()

    def _ensure_dirs(self) -> None:
        self.config.cache_root.mkdir(parents=True, exist_ok=True)
        self.config.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self.config.charts_dir.mkdir(parents=True, exist_ok=True)
        self.config.reports_dir.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        self.config.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.config.sqlite_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS option_chain_cache (
                    ticker TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    snapshot_path TEXT NOT NULL,
                    underlying_price REAL NOT NULL,
                    expirations_json TEXT NOT NULL,
                    row_count INTEGER NOT NULL,
                    avg_iv REAL,
                    source TEXT NOT NULL,
                    PRIMARY KEY (ticker, fetched_at)
                )
                """
            )
            # Backward-compatible migration for existing local sqlite files.
            columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(option_chain_cache)").fetchall()
            }
            if "avg_iv" not in columns:
                conn.execute(
                    "ALTER TABLE option_chain_cache ADD COLUMN avg_iv REAL")
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_option_chain_cache_ticker_fetched
                ON option_chain_cache(ticker, fetched_at)
                """
            )

    def _cache_fresh_threshold(self) -> datetime:
        return datetime.now(timezone.utc) - timedelta(minutes=self.config.cache_ttl_minutes)

    def latest_snapshot(self, ticker: str) -> CacheSnapshotMetadata | None:
        threshold = self._cache_fresh_threshold().isoformat()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT ticker, fetched_at, snapshot_path, underlying_price, expirations_json, row_count, source
                FROM option_chain_cache
                WHERE ticker = ? AND fetched_at >= ?
                ORDER BY fetched_at DESC
                LIMIT 1
                """,
                (ticker.upper(), threshold),
            ).fetchone()
        if row is None:
            return None

        fetched_at = datetime.fromisoformat(row["fetched_at"])
        expirations = [
            part for part in row["expirations_json"].split(",") if part]
        return CacheSnapshotMetadata(
            ticker=row["ticker"],
            fetched_at=fetched_at,
            path=row["snapshot_path"],
            underlying_price=float(row["underlying_price"]),
            expirations=expirations,
            row_count=int(row["row_count"]),
            source=row["source"],
        )

    def load_snapshot_frame(self, metadata: CacheSnapshotMetadata) -> pd.DataFrame:
        path = Path(metadata.path)
        if path.is_dir():
            # Backward compatibility: if an old cache row accidentally points to
            # a directory, pick the latest ticker-specific parquet only.
            candidates = sorted(
                path.glob(f"{metadata.ticker.upper()}_*.parquet"),
                key=lambda item: item.stat().st_mtime,
                reverse=True,
            )
            if not candidates:
                return pd.DataFrame()
            path = candidates[0]
        if not path.exists() or path.suffix.lower() != ".parquet":
            return pd.DataFrame()
        frame = pd.read_parquet(path)
        if "ticker" not in frame.columns:
            return frame
        ticker_col = frame["ticker"].astype("string").str.upper()
        filtered = frame[ticker_col == metadata.ticker.upper()].copy()
        return filtered.reset_index(drop=True)

    def iv_history(self, ticker: str, *, lookback_days: int) -> pd.Series:
        """Return average IV history from cache metadata for the ticker."""
        threshold = (datetime.now(timezone.utc) -
                     timedelta(days=max(1, lookback_days))).isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT fetched_at, avg_iv
                FROM option_chain_cache
                WHERE ticker = ?
                  AND fetched_at >= ?
                  AND avg_iv IS NOT NULL
                ORDER BY fetched_at ASC
                """,
                (ticker.upper(), threshold),
            ).fetchall()
        if not rows:
            return pd.Series(dtype=float)
        values = [float(row["avg_iv"])
                  for row in rows if row["avg_iv"] is not None]
        return pd.Series(values, dtype=float)

    def persist_snapshot(
        self,
        *,
        ticker: str,
        frame: pd.DataFrame,
        underlying_price: float,
        expirations: list[str],
        source: str,
    ) -> CacheSnapshotMetadata:
        now = datetime.now(timezone.utc)
        stamp = now.strftime("%Y%m%d_%H%M%S")
        filename = f"{ticker.upper()}_{stamp}.parquet"
        path = self.config.snapshots_dir / filename
        frame.to_parquet(path, index=False)

        metadata = CacheSnapshotMetadata(
            ticker=ticker.upper(),
            fetched_at=now,
            path=str(path),
            underlying_price=float(underlying_price),
            expirations=expirations,
            row_count=len(frame),
            source=source,
        )
        iv_col = frame["implied_volatility"] if "implied_volatility" in frame.columns else pd.Series(
            dtype=float)
        avg_iv = pd.to_numeric(iv_col, errors="coerce").dropna().mean()
        avg_iv_value = float(avg_iv) if pd.notna(avg_iv) else None

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO option_chain_cache(
                    ticker, fetched_at, snapshot_path, underlying_price,
                    expirations_json, row_count, avg_iv, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    metadata.ticker,
                    metadata.fetched_at.isoformat(),
                    metadata.path,
                    metadata.underlying_price,
                    ",".join(metadata.expirations),
                    metadata.row_count,
                    avg_iv_value,
                    metadata.source,
                ),
            )

        return metadata
