"""
Manual QuantData MCP setup — uses cookie-based auth (required by the API).
Creates tools on the existing MCP Agentic Page and saves config.
"""
import json
import os
import sys
from datetime import datetime, timezone
from curl_cffi import requests

TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJjcmVhdGVkVGltZSI6MTc3NzczNTE3OTg1NCwidXNlcklkIjoiYTdkYTY2ZGMtN2M2ZS00ZTcyLWJjMWUtNTU1ZTY4NmFkYzcyIiwiaXNzIjoiUXVhbnQgRGF0YSJ9.Zn0fwDn6zYotf4UQA6YTNRt6i4eVqh5FOK6mDvi8N5M"
COOKIE = "intercom-device-id-rxw83n6n=150398c0-5428-4a9b-9e30-f7f51f6fb6bb; client-secret=8d01584c-9a24-443f-b842-67030d180013; token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJjcmVhdGVkVGltZSI6MTc3NzczNTE3OTg1NCwidXNlcklkIjoiYTdkYTY2ZGMtN2M2ZS00ZTcyLWJjMWUtNTU1ZTY4NmFkYzcyIiwiaXNzIjoiUXVhbnQgRGF0YSJ9.Zn0fwDn6zYotf4UQA6YTNRt6i4eVqh5FOK6mDvi8N5M"
USER_ID = "a7da66dc-7c6e-4e72-bc1e-555e686adc72"
PAGE_ID = "ad949618-f765-4a21-a1c1-316eab956bd2"  # MCP Agentic Page
BASE_URL = "https://core-lb-prod.quantdata.us/api"

HEADERS = {
    "accept": "application/json",
    "authorization": TOKEN,
    "cookie": COOKIE,
    "origin": "https://v3.quantdata.us",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "content-type": "application/json",
}

TOOL_DEFINITIONS = {
    "exposure_by_strike": ("OPTIONS_EXPOSURE_BY_STRIKE_CHART", "options/exposure/strike", "Exposure by Strike (GEX/DEX/CEX/VEX)"),
    "net_drift": ("OPTIONS_NET_DRIFT_CHART", "options/net-drift", "Net Drift"),
    "iv_rank": ("OPTIONS_IV_RANK_CHART", "options/iv-rank", "IV Rank"),
    "contract_side_stats": ("OPTIONS_CONTRACT_TRADE_SIDE_STATISTICS_CHART", "options/contract/statistics/trade-side", "Contract Side Statistics"),
    "max_pain": ("OPTIONS_MAX_PAIN_CHART", "options/max-pain", "Max Pain"),
    "net_flow": ("OPTIONS_NET_FLOW_CHART", "options/net-flow", "Net Flow"),
    "order_flow": ("OPTIONS_ORDER_FLOW_CONSOLIDATED_TABLE", "options/order-flow/consolidated", "Order Flow (Consolidated)"),
    "oi_by_strike": ("OPTIONS_OPEN_INTEREST_BY_STRIKE_CHART", "options/open-interest/strike", "Open Interest by Strike"),
    "contract_statistics": ("OPTIONS_CONTRACT_STATISTICS_CHART", "options/contract/statistics", "Contract Statistics"),
    "exposure_by_expiration": ("OPTIONS_EXPOSURE_BY_EXPIRATION_CHART", "options/exposure/expiration", "Exposure by Expiration"),
    "contract_price_time": ("OPTIONS_CONTRACT_PRICE_OVER_TIME_CHART", "options/contract/price/time", "Contract Price / Time"),
}

session = requests.Session(impersonate="chrome110")
session.headers.update(HEADERS)

def create_tool(page_id, tool_type, label):
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    payload = {
        "pageId": page_id,
        "type": tool_type,
    }
    resp = session.post(f"{BASE_URL}/tool", json=payload, timeout=15)
    if resp.status_code == 200:
        data = resp.json()
        tool = data.get("response", {}).get("toolDTO", {})
        return tool.get("id")
    else:
        print(f"  Failed to create tool {label}: HTTP {resp.status_code} — {resp.text[:200]}")
        return None

print("Creating tools on MCP Agentic Page...")
tool_ids = {}
for name, (tool_type, endpoint, label) in TOOL_DEFINITIONS.items():
    print(f"  Creating: {label}... ", end="", flush=True)
    tid = create_tool(PAGE_ID, tool_type, label)
    if tid:
        tool_ids[name] = tid
        print(f"OK ({tid[:12]}...)")
    else:
        print("FAILED")

# Set page filter to today / SPX
today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
filter_payload = {
    "id": PAGE_ID,
    "expirationDate": {"filterOperationType": "EQUALS", "value": today},
    "sessionDate": {"filterOperationType": "EQUALS", "value": today},
    "ticker": {"filterOperationType": "EQUALS", "value": ["SPX"]},
    "createdTime": now_ms,
    "lastUpdatedTime": now_ms,
}
resp = session.put(f"{BASE_URL}/page/filter", json=filter_payload, timeout=10)
print(f"\nSet page filter: HTTP {resp.status_code}")

# Save config
import pathlib
config_dir = pathlib.Path.home() / ".quantdata-mcp"
config_dir.mkdir(exist_ok=True)
config = {
    "auth_token": TOKEN,
    "cookie": COOKIE,
    "instance_id": "manual",
    "page_id": PAGE_ID,
    "tools": tool_ids,
}
with open(config_dir / "config.json", "w") as f:
    json.dump(config, f, indent=2)

print(f"\nConfig saved to ~/.quantdata-mcp/config.json")
print(f"Tools created: {list(tool_ids.keys())}")
