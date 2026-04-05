from datetime import datetime, timezone
from typing import Any
from collections.abc import Hashable, Mapping

import pandas as pd

from app.domain.openbb_indicators import OPENBB_INDICATORS


def _get_obb():
    """Lazy load OpenBB to avoid slow startup."""
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


def fetch_fred_series(series_id: str) -> dict[str, Any]:
    obb = _get_obb()
    result = obb.economy.fred_series(  # type: ignore[attr-defined]
        series_id=series_id)
    return {
        "series_id": series_id,
        "records": _to_records(result),
        "as_of": datetime.now(timezone.utc).isoformat(),
    }


def fetch_fixedincome_rate(symbol: str) -> dict[str, Any]:
    obb = _get_obb()
    result = obb.fixedincome.rate(symbol=symbol)  # type: ignore[attr-defined]
    return {
        "symbol": symbol,
        "records": _to_records(result),
        "as_of": datetime.now(timezone.utc).isoformat(),
    }


def fetch_openbb_indicator(slug: str) -> dict[str, Any]:
    if slug not in OPENBB_INDICATORS:
        raise KeyError(f"Unknown OpenBB indicator: {slug}")

    # TEMPORARY: Return mock data for testing frontend integration
    # TODO: Restore actual OpenBB calls when library and API keys are configured
    import random
    from datetime import timedelta

    indicator = OPENBB_INDICATORS[slug]
    indicator_type = indicator["type"]

    # Generate mock data based on indicator type
    if indicator_type == "fred_series":
        # Mock FRED series data
        value = random.uniform(
            0, 1000) if "TGA" in indicator["series_id"] or "RRP" in indicator["series_id"] else random.uniform(0, 10)
        return {
            "series_id": indicator["series_id"],
            "value": round(value, 2),
            "date": (datetime.now(timezone.utc) - timedelta(days=random.randint(0, 7))).date().isoformat(),
            "unit": "Billions of USD" if "TGA" in indicator["series_id"] or "RRP" in indicator["series_id"] else "Percent",
            "as_of": datetime.now(timezone.utc).isoformat(),
        }

    if indicator_type == "fixedincome_rate":
        # Mock fixed income rate
        value = random.uniform(3.0, 6.0)
        return {
            "symbol": indicator["symbol"],
            "value": round(value, 2),
            "date": (datetime.now(timezone.utc) - timedelta(days=random.randint(0, 1))).date().isoformat(),
            "unit": "Percent",
            "as_of": datetime.now(timezone.utc).isoformat(),
        }

    if indicator_type == "yield_curve_spread":
        # Mock yield curve spread
        long_value = random.uniform(4.0, 5.5)
        short_value = random.uniform(4.0, 5.0)
        spread = long_value - short_value
        return {
            "long_symbol": indicator["long_symbol"],
            "short_symbol": indicator["short_symbol"],
            "long_value": round(long_value, 2),
            "short_value": round(short_value, 2),
            "spread": round(spread, 2),
            "date": (datetime.now(timezone.utc) - timedelta(days=random.randint(0, 1))).date().isoformat(),
            "unit": "Percentage Points",
            "as_of": datetime.now(timezone.utc).isoformat(),
        }

    raise ValueError(f"Unsupported indicator type: {indicator_type}")

    # Original OpenBB code (commented out until library is properly configured):
    """
    indicator = OPENBB_INDICATORS[slug]
    indicator_type = indicator["type"]

    if indicator_type == "fred_series":
        return fetch_fred_series(indicator["series_id"])

    if indicator_type == "fixedincome_rate":
        return fetch_fixedincome_rate(indicator["symbol"])

    if indicator_type == "yield_curve_spread":
        long_term = fetch_fixedincome_rate(indicator["long_symbol"])
        short_term = fetch_fixedincome_rate(indicator["short_symbol"])

        long_value = _extract_latest_value(long_term.get("records", []))
        short_value = _extract_latest_value(short_term.get("records", []))

        spread = None
        if long_value is not None and short_value is not None:
            spread = float(long_value) - float(short_value)

        return {
            "long_symbol": indicator["long_symbol"],
            "short_symbol": indicator["short_symbol"],
            "long_value": long_value,
            "short_value": short_value,
            "spread": spread,
            "as_of": datetime.now(timezone.utc).isoformat(),
        }

    raise ValueError(f"Unsupported indicator type: {indicator_type}")
    """


def _extract_latest_value(records: list[dict[str, Any]]) -> Any:
    if not records:
        return None

    latest = records[-1]
    for key in ("value", "rate", "close", "last"):
        if key in latest:
            return latest[key]
    return latest
