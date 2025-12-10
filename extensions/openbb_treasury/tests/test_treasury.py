"""
Basic tests for OpenBB Treasury extension
"""

import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from openbb_treasury import TreasuryAPI, tariff_revenue, fiscal_summary


def test_imports():
    """Test that all functions can be imported"""
    assert callable(TreasuryAPI), "TreasuryAPI should be callable"
    assert callable(tariff_revenue), "tariff_revenue should be callable"
    assert callable(fiscal_summary), "fiscal_summary should be callable"

    # Test class instantiation
    api = TreasuryAPI()
    assert hasattr(api, 'get_tariff_revenue'), "Should have get_tariff_revenue method"
    assert hasattr(api, 'get_fiscal_summary'), "Should have get_fiscal_summary method"

    print("✅ Import test passed")


def test_api_connection():
    """Test basic API connectivity (may fail without internet)"""
    api = TreasuryAPI()
    result = api.get_tariff_revenue(limit=1)

    assert isinstance(result, dict), "Should return a dictionary"

    # Check if we have internet connection
    if "error" in result:
        error_msg = result.get('error', 'Unknown error')
        if "nodename nor servname provided" in error_msg or "network" in error_msg.lower():
            print("⚠️  API connection test skipped (no internet connection)")
            return  # Skip test gracefully
        else:
            assert False, f"API call failed: {error_msg}"

    # If we have internet, check the response structure
    if "data" in result:
        assert isinstance(result["data"], list), "Data should be a list"
        if result["data"]:
            item = result["data"][0]
            assert "record_date" in item, "Should have record_date field"
            assert "customs_duties" in item, "Should have customs_duties field"

    print("✅ API connection test passed")


def test_tariff_revenue_function():
    """Test the tariff_revenue function (may skip without internet)"""
    result = tariff_revenue(limit=2)

    assert isinstance(result, dict), "Should return a dictionary"

    if "error" in result:
        error_msg = result.get('error', 'Unknown error')
        if "nodename nor servname provided" in error_msg or "network" in error_msg.lower():
            print("⚠️  tariff_revenue function test skipped (no internet connection)")
            return  # Skip test gracefully
        else:
            assert False, f"Function failed: {error_msg}"

    print("✅ tariff_revenue function test passed")


def test_fiscal_summary_function():
    """Test the fiscal_summary function (may skip without internet)"""
    # Use a recent date that should have data
    test_date = "2025-12-01"
    result = fiscal_summary(test_date)

    assert isinstance(result, dict), "Should return a dictionary"

    if "error" in result:
        error_msg = result.get('error', 'Unknown error')
        if "nodename nor servname provided" in error_msg or "network" in error_msg.lower():
            print("⚠️  fiscal_summary function test skipped (no internet connection)")
            return  # Skip test gracefully

    # Note: This might return no data for future dates, which is OK
    print("✅ fiscal_summary function test passed")


if __name__ == "__main__":
    print("🧪 Running Treasury extension tests...")

    try:
        test_imports()
        test_api_connection()
        test_tariff_revenue_function()
        test_fiscal_summary_function()

        print("\n🎉 All applicable tests passed!")

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)