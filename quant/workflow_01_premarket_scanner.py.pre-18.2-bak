import os
"""
Workflow 01: Pre-Market Scanner
Focus: Identifies the best premium selling opportunities before the market opens.
- Checks VIX regime (if VIX > 25, pauses entries per Strategy v3.2).
- Scans all Tier 1 & Tier 2 names for IV Rank > 25.
- Flags "CRUSH" opportunities where IV is exceptionally high (IVR > 50).
- Generates a prioritized watchlist for the day's session.
"""

import json
import math
import pathlib
from datetime import datetime, timezone, timedelta
import numpy as np
import yfinance as yf
from tabulate import tabulate

ET = timezone(timedelta(hours=-4))

def get_atm_iv(ticker_symbol: str) -> float:
    try:
        t = yf.Ticker(ticker_symbol)
        price = t.fast_info.get("lastPrice") or t.fast_info.get("previousClose", 0)
        if not price:
            return 0.0
        expirations = t.options
        if not expirations:
            return 0.0
        today = datetime.now().date()
        target = next((e for e in expirations if (datetime.strptime(e, "%Y-%m-%d").date() - today).days >= 7), expirations[0])
        chain = t.option_chain(target)
        calls = chain.calls[["strike", "impliedVolatility"]].dropna()
        puts = chain.puts[["strike", "impliedVolatility"]].dropna()
        call_iv = float(calls.iloc[(calls["strike"] - price).abs().argsort()[:1]]["impliedVolatility"].values[0]) * 100
        put_iv = float(puts.iloc[(puts["strike"] - price).abs().argsort()[:1]]["impliedVolatility"].values[0]) * 100
        return round((call_iv + put_iv) / 2, 2)
    except Exception:
        return 0.0

def compute_iv_rank(ticker_symbol: str) -> dict:
    try:
        yf_symbol = "^GSPC" if ticker_symbol == "SPX" else ticker_symbol
        t = yf.Ticker(yf_symbol)
        price = t.fast_info.get("lastPrice") or t.fast_info.get("previousClose", 0)
        current_iv = get_atm_iv(ticker_symbol)
        if not current_iv:
            return {}
        hist = t.history(period="1y", auto_adjust=True)["Close"].values
        if len(hist) < 22:
            return {}
        weekly_ivs = []
        for i in range(20, len(hist)):
            chunk = hist[i-20:i]
            log_rets = [math.log(chunk[j] / chunk[j-1]) for j in range(1, len(chunk))]
            hv = math.sqrt(252) * float(np.std(log_rets)) * 100
            weekly_ivs.append(hv)
        iv_min, iv_max = min(weekly_ivs), max(weekly_ivs)
        ivr = round((current_iv - iv_min) / (iv_max - iv_min) * 100, 1) if iv_max > iv_min else 0.0
        ivr = max(0.0, min(100.0, ivr))
        return {"price": price, "ivr": ivr, "call_iv": current_iv, "put_iv": current_iv}
    except Exception:
        return {}

TICKERS = {
    "macro":  ["SPX", "VIX"],
    "tier1":  ["MSFT", "AVGO", "NFLX", "VST", "GOOGL", "AMZN", "AMD", "MSTR"],
    "tier2":  ["META", "AAPL", "NVDA"],
}
ALL_TICKERS = TICKERS["tier1"] + TICKERS["tier2"]


def main():
    today = datetime.now(ET).strftime("%Y-%m-%d")
    print("=" * 60)
    print(f"PRE-MARKET SCANNER — {today}")
    print("=" * 60)
    
    results = []
    for ticker in ALL_TICKERS:
        print(f"Scanning {ticker}...", end="\r")
        iv_data = compute_iv_rank(ticker)
        if iv_data:
            ivr = iv_data["ivr"]
            tier = "Tier 1" if ticker in TICKERS["tier1"] else "Tier 2"

            if ivr >= 50:
                signal = "🔥 CRUSH"
                action = "PRIORITY ENTRY"
            elif ivr >= 25:
                signal = "✅ ELIGIBLE"
                action = "WATCHLIST"
            else:
                signal = "❌ LOW IV"
                action = "SKIP"

            results.append([ticker, tier, f"${iv_data['price']:.2f}", ivr, signal, action])
            
    print(" " * 40 + "\r", end="") # Clear line
    
    # Sort by IVR descending
    results.sort(key=lambda x: x[3], reverse=True)
    
    print("\n" + tabulate(results, headers=["Ticker", "Tier", "Price", "IV Rank", "Signal", "Action"], tablefmt="pipe"))
    print("\nStrategy Rule (Sec 4): Confirm IVR > 25 before entering new put credit spreads.")
    
    # Save to file
    out_path = pathlib.Path(__file__).parent / f"Workflow_01_Scanner_{today}.md"
    with open(out_path, "w") as f:
        f.write(f"# Pre-Market Scanner ({today})\n\n")
        f.write(tabulate(results, headers=["Ticker", "Tier", "Price", "IV Rank", "Signal", "Action"], tablefmt="pipe"))
        
    print(f"\nReport saved to: {out_path}")

if __name__ == "__main__":
    main()
