"""Deterministic ISM -> equity discovery and decision funnel.

This module intentionally stops at a bounded research queue.  It never buys,
changes a watch, or treats a missing company-research field as approval.  An
agent may fill ``research`` after the deterministic funnel selects the small
set of highest-information candidates, then call :func:`evaluate_candidate`.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

VERDICTS = {
    "INCLUDE_WATCH",
    "REJECT",
    "HOLD_EXISTING",
    "KEEP_EXISTING_WATCH",
    "REMOVE_EXISTING_WATCH",
    "INCONCLUSIVE",
}


def _norm(value: Any) -> str:
    return str(value or "").strip().upper()


def _candidate_rank(candidate: Mapping[str, Any], report: Mapping[str, Any]) -> int | None:
    driver = str(candidate.get("driver_industry") or "").casefold()
    for item in report.get("hottest_industries") or []:
        if driver and driver in str(item.get("industry") or "").casefold():
            try:
                return int(item.get("rank"))
            except (TypeError, ValueError):
                return None
    return None


def discover_candidate_pool(
    manufacturing: Mapping[str, Any],
    services: Mapping[str, Any],
    *,
    portfolio_symbols: Sequence[str] = (),
    watch_symbols: Sequence[str] = (),
    additional_candidates: Sequence[Mapping[str, Any]] = (),
    limit: int = 6,
) -> list[dict[str, Any]]:
    """Merge both ISM reports, dedupe symbols, and select a small queue.

    Candidate discovery may use report-derived winners.  The final verdict
    must use company evidence supplied separately; this keeps winner/sector
    discovery distinct from the research decision and makes hindsight leakage
    visible in the artifact.
    """
    if limit < 1:
        return []
    grouped: dict[str, dict[str, Any]] = {}
    reports = (("manufacturing", manufacturing), ("services", services))
    for source, report in reports:
        for candidate in (report.get("candidates") or {}).get("longs", []):
            symbol = _norm(candidate.get("symbol"))
            if not symbol:
                continue
            entry = grouped.setdefault(
                symbol,
                {
                    "symbol": symbol,
                    "company_name": candidate.get("company_name"),
                    "sector": candidate.get("sector"),
                    "industry": candidate.get("industry"),
                    "sources": [],
                    "ism_signals": [],
                    "candidate": dict(candidate),
                },
            )
            entry["sources"].append(source)
            entry["ism_signals"].append(
                {
                    "source": source,
                    "report_month": report.get("report_month"),
                    "pmi": report.get("pmi"),
                    "driver_industry": candidate.get("driver_industry"),
                    "rank": _candidate_rank(candidate, report),
                    "confidence": candidate.get("confidence"),
                    "match_confidence": candidate.get("match_confidence"),
                }
            )

    # Existing holdings/watches can be re-evaluated against the new report
    # even when the screener did not return them in its top-N list.  Callers
    # must provide the actual ISM evidence; this avoids silently inventing a
    # sector match for a pre-existing position.
    for candidate in additional_candidates:
        symbol = _norm(candidate.get("symbol"))
        if not symbol:
            continue
        entry = grouped.setdefault(
            symbol,
            {
                "symbol": symbol,
                "company_name": candidate.get("company_name"),
                "sector": candidate.get("sector"),
                "industry": candidate.get("industry"),
                "sources": [],
                "ism_signals": [],
                "candidate": dict(candidate),
            },
        )
        entry["sources"] = sorted(
            set(entry["sources"]) | set(candidate.get("sources") or [])
        )
        entry["ism_signals"].extend(candidate.get("ism_signals") or [])
        if candidate.get("research_priority"):
            entry["research_priority"] = True

    held = {_norm(symbol) for symbol in portfolio_symbols}
    watched = {_norm(symbol) for symbol in watch_symbols}
    for entry in grouped.values():
        signals = entry["ism_signals"]
        ranks = [item["rank"] for item in signals if item["rank"] is not None]
        confidences = [
            float(item["confidence"])
            for item in signals
            if isinstance(item.get("confidence"), (int, float))
        ]
        matches = [
            float(item["match_confidence"])
            for item in signals
            if isinstance(item.get("match_confidence"), (int, float))
        ]
        entry["portfolio_state"] = (
            "HELD" if entry["symbol"] in held
            else "WATCHED" if entry["symbol"] in watched
            else "NEW"
        )
        entry["discovery_score"] = round(
            (max(confidences) if confidences else 0.0)
            * (max(matches) if matches else 0.0)
            * (1.0 / max(min(ranks or [10]), 1)),
            6,
        )

    return sorted(
        grouped.values(),
        key=lambda item: (
            0 if item["portfolio_state"] in {"HELD", "WATCHED"} else 1,
            0 if item.get("research_priority") else 1,
            -item["discovery_score"],
            item["symbol"],
        ),
    )[:limit]


def _research_is_complete(research: Mapping[str, Any]) -> bool:
    required = (
        "exposure",
        "fundamentals",
        "valuation",
        "technical",
        "access",
        "risks",
    )
    return bool(research.get("complete")) and all(
        isinstance(research.get(key), Mapping) for key in required
    )


def evaluate_candidate(
    candidate: Mapping[str, Any],
    research: Mapping[str, Any],
    *,
    portfolio_symbols: Sequence[str] = (),
    watch_symbols: Sequence[str] = (),
) -> dict[str, Any]:
    """Return a completed, human-reviewable decision or ``RESEARCHING``."""
    symbol = _norm(candidate.get("symbol"))
    result: dict[str, Any] = {
        "symbol": symbol,
        "status": "RESEARCHING",
        "verdict": None,
        "research_complete": _research_is_complete(research),
        "reasons": [],
        "research": dict(research),
    }
    if not result["research_complete"]:
        result["reasons"].append("company research is incomplete")
        return result

    held = symbol in {_norm(item) for item in portfolio_symbols}
    watched = symbol in {_norm(item) for item in watch_symbols}
    blocking: list[str] = []
    exposure = research["exposure"]
    if exposure.get("direct") is False or exposure.get("strength") == "weak":
        blocking.append("ISM exposure is weak or indirect")
    for section in ("fundamentals", "valuation", "technical", "access"):
        evidence = research[section]
        if evidence.get("acceptable") is False:
            blocking.append(str(evidence.get("reason") or f"{section} is unacceptable"))
    if research.get("thesis_supported") is False:
        blocking.append("company thesis does not corroborate the ISM signal")

    if held:
        verdict = "HOLD_EXISTING" if not blocking else "INCONCLUSIVE"
    elif watched:
        verdict = "KEEP_EXISTING_WATCH" if not blocking else "REMOVE_EXISTING_WATCH"
    elif blocking:
        verdict = "REJECT"
    elif research.get("thesis_supported") is not True:
        verdict = "INCONCLUSIVE"
        blocking.append("thesis support was not explicitly established")
    else:
        verdict = "INCLUDE_WATCH"

    result.update(
        {
            "status": "COMPLETED",
            "verdict": verdict,
            "reasons": blocking,
            "thesis": research.get("thesis"),
            "watch_zone": research.get("watch_zone"),
            "invalidation": research.get("invalidation"),
            "access_status": research["access"].get("status"),
            "human_review_needed": verdict in {"INCLUDE_WATCH", "REMOVE_EXISTING_WATCH"},
        }
    )
    return result


def build_ism_equity_pipeline(
    manufacturing: Mapping[str, Any],
    services: Mapping[str, Any],
    *,
    research_by_symbol: Mapping[str, Mapping[str, Any]] | None = None,
    portfolio_symbols: Sequence[str] = (),
    watch_symbols: Sequence[str] = (),
    additional_candidates: Sequence[Mapping[str, Any]] = (),
    limit: int = 6,
) -> dict[str, Any]:
    """Build the autonomous discovery -> research -> verdict artifact."""
    pool = discover_candidate_pool(
        manufacturing,
        services,
        portfolio_symbols=portfolio_symbols,
        watch_symbols=watch_symbols,
        additional_candidates=additional_candidates,
        limit=limit,
    )
    research = research_by_symbol or {}
    decisions = [
        evaluate_candidate(
            candidate,
            research.get(candidate["symbol"], {}),
            portfolio_symbols=portfolio_symbols,
            watch_symbols=watch_symbols,
        )
        for candidate in pool
    ]
    return {
        "pipeline": "ISM -> bounded equity discovery -> company research -> verdict",
        "report_months": {
            "manufacturing": manufacturing.get("report_month"),
            "services": services.get("report_month"),
        },
        "both_inputs_used": True,
        "bounded_limit": limit,
        "candidate_pool": pool,
        "reports": {
            "manufacturing": {
                "report_month": manufacturing.get("report_month"),
                "pmi": manufacturing.get("pmi"),
                "source_url": manufacturing.get("source_url"),
                "headline": manufacturing.get("headline"),
                "subindices": manufacturing.get("subindices"),
                "industry_rankings": manufacturing.get("industry_rankings") or manufacturing.get("hottest_industries"),
                "comments": manufacturing.get("comments"),
            },
            "services": {
                "report_month": services.get("report_month"),
                "pmi": services.get("pmi"),
                "source_url": services.get("source_url"),
                "headline": services.get("headline"),
                "subindices": services.get("subindices"),
                "industry_rankings": services.get("industry_rankings") or services.get("hottest_industries"),
                "comments": services.get("comments"),
            },
        },
        "decisions": decisions,
        "human_review": [
            item for item in decisions if item.get("human_review_needed")
        ],
    }
