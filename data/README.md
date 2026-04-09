# Data directory

Drop crypto OHLCV files here. They are auto-discovered by scripts/data_loader.py.

## Naming convention
  {COIN}_{TIMEFRAME}_{start_year}_{end_year}.csv   (preferred)
  Examples:
    BTC_1H_2018_2025.csv
    ETHUSDT_1H_2020_2025.parquet
    bitcoin_daily.csv

## Required columns
  timestamp (or date / time / datetime), open, high, low, close, volume
  Column names are normalized automatically.

## Supported formats
  CSV (.csv) and Parquet (.parquet)

## Timeframe detection
  Include the timeframe in the filename for reliable detection:
  1h, 4h, 1d, 1w (case-insensitive)
  If absent, the loader infers it from the median row interval.

## Notes
- Files do not need to be complete. The loader gap-fills missing
  date ranges from OpenBB automatically.
- Subdirectories are scanned recursively.
- All timestamps are normalized to UTC.
