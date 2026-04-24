"""Shared ISM industry report builder for CLI, MCP, and Hermes surfaces."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, cast

from trading.stocks.data_provider import MassiveClient, MassiveRateLimitError
from trading.stocks.ism_scraper import ISMReportFetcher
from trading.stocks.screener import SectorScreener, StockCandidate, StockScreenerError

# Keep this short so FMP daily-budget usage stays practical.
# The default basket leans toward names whose public-company industries map
# more cleanly onto ISM buckets than broad mega-cap sector placeholders do.
DEFAULT_UNIVERSE: dict[str, list[str]] = {
    "Information Technology": ["AAPL", "HPQ", "DELL", "AMAT", "GLW"],
    "Industrials": ["GE", "ETN", "CAT", "PH", "EMR", "ITW", "ROK"],
    "Health Care": ["LLY", "JNJ", "UNH", "ABT"],
    "Consumer Discretionary": ["NKE", "DECK", "WHR", "LEN", "MHK", "MLKN"],
    "Materials": ["NUE", "FCX", "IP", "DD", "LIN", "LYB", "DOW", "EMN"],
    "Energy": ["XOM", "PSX", "VLO", "MPC"],
    "Financials": ["JPM", "BAC", "V", "MS"],
    "Consumer Staples": ["MO", "KO", "MDLZ", "GIS", "KHC", "CPB", "PM"],
    "Communication Services": ["GOOGL", "META", "NFLX", "DIS"],
    "Utilities": ["NEE", "DUK", "SO"],
    "Real Estate": ["PLD", "AMT", "EQIX"],
}


def build_ism_industry_report(
    *,
    kind: str = "manufacturing",
    top_n: int = 10,
    max_sectors_per_trend: int = 4,
    min_eps_growth_next_year: float | None = None,
    min_confidence: float = 0.3,
    universe: Mapping[str, list[str]] | None = None,
    fetcher: ISMReportFetcher | None = None,
    massive: MassiveClient | None = None,
    persist_snapshot: bool = False,
    snapshot_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Build a complete ISM report with hottest/worst sectors and filtered names."""
    if kind not in {"manufacturing", "services"}:
        raise ValueError("kind must be 'manufacturing' or 'services'")

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
    )
    short_candidates = _safe_rank(
        screener,
        report=report,
        trend="contracting",
        top_n=top_n,
        max_sectors=max_sectors_per_trend,
        min_eps_growth_next_year=min_eps_growth_next_year,
        min_confidence=min_confidence,
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
    )

    expanding_primary_industry = _sector_primary_industry(report.expanding)
    contracting_primary_industry = _sector_primary_industry(report.contracting)
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
        "report_month": report.report_month,
        "pmi": report.pmi,
        "source_url": report.source_url,
        "criteria": {
            "top_n": top_n,
            "max_sectors_per_trend": max_sectors_per_trend,
            "min_eps_growth_next_year": min_eps_growth_next_year,
            "min_confidence": min_confidence,
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
                )
                for item in short_candidates
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
                )
                for item in short_candidates
            ],
        },
        "summary": {
            "hottest_sector_count": len(expanding_sectors),
            "worst_sector_count": len(contracting_sectors),
            "long_candidates": len(long_candidates),
            "short_candidates": len(short_candidates),
            "screened_symbol_count": len(screened_all_symbols),
            # Backward compatibility summary keys
            "expanding_candidates": len(long_candidates),
            "contracting_candidates": len(short_candidates),
        },
        "screened_universe": {
            **screened_by_trend,
            "all_symbols": screened_all_symbols,
        },
    }

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
        )
    except (StockScreenerError, MassiveRateLimitError):
        return []


def _candidate_to_dict(
    item: StockCandidate,
    *,
    ism_industry_hint: Mapping[str, str] | None = None,
    industry_momentum: str | None = None,
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

    return {
        "symbol": item.symbol,
        "company_name": item.company_name,
        "sector": item.sector,
        "industry": industry,
        "driver_industry": hinted_industry,
        "industry_source": industry_source,
        "industry_momentum": industry_momentum,
        "side": item.side,
        "confidence": round(item.confidence, 4),
        "match_confidence": round(item.match_confidence, 4),
        "score": round(item.score, 4),
        "eps_growth_next_year": round(item.eps_growth_next_year, 2) if item.eps_growth_next_year is not None else None,
        "eps_growth_source": item.eps_growth_source,
        "reason": item.reason,
    }


def _sector_primary_industry(rankings: list[Any]) -> dict[str, str]:
    """Build a best-effort sector->industry hint map from ISM rankings."""
    out: dict[str, str] = {}
    for item in rankings:
        sector = getattr(item, "gics_sector", None)
        industry = getattr(item, "industry", None)
        if isinstance(sector, str) and sector and isinstance(industry, str) and industry:
            out.setdefault(sector, industry)
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
) -> list[StockCandidate]:
    filtered: list[StockCandidate] = []
    for item in candidates:
        if item.confidence < min_confidence:
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


def _persist_monthly_snapshot(
    payload: Mapping[str, Any],
    *,
    snapshot_dir: str | Path | None,
) -> Path:
    root = Path(snapshot_dir) if snapshot_dir is not None else _default_snapshot_dir()
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
    return Path(__file__).resolve().parents[2] / "var" / "stocks_history"
