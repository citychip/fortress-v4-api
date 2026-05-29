import os
"""
Workflow 08: Max Pain Report
Focus: Short-dated position management.
- Pulls Max Pain strike for all tickers.
- Compares to current price to identify pinning targets.
"""

import json
import pathlib
from datetime import datetime, timezone, timedelta
import yfinance as yf
from tabulate import tabulate

ET = timezone(timedelta(hours=-4))

TICKERS = ["MSFT", "AVGO", "NFLX", "VST", "GOOGL", "AMZN", "AMD", "MSTR", "META", "AAPL", "NVDA"]

def compute_max_pain(ticker_symbol: str) -> dict:
    """
    Compute max pain strike from yfinance options chain.
    Max pain = strike where sum of ITM call + put value is minimized (for option holders).
    Returns {price, max_pain} or {} on failure.
    """
    try:
        t = yf.Ticker(ticker_symbol)
        price = t.fast_info.get("lastPrice") or t.fast_info.get("previousClose", 0)
        if not price:
            return {}
        expirations = t.options
        if not expirations:
            return {}
        # Use nearest expiry 7-30 days out for max pain relevance
        today = datetime.now().date()
        target = None
        for exp in expirations:
            days = (datetime.strptime(exp, "%Y-%m-%d").date() - today).days
            if 7 <= days <= 30:
                target = exp
                break
        if not target:
            target = expirations[0]
        chain = t.option_chain(target)
        calls = chain.calls[["strike", "openInterest"]].dropna()
        puts = chain.puts[["strike", "openInterest"]].dropna()
        strikes = sorted(set(calls["strike"].tolist() + puts["strike"].tolist()))
        min_pain, max_pain_strike = float("inf"), strikes[0]
        for s in strikes:
            call_pain = sum(max(0, s - k) * oi for k, oi in zip(calls["strike"], calls["openInterest"]) if k < s)
            put_pain  = sum(max(0, k - s) * oi for k, oi in zip(puts["strike"],  puts["openInterest"])  if k > s)
            total = call_pain + put_pain
            if total < min_pain:
                min_pain, max_pain_strike = total, s
        return {"price": price, "max_pain": max_pain_strike}
    except Exception:
        return {}


def main():
    today = datetime.now(ET).strftime("%Y-%m-%d")
    print("=" * 60)
    print(f"MAX PAIN REPORT — {today}")
    print("=" * 60)

    results = []
    for ticker in TICKERS:
        print(f"Scanning {ticker}...", end="\r")
        data = compute_max_pain(ticker)
        if data:
            price = data["price"]
            pain = data["max_pain"]
            dist = (pain - price) / price * 100
            pull = "⬆️ UP" if pain > price else "⬇️ DOWN"
            results.append([ticker, f"${price:.2f}", f"${pain:.2f}", f"{dist:+.1f}%", pull])
            
    print(" " * 40 + "\r", end="") # Clear line
    
    print("\n" + tabulate(results, headers=["Ticker", "Current Price", "Max Pain Strike", "Distance", "Pinning Pull"], tablefmt="pipe"))
    print("\nStrategy Note: Most relevant for positions in their final 7-14 days before expiration.")
    
    # Save to file
    out_path = pathlib.Path(__file__).parent / f"Workflow_08_Max_Pain_{today}.md"
    with open(out_path, "w") as f:
        f.write(f"# Max Pain Report ({today})\n\n")
        f.write(tabulate(results, headers=["Ticker", "Current Price", "Max Pain Strike", "Distance", "Pinning Pull"], tablefmt="pipe"))
        
    print(f"\nReport saved to: {out_path}")

if __name__ == "__main__":
    main()
