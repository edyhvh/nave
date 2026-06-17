"""Default ISM screening universe."""

from __future__ import annotations

# Keep this short so FMP daily-budget usage stays practical.
# The default basket leans toward names whose public-company industries map
# more cleanly onto ISM buckets than broad mega-cap sector placeholders do.
DEFAULT_UNIVERSE: dict[str, list[str]] = {
    "Information Technology": ["AAPL", "HPQ", "DELL", "AMAT", "GLW"],
    "Industrials": ["GE", "ETN", "CAT", "PH", "EMR", "ITW", "ROK"],
    "Health Care": ["LLY", "JNJ", "UNH", "ABT"],
    "Consumer Discretionary": ["NKE", "DECK", "WHR", "LEN", "MHK", "MLKN"],
    "Materials": ["NUE", "FCX", "IP", "DD", "LIN", "LYB", "DOW", "EMN"],
    "Energy": ["XOM", "PSX", "VLO", "MPC"],
    "Financials": ["JPM", "BAC", "V", "MS"],
    "Consumer Staples": ["MO", "KO", "MDLZ", "GIS", "KHC", "CPB", "PM"],
    "Communication Services": ["GOOGL", "META", "NFLX", "DIS"],
    "Utilities": ["NEE", "DUK", "SO"],
    "Real Estate": ["PLD", "AMT", "EQIX"],
}
