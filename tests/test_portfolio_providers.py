from datetime import UTC, datetime

import pandas as pd
import pytest

from research.portfolio_providers import PortfolioContextProvider, load_current_ism_inputs
from trading.stocks.ism_scraper import ISMIndustryRanking, ISMReport


NOW = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)


class ReportFetcher:
    def fetch_report(self, *, kind):
        return ISMReport(
            kind=kind,
            report_month="August 2026",
            pmi=51.0,
            expanding=[ISMIndustryRanking("Software", "expanding", 1, "Information Technology")],
            contracting=[],
            source_url=f"https://ism.test/{kind}",
        )


def test_ism_inputs_prefer_openbb_fred_for_headline_and_keep_official_ranking():
    result = load_current_ism_inputs(
        now=NOW,
        report_fetcher=ReportFetcher(),
        fred_fetcher=lambda series: {
            "records": [
                {"date": "2026-09-03", "value": 53.2},
                {"date": "2026-08-01", "value": 50.0},
            ],
            "as_of": "2026-09-04",
            "retrieved_at": "2026-09-04",
        },
    )
    assert result["manufacturing"]["pmi"] == 50.0
    assert result["manufacturing"]["pmi_source"] == "NAPM via OpenBB/FRED"
    assert result["manufacturing"]["pmi_observation_at"] == "2026-08-01T00:00:00+00:00"
    assert result["manufacturing"]["pmi_retrieved_at"] == "2026-09-04T00:00:00+00:00"
    assert result["services"]["pmi"] == 51.0
    assert result["manufacturing"]["hottest_industries"][0]["industry"] == "Software"


def test_portfolio_context_uses_openbb_history_and_keeps_missing_fundamentals_truthful():
    def history(symbol, _start, _end):
        return {
            "records": [
                {"date": "2026-08-01", "close": 100},
                {"date": "2026-09-04", "close": 110},
            ],
            "as_of": "2026-09-04T12:00:00+00:00",
        }

    class Fundamentals:
        def fundamentals(self, symbol):
            raise RuntimeError("provider offline")

    result = PortfolioContextProvider(history_fetcher=history, fundamentals=Fundamentals()).build_review_context(
        ["AAPL"], now=NOW
    )
    assert result["AAPL"]["market_state"]["current_price"] == 110
    assert result["AAPL"]["market_state"]["as_of"] == "2026-09-04T00:00:00+00:00"
    assert result["AAPL"]["market_state"]["retrieved_at"] == "2026-09-04T12:00:00+00:00"
    assert result["AAPL"]["market_state"]["availability"] == "KNOWN"
    assert result["AAPL"]["technical_condition"] == "healthy"
    assert result["AAPL"]["company_information"]["unavailable_reason"] == "provider offline"


@pytest.mark.parametrize("index", [
    pd.DatetimeIndex(["2026-09-03", "2026-09-04"]),
    pd.DatetimeIndex(["2026-09-03", "2026-09-04"], tz="America/New_York"),
])
def test_daily_fallback_preserves_observation_date_with_aware_timestamp(index):
    from research.portfolio import fresh_timestamp

    class Prices:
        def fetch_daily_closes(self, *_args, **_kwargs):
            return {"BE": pd.Series([100.0, 110.0], index=index)}

    provider = PortfolioContextProvider(history_fetcher=lambda *_: {}, price_provider=Prices())
    series, source, observed, retrieved = provider._history("BE", NOW)
    assert len(series) == 2 and source == "repo YFinancePriceProvider"
    timestamp = datetime.fromisoformat(observed)
    assert timestamp.tzinfo is not None
    assert timestamp.date() == index[-1].date()
    assert observed != retrieved
    assert retrieved == NOW.isoformat()
    assert fresh_timestamp(observed, NOW)
    assert not fresh_timestamp(observed, datetime(2026, 9, 10, tzinfo=UTC))
