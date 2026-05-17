import yfinance as yf
import json
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

tickers = ["SPY", "SPYV", "SPYG", "XLE"]
results = {}

for t in tickers:
    try:
        obj = yf.Ticker(t)
        hist = obj.history(period="1y")
        info = obj.info
        
        current = hist['Close'].iloc[-1]
        sma20 = hist['Close'].rolling(20).mean().iloc[-1]
        sma50 = hist['Close'].rolling(50).mean().iloc[-1]
        sma200 = hist['Close'].rolling(200).mean().iloc[-1]
        week52_high = hist['Close'].max()
        week52_low = hist['Close'].min()
        
        dist_52w_high = (current / week52_high - 1) * 100
        dist_52w_low = (current / week52_low - 1) * 100
        
        perf_1m = (current / hist['Close'].iloc[-22] - 1) * 100 if len(hist) >= 22 else None
        perf_3m = (current / hist['Close'].iloc[-66] - 1) * 100 if len(hist) >= 66 else None
        
        fundamentals = {
            "category": info.get("category"),
            "expense_ratio": info.get("expenseRatio"),
            "aum": info.get("totalAssets"),
            "yield": info.get("yield"),
            "beta3y": info.get("beta3Year"),
            "description": info.get("longBusinessSummary") or info.get("description")
        }
        
        results[t] = {
            "current_price": round(current, 2),
            "sma20": round(sma20, 2),
            "sma50": round(sma50, 2),
            "sma200": round(sma200, 2),
            "week52_high": round(week52_high, 2),
            "week52_low": round(week52_low, 2),
            "dist_52w_high_pct": round(dist_52w_high, 2),
            "dist_52w_low_pct": round(dist_52w_low, 2),
            "perf_1m_pct": round(perf_1m, 2) if perf_1m else None,
            "perf_3m_pct": round(perf_3m, 2) if perf_3m else None,
            "fundamentals": fundamentals,
            "volume_avg_10d": round(hist['Volume'].tail(10).mean(), 0)
        }
    except Exception as e:
        results[t] = {"error": str(e)}

print(json.dumps(results, indent=2, default=str))
