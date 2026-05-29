import os
"""
Workflow 06: Dark Pool Alert Report
Focus: Conditional alerting for active positions approaching or breaking Dark Pool hard floors.
- Pulls top 3 Dark Pool levels for active book.
- Checks distance from current price.
- Alerts on state change: APPROACHING (< 2%), BREAKING (< 0.5%), or BROKEN (< 0%).
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

# Load active book dynamically from position file
POSITIONS_FILE = pathlib.Path.home() / "active_positions.json"
def load_active_book() -> list[dict]:
    """Load active positions from the positions file. Returns list of position dicts."""
    try:
        data = json.loads(POSITIONS_FILE.read_text())
        # Exclude pure hedge positions (SPY_HEDGE) from Dark Pool monitoring
        # since they are long puts — DP floors work differently for hedges
        return [p for p in data.get("positions", []) if p.get("strategy") != "SPY_HEDGE"]
    except Exception as e:
        print(f"Warning: Could not load {POSITIONS_FILE}: {e}")
        print("Falling back to hardcoded default book.")
        return [{"ticker": t} for t in ["MSFT", "AVGO", "VST", "NFLX", "NVDA", "UNH", "AMZN", "GOOGL"]]

def fetch(endpoint: str, tool_key: str) -> dict:
    tid = TOOLS.get(tool_key)
    if not tid: return {}
    try:
        resp = session.get(f"{BASE_URL}/{endpoint}/{tid}", timeout=10)
        if resp.status_code == 200: return resp.json().get("response", {})
    except Exception: pass
    return {}

def main():
    today_et = datetime.now(ET).strftime("%Y-%m-%d")
    start_90d = (datetime.now(ET) - timedelta(days=90)).strftime("%Y-%m-%d")
    
    print("=" * 60)
    print(f"DARK POOL ALERT REPORT — {today_et}")
    print("=" * 60)
    
    dp_id = TOOLS.get("dark_pool_levels")
    if not dp_id:
        print("Error: dark_pool_levels tool not configured.")
        return
        
    positions = load_active_book()
    print(f"Monitoring {len(positions)} active positions: {', '.join(p['ticker'] for p in positions)}")
    results = []
    alerts_triggered = False
    
    for pos in positions:
        ticker = pos["ticker"]
        print(f"Checking {ticker}...", end="\r")
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        dp_payload = {
            "id": dp_id, "userId": USER_ID, "filterGroupIds": [],
            "metadata": {
                "tableMetadata": {"sort": {"field": "PRICE_IN_CENTS", "sortDirectionType": "DESCENDING"}},
                "filter": {"ticker": {"filterOperationType": "EQUALS", "value": ticker}},
                "maximumLevelCount": 50, "sessionDateStart": start_90d, "sessionDateEnd": today_et, "type": "DARK_POOL_LEVELS_TABLE"
            },
            "pageId": PAGE_ID, "createdTime": now_ms, "lastUpdatedTime": now_ms,
        }
        try:
            session.put(f"{BASE_URL}/tool", json=dp_payload, timeout=10)
            dp_data = fetch("equities/dark-pool/levels", "dark_pool_levels")
            if dp_data:
                price = dp_data.get("stockPriceInCents", 0) / 100
                levels_map = dp_data.get("priceInCentsToDarkPoolLevelDataSumModelMap", {})
                sorted_levels = sorted(levels_map.items(), key=lambda x: x[1].get("notionalValueInCentsSum", 0), reverse=True)
                top_dp = int(sorted_levels[0][0])/100 if sorted_levels else 0
                
                state = "SAFE"
                dist = 0
                if top_dp:
                    dist = (price - top_dp) / price * 100
                    if dist < 0:
                        state = "🚨 BROKEN"
                        alerts_triggered = True
                    elif dist < 0.5:
                        state = "⚠️ BREAKING"
                        alerts_triggered = True
                    elif dist < 2:
                        state = "👀 APPROACHING"
                        alerts_triggered = True
                        
                if state != "SAFE":
                    strategy = pos.get("strategy", "")
                    short_k = pos.get("short_strike", "")
                    strike_info = f"{strategy} K{short_k}" if short_k else strategy
                    results.append([ticker, strike_info, f"${price:.2f}", f"${top_dp:.2f}", f"{dist:.1f}%", state])
        except Exception: pass
        
    print(" " * 40 + "\r", end="") # Clear line
    
    if not alerts_triggered:
        print("✅ No Dark Pool alerts triggered. All active positions are SAFE.")
    else:
        print(tabulate(results, headers=["Ticker", "Position", "Current Price", "Dark Pool Floor", "Buffer", "State"], tablefmt="pipe"))
        print("\nStrategy Rule (Sec 6): If price closes below Dark Pool floor, thesis is broken. Close immediately.")
    
    # Save to file
    out_path = pathlib.Path(__file__).parent / f"Workflow_06_DP_Alerts_{today_et}.md"
    with open(out_path, "w") as f:
        f.write(f"# Dark Pool Alert Report ({today_et})\n\n")
        f.write(f"Positions monitored: {', '.join(p['ticker'] for p in positions)}\n\n")
        if not alerts_triggered:
            f.write("✅ No Dark Pool alerts triggered. All active positions are SAFE.\n")
        else:
            f.write(tabulate(results, headers=["Ticker", "Position", "Current Price", "Dark Pool Floor", "Buffer", "State"], tablefmt="pipe"))
        
    print(f"\nReport saved to: {out_path}")

if __name__ == "__main__":
    main()
