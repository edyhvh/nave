from __future__ import annotations

from datetime import date, timedelta

from trading.cot.cot_analyzer import COTAnalyzer


def _build_asset_rows(
    start_date: date,
    weeks: int,
    *,
    noncomm_long_start: int,
    noncomm_short_start: int,
    comm_long_start: int,
    comm_short_start: int,
    oi_start: int,
    traders_noncomm_start: int,
    traders_comm_start: int,
) -> list[dict]:
    rows: list[dict] = []
    for i in range(weeks):
        d = start_date + timedelta(days=7 * i)
        rows.append(
            {
                "report_date_as_yyyy_mm_dd": d.isoformat(),
                "noncomm_positions_long_all": noncomm_long_start + 100 * i,
                "noncomm_positions_short_all": noncomm_short_start + 50 * i,
                "comm_positions_long_all": comm_long_start + 20 * i,
                "comm_positions_short_all": comm_short_start + 10 * i,
                "open_interest_all": oi_start + 120 * i,
                "number_of_traders_noncommercial_all": traders_noncomm_start + i,
                "number_of_traders_commercial_all": traders_comm_start - i,
            }
        )
    return rows


def _build_cot_data() -> dict[str, dict]:
    # Tuesdays from 2026-01-06 through 2026-03-31 (13 weeks)
    start = date(2026, 1, 6)
    weeks = 13
    return {
        "BTC": {
            "as_of_date": "2026-03-31",
            "raw": _build_asset_rows(
                start,
                weeks,
                noncomm_long_start=10_000,
                noncomm_short_start=8_000,
                comm_long_start=6_000,
                comm_short_start=7_500,
                oi_start=20_000,
                traders_noncomm_start=90,
                traders_comm_start=60,
            ),
        },
        "ETH": {
            "as_of_date": "2026-03-31",
            "raw": _build_asset_rows(
                start,
                weeks,
                noncomm_long_start=8_000,
                noncomm_short_start=7_900,
                comm_long_start=5_500,
                comm_short_start=5_900,
                oi_start=14_000,
                traders_noncomm_start=70,
                traders_comm_start=42,
            ),
        },
    }


def test_generate_historical_variation_report_periods_and_ranges():
    analyzer = COTAnalyzer()
    report = analyzer.generate_historical_variation_report(
        months=3,
        cot_data=_build_cot_data(),
        as_of_date="2026-03-31",
    )

    btc_rows = report["assets"]["BTC"]
    assert [row["period"] for row in btc_rows] == [
        "Last Week",
        "Last 1 Month",
        "Last 2 Months",
        "Last 3 Months",
    ]

    assert btc_rows[0]["start_date"] == "2026-03-24"
    assert btc_rows[0]["end_date"] == "2026-03-31"
    assert btc_rows[1]["start_date"] == "2026-03-03"
    assert btc_rows[1]["end_date"] == "2026-03-31"
    assert btc_rows[2]["start_date"] == "2026-02-03"
    assert btc_rows[2]["end_date"] == "2026-03-31"
    assert btc_rows[3]["start_date"] == "2026-01-06"
    assert btc_rows[3]["end_date"] == "2026-03-31"


def test_generate_historical_variation_report_delta_values_and_markdown():
    analyzer = COTAnalyzer()
    report = analyzer.generate_historical_variation_report(
        months=3,
        cot_data=_build_cot_data(),
        as_of_date="2026-03-31",
    )

    btc_rows = report["assets"]["BTC"]

    # Net non-commercial is +50 per week with synthetic dataset.
    assert btc_rows[0]["net_non_commercial_delta"] == 50
    assert btc_rows[1]["net_non_commercial_delta"] == 200
    assert btc_rows[2]["net_non_commercial_delta"] == 400
    assert btc_rows[3]["net_non_commercial_delta"] == 600

    # Open interest increases +120 per week.
    assert btc_rows[0]["open_interest_delta"] == 120
    assert btc_rows[1]["open_interest_delta"] == 480

    markdown = report["markdown"]
    assert "NAVE COT HISTORICAL VARIATION REPORT - Last 3 Months (as-of 2026-03-31)" in markdown
    assert "[BTC]" in markdown
    assert "[ETH]" in markdown
    assert "2026-03-03 to 2026-03-31" in markdown
