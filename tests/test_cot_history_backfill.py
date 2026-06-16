from __future__ import annotations

import pandas as pd

from scripts.backfill_cot_history import extract_asset_rows


def test_extract_asset_rows_keeps_main_contract_and_maps_cache_shape():
    frame = pd.DataFrame(
        [
            {
                "Market and Exchange Names": "BITCOIN - CHICAGO MERCANTILE EXCHANGE",
                "As of Date in Form YYYY-MM-DD": "2024-12-31",
                "Open Interest (All)": 34_886,
                "Noncommercial Positions-Long (All)": 27_686,
                "Noncommercial Positions-Short (All)": 28_128,
                "Commercial Positions-Long (All)": 2_233,
                "Commercial Positions-Short (All)": 2_202,
            },
            {
                "Market and Exchange Names": "MICRO BITCOIN - CHICAGO MERCANTILE EXCHANGE",
                "As of Date in Form YYYY-MM-DD": "2024-12-31",
                "Open Interest (All)": 1,
                "Noncommercial Positions-Long (All)": 1,
                "Noncommercial Positions-Short (All)": 1,
            },
        ]
    )

    rows = extract_asset_rows(frame, asset="BTC", include_micro=False)

    assert len(rows) == 1
    assert rows[0]["market_and_exchange_names"] == "BITCOIN - CHICAGO MERCANTILE EXCHANGE"
    assert rows[0]["report_date"] == "2024-12-31"
    assert rows[0]["noncomm_positions_long_all"] == 27_686
    assert rows[0]["noncomm_positions_short_all"] == 28_128


def test_extract_asset_rows_can_include_micro_contracts():
    frame = pd.DataFrame(
        [
            {
                "Market and Exchange Names": "ETHER CASH SETTLED - CHICAGO MERCANTILE EXCHANGE",
                "As of Date in Form YYYY-MM-DD": "2024-12-31",
            },
            {
                "Market and Exchange Names": "MICRO ETHER - CHICAGO MERCANTILE EXCHANGE",
                "As of Date in Form YYYY-MM-DD": "2024-12-31",
            },
        ]
    )

    rows = extract_asset_rows(frame, asset="ETH", include_micro=True)

    assert [row["market_and_exchange_names"] for row in rows] == [
        "ETHER CASH SETTLED - CHICAGO MERCANTILE EXCHANGE",
        "MICRO ETHER - CHICAGO MERCANTILE EXCHANGE",
    ]
