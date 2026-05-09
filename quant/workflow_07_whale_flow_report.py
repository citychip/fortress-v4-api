"""
Workflow 07: Whale Flow Report
Focus: Confirmation tool for new entries. Evaluates institutional order flow sweeps.
- Pulls order flow sweeps for Tier 1 tickers.
- Calculates call vs put premium bias from aggressive sweeps.
- Flags bullish or bearish institutional intent.
- Strategy Note: Use as confirmation only, NOT as a primary trade trigger.
  The 10-day earnings blackout rule overrides any flow signal.
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
    print(f"WHALE FLOW REPORT — {today}")
    print("=" * 60)

    # Fetch all trades from the order_flow_ticker tool (currently set to last ticker)
    # We use the consolidated order flow which has all tickers' trades
    tid = TOOLS.get("order_flow_ticker")
    if not tid:
        print("Error: order_flow_ticker tool not configured.")
        return

    # Fetch current trades (the tool is already loaded with recent data)
    data = {}
    try:
        resp = session.get(f"{BASE_URL}/options/order-flow/consolidated/{tid}", timeout=10)
        if resp.status_code == 200:
            data = resp.json().get("response", {})
    except Exception: pass

    trades = data.get("trades", [])

    # Aggregate call vs put premium by ticker from the trades list
    ticker_flow = {}
    for trade in trades:
        t = trade.get("ticker", "")
        if t not in TICKERS:
            continue
        if t not in ticker_flow:
            ticker_flow[t] = {"call_premium": 0, "put_premium": 0, "call_sweeps": 0, "put_sweeps": 0}
        premium = trade.get("premiumInCents", 0) / 100
        ct = trade.get("contractType", "")
        is_sweep = trade.get("tradeConsolidationType", "") == "SWEEP"
        if ct == "CALL":
            ticker_flow[t]["call_premium"] += premium
            if is_sweep: ticker_flow[t]["call_sweeps"] += 1
        elif ct == "PUT":
            ticker_flow[t]["put_premium"] += premium
            if is_sweep: ticker_flow[t]["put_sweeps"] += 1

    results = []
    for ticker in TICKERS:
        flow = ticker_flow.get(ticker)
        if not flow:
            results.append([ticker, "$0.0M", "$0.0M", "0", "0", "—"])
            continue
        call_p = flow["call_premium"] / 1e6
        put_p = flow["put_premium"] / 1e6
        bias = "🟢 CALL-HEAVY" if call_p > put_p else "🔴 PUT-HEAVY" if put_p > call_p else "—"
        results.append([ticker, f"${call_p:.1f}M", f"${put_p:.1f}M", str(flow["call_sweeps"]), str(flow["put_sweeps"]), bias])

    print("\n" + tabulate(results, headers=["Ticker", "Call Premium", "Put Premium", "Call Sweeps", "Put Sweeps", "Bias"], tablefmt="pipe"))
    print("\n⚠️  Strategy Note: Use as confirmation only, NOT as a primary trade trigger.")
    print("   The 10-day earnings blackout rule overrides any flow signal.")

    # Save to file
    out_path = pathlib.Path.home() / "quantdata_reports" / f"Workflow_07_Whale_Flow_{today}.md"
    with open(out_path, "w") as f:
        f.write(f"# Whale Flow Report ({today})\n\n")
        f.write(tabulate(results, headers=["Ticker", "Call Premium", "Put Premium", "Call Sweeps", "Put Sweeps", "Bias"], tablefmt="pipe"))
        f.write("\n\n> **Strategy Note:** Use as confirmation only, NOT as a primary trade trigger. The 10-day earnings blackout rule overrides any flow signal.\n")

    print(f"\nReport saved to: {out_path}")

if __name__ == "__main__":
    main()
