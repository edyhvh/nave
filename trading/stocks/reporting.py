"""Shared ISM industry report builder for CLI, MCP, and Hermes surfaces."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Protocol, cast

from trading.stocks.data_provider import (
    FundamentalSnapshot,
    MassiveClient,
    MassiveRateLimitError,
)
from trading.stocks.ism_calendar import load_calendar
from trading.stocks.ism_scraper import ISMReport, ISMReportFetcher
from trading.stocks.ondo_universe import (
    ONDO_STOCK_PERP_EXECUTION_STATUS,
    ONDO_STOCK_PERP_UNIVERSE,
    ONDO_STOCK_PERP_UNIVERSE_SOURCE,
    ONDO_STOCK_PERP_VENUE,
    is_ondo_stock_perp,
)
from trading.stocks.screener import (
    MassiveLike,
    ScreenerMode,
    SectorScreener,
    StockCandidate,
    StockScreenerError,
    _safe_sector_avg_pe,
)
from trading.stocks.strategy import (
    build_ism_short_trade_plan,
    short_candidate_quality,
    _normalize_min_short_score,
)
from trading.stocks.universe import DEFAULT_UNIVERSE


class ISMReportFetcherLike(Protocol):
    """Minimal fetcher contract needed by report builder."""

    def fetch_report(self, *, kind: str) -> ISMReport:
        ...

def build_ism_industry_report(
    *,
    kind: str = "manufacturing",
    mode: str | None = None,
    top_n: int = 10,
    max_sectors_per_trend: int = 4,
    min_eps_growth_next_year: float | None = None,
    min_confidence: float = 0.3,
    min_short_score: float | None = None,
    research_mode: bool = False,
    universe: Mapping[str, list[str]] | None = None,
    fetcher: ISMReportFetcherLike | None = None,
    massive: MassiveLike | None = None,
    persist_snapshot: bool = False,
    snapshot_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Build a complete ISM report with hottest/worst sectors and filtered names.

    ``mode`` selects the screening strategy (``manufacturing`` = EPS growth,
    ``services`` = long-term revenue growth + PE-relative filter). When
    omitted it mirrors ``kind``.
    """
    if kind not in {"manufacturing", "services"}:
        raise ValueError("kind must be 'manufacturing' or 'services'")
    effective_mode: ScreenerMode = cast("ScreenerMode", mode or kind)
    if effective_mode not in {"manufacturing", "services"}:
        raise ValueError("mode must be 'manufacturing' or 'services'")
    effective_min_short_score = _normalize_min_short_score(
        min_short_score,
        research_mode=research_mode,
    )

    report_fetcher = fetcher or ISMReportFetcher()
    report = report_fetcher.fetch_report(kind=cast("Any", kind))
    effective_universe = (
        {sector: list(tickers) for sector, tickers in universe.items()}
        if universe is not None
        else DEFAULT_UNIVERSE
    )
    screener = SectorScreener(
        massive=massive or MassiveClient(), universe=effective_universe)

    long_candidates = _safe_rank(
        screener,
        report=report,
        trend="expanding",
        top_n=top_n,
        max_sectors=max_sectors_per_trend,
        min_eps_growth_next_year=min_eps_growth_next_year,
        min_confidence=min_confidence,
        mode=effective_mode,
    )
    short_candidates = _safe_rank(
        screener,
        report=report,
        trend="contracting",
        top_n=top_n,
        max_sectors=max_sectors_per_trend,
        min_eps_growth_next_year=min_eps_growth_next_year,
        min_confidence=min_confidence,
        mode=effective_mode,
    )

    long_candidates, short_candidates = _remove_overlaps(
        long_candidates, short_candidates)
    long_candidates = _filter_report_candidates(
        long_candidates,
        side="long",
        top_n=top_n,
        min_confidence=min_confidence,
    )
    short_candidates = _filter_report_candidates(
        short_candidates,
        side="short",
        top_n=top_n,
        min_confidence=min_confidence,
        min_short_score=effective_min_short_score,
        research_mode=research_mode,
    )
    ondo_short_candidates, non_ondo_short_candidates = _split_ondo_short_candidates(
        short_candidates
    )

    expanding_primary_industry = _sector_primary_industry(report.expanding)
    contracting_primary_industry = _sector_primary_industry(report.contracting)
    contracting_sector_rank = _sector_badness_rank(report.contracting)
    expanding_sectors = report.by_sector("expanding")
    contracting_sectors = report.by_sector("contracting")

    screened_by_trend = {
        "expanding_by_sector": _symbols_by_sector(
            effective_universe,
            expanding_sectors[:max_sectors_per_trend] if max_sectors_per_trend > 0 else expanding_sectors,
        ),
        "contracting_by_sector": _symbols_by_sector(
            effective_universe,
            contracting_sectors[:max_sectors_per_trend] if max_sectors_per_trend > 0 else contracting_sectors,
        ),
    }

    screened_all_symbols = sorted(
        {
            *screened_by_trend["expanding_by_sector"].get("all_symbols", []),
            *screened_by_trend["contracting_by_sector"].get("all_symbols", []),
        }
    )

    payload: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "kind": report.kind,
        "mode": effective_mode,
        "report_month": report.report_month,
        "pmi": report.pmi,
        "source_url": report.source_url,
        "criteria": {
            "top_n": top_n,
            "mode": effective_mode,
            "max_sectors_per_trend": max_sectors_per_trend,
            "min_eps_growth_next_year": min_eps_growth_next_year,
            "min_confidence": min_confidence,
            "min_short_score": effective_min_short_score,
            "research_mode": research_mode,
        },
        "hottest_industries": [
            {
                "rank": item.rank,
                "industry": item.industry,
                "gics_sector": item.gics_sector,
            }
            for item in report.expanding
        ],
        "worst_industries": [
            {
                "rank": item.rank,
                "industry": item.industry,
                "gics_sector": item.gics_sector,
            }
            for item in report.contracting
        ],
        "short_thesis": {
            "source": f"ISM {report.kind} report",
            "lookback": "latest report plus 6-month backtest window",
            "top_bad_industries": [
                {
                    "rank": item.rank,
                    "industry": item.industry,
                    "gics_sector": item.gics_sector,
                }
                for item in report.contracting[:5]
            ],
            "top_bad_sectors": _top_bad_sectors(report.contracting, limit=5),
            "execution_context": (
                "Short candidates are research candidates for listed stock perps "
                "where the Ondo venue supports the symbol; broker execution remains stubbed."
            ),
            "venue": ONDO_STOCK_PERP_VENUE,
            "ondo_universe_size": len(ONDO_STOCK_PERP_UNIVERSE),
            "ondo_universe_source": ONDO_STOCK_PERP_UNIVERSE_SOURCE,
            "ondo_execution_status": ONDO_STOCK_PERP_EXECUTION_STATUS,
            "ondo_tradeable_count": len(ondo_short_candidates),
            "non_ondo_short_count": len(non_ondo_short_candidates),
        },
        "candidates": {
            "longs": [
                _candidate_to_dict(
                    item,
                    ism_industry_hint=expanding_primary_industry,
                    industry_momentum="gaining",
                )
                for item in long_candidates
            ],
            "shorts": [
                _candidate_to_dict(
                    item,
                    ism_industry_hint=contracting_primary_industry,
                    industry_momentum="losing",
                    venue=ONDO_STOCK_PERP_VENUE if is_ondo_stock_perp(item.symbol) else None,
                    perp_candidate=is_ondo_stock_perp(item.symbol),
                    ondo_perp_available=is_ondo_stock_perp(item.symbol),
                    sector_badness_rank=contracting_sector_rank.get(item.sector),
                    min_short_score=effective_min_short_score,
                )
                for item in short_candidates
            ],
            "ondo_shorts": [
                _candidate_to_dict(
                    item,
                    ism_industry_hint=contracting_primary_industry,
                    industry_momentum="losing",
                    venue=ONDO_STOCK_PERP_VENUE,
                    perp_candidate=True,
                    ondo_perp_available=True,
                    sector_badness_rank=contracting_sector_rank.get(item.sector),
                    min_short_score=effective_min_short_score,
                )
                for item in ondo_short_candidates
            ],
            # Backward compatibility keys
            "expanding": [
                _candidate_to_dict(
                    item,
                    ism_industry_hint=expanding_primary_industry,
                    industry_momentum="gaining",
                )
                for item in long_candidates
            ],
            "contracting": [
                _candidate_to_dict(
                    item,
                    ism_industry_hint=contracting_primary_industry,
                    industry_momentum="losing",
                    venue=ONDO_STOCK_PERP_VENUE if is_ondo_stock_perp(item.symbol) else None,
                    perp_candidate=is_ondo_stock_perp(item.symbol),
                    ondo_perp_available=is_ondo_stock_perp(item.symbol),
                    sector_badness_rank=contracting_sector_rank.get(item.sector),
                    min_short_score=effective_min_short_score,
                )
                for item in short_candidates
            ],
        },
        "summary": {
            "hottest_sector_count": len(expanding_sectors),
            "worst_sector_count": len(contracting_sectors),
            "long_candidates": len(long_candidates),
            "short_candidates": len(short_candidates),
            "ondo_short_candidates": len(ondo_short_candidates),
            "screened_symbol_count": len(screened_all_symbols),
            # Backward compatibility summary keys
            "expanding_candidates": len(long_candidates),
            "contracting_candidates": len(short_candidates),
        },
        "screened_universe": {
            **screened_by_trend,
            "all_symbols": screened_all_symbols,
        },
        "reviewed_companies": _capture_reviewed_companies(
            screener=screener,
            mode=effective_mode,
            expanding_by_sector=screened_by_trend["expanding_by_sector"]["by_sector"],
            contracting_by_sector=screened_by_trend["contracting_by_sector"]["by_sector"],
            long_candidates=long_candidates,
            short_candidates=short_candidates,
            ism_industry_hint_long=expanding_primary_industry,
            ism_industry_hint_short=contracting_primary_industry,
            min_eps_growth_next_year=min_eps_growth_next_year,
            min_confidence=min_confidence,
        ),
    }

    report_month_key = _month_key(payload)
    expected_covers_month = _latest_expected_covers_month(kind=report.kind)
    payload["report_month_key"] = report_month_key
    payload["expected_covers_month"] = expected_covers_month
    payload["is_expected_month"] = bool(
        expected_covers_month and report_month_key == expected_covers_month
    )
    payload["freshness_status"] = (
        "current"
        if payload["is_expected_month"]
        else ("stale" if expected_covers_month else "unknown")
    )

    if persist_snapshot:
        saved_to = _persist_monthly_snapshot(
            payload,
            snapshot_dir=snapshot_dir,
        )
        payload["saved_to"] = str(saved_to)

    return payload


def _safe_rank(
    screener: SectorScreener,
    *,
    report,
    trend: str,
    top_n: int,
    max_sectors: int,
    min_eps_growth_next_year: float | None,
    min_confidence: float,
    mode: ScreenerMode = "manufacturing",
) -> list[StockCandidate]:
    try:
        sectors = report.by_sector(trend=trend)
        if max_sectors > 0:
            sectors = sectors[:max_sectors]
        if not sectors:
            return []
        bucket = report.expanding if trend == "expanding" else report.contracting
        sector_rankings: dict[str, list[Any]] = {}
        for item in bucket:
            sector = getattr(item, "gics_sector", None)
            if isinstance(sector, str) and sector in sectors:
                sector_rankings.setdefault(sector, []).append(item)
        return screener.rank_sectors(
            sectors,
            top_n=top_n,
            side="short" if trend == "contracting" else "long",
            min_eps_growth_next_year=min_eps_growth_next_year,
            industry_rankings_by_sector=sector_rankings,
            min_confidence=min_confidence,
            mode=mode,
        )
    except (StockScreenerError, MassiveRateLimitError):
        return []


def _candidate_to_dict(
    item: StockCandidate,
    *,
    ism_industry_hint: Mapping[str, str] | None = None,
    industry_momentum: str | None = None,
    venue: str | None = None,
    perp_candidate: bool = False,
    ondo_perp_available: bool | None = None,
    sector_badness_rank: int | None = None,
    min_short_score: float = 0.0,
) -> dict[str, Any]:
    fundamentals_industry = item.industry
    hinted_industry = item.driver_industry or (
        ism_industry_hint or {}).get(item.sector)
    industry = fundamentals_industry or hinted_industry
    if fundamentals_industry:
        industry_source = "fmp"
    elif hinted_industry:
        industry_source = "ism_hint"
    else:
        industry_source = None

    out = {
        "symbol": item.symbol,
        "company_name": item.company_name,
        "sector": item.sector,
        "industry": industry,
        "driver_industry": hinted_industry,
        "industry_source": industry_source,
        "industry_momentum": industry_momentum,
        "side": item.side,
        "mode": item.mode,
        "confidence": round(item.confidence, 4),
        "match_confidence": round(item.match_confidence, 4),
        "score": round(item.score, 4),
        "eps_growth_next_year": round(item.eps_growth_next_year, 2) if item.eps_growth_next_year is not None else None,
        "eps_growth_source": item.eps_growth_source,
        "revenue_growth_long_term": (
            round(item.revenue_growth_long_term, 2)
            if item.revenue_growth_long_term is not None
            else None
        ),
        "revenue_growth_source": item.revenue_growth_source,
        "reason": item.reason,
    }
    if venue is not None:
        out["venue"] = venue
    if perp_candidate:
        out["perp_candidate"] = True
    if ondo_perp_available is not None:
        out["ondo_perp_available"] = ondo_perp_available
    if item.side == "short":
        trade_plan = build_ism_short_trade_plan(
            item,
            allocation_usd=0.0,
            min_short_score=min_short_score,
        )
        out["short_quality_score"] = short_candidate_quality(
            item,
            sector_badness_rank=sector_badness_rank,
            ondo_available=bool(ondo_perp_available),
        )
        out["short_gate"] = "bearish_growth_score"
        out["entry_rule"] = trade_plan["entry_rule"]
        out["entry_price"] = trade_plan["entry_price"]
        out["target"] = trade_plan["target"]
        out["stop"] = trade_plan["stop"]
        out["holding_window_days"] = trade_plan["holding_window_days"]
        out["risk_pct"] = trade_plan["risk_pct"]
        out["size_guidance"] = trade_plan["size_guidance"]
        out["max_leverage"] = trade_plan["max_leverage"]
        out["trade_plan"] = trade_plan
    return out


def _split_ondo_short_candidates(
    short_candidates: list[StockCandidate],
) -> tuple[list[StockCandidate], list[StockCandidate]]:
    ondo: list[StockCandidate] = []
    non_ondo: list[StockCandidate] = []
    for item in short_candidates:
        if is_ondo_stock_perp(item.symbol):
            ondo.append(item)
        else:
            non_ondo.append(item)
    return ondo, non_ondo


def _sector_primary_industry(rankings: list[Any]) -> dict[str, str]:
    """Build a best-effort sector->industry hint map from ISM rankings."""
    out: dict[str, str] = {}
    for item in rankings:
        sector = getattr(item, "gics_sector", None)
        industry = getattr(item, "industry", None)
        if isinstance(sector, str) and sector and isinstance(industry, str) and industry:
            out.setdefault(sector, industry)
    return out


def _top_bad_sectors(rankings: list[Any], *, limit: int) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for item in rankings:
        sector = getattr(item, "gics_sector", None)
        industry = getattr(item, "industry", None)
        rank = getattr(item, "rank", None)
        if not isinstance(sector, str) or not sector:
            continue
        if sector not in seen:
            seen[sector] = {
                "sector": sector,
                "first_rank": rank,
                "driver_industries": [],
            }
        if isinstance(industry, str) and industry:
            seen[sector]["driver_industries"].append(industry)
    return list(seen.values())[:limit]


def _sector_badness_rank(rankings: list[Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for item in rankings:
        sector = getattr(item, "gics_sector", None)
        rank = getattr(item, "rank", None)
        if not isinstance(sector, str) or not sector:
            continue
        try:
            rank_int = int(rank)
        except (TypeError, ValueError):
            continue
        out[sector] = min(rank_int, out.get(sector, rank_int))
    return out


def _remove_overlaps(
    long_candidates: list[StockCandidate],
    short_candidates: list[StockCandidate],
) -> tuple[list[StockCandidate], list[StockCandidate]]:
    by_symbol_long = {item.symbol: item for item in long_candidates}
    by_symbol_short = {item.symbol: item for item in short_candidates}
    overlapping = set(by_symbol_long) & set(by_symbol_short)
    if not overlapping:
        return long_candidates, short_candidates

    keep_long = set(by_symbol_long)
    keep_short = set(by_symbol_short)
    for symbol in overlapping:
        long_item = by_symbol_long[symbol]
        short_item = by_symbol_short[symbol]
        if long_item.score >= short_item.score:
            keep_short.discard(symbol)
        else:
            keep_long.discard(symbol)

    return (
        [item for item in long_candidates if item.symbol in keep_long],
        [item for item in short_candidates if item.symbol in keep_short],
    )


def _filter_report_candidates(
    candidates: list[StockCandidate],
    *,
    side: str,
    top_n: int,
    min_confidence: float,
    min_short_score: float = 0.0,
    research_mode: bool = False,
) -> list[StockCandidate]:
    filtered: list[StockCandidate] = []
    for item in candidates:
        if item.confidence < min_confidence:
            continue
        if side == "short" and item.score <= min_short_score and not research_mode:
            continue
        if side == "short" and item.score < min_short_score and research_mode:
            continue
        filtered.append(item)
    return filtered[:top_n]


def _symbols_by_sector(
    universe: Mapping[str, list[str]],
    sectors: list[str],
) -> dict[str, Any]:
    by_sector: dict[str, list[str]] = {}
    all_symbols: set[str] = set()
    for sector in sectors:
        symbols = [str(sym).upper() for sym in universe.get(sector, [])]
        by_sector[sector] = symbols
        all_symbols.update(symbols)
    return {
        "sectors": sectors,
        "by_sector": by_sector,
        "all_symbols": sorted(all_symbols),
    }


def _capture_reviewed_companies(
    *,
    screener: SectorScreener,
    mode: ScreenerMode,
    expanding_by_sector: Mapping[str, list[str]],
    contracting_by_sector: Mapping[str, list[str]],
    long_candidates: list[StockCandidate],
    short_candidates: list[StockCandidate],
    ism_industry_hint_long: Mapping[str, str],
    ism_industry_hint_short: Mapping[str, str],
    min_eps_growth_next_year: float | None,
    min_confidence: float,
) -> list[dict[str, Any]]:
    """Per-symbol fundamentals + selection status for everything reviewed."""
    long_by_symbol = {c.symbol: c for c in long_candidates}
    short_by_symbol = {c.symbol: c for c in short_candidates}

    rows: dict[str, dict[str, Any]] = {}
    for trend, sector_map, hint_map in (
        ("expanding", expanding_by_sector, ism_industry_hint_long),
        ("contracting", contracting_by_sector, ism_industry_hint_short),
    ):
        for sector, symbols in sector_map.items():
            if not symbols:
                continue
            sector_avg_pe = (
                _safe_sector_avg_pe(screener.massive, sector)
                if mode == "services"
                else None
            )
            try:
                snapshots = screener.massive.batch_fundamentals(symbols)
            except MassiveRateLimitError:
                snapshots = []
            snap_by_symbol = {s.symbol.upper(): s for s in snapshots}
            for raw_symbol in symbols:
                symbol = str(raw_symbol).upper()
                if symbol in rows:
                    # Already captured under the other trend — keep the first.
                    continue
                snap = snap_by_symbol.get(symbol)
                rows[symbol] = _reviewed_company_row(
                    symbol=symbol,
                    sector=sector,
                    trend=trend,
                    snap=snap,
                    sector_avg_pe=sector_avg_pe,
                    long_candidate=long_by_symbol.get(symbol),
                    short_candidate=short_by_symbol.get(symbol),
                    ism_industry_hint=hint_map.get(sector),
                    mode=mode,
                    min_eps_growth_next_year=min_eps_growth_next_year,
                    min_confidence=min_confidence,
                )
    return [rows[symbol] for symbol in sorted(rows)]


def _reviewed_company_row(
    *,
    symbol: str,
    sector: str,
    trend: str,
    snap: FundamentalSnapshot | None,
    sector_avg_pe: float | None,
    long_candidate: StockCandidate | None,
    short_candidate: StockCandidate | None,
    ism_industry_hint: str | None,
    mode: ScreenerMode,
    min_eps_growth_next_year: float | None,
    min_confidence: float,
) -> dict[str, Any]:
    if long_candidate is not None:
        side = "long"
        scored = long_candidate
    elif short_candidate is not None:
        side = "short"
        scored = short_candidate
    else:
        side = "not_selected"
        scored = None

    row: dict[str, Any] = {
        "symbol": symbol,
        "sector": sector,
        "trend": trend,
        "side": side,
        "company_name": snap.company_name if snap else None,
        "industry": snap.industry if snap else None,
        "driver_industry": (scored.driver_industry if scored else ism_industry_hint),
        "pe_ratio": _round(snap.pe_ratio if snap else None, 2),
        "forward_pe": _round(snap.forward_pe if snap else None, 2),
        "sector_avg_pe": _round(sector_avg_pe, 2),
        "eps_growth_next_year": _round(snap.eps_growth_next_year if snap else None, 2),
        "eps_growth_source": snap.eps_growth_source if snap else None,
        "eps_growth_confidence": _round(snap.eps_growth_confidence if snap else None, 4),
        "revenue_growth_long_term": _round(
            snap.revenue_growth_long_term if snap else None, 2
        ),
        "revenue_growth_source": snap.revenue_growth_source if snap else None,
    }

    if scored is not None:
        row["confidence"] = round(scored.confidence, 4)
        row["score"] = round(scored.score, 4)
        row["reason"] = scored.reason
        row["exclusion_reason"] = None
    else:
        row["confidence"] = None
        row["score"] = None
        row["reason"] = None
        row["exclusion_reason"] = _infer_exclusion_reason(
            snap=snap,
            sector_avg_pe=sector_avg_pe,
            mode=mode,
            min_eps_growth_next_year=min_eps_growth_next_year,
            min_confidence=min_confidence,
        )
    return row


def _infer_exclusion_reason(
    *,
    snap: FundamentalSnapshot | None,
    sector_avg_pe: float | None,
    mode: ScreenerMode,
    min_eps_growth_next_year: float | None,
    min_confidence: float,
) -> str:
    if snap is None:
        return "fundamentals_unavailable"
    if mode == "services":
        if snap.revenue_growth_long_term is None:
            return "missing_revenue_forecast"
        if (
            sector_avg_pe is not None
            and snap.pe_ratio is not None
            and snap.pe_ratio >= sector_avg_pe
        ):
            return f"pe_above_sector_avg ({snap.pe_ratio:.1f} >= {sector_avg_pe:.1f})"
    if mode == "manufacturing" and min_eps_growth_next_year is not None:
        if snap.eps_growth_next_year is None or snap.eps_growth_next_year < min_eps_growth_next_year:
            return f"below_min_eps_growth ({min_eps_growth_next_year}%)"
    # If a min_confidence floor was applied, a low source/match confidence
    # would have been the gate. We can't re-derive match confidence here
    # without re-scoring, so describe the floor.
    if min_confidence > 0:
        return f"below_min_confidence_or_outside_top_n ({min_confidence})"
    return "outside_top_n"


def _round(value: float | None, ndigits: int) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), ndigits)
    except (TypeError, ValueError):
        return None


def _persist_monthly_snapshot(
    payload: Mapping[str, Any],
    *,
    snapshot_dir: str | Path | None,
) -> Path:
    root = Path(
        snapshot_dir) if snapshot_dir is not None else _default_snapshot_dir()
    root.mkdir(parents=True, exist_ok=True)
    month_key = _month_key(payload)
    kind = str(payload.get("kind") or "unknown")
    path = root / f"ism_{kind}_{month_key}.json"
    # Keep the first snapshot of the month as the source of truth.
    if not path.exists():
        path.write_text(json.dumps(payload, indent=2, default=str))
    return path


def _month_key(payload: Mapping[str, Any]) -> str:
    report_month = str(payload.get("report_month") or "").strip()
    if report_month:
        try:
            dt = datetime.strptime(report_month, "%B %Y")
            return dt.strftime("%Y-%m")
        except ValueError:
            pass

    generated_at = str(payload.get("generated_at") or "")
    if len(generated_at) >= 7:
        return generated_at[:7]
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _default_snapshot_dir() -> Path:
    # Repo-committed so monthly ISM rankings + reviewed-company data live
    # alongside the code (the local copy *is* the committed copy).
    return Path(__file__).resolve().parents[2] / "stocks_history"


def _latest_expected_covers_month(*, kind: str, today: date | None = None) -> str | None:
    """Return the latest expected data month for ``kind`` from stored calendars."""
    today = today or datetime.now(timezone.utc).date()
    latest_release_at: datetime | None = None
    latest_covers_month: str | None = None

    for year in (today.year - 1, today.year, today.year + 1):
        calendar = load_calendar(year)
        if calendar is None:
            continue
        for release in calendar.releases:
            if release.kind != kind or not release.covers_month:
                continue
            try:
                release_at = datetime.fromisoformat(release.release_at_utc)
            except ValueError:
                continue
            if release_at.date() > today:
                continue
            if latest_release_at is None or release_at > latest_release_at:
                latest_release_at = release_at
                latest_covers_month = release.covers_month

    return latest_covers_month
