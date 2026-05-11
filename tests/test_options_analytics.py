from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from options.analytics.greeks import enrich_greeks
from options.analytics.volatility import compute_historical_volatility, compute_iv_rank_percentile
from options.config import OptionsConfig


def _config(tmp_path: Path) -> OptionsConfig:
    cache_root = tmp_path / "options_cache"
    return OptionsConfig(
        cache_root=cache_root,
        sqlite_path=cache_root / "options_cache.sqlite",
        snapshots_dir=cache_root / "snapshots",
        charts_dir=cache_root / "charts",
        reports_dir=cache_root / "reports",
    )


def test_compute_historical_volatility_returns_finite_value() -> None:
    closes = pd.Series(np.linspace(100.0, 130.0, 120))
    hv = compute_historical_volatility(closes, window=30)
    assert np.isfinite(hv)
    assert hv >= 0


def test_compute_iv_rank_percentile() -> None:
    iv = pd.Series([0.20, 0.22, 0.24, 0.19, 0.26, 0.30])
    iv_rank, iv_percentile = compute_iv_rank_percentile(iv, lookback=6)
    assert 0 <= iv_rank <= 100
    assert 0 <= iv_percentile <= 100


def test_enrich_greeks_adds_expected_columns(tmp_path: Path) -> None:
    expiration = (datetime.now(timezone.utc) +
                  timedelta(days=45)).date().isoformat()
    frame = pd.DataFrame(
        {
            "ticker": ["MSFT", "MSFT"],
            "contract_symbol": ["MSFTC", "MSFTP"],
            "option_type": ["call", "put"],
            "expiration": [expiration, expiration],
            "strike": [420.0, 420.0],
            "last_price": [6.0, 5.5],
            "bid": [5.8, 5.3],
            "ask": [6.2, 5.7],
            "mid_price": [6.0, 5.5],
            "volume": [200, 190],
            "open_interest": [500, 520],
            "implied_volatility": [0.25, 0.27],
            "in_the_money": [False, False],
            "last_trade_date": ["2026-05-10", "2026-05-10"],
            "spread_pct": [0.07, 0.07],
            "liquidity_score": [400.0, 390.0],
        }
    )

    out = enrich_greeks(frame, underlying_price=420.0,
                        config=_config(tmp_path))
    assert {"delta", "gamma", "theta", "vega"}.issubset(set(out.columns))
    assert out["delta"].notna().all()
