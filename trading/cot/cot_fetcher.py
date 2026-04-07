"""COT Fetcher for CME Commitment of Traders reports.

Downloads latest COT data for BTC and ETH from CFTC via OpenBB.
Caches weekly reports (released Fridays, analyzed Sundays).

Exact CFTC market names used for filtering:
  BTC: "BITCOIN - CHICAGO MERCANTILE EXCHANGE"
  ETH: "ETHER CASH SETTLED - CHICAGO MERCANTILE EXCHANGE"
  Micro BTC: "MICRO BITCOIN - CHICAGO MERCANTILE EXCHANGE"
  Micro ETH: "MICRO ETHER - CHICAGO MERCANTILE EXCHANGE"

Supports both Legacy Combined (deacmelof) and Futures Only (deacmesf) reports.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta
from html import unescape
from pathlib import Path
from typing import Any, Dict, Literal

import numpy as np
import pandas as pd
import requests

logger = logging.getLogger(__name__)

CACHE_DIR = Path.home() / ".cache" / "nave" / "cot"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_VERSION = 4
HISTORY_CACHE_FILE = CACHE_DIR / "history_cot.json"
MIN_PERCENTILE_HISTORY_WEEKS = 52
TARGET_PERCENTILE_HISTORY_WEEKS = 104

# CFTC contract codes for CME crypto futures
CFTC_CODES: dict[str, str] = {
    "BTC": "133741",
    "ETH": "146021",
}

# Exact CFTC market_and_exchange_names for robust filtering
MARKET_NAMES: dict[str, dict[str, str]] = {
    "BTC": {
        "main": "BITCOIN - CHICAGO MERCANTILE EXCHANGE",
        "micro": "MICRO BITCOIN - CHICAGO MERCANTILE EXCHANGE",
    },
    "ETH": {
        "main": "ETHER CASH SETTLED - CHICAGO MERCANTILE EXCHANGE",
        "micro": "MICRO ETHER - CHICAGO MERCANTILE EXCHANGE",
    },
}

ReportType = Literal["futures_only", "futures_and_options", "legacy_combined"]

CFTC_REPORT_URLS: dict[ReportType, str] = {
    "futures_only": "https://www.cftc.gov/dea/futures/deacmelf.htm",
    "futures_and_options": "https://www.cftc.gov/dea/options/deacmelof.htm",
    "legacy_combined": "https://www.cftc.gov/dea/options/deacmelof.htm",
}

NONCOMM_LONG_COLUMNS = [
    "noncomm_positions_long_all",
    "Noncommercial_Positions_Long",
]
NONCOMM_SHORT_COLUMNS = [
    "noncomm_positions_short_all",
    "Noncommercial_Positions_Short",
]
COMM_LONG_COLUMNS = [
    "comm_positions_long_all",
    "Commercial_Positions_Long",
]
COMM_SHORT_COLUMNS = [
    "comm_positions_short_all",
    "Commercial_Positions_Short",
]
OI_COLUMNS = [
    "open_interest_all",
    "Open_Interest_All",
]
TRADERS_NONCOMM_COLUMNS = [
    "number_of_traders_noncommercial_all",
    "Number_of_Traders_Noncommercial_All",
    "number_traders_noncommercial_all",
]
TRADERS_COMM_COLUMNS = [
    "number_of_traders_commercial_all",
    "Number_of_Traders_Commercial_All",
    "number_traders_commercial_all",
]
TRADERS_NONCOMM_LONG_COLUMNS = [
    "traders_noncomm_long_all",
    "traders_noncomm_long_old",
    "traders_noncomm_long_other",
]
TRADERS_NONCOMM_SHORT_COLUMNS = [
    "traders_noncomm_short_all",
    "traders_noncomm_short_old",
    "traders_noncomm_short_other",
]
TRADERS_COMM_LONG_COLUMNS = [
    "traders_comm_long_all",
    "traders_comm_long_old",
    "traders_comm_long_other",
]
TRADERS_COMM_SHORT_COLUMNS = [
    "traders_comm_short_all",
    "traders_comm_short_old",
    "traders_comm_short_other",
]
TRADERS_FIN_NONCOMM_COLUMNS = [
    "traders_asset_mgr_long_all",
    "traders_lev_money_long_all",
    "traders_other_rept_long_all",
]
TRADERS_FIN_COMM_COLUMNS = [
    "traders_dealer_long_all",
]
FIN_SPEC_LONG_COLUMNS = [
    "asset_mgr_positions_long",
    "lev_money_positions_long",
    "other_rept_positions_long",
]
FIN_SPEC_SHORT_COLUMNS = [
    "asset_mgr_positions_short",
    "lev_money_positions_short",
    "other_rept_positions_short",
]


def fetch_latest_cot(
    *,
    report_type: ReportType = "futures_and_options",
    include_micro: bool = False,
    debug: bool = False,
) -> Dict[str, Any]:
    """Fetch latest COT for BTC and ETH, with 7-day caching.

    Args:
        report_type: 'futures_only' (deacmelf) or 'futures_and_options' (deacmelof).
        include_micro: If True, include MICRO contracts in the filter.
        debug: If True, log raw DataFrame columns and unique market names.

    Returns:
        Dict mapping asset name -> {raw: list[dict], latest_date: str, symbol: str, cached: bool}
    """
    cache_file = CACHE_DIR / "latest_cot.json"
    today = datetime.now()
    report_type = _normalize_report_type(report_type)
    cache_key = f"{report_type}|micro={int(include_micro)}"

    # Check cache (valid for 7 days)
    if cache_file.exists():
        try:
            with open(cache_file) as f:
                cached = json.load(f)
            cached_version = int(cached.get("cache_version", 0))
            cached_key = str(cached.get("cache_key", ""))
            cache_date = datetime.fromisoformat(
                cached.get("fetch_date", "2000-01-01"))
            if cached_version != CACHE_VERSION:
                logger.debug(
                    "Ignoring stale COT cache: version %s != %s", cached_version, CACHE_VERSION)
            elif cached_key != cache_key:
                logger.debug(
                    "Ignoring stale COT cache: key %s != %s", cached_key, cache_key)
            elif (today - cache_date).days < 7:
                logger.debug("Using cached COT data (fetched %s)",
                             cache_date.date())
                data = cached["data"]
                for asset_name, v in data.items():
                    v["cached"] = True
                    rows = _augment_with_local_history(
                        asset=asset_name,
                        report_type=report_type,
                        include_micro=include_micro,
                        rows=v.get("raw", []),
                    )
                    if rows:
                        v["raw"] = rows
                return data
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning("Cache file corrupt (%s), re-fetching", exc)

    logger.debug("Fetching latest COT reports via OpenBB (%s)...", report_type)

    data: Dict[str, Any] = {}
    try:
        from openbb import obb

        # Fetch one combined DataFrame per asset via OpenBB CFTC endpoint
        for asset, symbol in [("BTC", "BTC"), ("ETH", "ETH")]:
            try:
                df = _fetch_openbb_cot(obb, asset, report_type, debug=debug)

                if debug:
                    _log_debug_info(df, asset)

                filtered = _filter_asset_rows(
                    df, asset, include_micro=include_micro, debug=debug)

                if filtered.empty:
                    direct_df, direct_as_of = _fetch_cftc_direct_asset_rows(
                        asset,
                        report_type=report_type,
                        include_micro=include_micro,
                        debug=debug,
                    )
                    if not direct_df.empty:
                        direct_release = _derive_release_date(direct_as_of)
                        data[asset] = {
                            "raw": direct_df.to_dict("records"),
                            "latest_date": direct_as_of,
                            "as_of_date": direct_as_of,
                            "release_date": direct_release,
                            "symbol": symbol,
                            "report_type": report_type,
                            "cached": False,
                            "source": "cftc_direct",
                        }
                        data[asset]["raw"] = _augment_with_local_history(
                            asset=asset,
                            report_type=report_type,
                            include_micro=include_micro,
                            rows=data[asset]["raw"],
                        )
                        _persist_history_rows(
                            asset=asset,
                            report_type=report_type,
                            include_micro=include_micro,
                            rows=data[asset]["raw"],
                        )
                        logger.debug(
                            "Fetched COT for %s from direct CFTC source: as-of %s, released %s",
                            asset,
                            direct_as_of,
                            direct_release,
                        )
                        continue

                    if debug:
                        logger.info(
                            "No rows matched for %s after filtering — falling back to mock data. "
                            "Check market_and_exchange_names values with --debug-cot.",
                            asset,
                        )
                    data[asset] = _mock_cot_data(asset)
                    continue

                latest_date = _extract_latest_date(filtered, today)
                filtered = _slice_to_as_of(filtered, latest_date)
                release_date = _derive_release_date(latest_date)
                data[asset] = {
                    "raw": filtered.to_dict("records"),
                    "latest_date": latest_date,
                    "as_of_date": latest_date,
                    "release_date": release_date,
                    "symbol": symbol,
                    "report_type": report_type,
                    "cached": False,
                }
                data[asset]["raw"] = _augment_with_local_history(
                    asset=asset,
                    report_type=report_type,
                    include_micro=include_micro,
                    rows=data[asset]["raw"],
                )
                _persist_history_rows(
                    asset=asset,
                    report_type=report_type,
                    include_micro=include_micro,
                    rows=data[asset]["raw"],
                )
                logger.debug(
                    "Fetched COT for %s: %d rows, as-of %s, released %s",
                    asset, len(filtered), latest_date, release_date,
                )

            except Exception as e_asset:
                logger.warning(
                    "COT fetch for %s failed: %s — using mock data", asset, e_asset)
                data[asset] = _mock_cot_data(asset)

    except Exception as e:
        logger.warning(
            "OpenBB COT fetch failed: %s — using mock data for all assets", e)
        data = {a: _mock_cot_data(a) for a in ["BTC", "ETH"]}

    # Cache result
    cache_data = {
        "fetch_date": today.isoformat(),
        "cache_version": CACHE_VERSION,
        "cache_key": cache_key,
        "data": data,
    }
    try:
        with open(cache_file, "w") as f:
            json.dump(cache_data, f, default=str, indent=2)
    except OSError as exc:
        logger.warning("Failed to write cache: %s", exc)

    return data


def _fetch_openbb_cot(obb: Any, asset: str, report_type: ReportType, *, debug: bool = False) -> pd.DataFrame:
    """Call OpenBB CFTC COT endpoint and return a DataFrame."""
    regulators = getattr(obb, "regulators", None)
    cftc = getattr(regulators, "cftc", None) if regulators else None
    cot_fn = getattr(cftc, "cot", None) if cftc else None
    if not callable(cot_fn):
        raise AttributeError("OpenBB CFTC COT endpoint is unavailable")

    normalized_report = _normalize_report_type(report_type)
    # OpenBB expects CFTC report types: legacy/disaggregated/financial/supplemental.
    # For crypto contracts, financial aligns with futures-only style output and
    # legacy aligns with combined futures+options style output.
    report_value = "financial" if normalized_report == "futures_only" else "legacy"
    cftc_code = CFTC_CODES.get(asset)
    market_main_name = MARKET_NAMES.get(asset, {}).get("main", "")
    history_start = (datetime.now(
    ) - timedelta(weeks=TARGET_PERCENTILE_HISTORY_WEEKS + 52)).date().isoformat()
    attempts = [
        {"id": cftc_code, "report_type": report_value,
            "start_date": history_start} if cftc_code else None,
        {"id": market_main_name, "report_type": report_value,
            "start_date": history_start} if market_main_name else None,
        {"id": cftc_code, "report_type": report_value} if cftc_code else None,
        {"id": market_main_name, "report_type": report_value} if market_main_name else None,
    ]

    last_exc: Exception | None = None
    best_df = pd.DataFrame()
    for kwargs in [a for a in attempts if a is not None]:
        try:
            result = cot_fn(**kwargs)
            if debug:
                logger.info(
                    "OpenBB COT call succeeded for %s with args: %s", asset, kwargs)
            df = _openbb_result_to_df(result)
            if df.empty:
                continue
            return df
        except TypeError as exc:
            last_exc = exc
            continue
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            continue

    if not best_df.empty:
        return best_df

    if last_exc is None:
        last_exc = RuntimeError("no non-empty OpenBB COT response")

    if best_df.empty:
        raise RuntimeError(
            f"OpenBB COT endpoint failed for {asset} and report_type={report_type}: {last_exc}"
        )
    # Unreachable in normal flow; keeps static type checkers satisfied.
    return pd.DataFrame()


def _openbb_result_to_df(result: Any) -> pd.DataFrame:
    """Convert OpenBB endpoint response into a DataFrame."""
    to_df = getattr(result, "to_df", None)
    if callable(to_df):
        converted = to_df()
        if isinstance(converted, pd.DataFrame):
            return converted
        if isinstance(converted, (list, tuple, dict)):
            return pd.DataFrame(converted)
        return pd.DataFrame()
    if isinstance(result, pd.DataFrame):
        return result
    if isinstance(result, (list, tuple, dict)):
        return pd.DataFrame(result)
    return pd.DataFrame()


def _filter_asset_rows(
    df: pd.DataFrame,
    asset: str,
    *,
    include_micro: bool = False,
    debug: bool = False,
) -> pd.DataFrame:
    """Filter DataFrame to keep only rows for the requested crypto asset.

    Uses strict contains matching against the exact canonical CFTC market names
    for BTC/ETH contracts, case-insensitive.
    Never falls back to broad keyword matching or full DataFrame passthrough.

    Args:
        df: Raw COT DataFrame from OpenBB.
        asset: "BTC" or "ETH".
        include_micro: If True, also include MICRO contract rows.
    """
    if df.empty:
        return df

    # Find the market name column (case varies between OpenBB versions)
    market_col = _find_column(
        df, ["market_and_exchange_names", "Market_and_Exchange_Names"])
    if market_col is None:
        logger.warning(
            "No market_and_exchange_names column found in COT data. "
            "Available columns: %s", list(df.columns),
        )
        return pd.DataFrame()

    names_upper = df[market_col].astype(str).str.upper().str.strip()
    asset_upper = asset.upper()
    names_cfg = MARKET_NAMES.get(asset_upper)

    if names_cfg is None:
        logger.warning("Unknown asset %s — no CFTC market name mapping", asset)
        return pd.DataFrame()

    # Log all unique market names for debugging
    unique_names = names_upper.unique().tolist()
    if debug:
        logger.info("Unique market names in DataFrame (%d): %s",
                    len(unique_names), unique_names)

    # --- Strategy 1: Exact match on known CFTC market names ---
    main_name = names_cfg["main"].upper()
    micro_name = names_cfg["micro"].upper()

    main_mask = names_upper.str.contains(
        re.escape(main_name), na=False, regex=True)
    if include_micro:
        micro_mask = names_upper.str.contains(
            re.escape(micro_name), na=False, regex=True)
        mask = main_mask | micro_mask
    else:
        mask = main_mask

    filtered = df[mask].copy()
    if not filtered.empty:
        filtered = _validate_filtered_rows(filtered, asset, market_col)
        if filtered.empty:
            return filtered
        if debug:
            logger.info(
                "Exact match for %s: %d rows (include_micro=%s)",
                asset, len(filtered), include_micro,
            )
            logger.info("Filtered market names for %s: %s", asset,
                        filtered[market_col].astype(str).unique().tolist())
        return filtered

    # --- No match: return empty, do NOT fall back to full DataFrame ---
    if debug:
        logger.info(
            "No COT rows matched for %s. Unique market names in data: %s",
            asset, unique_names[:20],
        )
    return pd.DataFrame()


def _extract_latest_date(df: pd.DataFrame, fallback: datetime) -> str:
    """Extract the latest report date from a filtered DataFrame."""
    latest_released: date | None = None
    for date_col in (
        "report_date_as_yyyy_mm_dd",
        "report_date_as_of_yyyy_mm_dd",
        "Report_Date_as_of",
        "Report_Date_as_of_yyyy_mm_dd",
        "report_date",
        "date",
    ):
        if date_col in df.columns:
            series = pd.to_datetime(df[date_col], errors="coerce").dropna()
            if not series.empty:
                dates = sorted({d.date() for d in series.tolist()})
                for d in dates:
                    rel = pd.to_datetime(_derive_release_date(
                        d.isoformat()), errors="coerce")
                    if pd.notna(rel) and rel.date() <= fallback.date():
                        latest_released = d
                if latest_released is not None:
                    return latest_released.isoformat()
                return dates[-1].isoformat()

    # OpenBB CFTC often provides report_week strings like "2026 Report Week 13"
    # plus an `id` with YYMMDD prefix (e.g. 260331133741C). Prefer id-derived date.
    if "id" in df.columns:
        ids = df["id"].dropna().astype(str)
        parsed_dates: list[date] = []
        for raw_id in ids:
            m = re.match(r"^(\d{6})", raw_id)
            if not m:
                continue
            parsed = pd.to_datetime(
                m.group(1), format="%y%m%d", errors="coerce")
            if pd.notna(parsed):
                parsed_dates.append(parsed.date())
        if parsed_dates:
            return max(parsed_dates).isoformat()

    return str(fallback.date())


def _slice_to_as_of(df: pd.DataFrame, as_of_date: str) -> pd.DataFrame:
    """Trim rows to <= as_of_date to avoid using unreleased report-week rows."""
    if df.empty:
        return df

    as_of = pd.to_datetime(as_of_date, errors="coerce")
    if pd.isna(as_of):
        return df

    for date_col in (
        "report_date_as_yyyy_mm_dd",
        "report_date_as_of_yyyy_mm_dd",
        "Report_Date_as_of",
        "Report_Date_as_of_yyyy_mm_dd",
        "report_date",
        "date",
    ):
        if date_col in df.columns:
            parsed = pd.to_datetime(df[date_col], errors="coerce")
            mask = parsed <= as_of
            sliced = df[mask].copy()
            if not sliced.empty:
                return sliced
    return df


def _derive_release_date(as_of_date: str) -> str:
    """Derive official COT release date (Friday) from as-of report date (usually Tuesday)."""
    parsed = pd.to_datetime(as_of_date, errors="coerce")
    if pd.isna(parsed):
        return "N/A"
    as_of = parsed.date()
    # Monday=0 ... Friday=4
    days_to_friday = (4 - as_of.weekday()) % 7
    release = as_of + timedelta(days=days_to_friday)
    return release.isoformat()


def _fetch_cftc_direct_asset_rows(
    asset: str,
    *,
    report_type: ReportType,
    include_micro: bool,
    debug: bool,
) -> tuple[pd.DataFrame, str]:
    """Fallback parser for direct CFTC long report pages.

    Parses official CFTC CME long report HTML pages when OpenBB cannot provide
    crypto rows in this environment.
    """
    normalized_report = _normalize_report_type(report_type)
    url = CFTC_REPORT_URLS[normalized_report]
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Direct CFTC fetch failed for %s (%s): %s", asset, url, exc)
        return pd.DataFrame(), "N/A"

    m = re.search(r"<pre[^>]*>(.*?)</pre>", resp.text,
                  re.IGNORECASE | re.DOTALL)
    if not m:
        logger.warning(
            "Direct CFTC parser could not find <pre> section in %s", url)
        return pd.DataFrame(), "N/A"

    pre_text = unescape(m.group(1))
    lines = [ln.rstrip("\n") for ln in pre_text.splitlines()]

    market_candidates = [MARKET_NAMES[asset]["main"]]
    if include_micro:
        market_candidates.append(MARKET_NAMES[asset]["micro"])

    if debug:
        all_market_headers = [
            ln.strip() for ln in lines if "CODE-" in ln.upper() and "CHICAGO" in ln.upper()
        ]
        logger.info("Direct CFTC available market headers (%d)",
                    len(all_market_headers))
        for ln in all_market_headers:
            logger.info("  - %s", ln)

    frames: list[pd.DataFrame] = []
    selected_as_of = "N/A"
    for market_name in market_candidates:
        block_df, as_of = _parse_cftc_market_block(lines, market_name)
        if not block_df.empty:
            frames.append(block_df)
            selected_as_of = as_of
            # Prefer main contract; only include micro if explicitly requested and main missing.
            if market_name == MARKET_NAMES[asset]["main"]:
                break

    if not frames:
        logger.warning("Direct CFTC parser found no %s rows in %s", asset, url)
        return pd.DataFrame(), "N/A"

    return pd.concat(frames, ignore_index=True), selected_as_of


def _parse_cftc_market_block(lines: list[str], market_name: str) -> tuple[pd.DataFrame, str]:
    """Parse a single market block (e.g., BITCOIN CME) from CFTC long report lines."""
    target = market_name.upper()
    header_idx = -1
    for i, line in enumerate(lines):
        if target in line.upper() and "CODE-" in line.upper():
            header_idx = i
            break

    if header_idx < 0:
        return pd.DataFrame(), "N/A"

    as_of = "N/A"
    for j in range(header_idx + 1, min(header_idx + 8, len(lines))):
        mm = re.search(r"([A-Za-z]+\s+\d{1,2},\s+\d{4})", lines[j])
        if mm:
            try:
                parsed = pd.to_datetime(mm.group(1), errors="coerce")
                if pd.notna(parsed):
                    as_of = parsed.date().isoformat()
            except Exception:  # noqa: BLE001
                as_of = "N/A"
            break

    next_header = len(lines)
    for k in range(header_idx + 1, len(lines)):
        if "CODE-" in lines[k].upper() and k > header_idx:
            next_header = k
            break
    block = lines[header_idx:next_header]

    all_line = next(
        (ln for ln in block if ln.strip().startswith("All  :")), "")
    change_hdr_idx = next((idx for idx, ln in enumerate(
        block) if "CHANGES IN COMMITMENTS FROM" in ln.upper()), -1)
    change_line = ""
    if change_hdr_idx >= 0 and change_hdr_idx + 1 < len(block):
        change_line = block[change_hdr_idx + 1]

    if not all_line:
        return pd.DataFrame(), "N/A"

    def ints_from_line(s: str) -> list[int]:
        vals = re.findall(r"[-+]?\d[\d,]*", s)
        out: list[int] = []
        for v in vals:
            out.append(int(v.replace(",", "")))
        return out

    all_vals = ints_from_line(all_line)
    change_vals = ints_from_line(change_line) if change_line else []
    if len(all_vals) < 6:
        return pd.DataFrame(), "N/A"

    # CFTC All line order:
    # OI, noncomm_long, noncomm_short, spreading, comm_long, comm_short, ...
    oi = all_vals[0]
    noncomm_long = all_vals[1]
    noncomm_short = all_vals[2]
    comm_long = all_vals[4]
    comm_short = all_vals[5]

    # Changes line has same leading order when present.
    change_oi = change_vals[0] if len(change_vals) > 0 else 0
    change_noncomm_long = change_vals[1] if len(change_vals) > 1 else 0
    change_noncomm_short = change_vals[2] if len(change_vals) > 2 else 0

    row = {
        "report_date": as_of,
        "report_date_as_yyyy_mm_dd": as_of,
        "market_and_exchange_names": market_name,
        "open_interest_all": oi,
        "noncomm_positions_long_all": noncomm_long,
        "noncomm_positions_short_all": noncomm_short,
        "comm_positions_long_all": comm_long,
        "comm_positions_short_all": comm_short,
        "change_in_open_interest_all": change_oi,
        "change_in_noncomm_long_all": change_noncomm_long,
        "change_in_noncomm_short_all": change_noncomm_short,
    }
    return pd.DataFrame([row]), as_of


def _validate_filtered_rows(df: pd.DataFrame, asset: str, market_col: str) -> pd.DataFrame:
    """Validate filtered rows belong to the requested asset contract family only."""
    if df.empty:
        return df

    names = df[market_col].astype(str).str.upper().tolist()
    has_btc = any("BITCOIN" in n for n in names)
    has_eth = any("ETHER" in n for n in names)

    if asset.upper() == "BTC" and (has_eth or not has_btc):
        logger.debug(
            "Filtered BTC rows contain invalid market names: %s", sorted(set(names))[:10])
        return pd.DataFrame()
    if asset.upper() == "ETH" and (has_btc or not has_eth):
        logger.debug(
            "Filtered ETH rows contain invalid market names: %s", sorted(set(names))[:10])
        return pd.DataFrame()
    return df


def _find_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    """Return the first column name that exists in df."""
    for c in candidates:
        if c in df.columns:
            return c
    return None


def _normalize_report_type(report_type: str) -> ReportType:
    """Normalize report type aliases to supported values."""
    rt = str(report_type).strip().lower()
    if rt in {"futures_only"}:
        return "futures_only"
    if rt in {"futures_and_options", "legacy_combined"}:
        return "futures_and_options"
    raise ValueError(f"Unsupported report_type: {report_type}")


def _log_debug_info(df: pd.DataFrame, asset: str) -> None:
    """Log detailed debug information about the raw DataFrame."""
    logger.info("=== DEBUG COT: %s ===", asset)
    logger.info("DataFrame shape: %s", df.shape)
    logger.info("Columns: %s", list(df.columns))

    market_col = _find_column(
        df, ["market_and_exchange_names", "Market_and_Exchange_Names"])
    if market_col:
        unique = df[market_col].unique().tolist()
        logger.info("Unique market_and_exchange_names (%d):", len(unique))
        for name in unique:
            logger.info("  - %s", name)
    else:
        logger.info("No market_and_exchange_names column found")

    if not df.empty:
        logger.info("First row sample: %s", dict(df.iloc[0]))
        logger.info("Last row sample: %s", dict(df.iloc[-1]))
    logger.info("=== END DEBUG COT: %s ===", asset)


def _mock_cot_data(asset: str) -> Dict[str, Any]:
    """Generate realistic mock COT data for development/demo when API fails.

    Produces distinct values for BTC vs ETH to avoid the duplication bug.
    Uses deterministic seeds per asset for reproducibility.
    """
    seed = 42 if asset == "BTC" else 99
    rng = np.random.default_rng(seed)
    today = datetime.now()

    # Generate ~52 weeks of synthetic data with distinct profiles per asset
    dates = pd.date_range(end=today, periods=52, freq="W-TUE")

    if asset == "BTC":
        # BTC: larger contracts, specs tend net short, higher OI
        base_oi = 55_000
        base_long = 22_000
        base_short = 28_000
        comm_long_base = 18_000
        comm_short_base = 14_000
    else:
        # ETH: smaller contracts, different positioning
        base_oi = 12_000
        base_long = 5_500
        base_short = 4_200
        comm_long_base = 3_800
        comm_short_base = 4_500

    records = []
    for i, date in enumerate(dates):
        cycle = np.sin(i / 8) * 0.15
        noise = rng.normal(0, 0.05)
        factor = 1.0 + cycle + noise

        noncomm_long = int(base_long * factor)
        noncomm_short = int(base_short * (1.0 + rng.normal(0, 0.08)))
        comm_long = int(comm_long_base * (1.0 + rng.normal(0, 0.06)))
        comm_short = int(comm_short_base * (1.0 + rng.normal(0, 0.06)))
        oi = int(base_oi * (1.0 + rng.normal(0, 0.04)))

        records.append({
            "report_date": str(date.date()),
            "noncomm_positions_long_all": noncomm_long,
            "noncomm_positions_short_all": noncomm_short,
            "comm_positions_long_all": comm_long,
            "comm_positions_short_all": comm_short,
            "open_interest_all": oi,
            "market_and_exchange_names": MARKET_NAMES[asset]["main"],
        })

    all_dates = pd.DataFrame(records)
    as_of = _extract_latest_date(all_dates, today)
    records = [r for r in records if pd.to_datetime(
        r["report_date"], errors="coerce").date() <= pd.to_datetime(as_of).date()]
    latest = records[-1]
    net = latest["noncomm_positions_long_all"] - \
        latest["noncomm_positions_short_all"]
    net_comm = latest["comm_positions_long_all"] - \
        latest["comm_positions_short_all"]
    oi = latest["open_interest_all"]
    pct = round(abs(net) / oi * 100, 2) if oi else 0.0
    prev = records[-2] if len(records) >= 2 else records[-1]
    prev_net = prev["noncomm_positions_long_all"] - \
        prev["noncomm_positions_short_all"]
    change = net - prev_net

    return {
        "raw": records,
        "latest_date": as_of,
        "as_of_date": as_of,
        "release_date": _derive_release_date(as_of),
        "symbol": asset,
        "cached": False,
        # Pre-computed fields for fallback (also computed by analyzer from raw)
        "net_non_commercial": net,
        "net_commercial": net_comm,
        "pct_oi_non_com": pct,
        "change": change,
        "open_interest": oi,
    }


def _history_cache_key(asset: str, report_type: ReportType, include_micro: bool) -> str:
    return f"{asset.upper()}|{report_type}|micro={int(include_micro)}"


def _load_history_cache() -> dict[str, list[dict[str, Any]]]:
    if not HISTORY_CACHE_FILE.exists():
        return {}
    try:
        with open(HISTORY_CACHE_FILE) as f:
            parsed = json.load(f)
        if isinstance(parsed, dict):
            return {str(k): list(v) for k, v in parsed.items() if isinstance(v, list)}
    except (OSError, json.JSONDecodeError):
        return {}
    return {}


def _save_history_cache(cache: dict[str, list[dict[str, Any]]]) -> None:
    try:
        with open(HISTORY_CACHE_FILE, "w") as f:
            json.dump(cache, f, default=str, indent=2)
    except OSError:
        return


def _row_date_value(row: dict[str, Any]) -> str:
    for date_key in (
        "report_date_as_yyyy_mm_dd",
        "report_date_as_of_yyyy_mm_dd",
        "Report_Date_as_of",
        "report_date",
        "date",
    ):
        if date_key in row and row[date_key]:
            return str(row[date_key])

    raw_id = str(row.get("id", ""))
    m_id = re.match(r"^(\d{6})", raw_id)
    if m_id:
        parsed = pd.to_datetime(m_id.group(
            1), format="%y%m%d", errors="coerce")
        if pd.notna(parsed):
            return parsed.date().isoformat()

    report_week = str(row.get("report_week", ""))
    m_week = re.search(r"(\d{4})\s+Report Week\s+(\d{1,2})", report_week)
    if m_week:
        try:
            year = int(m_week.group(1))
            week = int(m_week.group(2))
            # CFTC report week aligns closest to Tuesday observations.
            return datetime.fromisocalendar(year, week, 2).date().isoformat()
        except ValueError:
            pass
    return "N/A"


def _row_dedupe_key(row: dict[str, Any]) -> tuple[str, str]:
    market_name = str(row.get("market_and_exchange_names", "")).upper().strip()
    return (_row_date_value(row), market_name)


def _dedupe_and_sort_rows(rows: list[dict[str, Any]], *, max_points: int = TARGET_PERCENTILE_HISTORY_WEEKS) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        if isinstance(row, dict):
            deduped[_row_dedupe_key(row)] = row
    unique_rows = list(deduped.values())
    unique_rows.sort(key=lambda r: _row_date_value(r))
    return unique_rows[-max_points:]


def _augment_with_local_history(
    *,
    asset: str,
    report_type: ReportType,
    include_micro: bool,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    history = _load_history_cache()
    key = _history_cache_key(asset, report_type, include_micro)
    existing = history.get(key, [])
    merged = _dedupe_and_sort_rows(existing + list(rows))
    return merged


def _persist_history_rows(
    *,
    asset: str,
    report_type: ReportType,
    include_micro: bool,
    rows: list[dict[str, Any]],
) -> None:
    history = _load_history_cache()
    key = _history_cache_key(asset, report_type, include_micro)
    history[key] = _dedupe_and_sort_rows(history.get(
        key, []) + list(rows), max_points=TARGET_PERCENTILE_HISTORY_WEEKS)
    _save_history_cache(history)


def fetch_cot_sections(
    *,
    include_micro: bool = False,
    debug: bool = False,
) -> dict[str, dict[str, Any]]:
    """Fetch Futures Only + Futures and Options and derive section snapshots.

    Returns a per-asset mapping with `futures_only`, `combined`, and optional
    `options` metrics (derived by subtraction when valid).
    """
    futures_only_data = fetch_latest_cot(
        report_type="futures_only",
        include_micro=include_micro,
        debug=debug,
    )
    combined_data = fetch_latest_cot(
        report_type="futures_and_options",
        include_micro=include_micro,
        debug=debug,
    )

    return build_cot_sections_from_datasets(
        futures_only_data=futures_only_data,
        combined_data=combined_data,
    )


def build_cot_sections_from_datasets(
    *,
    futures_only_data: dict[str, Any],
    combined_data: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Build per-asset section metrics from already-fetched COT datasets."""
    assets = sorted(set(futures_only_data.keys()) | set(combined_data.keys()))
    out: dict[str, dict[str, Any]] = {}
    for asset in assets:
        fo_asset = futures_only_data.get(asset, {})
        co_asset = combined_data.get(asset, {})

        futures_only_metrics = _extract_section_metrics(
            fo_asset.get("raw", []))
        combined_metrics = _extract_section_metrics(co_asset.get("raw", []))
        options_metrics, options_validation = _derive_options_metrics(
            futures_only_metrics,
            combined_metrics,
        )

        out[asset] = {
            "asset": asset,
            "as_of_date": co_asset.get("as_of_date", co_asset.get("latest_date", "N/A")),
            "release_date": co_asset.get("release_date", "N/A"),
            "cached_futures_only": bool(fo_asset.get("cached", False)),
            "cached_combined": bool(co_asset.get("cached", False)),
            "futures_only": futures_only_metrics,
            "combined": combined_metrics,
            "options": options_metrics if options_validation["valid"] else None,
            "options_validation": options_validation,
            "raw": {
                "futures_only": fo_asset.get("raw", []),
                "combined": co_asset.get("raw", []),
            },
        }
    return out


def _derive_options_metrics(
    futures_only: dict[str, Any] | None,
    combined: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    if not futures_only or not combined:
        return None, {
            "valid": False,
            "reason": "missing_futures_or_combined",
        }

    required_keys = [
        "net_non_commercial",
        "net_non_commercial_delta",
        "net_commercial",
        "net_commercial_delta",
        "open_interest",
        "open_interest_delta",
        "traders_non_commercial",
        "traders_commercial",
    ]
    missing = [
        key for key in required_keys
        if key not in futures_only or key not in combined
    ]
    if missing:
        return None, {
            "valid": False,
            "reason": "missing_required_keys",
            "missing": missing,
        }

    if any(futures_only.get(key) is None or combined.get(key) is None for key in required_keys):
        return None, {
            "valid": False,
            "reason": "missing_required_values",
        }

    options: dict[str, Any] = {
        "net_non_commercial": int(combined["net_non_commercial"] - futures_only["net_non_commercial"]),
        "net_non_commercial_delta": int(combined["net_non_commercial_delta"] - futures_only["net_non_commercial_delta"]),
        "net_commercial": int(combined["net_commercial"] - futures_only["net_commercial"]),
        "net_commercial_delta": int(combined["net_commercial_delta"] - futures_only["net_commercial_delta"]),
        "open_interest": int(combined["open_interest"] - futures_only["open_interest"]),
        "open_interest_delta": int(combined["open_interest_delta"] - futures_only["open_interest_delta"]),
        "traders_non_commercial": int(combined["traders_non_commercial"] - futures_only["traders_non_commercial"]),
        "traders_commercial": int(combined["traders_commercial"] - futures_only["traders_commercial"]),
    }

    if options["open_interest"] < 0:
        return None, {
            "valid": False,
            "reason": "negative_open_interest",
            "value": options["open_interest"],
        }
    if options["traders_non_commercial"] < 0 or options["traders_commercial"] < 0:
        return None, {
            "valid": False,
            "reason": "negative_trader_count",
            "non_commercial": options["traders_non_commercial"],
            "commercial": options["traders_commercial"],
        }

    oi = options["open_interest"]
    options["pct_oi"] = round((options["net_non_commercial"] / oi) * 100,
                              1) if oi else None

    return options, {
        "valid": True,
        "reason": "ok",
    }


def _extract_section_metrics(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None

    df = pd.DataFrame(_dedupe_and_sort_rows(rows, max_points=500))
    if df.empty:
        return None

    latest_noncomm, prev_noncomm = _extract_net_pair(
        df,
        NONCOMM_LONG_COLUMNS,
        NONCOMM_SHORT_COLUMNS,
        FIN_SPEC_LONG_COLUMNS,
        FIN_SPEC_SHORT_COLUMNS,
    )
    latest_comm, prev_comm = _extract_net_pair(
        df,
        COMM_LONG_COLUMNS,
        COMM_SHORT_COLUMNS,
        [],
        [],
    )
    latest_oi, prev_oi = _extract_single_pair(df, OI_COLUMNS)

    if latest_noncomm is None:
        latest_noncomm = 0.0
    if latest_comm is None:
        latest_comm = 0.0
    if latest_oi is None:
        latest_oi = 0.0

    delta_noncomm = _resolve_net_delta(
        latest_noncomm,
        prev_noncomm,
        df,
        "change_in_noncomm_long_all",
        "change_in_noncomm_short_all",
        (
            "change_in_asset_mgr_long",
            "change_in_lev_money_long",
            "change_in_other_rept_long",
        ),
        (
            "change_in_asset_mgr_short",
            "change_in_lev_money_short",
            "change_in_other_rept_short",
        ),
    )
    delta_comm = _resolve_net_delta(
        latest_comm,
        prev_comm,
        df,
        "change_in_comm_long_all",
        "change_in_comm_short_all",
        (),
        (),
    )
    delta_oi = _resolve_value_delta(
        latest_oi,
        prev_oi,
        df,
        "change_in_open_interest_all",
    )

    traders_noncomm = _extract_trader_all_count(
        df,
        direct_aliases=TRADERS_NONCOMM_COLUMNS,
        long_aliases=TRADERS_NONCOMM_LONG_COLUMNS,
        short_aliases=TRADERS_NONCOMM_SHORT_COLUMNS,
        fallback_sum_aliases=TRADERS_FIN_NONCOMM_COLUMNS,
    )
    traders_comm = _extract_trader_all_count(
        df,
        direct_aliases=TRADERS_COMM_COLUMNS,
        long_aliases=TRADERS_COMM_LONG_COLUMNS,
        short_aliases=TRADERS_COMM_SHORT_COLUMNS,
        fallback_sum_aliases=TRADERS_FIN_COMM_COLUMNS,
    )

    oi_for_pct = float(latest_oi)
    pct_oi = round((float(latest_noncomm) / oi_for_pct) * 100,
                   1) if oi_for_pct else None

    return {
        "net_non_commercial": int(round(latest_noncomm)),
        "net_non_commercial_delta": int(round(delta_noncomm)),
        "net_commercial": int(round(latest_comm)),
        "net_commercial_delta": int(round(delta_comm)),
        "open_interest": int(round(latest_oi)),
        "open_interest_delta": int(round(delta_oi)),
        "pct_oi": pct_oi,
        "traders_non_commercial": traders_noncomm,
        "traders_commercial": traders_comm,
    }


def _extract_net_pair(
    df: pd.DataFrame,
    long_aliases: list[str],
    short_aliases: list[str],
    fallback_long_cols: list[str],
    fallback_short_cols: list[str],
) -> tuple[float | None, float | None]:
    long_col = _first_existing_from_df(df, long_aliases)
    short_col = _first_existing_from_df(df, short_aliases)
    if long_col:
        latest_long, prev_long = _extract_single_pair(df, [long_col])
        latest_short, prev_short = _extract_single_pair(
            df, [short_col] if short_col else [])
        latest_net = (latest_long or 0.0) - (latest_short or 0.0)
        prev_net = None
        if prev_long is not None or prev_short is not None:
            prev_net = (prev_long or 0.0) - (prev_short or 0.0)
        return latest_net, prev_net

    if fallback_long_cols and fallback_short_cols:
        existing_longs = [c for c in fallback_long_cols if c in df.columns]
        existing_shorts = [c for c in fallback_short_cols if c in df.columns]
        if existing_longs and existing_shorts:
            latest_long = sum(_safe_float(df[c].iloc[-1])
                              for c in existing_longs)
            latest_short = sum(_safe_float(df[c].iloc[-1])
                               for c in existing_shorts)
            latest_net = latest_long - latest_short
            prev_net = None
            if len(df) >= 2:
                prev_long = sum(_safe_float(df[c].iloc[-2])
                                for c in existing_longs)
                prev_short = sum(_safe_float(df[c].iloc[-2])
                                 for c in existing_shorts)
                prev_net = prev_long - prev_short
            return latest_net, prev_net

    return None, None


def _extract_single_pair(df: pd.DataFrame, aliases: list[str]) -> tuple[float | None, float | None]:
    col = _first_existing_from_df(df, aliases)
    if not col:
        return None, None
    latest = _safe_float(df[col].iloc[-1])
    prev = _safe_float(df[col].iloc[-2]) if len(df) >= 2 else None
    return latest, prev


def _resolve_net_delta(
    latest_net: float,
    prev_net: float | None,
    df: pd.DataFrame,
    long_change_col: str,
    short_change_col: str,
    long_change_group: tuple[str, ...],
    short_change_group: tuple[str, ...],
) -> float:
    if prev_net is not None:
        return latest_net - prev_net
    if long_change_col in df.columns and short_change_col in df.columns:
        return _safe_float(df[long_change_col].iloc[-1]) - _safe_float(df[short_change_col].iloc[-1])
    if long_change_group and short_change_group:
        if all(col in df.columns for col in long_change_group) and all(col in df.columns for col in short_change_group):
            long_total = sum(_safe_float(df[col].iloc[-1])
                             for col in long_change_group)
            short_total = sum(_safe_float(df[col].iloc[-1])
                              for col in short_change_group)
            return long_total - short_total
    return 0.0


def _resolve_value_delta(latest_value: float, prev_value: float | None, df: pd.DataFrame, delta_col: str) -> float:
    if prev_value is not None:
        return latest_value - prev_value
    if delta_col in df.columns:
        return _safe_float(df[delta_col].iloc[-1])
    return 0.0


def _extract_latest_int(df: pd.DataFrame, aliases: list[str]) -> int | None:
    col = _first_existing_from_df(df, aliases)
    if not col:
        return None
    val = _safe_float(df[col].iloc[-1], default=float("nan"))
    if pd.isna(val):
        return None
    return int(round(val))


def _extract_trader_all_count(
    df: pd.DataFrame,
    *,
    direct_aliases: list[str],
    long_aliases: list[str],
    short_aliases: list[str],
    fallback_sum_aliases: list[str],
) -> int | None:
    direct = _extract_latest_int(df, direct_aliases)
    if direct is not None:
        return direct

    long_val = _extract_latest_int(df, long_aliases)
    short_val = _extract_latest_int(df, short_aliases)
    if long_val is not None or short_val is not None:
        # Trader categories are typically reported by side; take max(long, short)
        # as a stable proxy for category-level participation (All).
        return max(long_val or 0, short_val or 0)

    fallback_values = [
        _extract_latest_int(df, [col]) for col in fallback_sum_aliases
    ]
    fallback_values = [v for v in fallback_values if v is not None]
    if fallback_values:
        return int(sum(fallback_values))

    return None


def _first_existing_from_df(df: pd.DataFrame, aliases: list[str]) -> str | None:
    for col in aliases:
        if col in df.columns:
            return col
    return None


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        out = float(value)
        return default if pd.isna(out) else out
    except (TypeError, ValueError):
        return default


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG,
                        format="%(levelname)s: %(message)s")
    data = fetch_latest_cot(debug=True)
    print("\nCOT Data keys:", list(data.keys()))
    for k, v in data.items():
        raw = v.get("raw", [])
        if raw:
            latest = raw[-1]
            long_val = latest.get("noncomm_positions_long_all", 0)
            short_val = latest.get("noncomm_positions_short_all", 0)
            net = long_val - short_val
            print(
                f"{k}: net_non_commercial={net:+,} ({len(raw)} rows, date={v.get('latest_date')})")
        else:
            print(
                f"{k}: net={v.get('net_non_commercial', 'N/A')} (mock/pre-computed)")
