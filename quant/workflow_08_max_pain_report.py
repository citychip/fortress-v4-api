"""
Workflow 08: Max Pain Report
Focus: Short-dated position management.
- Pulls Max Pain strike for all tickers.
- Compares to current price to identify pinning targets.
"""

import json
import pathlib
from datetime import datetime, timezone, timedelta
from curl_cffi import requests
from tabulate import tabulate

CONFIG_PATH = pathlib.Path.home() / ".quantdata-mcp" / "config.json"
config = json.loads(CONFIG_PATH.read_text())
TOKEN = config["auth_token"]
COOKIE = config["cookie"]
PAGE_ID = config["page_id"]
TOOLS = config["tools"]
BASE_URL = "https://core-lb-prod.quantdata.us/api"
USER_ID = "a7da66dc-7c6e-4e72-bc1e-555e686adc72"
ET = timezone(timedelta(hours=-4))

HEADERS = {
    "accept": "application/json",
    "authorization": TOKEN,
    "cookie": COOKIE,
    "origin": "https://v3.quantdata.us",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "content-type": "application/json",
}
session = requests.Session(impersonate="chrome110")
session.headers.update(HEADERS)

TICKERS = ["MSFT", "AVGO", "NFLX", "VST", "GOOGL", "AMZN", "AMD", "MSTR", "META", "AAPL", "NVDA"]

def update_tool(tool_key: str, metadata: dict):
    tid = TOOLS.get(tool_key)
    if not tid: return
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    payload = {
        "id": tid, "userId": USER_ID, "filterGroupIds": [],
        "metadata": metadata, "pageId": PAGE_ID,
        "createdTime": now_ms, "lastUpdatedTime": now_ms,
    }
    try: session.put(f"{BASE_URL}/tool", json=payload, timeout=10)
    except Exception: pass

def fetch(endpoint: str, tool_key: str) -> dict:
    tid = TOOLS.get(tool_key)
    if not tid: return {}
    try:
        resp = session.get(f"{BASE_URL}/{endpoint}/{tid}", timeout=10)
        if resp.status_code == 200: return resp.json().get("response", {})
    except Exception: pass
    return {}

def main():
    today = datetime.now(ET).strftime("%Y-%m-%d")
    print("=" * 60)
    print(f"MAX PAIN REPORT — {today}")
    print("=" * 60)
    
    results = []
    for ticker in TICKERS:
        print(f"Scanning {ticker}...", end="\r")
        meta = {
            "filter": {
                "expirationDate": {"filterOperationType": "EQUALS"},
                "ticker": {"filterOperationType": "EQUALS", "value": ticker}
            },
            "type": "OPTIONS_MAX_PAIN_CHART"
        }
        update_tool("max_pain", meta)
        data = fetch("options/max-pain", "max_pain")
        if data:
            price = data.get("stockPriceInCents", 0) / 100
            pain = data.get("strikePriceInCentsWithMaxPain", 0) / 100
            if pain:
                dist = (pain - price) / price * 100
                pull = "⬆️ UP" if pain > price else "⬇️ DOWN"
                results.append([ticker, f"${price:.2f}", f"${pain:.2f}", f"{dist:+.1f}%", pull])
            
    print(" " * 40 + "\r", end="") # Clear line
    
    print("\n" + tabulate(results, headers=["Ticker", "Current Price", "Max Pain Strike", "Distance", "Pinning Pull"], tablefmt="pipe"))
    print("\nStrategy Note: Most relevant for positions in their final 7-14 days before expiration.")
    
    # Save to file
    out_path = pathlib.Path.home() / "quantdata_reports" / f"Workflow_08_Max_Pain_{today}.md"
    with open(out_path, "w") as f:
        f.write(f"# Max Pain Report ({today})\n\n")
        f.write(tabulate(results, headers=["Ticker", "Current Price", "Max Pain Strike", "Distance", "Pinning Pull"], tablefmt="pipe"))
        
    print(f"\nReport saved to: {out_path}")

if __name__ == "__main__":
    main()
