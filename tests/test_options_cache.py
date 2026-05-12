from __future__ import annotations

from pathlib import Path

import pandas as pd

from options.cache import OptionsCacheStore
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


def test_cache_persist_and_load_snapshot(tmp_path: Path) -> None:
    config = _config(tmp_path)
    store = OptionsCacheStore(config)

    frame = pd.DataFrame(
        {
            "ticker": ["MSFT", "MSFT"],
            "contract_symbol": ["MSFTC", "MSFTP"],
            "option_type": ["call", "put"],
            "expiration": ["2099-12-15", "2099-12-15"],
            "strike": [100.0, 100.0],
            "last_price": [5.0, 4.8],
            "bid": [4.9, 4.6],
            "ask": [5.1, 5.0],
            "mid_price": [5.0, 4.8],
            "volume": [200, 180],
            "open_interest": [500, 450],
            "implied_volatility": [0.25, 0.27],
            "in_the_money": [False, False],
            "last_trade_date": ["2026-01-01", "2026-01-01"],
            "spread_pct": [0.04, 0.08],
            "liquidity_score": [450.0, 410.0],
        }
    )

    metadata = store.persist_snapshot(
        ticker="MSFT",
        frame=frame,
        underlying_price=420.0,
        expirations=["2099-12-15"],
        source="unit_test",
    )
    assert metadata.row_count == 2

    latest = store.latest_snapshot("MSFT")
    assert latest is not None
    loaded = store.load_snapshot_frame(latest)
    assert len(loaded) == 2

    iv_hist = store.iv_history("MSFT", lookback_days=90)
    assert not iv_hist.empty
    assert iv_hist.iloc[-1] > 0
