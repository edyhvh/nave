"""
OpenBB Treasury Extension
Provides access to US Treasury FiscalData API for tariff revenue data
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

HTTP_OK = 200


class TreasuryAPI:
    """Simple client for US Treasury FiscalData API"""

    BASE_URL = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1"
    TARIFF_ENDPOINT = f"{BASE_URL}/accounting/mts/mts_table_9"
    CUSTOMS_DUTIES_LINE_CODE = "100"

    def get_tariff_revenue(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """
        Get customs duties/tariff revenue data

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            limit: Maximum number of records to return

        Returns:
            Dictionary containing tariff revenue data
        """
        params = {
            "filter": f"line_code_nbr:eq:{self.CUSTOMS_DUTIES_LINE_CODE}",
            "fields": (
                "record_date,classification_desc,current_month_rcpt_outly_amt,"
                "current_fytd_rcpt_outly_amt,prior_fytd_rcpt_outly_amt,line_code_nbr"
            ),
            "sort": "-record_date",
            "page[size]": str(limit),
        }

        # Add date filters if provided
        if start_date:
            params["filter"] += f",record_date:gte:{start_date}"
        if end_date:
            params["filter"] += f",record_date:lte:{end_date}"

        try:
            url = f"{self.TARIFF_ENDPOINT}?{urllib.parse.urlencode(params)}"

            with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310
                if response.getcode() == HTTP_OK:
                    data = json.loads(response.read().decode())
                    for row in data.get("data", []):
                        row["customs_duties"] = row.get("current_month_rcpt_outly_amt")
                        row["customs_duties_fytd"] = row.get(
                            "current_fytd_rcpt_outly_amt"
                        )
                    return data
                return {"error": f"HTTP {response.getcode()}"}

        except (OSError, urllib.error.URLError, json.JSONDecodeError) as e:
            return {"error": str(e)}

    def get_fiscal_summary(self, record_date: str) -> dict[str, Any]:
        """
        Get daily treasury statement for a specific date

        Args:
            record_date: Date in YYYY-MM-DD format

        Returns:
            Dictionary containing fiscal summary data
        """
        params = {
            "filter": f"record_date:eq:{record_date}",
            "fields": (
                "record_date,classification_desc,current_month_rcpt_outly_amt,"
                "current_fytd_rcpt_outly_amt,prior_fytd_rcpt_outly_amt,line_code_nbr"
            ),
            "sort": "print_order_nbr",
            "page[size]": "100",
        }

        try:
            url = f"{self.TARIFF_ENDPOINT}?{urllib.parse.urlencode(params)}"

            with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310
                if response.getcode() == HTTP_OK:
                    data = json.loads(response.read().decode())
                    if data.get("data"):
                        for row in data.get("data", []):
                            if (
                                row.get("line_code_nbr")
                                == self.CUSTOMS_DUTIES_LINE_CODE
                            ):
                                row["customs_duties"] = row.get(
                                    "current_month_rcpt_outly_amt"
                                )
                                row["customs_duties_fytd"] = row.get(
                                    "current_fytd_rcpt_outly_amt"
                                )
                        return data
                    return {"error": f"No data found for date {record_date}"}
                return {"error": f"HTTP {response.getcode()}"}

        except (OSError, urllib.error.URLError, json.JSONDecodeError) as e:
            return {"error": str(e)}


# OpenBB Integration Functions
def tariff_revenue(
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """
    Get US tariff revenue data

    Parameters:
    -----------
    start_date : str, optional
        Start date in YYYY-MM-DD format
    end_date : str, optional
        End date in YYYY-MM-DD format
    limit : int, default 100
        Maximum records to return

    Returns:
    --------
    dict
        Tariff revenue data from Treasury API
    """
    api = TreasuryAPI()
    return api.get_tariff_revenue(start_date, end_date, limit)


def fiscal_summary(record_date: str) -> dict[str, Any]:
    """
    Get fiscal summary for a specific date

    Parameters:
    -----------
    record_date : str
        Date in YYYY-MM-DD format

    Returns:
    --------
    dict
        Fiscal summary data
    """
    api = TreasuryAPI()
    return api.get_fiscal_summary(record_date)


# Test function
def test_connection():
    """Test API connectivity"""
    api = TreasuryAPI()

    # Test basic connectivity
    result = api.get_tariff_revenue(limit=1)
    return "error" not in result


if __name__ == "__main__":
    raise SystemExit(0 if test_connection() else 1)
