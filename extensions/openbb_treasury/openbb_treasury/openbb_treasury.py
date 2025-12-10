"""
OpenBB Treasury Extension
Provides access to US Treasury FiscalData API for tariff revenue data
"""

import json
import urllib.request
import urllib.parse
from datetime import datetime
from typing import Dict, List, Optional, Any


class TreasuryAPI:
    """Simple client for US Treasury FiscalData API"""

    BASE_URL = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1"

    def get_tariff_revenue(self,
                          start_date: Optional[str] = None,
                          end_date: Optional[str] = None,
                          limit: int = 100) -> Dict[str, Any]:
        """
        Get customs duties/tariff revenue data

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            limit: Maximum number of records to return

        Returns:
            Dictionary containing tariff revenue data
        """
        endpoint = f"{self.BASE_URL}/accounting/daily_treasury_statement"

        params = {
            'fields': 'record_date,customs_duties',
            'sort': '-record_date',
            'page[size]': str(limit)
        }

        # Add date filters if provided
        if start_date:
            params['filter'] = f"record_date:gte:{start_date}"
        if end_date:
            if 'filter' in params:
                params['filter'] += f",record_date:lte:{end_date}"
            else:
                params['filter'] = f"record_date:lte:{end_date}"

        try:
            url = f"{endpoint}?{urllib.parse.urlencode(params)}"
            print(f"📡 Fetching from: {url}")

            with urllib.request.urlopen(url, timeout=30) as response:
                if response.getcode() == 200:
                    data = json.loads(response.read().decode())
                    print(f"✅ Retrieved {len(data.get('data', []))} records")
                    return data
                else:
                    return {"error": f"HTTP {response.getcode()}"}

        except Exception as e:
            return {"error": str(e)}

    def get_fiscal_summary(self, record_date: str) -> Dict[str, Any]:
        """
        Get daily treasury statement for a specific date

        Args:
            record_date: Date in YYYY-MM-DD format

        Returns:
            Dictionary containing fiscal summary data
        """
        endpoint = f"{self.BASE_URL}/accounting/daily_treasury_statement"

        params = {
            'filter': f'record_date:eq:{record_date}',
            'fields': 'record_date,customs_duties,total_outlays,total_receipts'
        }

        try:
            url = f"{endpoint}?{urllib.parse.urlencode(params)}"
            print(f"📡 Fetching fiscal summary for {record_date}")

            with urllib.request.urlopen(url, timeout=30) as response:
                if response.getcode() == 200:
                    data = json.loads(response.read().decode())
                    if data.get('data'):
                        print("✅ Fiscal summary retrieved")
                        return data
                    else:
                        return {"error": f"No data found for date {record_date}"}
                else:
                    return {"error": f"HTTP {response.getcode()}"}

        except Exception as e:
            return {"error": str(e)}


# OpenBB Integration Functions
def tariff_revenue(start_date: str = None, end_date: str = None, limit: int = 100):
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


def fiscal_summary(record_date: str):
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
    print("🧪 Testing Treasury API connection...")

    api = TreasuryAPI()

    # Test basic connectivity
    result = api.get_tariff_revenue(limit=1)
    if "error" in result:
        print(f"❌ Connection test failed: {result['error']}")
        return False
    else:
        print("✅ API connection successful")
        return True


if __name__ == "__main__":
    # Run tests when executed directly
    test_connection()

    # Example usage
    print("\n📊 Example: Get latest tariff revenue")
    data = tariff_revenue(limit=5)
    if "data" in data:
        for item in data["data"][:3]:  # Show first 3 records
            print(f"  {item.get('record_date', 'N/A')}: ${item.get('customs_duties', 0):,.0f}")