from trading.stocks.ism_equity_pipeline import (
    build_ism_equity_pipeline,
    evaluate_candidate,
)


def _report(kind, candidates):
    return {
        "kind": kind,
        "report_month": "July 2026",
        "pmi": 55.6 if kind == "manufacturing" else 54.1,
        "hottest_industries": [
            {"industry": "electrical equipment", "rank": 1},
            {"industry": "information", "rank": 2},
        ],
        "candidates": {"longs": candidates},
    }


def _research(**overrides):
    base = {
        "complete": True,
        "thesis_supported": True,
        "thesis": "direct demand exposure",
        "watch_zone": [90, 100],
        "invalidation": "guidance reversal",
        "exposure": {"direct": True, "strength": "strong"},
        "fundamentals": {"acceptable": True},
        "valuation": {"acceptable": True},
        "technical": {"acceptable": True},
        "access": {"acceptable": True, "status": "research_proxy"},
        "risks": {"items": ["macro"]},
    }
    base.update(overrides)
    return base


def test_both_ism_inputs_dedupe_and_bound_candidate_pool():
    manufacturing = _report("manufacturing", [{
        "symbol": "ETN",
        "company_name": "Eaton",
        "sector": "Industrials",
        "industry": "Electrical Equipment",
        "driver_industry": "electrical equipment",
        "confidence": 0.9,
        "match_confidence": 0.9,
    }])
    services = _report("services", [{
        "symbol": "ETN",
        "company_name": "Eaton",
        "sector": "Industrials",
        "industry": "Electrical Equipment",
        "driver_industry": "electrical equipment",
        "confidence": 0.8,
        "match_confidence": 0.8,
    }])
    result = build_ism_equity_pipeline(
        manufacturing,
        services,
        research_by_symbol={"ETN": _research()},
        limit=1,
    )
    assert result["both_inputs_used"] is True
    assert len(result["candidate_pool"]) == 1
    assert result["candidate_pool"][0]["sources"] == ["manufacturing", "services"]
    assert result["decisions"][0]["verdict"] == "INCLUDE_WATCH"


def test_existing_holding_and_watch_are_not_duplicated():
    candidate = {"symbol": "FCX", "company_name": "Freeport"}
    assert evaluate_candidate(
        candidate,
        _research(),
        portfolio_symbols=["FCX"],
    )["verdict"] == "HOLD_EXISTING"
    assert evaluate_candidate(
        {"symbol": "EQIX"},
        _research(),
        watch_symbols=["EQIX"],
    )["verdict"] == "KEEP_EXISTING_WATCH"


def test_weak_indirect_candidate_is_rejected():
    result = evaluate_candidate(
        {"symbol": "WEAK"},
        _research(
            thesis_supported=True,
            exposure={"direct": False, "strength": "weak"},
        ),
    )
    assert result["verdict"] == "REJECT"


def test_incomplete_research_stays_researching_not_human_review():
    result = evaluate_candidate({"symbol": "ETN"}, {})
    assert result["status"] == "RESEARCHING"
    assert result["verdict"] is None
    assert not result.get("human_review_needed", False)
