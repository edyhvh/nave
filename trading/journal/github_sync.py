"""GitHub data repository sync utilities for trade journal snapshots."""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional
from urllib import error, parse, request

from .models import Trade


class GitHubSyncError(RuntimeError):
    """Raised when syncing to GitHub data repository fails."""


@dataclass
class GitHubDataRepoSync:
    """Sync trade journal data into a dedicated GitHub data repository."""

    owner: str
    repo: str
    token: str
    branch: str = "main"
    base_path: str = "trade_journal"
    api_base: str = "https://api.github.com"

    @classmethod
    def from_env(cls) -> Optional["GitHubDataRepoSync"]:
        """Build sync client from environment variables.

        Required:
            NAVE_GITHUB_DATA_REPO_OWNER
            NAVE_GITHUB_DATA_REPO_NAME
            NAVE_GITHUB_TOKEN
        Optional:
            NAVE_GITHUB_DATA_REPO_BRANCH (default: main)
            NAVE_GITHUB_DATA_BASE_PATH (default: trade_journal)
        """
        owner = os.getenv("NAVE_GITHUB_DATA_REPO_OWNER", "").strip()
        repo = os.getenv("NAVE_GITHUB_DATA_REPO_NAME", "").strip()
        token = os.getenv("NAVE_GITHUB_TOKEN", "").strip()
        if not owner or not repo or not token:
            return None

        branch = os.getenv("NAVE_GITHUB_DATA_REPO_BRANCH",
                           "main").strip() or "main"
        base_path = os.getenv("NAVE_GITHUB_DATA_BASE_PATH",
                              "trade_journal").strip() or "trade_journal"
        return cls(owner=owner, repo=repo, token=token, branch=branch, base_path=base_path)

    def _request_json(self, method: str, url: str, payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "nave-trade-journal-sync",
        }
        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = request.Request(url=url, data=body,
                              headers=headers, method=method)
        try:
            with request.urlopen(req, timeout=15) as resp:
                data = resp.read().decode("utf-8")
                return json.loads(data) if data else {}
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8")
            raise GitHubSyncError(
                f"GitHub sync failed ({exc.code}): {detail}") from exc
        except error.URLError as exc:
            raise GitHubSyncError(
                f"GitHub sync connection error: {exc}") from exc

    def _repo_file_url(self, path: str) -> str:
        safe_path = parse.quote(path.strip("/"))
        return f"{self.api_base}/repos/{self.owner}/{self.repo}/contents/{safe_path}"

    def _get_sha(self, path: str) -> Optional[str]:
        url = f"{self._repo_file_url(path)}?ref={parse.quote(self.branch)}"
        try:
            response = self._request_json("GET", url)
            return response.get("sha")
        except GitHubSyncError as exc:
            # File missing is normal for first write.
            if "(404)" in str(exc):
                return None
            raise

    def upsert_json(self, path: str, payload: dict[str, Any], message: str) -> dict[str, Any]:
        """Create or update a JSON file in the GitHub data repository."""
        sha = self._get_sha(path)
        content_bytes = json.dumps(
            payload, indent=2, default=str).encode("utf-8")
        b64_content = base64.b64encode(content_bytes).decode("utf-8")

        body: dict[str, Any] = {
            "message": message,
            "content": b64_content,
            "branch": self.branch,
        }
        if sha:
            body["sha"] = sha

        return self._request_json("PUT", self._repo_file_url(path), body)

    def sync_trade(self, trade: Trade, event: str = "update") -> dict[str, Any]:
        """Sync one trade as a dedicated JSON file."""
        path = f"{self.base_path.strip('/')}/trades/{trade.id}.json"
        payload = {
            "synced_at": datetime.utcnow().isoformat(),
            "event": event,
            "trade": trade.to_dict(),
        }
        return self.upsert_json(path, payload, f"journal({event}): sync trade {trade.id}")

    def sync_snapshot(
        self,
        trades: list[Trade],
        stats: Optional[dict[str, Any]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Sync latest full snapshot of trades and aggregate stats."""
        path = f"{self.base_path.strip('/')}/latest_snapshot.json"
        payload = {
            "generated_at": datetime.utcnow().isoformat(),
            "trade_count": len(trades),
            "stats": stats or {},
            "metadata": metadata or {},
            "trades": [trade.to_dict() for trade in trades],
        }
        return self.upsert_json(path, payload, "journal(snapshot): update latest trade journal snapshot")
