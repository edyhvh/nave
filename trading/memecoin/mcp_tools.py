"""
MCP tool surface for the memecoin scanner.

Three tools, all read-only:

    * ``memecoin_scan``           — Pump.fun new-launches → safety → score → ranked list.
    * ``memecoin_safety_report``  — full structured safety report for one mint.
    * ``memecoin_score``          — transparent rubric score for one mint
                                    (does not re-run safety unless asked).

Tools return JSON strings so they slot directly into FastMCP's
``@mcp.tool()``-decorated wrappers in ``trading/crypto/mcp_server.py``.
"""

from __future__ import annotations

import json
from typing import Any

from trading.memecoin.archive import scan_history_payload
from trading.memecoin.data_provider import MemecoinDataProvider
from trading.memecoin.recommend import memecoin_recommend_payload
from trading.memecoin.safety_check import check_safety
from trading.memecoin.scanner import MemecoinScanner
from trading.memecoin.scoring import score_candidate


def memecoin_scan_payload(
    *,
    limit: int = 50,
    top_n: int = 10,
    keep_skipped: bool = False,
    provider: MemecoinDataProvider | None = None,
) -> dict[str, Any]:
    """Run the scanner and return a JSON-ready dict."""
    scanner = MemecoinScanner(provider=provider)
    candidates = scanner.scan(limit=limit, keep_skipped=keep_skipped, top_n=top_n)
    return {
        "tool": "memecoin_scan",
        "params": {"limit": limit, "top_n": top_n, "keep_skipped": keep_skipped},
        "count": len(candidates),
        "candidates": [c.to_dict() for c in candidates],
    }


def memecoin_safety_report_payload(
    mint: str,
    *,
    provider: MemecoinDataProvider | None = None,
) -> dict[str, Any]:
    """Full safety report for one mint."""
    provider = provider or MemecoinDataProvider()
    report = check_safety(mint, provider=provider)
    return {"tool": "memecoin_safety_report", "report": report.to_dict()}


def memecoin_score_payload(
    mint: str,
    *,
    include_safety: bool = False,
    provider: MemecoinDataProvider | None = None,
) -> dict[str, Any]:
    """Transparent rubric score for one mint."""
    provider = provider or MemecoinDataProvider()
    market = provider.market(mint)
    safety = check_safety(mint, provider=provider) if include_safety else None
    score = score_candidate(mint, market, safety=safety)
    payload: dict[str, Any] = {
        "tool": "memecoin_score",
        "score": score.to_dict(),
    }
    if include_safety and safety is not None:
        payload["safety"] = safety.to_dict()
    return payload


def memecoin_scan_history_payload(
    *,
    hours: int = 24,
) -> dict[str, Any]:
    """Return archive visibility for trailing memecoin scans."""
    return scan_history_payload(hours=hours)


def memecoin_recommend_tool_payload(
    *,
    limit: int = 50,
    top_n: int = 10,
    keep_skipped: bool = False,
    history_hours: int = 24,
    capital_usd: float = 10_000.0,
    memecoin_exposure_usd: float = 0.0,
) -> dict[str, Any]:
    """Compose scan + history + sizing into enter-now recommendations."""
    return memecoin_recommend_payload(
        limit=limit,
        top_n=top_n,
        keep_skipped=keep_skipped,
        history_hours=history_hours,
        capital_usd=capital_usd,
        memecoin_exposure_usd=memecoin_exposure_usd,
    )


# Convenience wrappers that return JSON strings — what FastMCP tool
# functions are expected to return when they want pretty/parseable output.


def memecoin_scan_json(**kwargs: Any) -> str:
    return json.dumps(memecoin_scan_payload(**kwargs), default=str, indent=2)


def memecoin_safety_report_json(mint: str, **kwargs: Any) -> str:
    return json.dumps(
        memecoin_safety_report_payload(mint, **kwargs), default=str, indent=2
    )


def memecoin_score_json(mint: str, **kwargs: Any) -> str:
    return json.dumps(memecoin_score_payload(mint, **kwargs), default=str, indent=2)


def memecoin_scan_history_json(**kwargs: Any) -> str:
    return json.dumps(memecoin_scan_history_payload(**kwargs), default=str, indent=2)


def memecoin_recommend_json(**kwargs: Any) -> str:
    return json.dumps(memecoin_recommend_tool_payload(**kwargs), default=str, indent=2)
