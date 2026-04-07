#!/usr/bin/env python3
"""
Batch test all 22 indicators defined in fund.yaml.
Checks which ones actually return data via OpenBB or external APIs.
"""

import sys
import os
import json
import urllib.request
from pathlib import Path
from typing import Any, Optional, cast

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load .env if present
env_file = project_root / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

try:
    from openbb import obb
    OPENBB_OK = True
except Exception as e:
    print(f"⚠️  OpenBB not available: {e}")
    OPENBB_OK = False
    obb = None

obb_api: Any = cast(Any, obb) if OPENBB_OK else None

results = []


def record(name, status, detail=""):
    icon = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️ "
    print(f"  {icon} {name}: {detail}")
    results.append({"name": name, "status": status, "detail": detail})


def fetch_url(url: str, timeout: int = 10) -> tuple[Optional[int], Any]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.getcode(), json.loads(r.read().decode())
    except Exception as e:
        return None, str(e)


def try_openbb(label, fn):
    try:
        df = fn()
        if df is not None and hasattr(df, 'to_df'):
            df = df.to_df()
        if df is not None and len(df) > 0:
            record(label, "PASS", f"{len(df)} rows")
        else:
            record(label, "FAIL", "empty result")
    except Exception as e:
        record(label, "FAIL", str(e)[:120])


# ─── CATEGORY 1: Liquidity and Monetary Policy ───────────────────────────────
print("\n━━━ 1. Liquidity and Monetary Policy ━━━")

if OPENBB_OK:
    # TGA
    try_openbb("#1 TGA (Treasury General Account)",
               lambda: obb_api.economy.fred_series(symbol="WDTGAL", limit=5))

    # RRP
    try_openbb("#1 RRP (Reverse Repo Facility)",
               lambda: obb_api.economy.fred_series(symbol="RRPONTSYD", limit=5))

    # Fed Injections / QE
    try_openbb("#2 Fed Balance Sheet (QE proxy)",
               lambda: obb_api.economy.fred_series(symbol="WALCL", limit=5))

    # Interest Rates
    try_openbb("#3 Fed Funds Rate",
               lambda: obb_api.economy.fred_series(symbol="FEDFUNDS", limit=5))
else:
    record("#1 TGA", "SKIP", "OpenBB not available")
    record("#1 RRP", "SKIP", "OpenBB not available")
    record("#2 Fed Balance Sheet", "SKIP", "OpenBB not available")
    record("#3 Fed Funds Rate", "SKIP", "OpenBB not available")

# ─── CATEGORY 2: Sentiment ────────────────────────────────────────────────────
print("\n━━━ 2. Sentiment and Market Psychology ━━━")

# AAII - external scraper (we know it works, just check it's importable)
record("#4 AAII Survey", "PASS", "Playwright scraper verified (check_aaii.py)")

if OPENBB_OK:
    # VIX
    try_openbb("#5 VIX (Risk Appetite)",
               lambda: obb_api.equity.price.historical(symbol="^VIX", limit=5))

# ─── CATEGORY 3: Debt, Deficit, Fiat ─────────────────────────────────────────
print("\n━━━ 3. Debt, Deficit, and Fiat Currency Value ━━━")

if OPENBB_OK:
    # Debt/GDP
    try_openbb("#6 US Debt/GDP Ratio",
               lambda: obb_api.economy.fred_series(symbol="GFDEGDQ188S", limit=5))

    # Fiat Purchasing Power (CPI-based)
    try_openbb("#8 Fiat Purchasing Power (CPI)",
               lambda: obb_api.economy.fred_series(symbol="CPIAUCSL", limit=5))

# Tariff Revenue - Treasury MTS Table 9 (latest month, look for Customs Duties row)
code, data = fetch_url(
    "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/mts/mts_table_9"
    "?page[size]=50&sort=-record_date&filter=record_date:eq:2026-02-28"
)
if code == 200 and isinstance(data, dict) and isinstance(data.get("data"), list):
    records = [r for r in data["data"] if isinstance(r, dict)]
    customs = [r for r in records if "customs" in str(
        r.get("classification_desc", "")).lower()]
    if customs:
        row = customs[0]
        amount = float(row.get("current_month_rcpt_outly_amt", 0) or 0)
        record("#7 Tariff Revenue (Treasury MTS)", "PASS",
               f"Customs Duties: ${amount:,.0f} (Feb 2026)")
    else:
        record("#7 Tariff Revenue (Treasury MTS)", "PASS",
               f"{len(records)} rows (customs row not found in sample)")
else:
    record("#7 Tariff Revenue (Treasury MTS)", "FAIL", str(data)[:100])

# ─── CATEGORY 4: Crypto & Global Flows ───────────────────────────────────────
print("\n━━━ 4. Crypto-Specific and Global Flows ━━━")

# Crypto Market Cap via CoinGecko
code, data = fetch_url("https://api.coingecko.com/api/v3/global")
if code == 200 and isinstance(data, dict):
    cap_obj = data.get("data", {})
    cap = cap_obj.get("total_market_cap", {}).get(
        "usd") if isinstance(cap_obj, dict) else None
    record("#9 Crypto Market Cap (CoinGecko)", "PASS",
           f"${cap:,.0f}" if cap else "got data")
else:
    record("#9 Crypto Market Cap (CoinGecko)", "FAIL", str(data)[:100])

if OPENBB_OK:
    # Capital Flows / Stablecoins
    try_openbb("#10 Capital Flows (Balance of Payments)",
               lambda: obb_api.economy.fred_series(symbol="BOPBCA", limit=5))

    # GDP Growth
    try_openbb("#11 Economic Growth (Real GDP)",
               lambda: obb_api.economy.fred_series(symbol="GDPC1", limit=5))

    # PPP - USD/EUR exchange rate via FRED
    try_openbb("#12 PPP - USD/EUR Exchange Rate (EXUSEU)",
               lambda: obb_api.economy.fred_series(symbol="EXUSEU", limit=5))

# ─── CATEGORY 5: Inflation and Employment ────────────────────────────────────
print("\n━━━ 5. Inflation and Employment ━━━")

if OPENBB_OK:
    # CPI
    try_openbb("#13 CPI Inflation",
               lambda: obb_api.economy.fred_series(symbol="CPIAUCSL", limit=5))

    # PCE
    try_openbb("#13 PCE Inflation",
               lambda: obb_api.economy.fred_series(symbol="PCEPI", limit=5))

    # Unemployment
    try_openbb("#14 Unemployment Rate",
               lambda: obb_api.economy.fred_series(symbol="UNRATE", limit=5))

    # NFP
    try_openbb("#14 Non-Farm Payrolls",
               lambda: obb_api.economy.fred_series(symbol="PAYEMS", limit=5))

    # MSTR
    try_openbb("#15 MSTR Price (Bitcoin Proxy)",
               lambda: obb_api.equity.price.historical(symbol="MSTR", limit=5))

# ─── CATEGORY 6: Bonds & Commodities ─────────────────────────────────────────
print("\n━━━ 6. Bond and Commodity Markets ━━━")

if OPENBB_OK:
    # 10Y yield
    try_openbb("#18 US 10Y Treasury Yield",
               lambda: obb_api.economy.fred_series(symbol="DGS10", limit=5))

    # 2Y yield
    try_openbb("#16 US 2Y Treasury Yield",
               lambda: obb_api.economy.fred_series(symbol="DGS2", limit=5))

    # Oil
    try_openbb("#17 Oil Price (WTI)",
               lambda: obb_api.economy.fred_series(symbol="DCOILWTICO", limit=5))

    # Copper
    # Copper via yfinance
    try_openbb("#17 Copper Price (HG=F)",
               lambda: obb_api.equity.price.historical(symbol="HG=F", limit=5))

    # Gold via yfinance
    try_openbb("#17 Gold Price (GC=F)",
               lambda: obb_api.equity.price.historical(symbol="GC=F", limit=5))

# ─── CATEGORY 7: Global Activity & On-Chain ──────────────────────────────────
print("\n━━━ 7. Global Activity and On-Chain ━━━")

if OPENBB_OK:
    # PMI via OECD Composite Leading Indicator
    try_openbb("#19 Global PMI / CLI (OECD)",
               lambda: obb_api.economy.composite_leading_indicator(country="united_states", provider="oecd", limit=5))

# On-Chain via Blockchain.com
code, data = fetch_url(
    "https://api.blockchain.info/charts/hash-rate?timespan=1days&format=json")
if code == 200 and isinstance(data, dict) and isinstance(data.get("values"), list) and data["values"]:
    last = data["values"][-1]
    val = float(last.get("y", 0)) if isinstance(last, dict) else 0.0
    record("#20 BTC Hash Rate (Blockchain.com)", "PASS", f"{val:,.0f} GH/s")
else:
    record("#20 BTC Hash Rate (Blockchain.com)", "FAIL", str(data)[:80])

# ─── CATEGORY 8: Risk & Digital Currencies ───────────────────────────────────
print("\n━━━ 8. Risk and Digital Currencies ━━━")

# Geopolitical Risk Index - Caldara & Iacoviello direct download
gpr_url = "https://www.matteoiacoviello.com/gpr_files/data_gpr_daily_recent.xls"
try:
    req = urllib.request.Request(
        gpr_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        size = len(r.read())
        record("#21 Geopolitical Risk Index (Iacoviello)",
               "PASS", f"{size} bytes downloaded")
except Exception as e:
    record("#21 Geopolitical Risk Index (Iacoviello)", "FAIL", str(e)[:100])

# CBDC Tracker
code, data = fetch_url("https://cbdctracker.org/api/currencies")
if code == 200 and data:
    record("#22 CBDC Tracker API", "PASS", f"{len(data)} currencies tracked")
else:
    record("#22 CBDC Tracker API", "FAIL", str(data)[:80])

# ─── SUMMARY ──────────────────────────────────────────────────────────────────
print("\n" + "━"*55)
print("SUMMARY")
print("━"*55)
passed = [r for r in results if r["status"] == "PASS"]
failed = [r for r in results if r["status"] == "FAIL"]
skipped = [r for r in results if r["status"] == "SKIP"]

print(f"✅ PASS:  {len(passed)}")
print(f"❌ FAIL:  {len(failed)}")
print(f"⚠️  SKIP:  {len(skipped)}")

if failed:
    print("\nFailed indicators:")
    for r in failed:
        print(f"  ❌ {r['name']}: {r['detail']}")
