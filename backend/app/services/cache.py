"""In-memory cache service for API indicator responses.

For production deployments, swap the in-memory store for Redis or SQLite.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, Optional


class CacheService:
    """Simple async in-memory cache keyed by indicator name."""

    def __init__(self) -> None:
        self._store: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def get(self, name: str) -> Optional[Dict[str, Any]]:
        """Return cached entry or ``None`` if not present."""
        async with self._lock:
            return self._store.get(name)

    async def set(self, name: str, as_of: datetime, payload: Dict[str, Any]) -> None:
        """Store ``payload`` under ``name`` with timestamp ``as_of``."""
        async with self._lock:
            self._store[name] = {
                "as_of": as_of.astimezone(timezone.utc),
                "payload": payload,
            }

    async def delete(self, name: str) -> None:
        """Remove a cached entry."""
        async with self._lock:
            self._store.pop(name, None)

    async def clear(self) -> None:
        """Wipe the entire cache."""
        async with self._lock:
            self._store.clear()


# Application-level singleton
_cache: Optional[CacheService] = None


def get_cache() -> CacheService:
    """Return the application-level cache singleton."""
    global _cache
    if _cache is None:
        _cache = CacheService()
    return _cache
