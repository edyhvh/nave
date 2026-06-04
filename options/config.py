"""Configuration for options analytics and caching."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _as_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _as_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _as_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class OptionsConfig:
    """Runtime configuration for the options analysis workflow."""

    cache_root: Path
    sqlite_path: Path
    snapshots_dir: Path
    charts_dir: Path
    reports_dir: Path
    min_volume: int = 50
    min_open_interest: int = 100
    max_bid_ask_spread_pct: float = 0.15
    cache_ttl_minutes: int = 30
    request_timeout_seconds: int = 20
    max_retries: int = 3
    retry_backoff_seconds: float = 1.5
    risk_free_rate: float = 0.04
    equity_risk_premium: float = 0.03
    dividend_yield: float = 0.0
    hv_window_short: int = 30
    hv_window_long: int = 60
    iv_history_lookback_days: int = 90
    monte_carlo_paths: int = 5000
    monte_carlo_seed: int = 42
    default_history_period: str = "1y"
    enable_plotly: bool = True
    bull_put_otm_min_pct: float = 0.03
    bull_put_otm_max_pct: float = 0.06
    spread_width_min_points: float = 8.0
    spread_width_max_points: float = 15.0
    conservative_touch_max_pct: float = 75.0
    modeled_touch_warning_pct: float = 85.0
    deribit_conservative_touch_max_pct: float = 82.0
    deribit_modeled_touch_warning_pct: float = 92.0
    deribit_base_url: str = "https://test.deribit.com/api/v2"
    deribit_timeout_seconds: int = 20

    @property
    def hv_windows(self) -> tuple[int, int]:
        return (self.hv_window_short, self.hv_window_long)


def _default_cache_root() -> Path:
    repo_root = Path(__file__).resolve().parent.parent
    return repo_root / "data" / "options_cache"


def load_options_config() -> OptionsConfig:
    """Load options settings from env vars with safe defaults."""
    cache_root = Path(os.getenv("NAVE_OPTIONS_CACHE_ROOT",
                      str(_default_cache_root()))).expanduser()
    snapshots_dir = cache_root / "snapshots"
    charts_dir = cache_root / "charts"
    reports_dir = cache_root / "reports"
    sqlite_path = Path(os.getenv("NAVE_OPTIONS_SQLITE_PATH", str(
        cache_root / "options_cache.sqlite"))).expanduser()

    return OptionsConfig(
        cache_root=cache_root,
        sqlite_path=sqlite_path,
        snapshots_dir=snapshots_dir,
        charts_dir=charts_dir,
        reports_dir=reports_dir,
        min_volume=_as_int("NAVE_OPTIONS_MIN_VOLUME", 50),
        min_open_interest=_as_int("NAVE_OPTIONS_MIN_OI", 100),
        max_bid_ask_spread_pct=_as_float("NAVE_OPTIONS_MAX_SPREAD_PCT", 0.15),
        cache_ttl_minutes=_as_int("NAVE_OPTIONS_CACHE_TTL_MINUTES", 30),
        request_timeout_seconds=_as_int("NAVE_OPTIONS_TIMEOUT_SECONDS", 20),
        max_retries=_as_int("NAVE_OPTIONS_MAX_RETRIES", 3),
        retry_backoff_seconds=_as_float(
            "NAVE_OPTIONS_RETRY_BACKOFF_SECONDS", 1.5),
        risk_free_rate=_as_float("NAVE_OPTIONS_RISK_FREE_RATE", 0.04),
        dividend_yield=_as_float("NAVE_OPTIONS_DIVIDEND_YIELD", 0.0),
        hv_window_short=_as_int("NAVE_OPTIONS_HV_WINDOW_SHORT", 30),
        hv_window_long=_as_int("NAVE_OPTIONS_HV_WINDOW_LONG", 60),
        iv_history_lookback_days=_as_int("NAVE_OPTIONS_IV_LOOKBACK_DAYS", 90),
        monte_carlo_paths=_as_int("NAVE_OPTIONS_MC_PATHS", 5000),
        monte_carlo_seed=_as_int("NAVE_OPTIONS_MC_SEED", 42),
        default_history_period=os.getenv("NAVE_OPTIONS_HISTORY_PERIOD", "1y"),
        enable_plotly=_as_bool("NAVE_OPTIONS_ENABLE_PLOTLY", True),
        bull_put_otm_min_pct=_as_float(
            "NAVE_OPTIONS_BULL_PUT_OTM_MIN_PCT", 0.03),
        bull_put_otm_max_pct=_as_float(
            "NAVE_OPTIONS_BULL_PUT_OTM_MAX_PCT", 0.06),
        spread_width_min_points=_as_float(
            "NAVE_OPTIONS_SPREAD_WIDTH_MIN_POINTS", 8.0),
        spread_width_max_points=_as_float(
            "NAVE_OPTIONS_SPREAD_WIDTH_MAX_POINTS", 15.0),
        conservative_touch_max_pct=_as_float(
            "NAVE_OPTIONS_CONSERVATIVE_TOUCH_MAX_PCT", 75.0),
        modeled_touch_warning_pct=_as_float(
            "NAVE_OPTIONS_MODELED_TOUCH_WARNING_PCT", 85.0),
        deribit_conservative_touch_max_pct=_as_float(
            "NAVE_OPTIONS_DERIBIT_CONSERVATIVE_TOUCH_MAX_PCT", 82.0),
        deribit_modeled_touch_warning_pct=_as_float(
            "NAVE_OPTIONS_DERIBIT_MODELED_TOUCH_WARNING_PCT", 92.0),
        deribit_base_url=os.getenv(
            "NAVE_OPTIONS_DERIBIT_BASE_URL", "https://test.deribit.com/api/v2"
        ),
        deribit_timeout_seconds=_as_int(
            "NAVE_OPTIONS_DERIBIT_TIMEOUT_SECONDS", 20
        ),
    )
