import os
"""
Workflow 04: End of Day Review
Focus: Summarizes the day's macro regime and net drift to inform the next day's bias.
- Pulls SPX Net Drift (cumulative premium flow).
- Pulls SPX Order Flow (aggressive buys vs sells).
- Generates a final "Regime Status" for the trading journal.
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

def fetch(endpoint: str, tool_key: str) -> dict:
    tid = TOOLS.get(tool_key)
    if not tid: return {}
    try:
        resp = session.get(f"{BASE_URL}/{endpoint}/{tid}", timeout=10)
        if resp.status_code == 200: return resp.json().get("response", {})
    except Exception: pass
    return {}

def extract_net_drift(data: dict) -> dict:
    entries = data.get("netDrift", [])
    if not entries:
        return {"direction": "N/A", "call_cum": 0, "put_cum": 0, "net": 0}
    call_cum = sum(e[1] for e in entries if len(e) > 1)
    put_cum = sum(e[2] for e in entries if len(e) > 2)
    net = call_cum - put_cum
    return {
        "direction": "🟢 BULLISH" if net > 0 else "🔴 BEARISH",
        "call_cum": call_cum / 1e6,
        "put_cum": put_cum / 1e6,
        "net": net / 1e6
    }

def extract_order_flow(data: dict) -> dict:
    stats = data.get("contractSideStatistics", {})
    calls = stats.get("CALL", {})
    puts = stats.get("PUT", {})
    call_buy = calls.get("BUY", {}).get("premium", 0)
    put_sell = puts.get("SELL", {}).get("premium", 0)
    call_sell = calls.get("SELL", {}).get("premium", 0)
    put_buy = puts.get("BUY", {}).get("premium", 0)
    
    bull_flow = call_buy + put_sell
    bear_flow = call_sell + put_buy
    
    return {
        "bias": "🟢 BULLISH" if bull_flow > bear_flow else "🔴 BEARISH",
        "bull_flow": bull_flow / 1e6,
        "bear_flow": bear_flow / 1e6
    }

def main():
    today_et = datetime.now(ET).strftime("%Y-%m-%d")
    print("=" * 60)
    print(f"END OF DAY REVIEW — {today_et}")
    print("=" * 60)
    
    print("Fetching SPX Macro Data...\n")
    
    # Drift
    drift_data = fetch("options/net-drift", "net_drift")
    drift = extract_net_drift(drift_data) if drift_data else {"direction": "N/A", "call_cum": 0, "put_cum": 0, "net": 0}
    
    # Order Flow
    of_data = fetch("options/contract-side-statistics", "contract_side_stats")
    of = extract_order_flow(of_data) if of_data else {"bias": "N/A", "bull_flow": 0, "bear_flow": 0}
    
    results = [
        ["Net Drift (Cumulative Premium)", drift["direction"], f"${drift['net']:.1f}M"],
        ["Order Flow (Aggressive Sweeps)", of["bias"], f"Bull: ${of['bull_flow']:.1f}M | Bear: ${of['bear_flow']:.1f}M"]
    ]
    
    print(tabulate(results, headers=["Metric", "Direction", "Details"], tablefmt="pipe"))
    
    # Final Regime
    bull_count = sum(1 for r in results if "BULLISH" in r[1])
    regime = "🟢 BULLISH" if bull_count == 2 else "🔴 BEARISH" if bull_count == 0 else "🟡 MIXED"
    
    print("\n" + "-" * 60)
    print(f"FINAL REGIME: {regime}")
    print("-" * 60)
    
    # Save to file
    out_path = pathlib.Path.home() / "quantdata_reports" / f"Workflow_04_EOD_{today_et}.md"
    with open(out_path, "w") as f:
        f.write(f"# End of Day Review ({today_et})\n\n")
        f.write(tabulate(results, headers=["Metric", "Direction", "Details"], tablefmt="pipe"))
        f.write(f"\n\n**FINAL REGIME:** {regime}\n")
        
    print(f"\nReport saved to: {out_path}")

if __name__ == "__main__":
    main()
