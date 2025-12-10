#!/usr/bin/env python3
"""
Simple validation script for CBDC Tracker API
Based on fund.yaml requirements for CBDC Progress Tracker
"""

import urllib.request
import json
from datetime import datetime

class CBDCValidator:
    def __init__(self):
        # API base URL from the GitHub repository
        self.base_url = "https://cbdctracker.org/api"

    def validate_api_access(self):
        """Test basic API access"""
        try:
            # Test countries endpoint
            req = urllib.request.Request(f"{self.base_url}/countries")
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 200:
                    countries = json.loads(response.read().decode('utf-8'))
                    print(f"✅ Countries endpoint works - {len(countries)} countries found")
                    return True, countries
                else:
                    print(f"❌ Countries endpoint failed - Status: {response.status}")
                    return False, None
        except Exception as e:
            print(f"❌ API access failed: {e}")
            return False, None

    def validate_currencies_data(self):
        """Test currencies endpoint and data structure"""
        try:
            req = urllib.request.Request(f"{self.base_url}/currencies")
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 200:
                    currencies = json.loads(response.read().decode('utf-8'))
                    print(f"✅ Currencies endpoint works - {len(currencies)} currencies found")

                    # Check data structure
                    if currencies and isinstance(currencies, list) and len(currencies) > 0:
                        sample = currencies[0]
                        required_fields = ['country', 'status', 'digitalCurrency']
                        has_fields = all(field in sample for field in required_fields)

                        if has_fields:
                            print("✅ Data structure valid - has country, status, digitalCurrency fields")
                            return True, currencies
                        else:
                            print(f"❌ Missing required fields in data structure")
                            return False, currencies
                    else:
                        print("❌ No currency data received")
                        return False, currencies
                else:
                    print(f"❌ Currencies endpoint failed - Status: {response.status}")
                    return False, None
        except Exception as e:
            print(f"❌ Currencies validation failed: {e}")
            return False, None

    def check_key_countries(self, countries_data, currencies_data):
        """Check for key countries mentioned in fund.yaml"""
        key_countries = ['China', 'India', 'Brazil', 'Nigeria', 'United States', 'European Union']

        if not countries_data:
            print("❌ No countries data to check")
            return False

        countries_list = [c.lower() for c in countries_data] if isinstance(countries_data, list) else []
        currencies_countries = set()

        if currencies_data and isinstance(currencies_data, list):
            for currency in currencies_data:
                if 'country' in currency:
                    currencies_countries.add(currency['country'].lower())

        found_countries = []
        for country in key_countries:
            country_lower = country.lower()
            if country_lower in countries_list or country_lower in currencies_countries:
                found_countries.append(country)

        print(f"✅ Key countries found: {len(found_countries)}/{len(key_countries)} - {', '.join(found_countries)}")
        return len(found_countries) > 0

    def check_development_stages(self, currencies_data):
        """Check for development stages (Research/Pilot/Live)"""
        if not currencies_data or not isinstance(currencies_data, list):
            print("❌ No currencies data to check stages")
            return False

        stages_found = set()
        for currency in currencies_data:
            if 'status' in currency:
                stages_found.add(currency['status'])

        expected_stages = {'Research', 'Pilot', 'Launched', 'Live', 'Development'}
        found_expected = stages_found.intersection(expected_stages)

        print(f"✅ Development stages found: {sorted(stages_found)}")
        print(f"✅ Expected stages present: {len(found_expected)}/{len(expected_stages)}")

        return len(found_expected) > 0

    def run_validation(self):
        """Run complete validation"""
        print("🚀 Starting CBDC Tracker API Validation")
        print("=" * 50)

        # 1. Test API access
        api_ok, countries = self.validate_api_access()
        if not api_ok:
            return False

        # 2. Test currencies data
        currencies_ok, currencies = self.validate_currencies_data()
        if not currencies_ok:
            return False

        # 3. Check key countries
        countries_ok = self.check_key_countries(countries, currencies)
        if not countries_ok:
            print("⚠️  Warning: Key countries not found")

        # 4. Check development stages
        stages_ok = self.check_development_stages(currencies)

        print("\n" + "=" * 50)
        success = api_ok and currencies_ok and stages_ok
        if success:
            print("✅ VALIDATION PASSED: CBDC Tracker API is suitable for quarterly updates")
            print("💡 Recommendation: Implement wrapper script for automated data collection")
        else:
            print("❌ VALIDATION FAILED: API may not meet requirements")

        return success

if __name__ == "__main__":
    validator = CBDCValidator()
    validator.run_validation()