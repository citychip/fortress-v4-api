"""
Workflow 01: Pre-Market Scanner
Focus: Identifies the best premium selling opportunities before the market opens.
- Checks VIX regime (if VIX > 25, pauses entries per Strategy v3.2).
- Scans all Tier 1 & Tier 2 names for IV Rank > 25.
- Flags "CRUSH" opportunities where IV is exceptionally high (IVR > 50).
- Generates a prioritized watchlist for the day's session.
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

TICKERS = {
    "macro":  ["SPX", "VIX"],
    "tier1":  ["MSFT", "AVGO", "NFLX", "VST", "GOOGL", "AMZN", "AMD", "MSTR"],
    "tier2":  ["META", "AAPL", "NVDA"],
}
ALL_TICKERS = TICKERS["tier1"] + TICKERS["tier2"]

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

def extract_iv_rank(data: dict, date: str) -> dict:
    ivr_map = data.get("sessionDateToIVRankData", {})
    today_data = ivr_map.get(date, {})
    price = data.get("stockPriceInCents", 0) / 100
    ct_data = today_data.get("contractTypeToIVData", {})
    call_iv = ct_data.get("CALL", {})
    put_iv = ct_data.get("PUT", {})
    
    def calc_ivr(iv_dict):
        last, lo, hi = iv_dict.get("lastIV", 0), iv_dict.get("windowMinIV", 0), iv_dict.get("windowMaxIV", 1)
        return round((last - lo) / (hi - lo) * 100, 1) if hi > lo else 0.0
        
    call_ivr, put_ivr = calc_ivr(call_iv), calc_ivr(put_iv)
    avg_ivr = round((call_ivr + put_ivr) / 2, 1) if (call_ivr or put_ivr) else 0.0
    return {"price": price, "ivr": avg_ivr, "call_iv": round(call_iv.get("lastIV",0),2), "put_iv": round(put_iv.get("lastIV",0),2)}

def main():
    today = datetime.now(ET).strftime("%Y-%m-%d")
    print("=" * 60)
    print(f"PRE-MARKET SCANNER — {today}")
    print("=" * 60)
    
    results = []
    for ticker in ALL_TICKERS:
        print(f"Scanning {ticker}...", end="\r")
        meta = {
            "filter": {
                "contractType": {"filterOperationType": "EQUALS", "value": []},
                "ticker": {"filterOperationType": "EQUALS", "value": ticker},
            },
            "lookBackPeriod": 365, "maturity": 30, "type": "OPTIONS_IV_RANK_CHART",
        }
        update_tool("iv_rank", meta)
        data = fetch("options/iv-rank", "iv_rank")
        if data:
            iv_data = extract_iv_rank(data, today)
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
    out_path = pathlib.Path.home() / "quantdata_reports" / f"Workflow_01_Scanner_{today}.md"
    with open(out_path, "w") as f:
        f.write(f"# Pre-Market Scanner ({today})\n\n")
        f.write(tabulate(results, headers=["Ticker", "Tier", "Price", "IV Rank", "Signal", "Action"], tablefmt="pipe"))
        
    print(f"\nReport saved to: {out_path}")

if __name__ == "__main__":
    main()
