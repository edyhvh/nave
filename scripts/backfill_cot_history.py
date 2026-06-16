#!/usr/bin/env python3
"""Backfill BTC/ETH COT history from official CFTC annual archives."""

from __future__ import annotations

import argparse
import io
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from trading.crypto.cot.cot_fetcher import HISTORY_CACHE_FILE, MARKET_NAMES  # noqa: E402

CFTC_HISTORY_BASE = "https://www.cftc.gov/files/dea/history"
REPORT_ARCHIVES = {
    "futures_and_options": "deahistfo{year}.zip",
    "futures_only": "deacot{year}.zip",
}

COLUMN_MAP = {
    "Market and Exchange Names": "market_and_exchange_names",
    "As of Date in Form YYYY-MM-DD": "report_date_as_yyyy_mm_dd",
    "Open Interest (All)": "open_interest_all",
    "Noncommercial Positions-Long (All)": "noncomm_positions_long_all",
    "Noncommercial Positions-Short (All)": "noncomm_positions_short_all",
    "Commercial Positions-Long (All)": "comm_positions_long_all",
    "Commercial Positions-Short (All)": "comm_positions_short_all",
    "Change in Open Interest (All)": "change_in_open_interest_all",
    "Change in Noncommercial-Long (All)": "change_in_noncomm_long_all",
    "Change in Noncommercial-Short (All)": "change_in_noncomm_short_all",
}


def _history_cache_key(asset: str, report_type: str, include_micro: bool) -> str:
    return f"{asset.upper()}|{report_type}|micro={int(include_micro)}"


def _load_cache(path: Path = HISTORY_CACHE_FILE) -> dict[str, list[dict[str, Any]]]:
    if not path.exists():
        return {}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {str(key): list(value) for key, value in parsed.items() if isinstance(value, list)}


def _row_date_value(row: dict[str, Any]) -> str:
    return str(row.get("report_date_as_yyyy_mm_dd") or row.get("report_date") or "N/A")


def _dedupe_sort(rows: list[dict[str, Any]], *, max_points: int) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        market = str(row.get("market_and_exchange_names", "")).upper().strip()
        deduped[(_row_date_value(row), market)] = row
    ordered = list(deduped.values())
    ordered.sort(key=_row_date_value)
    return ordered[-max_points:]


def _annual_archive_url(report_type: str, year: int) -> str:
    try:
        filename = REPORT_ARCHIVES[report_type].format(year=year)
    except KeyError as exc:
        raise ValueError(f"unsupported report_type: {report_type}") from exc
    return f"{CFTC_HISTORY_BASE}/{filename}"


def fetch_annual_frame(report_type: str, year: int) -> pd.DataFrame:
    url = _annual_archive_url(report_type, year)
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = [name for name in archive.namelist() if not name.endswith("/")]
        if not names:
            return pd.DataFrame()
        with archive.open(names[0]) as handle:
            return pd.read_csv(handle, low_memory=False)


def extract_asset_rows(
    frame: pd.DataFrame,
    *,
    asset: str,
    include_micro: bool = False,
) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    market_col = "Market and Exchange Names"
    if market_col not in frame.columns:
        return []

    names = MARKET_NAMES[asset.upper()]
    allowed = [names["main"]]
    if include_micro:
        allowed.append(names["micro"])

    mask = frame[market_col].astype(str).str.upper().str.strip().isin(
        {name.upper() for name in allowed}
    )
    filtered = frame.loc[mask].copy()
    if filtered.empty:
        return []

    rows: list[dict[str, Any]] = []
    for _, raw in filtered.iterrows():
        row: dict[str, Any] = {}
        for source, target in COLUMN_MAP.items():
            if source in raw:
                value = raw[source]
                if pd.isna(value):
                    continue
                row[target] = value.item() if hasattr(value, "item") else value
        if "report_date_as_yyyy_mm_dd" in row:
            row["report_date"] = row["report_date_as_yyyy_mm_dd"]
        row["source"] = "cftc_historical_compressed"
        rows.append(row)
    return rows


def backfill(
    *,
    years: list[int],
    report_types: list[str],
    assets: list[str],
    include_micro: bool = False,
    max_points: int = 260,
    cache_path: Path = HISTORY_CACHE_FILE,
) -> dict[str, Any]:
    cache = _load_cache(cache_path)
    fetched: dict[str, dict[str, int]] = {}
    errors: list[dict[str, Any]] = []

    for report_type in report_types:
        for year in years:
            try:
                frame = fetch_annual_frame(report_type, year)
            except Exception as exc:  # noqa: BLE001 - keep historical backfill best-effort per year.
                errors.append(
                    {
                        "report_type": report_type,
                        "year": year,
                        "error": str(exc),
                    }
                )
                continue
            for asset in assets:
                rows = extract_asset_rows(frame, asset=asset, include_micro=include_micro)
                key = _history_cache_key(asset, report_type, include_micro)
                cache[key] = _dedupe_sort(cache.get(key, []) + rows, max_points=max_points)
                fetched.setdefault(key, {})[str(year)] = len(rows)

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, indent=2, default=str) + "\n", encoding="utf-8")

    coverage = {}
    for key, rows in cache.items():
        if not key.endswith(f"micro={int(include_micro)}"):
            continue
        dates = [_row_date_value(row) for row in rows if _row_date_value(row) != "N/A"]
        coverage[key] = {
            "rows": len(rows),
            "start": min(dates) if dates else None,
            "end": max(dates) if dates else None,
        }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "CFTC Historical Compressed annual archives",
        "years": years,
        "report_types": report_types,
        "assets": assets,
        "include_micro": include_micro,
        "cache_path": str(cache_path),
        "fetched": fetched,
        "errors": errors,
        "coverage": coverage,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", nargs="+", type=int, default=list(range(2022, 2027)))
    parser.add_argument(
        "--report-types",
        nargs="+",
        choices=sorted(REPORT_ARCHIVES),
        default=["futures_and_options"],
    )
    parser.add_argument("--assets", nargs="+", default=["BTC", "ETH"])
    parser.add_argument("--include-micro", action="store_true")
    parser.add_argument("--max-points", type=int, default=260)
    parser.add_argument("--cache-path", type=Path, default=HISTORY_CACHE_FILE)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    payload = backfill(
        years=args.years,
        report_types=args.report_types,
        assets=[asset.upper() for asset in args.assets],
        include_micro=args.include_micro,
        max_points=args.max_points,
        cache_path=args.cache_path,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
