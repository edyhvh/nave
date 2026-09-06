from datetime import datetime, timezone
from typing import Any
from collections.abc import Hashable, Mapping

import pandas as pd

from app.domain.openbb_indicators import OPENBB_INDICATORS
from core.env import load_repo_dotenv

def _get_obb():
    """Lazy load OpenBB to avoid slow startup."""
    load_repo_dotenv()
    try:
        from openbb import obb
        return obb
    except ImportError as e:
        raise RuntimeError(f"OpenBB not available: {e}")


def _normalize_record(record: Mapping[Hashable, Any]) -> dict[str, Any]:
    return {str(key): value for key, value in record.items()}


def _to_records(data: Any) -> list[dict[str, Any]]:
    if hasattr(data, "to_df"):
        data = data.to_df()
    if isinstance(data, pd.DataFrame):
        return [_normalize_record(row) for row in data.to_dict(orient="records")]
    if isinstance(data, pd.Series):
        return [
            _normalize_record(row)
            for row in data.to_frame().to_dict(orient="records")
        ]
    if isinstance(data, list):
        if all(isinstance(item, dict) for item in data):
            return [_normalize_record(item) for item in data]
        return [{"value": item} for item in data]
    if isinstance(data, dict):
        return [_normalize_record(data)]
    return [{"value": data}]


def _latest_observation_at(records: list[dict[str, Any]]) -> str | None:
    """Return the provider observation date separately from retrieval time."""
    values: list[pd.Timestamp] = []
    for record in records:
        raw = record.get("date") or record.get("Date") or record.get("timestamp")
        if raw in (None, ""):
            continue
        try:
            timestamp = pd.Timestamp(raw)
            if timestamp.tzinfo is None:
                timestamp = timestamp.tz_localize("UTC")
            else:
                timestamp = timestamp.tz_convert("UTC")
            values.append(timestamp)
        except (TypeError, ValueError):
            continue
    return max(values).isoformat() if values else None


def fetch_fred_series(series_id: str) -> dict[str, Any]:
    obb = _get_obb()
    result = obb.economy.fred_series(  # type: ignore[attr-defined]
        symbol=series_id)
    records = _to_records(result)
    retrieved_at = datetime.now(timezone.utc).isoformat()
    return {
        "series_id": series_id,
        "records": records,
        "as_of": retrieved_at,
        "retrieved_at": retrieved_at,
        "latest_observation_at": _latest_observation_at(records),
    }


def fetch_fixedincome_rate(symbol: str) -> dict[str, Any]:
    obb = _get_obb()
    result = obb.economy.fred_series(symbol=symbol)  # type: ignore[attr-defined]
    records = _to_records(result)
    retrieved_at = datetime.now(timezone.utc).isoformat()
    return {
        "symbol": symbol,
        "records": records,
        "as_of": retrieved_at,
        "retrieved_at": retrieved_at,
        "latest_observation_at": _latest_observation_at(records),
    }


def fetch_equity_history(symbol: str, start_date: str | None = None,
                         end_date: str | None = None) -> dict[str, Any]:
    """Fetch real historical equity/ETF observations through OpenBB."""
    obb = _get_obb()
    kwargs: dict[str, Any] = {"symbol": symbol}
    if start_date:
        kwargs["start_date"] = start_date
    if end_date:
        kwargs["end_date"] = end_date
    kwargs["provider"] = "yfinance"
    result = obb.equity.price.historical(**kwargs)  # type: ignore[attr-defined]
    records = _to_records(result)
    retrieved_at = datetime.now(timezone.utc).isoformat()
    return {
        "symbol": symbol,
        "records": records,
        "as_of": retrieved_at,
        "retrieved_at": retrieved_at,
        "latest_observation_at": _latest_observation_at(records),
    }


def fetch_crypto_price(symbol: str) -> dict[str, Any]:
    """Fetch a current crypto quote through OpenBB without fabricating data."""
    obb = _get_obb()
    result = obb.crypto.price(symbol=symbol)  # type: ignore[attr-defined]
    records = _to_records(result)
    retrieved_at = datetime.now(timezone.utc).isoformat()
    return {
        "symbol": symbol,
        "records": records,
        "as_of": retrieved_at,
        "retrieved_at": retrieved_at,
        "latest_observation_at": _latest_observation_at(records),
    }


def fetch_openbb_indicator(slug: str) -> dict[str, Any]:
    if slug not in OPENBB_INDICATORS:
        raise KeyError(f"Unknown OpenBB indicator: {slug}")

    indicator = OPENBB_INDICATORS[slug]
    indicator_type = indicator["type"]
    if indicator_type == "fred_series":
        return fetch_fred_series(indicator["series_id"])

    if indicator_type == "fixedincome_rate":
        return fetch_fixedincome_rate(indicator["symbol"])

    if indicator_type == "yield_curve_spread":
        long_data = fetch_fixedincome_rate(indicator["long_symbol"])
        short_data = fetch_fixedincome_rate(indicator["short_symbol"])
        long_value = _latest_numeric(long_data["records"])
        short_value = _latest_numeric(short_data["records"])
        return {
            "long_symbol": indicator["long_symbol"],
            "short_symbol": indicator["short_symbol"],
            "long": long_data,
            "short": short_data,
            "long_value": long_value,
            "short_value": short_value,
            "spread": long_value - short_value if long_value is not None and short_value is not None else None,
            "unit": "percentage points",
            "as_of": datetime.now(timezone.utc).isoformat(),
        }

    if indicator_type == "equity_history":
        return fetch_equity_history(indicator["symbol"])

    if indicator_type == "crypto_price":
        return fetch_crypto_price(indicator["symbol"])

    raise ValueError(f"Unsupported indicator type: {indicator_type}")


def _extract_latest_value(records: list[dict[str, Any]]) -> Any:
    if not records:
        return None

    latest = records[-1]
    for key in ("value", "rate", "close", "last"):
        if key in latest:
            return latest[key]
    return latest


def _latest_numeric(records: list[dict[str, Any]]) -> float | None:
    """Extract the latest numeric observation from a provider-shaped record."""
    if not records:
        return None
    for value in reversed(list(records[-1].values())):
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return None
