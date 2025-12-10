# OpenBB Treasury Extension

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)

An OpenBB extension for US Treasury FiscalData API integration, providing access to tariff revenue and customs duties data for economic analysis.

## Overview

This extension addresses the gap in OpenBB's coverage of US Treasury fiscal data by providing programmatic access to:

- **Customs duties and tariff revenue** from the Daily Treasury Statement
- **Fiscal summary data** including receipts, outlays, and balances
- **Historical data** going back to 2025 and earlier

The "Public Deficit and Tariff Revenue" indicator in fund.yaml can change from "Partial" to "Yes" with this extension.

## Installation

### From Source
```bash
git clone <repository-url>
cd openbb-treasury
pip install -e .
```

### Development Installation
```bash
pip install -e ".[dev]"
```

## Usage

### Basic Usage
```python
from openbb_treasury import tariff_revenue, fiscal_summary

# Get latest tariff revenue data
revenue_data = tariff_revenue(limit=10)

# Get fiscal summary for specific date
summary = fiscal_summary("2025-12-08")
```

### OpenBB Integration (Future)
Once integrated into OpenBB:
```python
import openbb as obb

# Access through OpenBB
tariff_data = obb.treasury.tariff_revenue()
fiscal_data = obb.treasury.fiscal_summary(date="2025-12-08")
```

## API Reference

### `tariff_revenue(start_date=None, end_date=None, limit=100)`
Get customs duties/tariff revenue data.

**Parameters:**
- `start_date` (str, optional): Start date in YYYY-MM-DD format
- `end_date` (str, optional): End date in YYYY-MM-DD format
- `limit` (int): Maximum records to return (default: 100)

**Returns:** Dict containing tariff revenue data

### `fiscal_summary(record_date)`
Get daily treasury statement summary for a specific date.

**Parameters:**
- `record_date` (str): Date in YYYY-MM-DD format

**Returns:** Dict containing fiscal summary data

## Data Source

- **API**: US Treasury FiscalData API
- **URL**: https://fiscaldata.treasury.gov/
- **Endpoint**: `/services/api/fiscal_service/v1/accounting/daily_treasury_statement`
- **Authentication**: None required (public API)
- **Update Frequency**: Daily
- **Historical Data**: Available from 2025-present

## Development

### Project Structure
```
openbb_treasury/
├── openbb_treasury/          # Main package
│   ├── __init__.py           # Package initialization
│   └── openbb_treasury.py    # Core functionality
├── tests/                    # Test suite
│   ├── __init__.py
│   └── test_treasury.py      # Unit tests
├── pyproject.toml            # Package configuration
├── README.md                 # This file
└── LICENSE                   # MIT License
```

### Testing
```bash
# Run tests
pytest

# Run with coverage
pytest --cov=openbb_treasury

# Run specific test
pytest tests/test_treasury.py::test_api_connection
```

### Code Quality
```bash
# Lint code
ruff check .

# Format code
ruff format .

# Type checking
mypy openbb_treasury/
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass
6. Submit a pull request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Related Projects

- [OpenBB Platform](https://github.com/OpenBB-finance/OpenBB) - Main OpenBB platform
- [US Treasury FiscalData](https://fiscaldata.treasury.gov/) - Data source API

## Disclaimer

This extension provides access to public US Treasury data. Users should verify data accuracy for critical applications. Not intended for production financial advice.