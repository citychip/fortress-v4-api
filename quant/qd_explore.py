"""Explore all QuantData API endpoints and print data structures."""
import json
import pathlib
from curl_cffi import requests

config = json.loads(pathlib.Path.home().joinpath(".quantdata-mcp/config.json").read_text())
TOKEN = config["auth_token"]
COOKIE = config["cookie"]
TOOLS = config["tools"]
BASE_URL = "https://core-lb-prod.quantdata.us/api"
TODAY = "2026-05-01"

HEADERS = {
    "accept": "application/json",
    "authorization": TOKEN,
    "cookie": COOKIE,
    "origin": "https://v3.quantdata.us",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}
session = requests.Session(impersonate="chrome110")
session.headers.update(HEADERS)

def fetch(endpoint, tool_key):
    tid = TOOLS[tool_key]
    resp = session.get(f"{BASE_URL}/{endpoint}/{tid}", timeout=15)
    print(f"\n{'='*60}")
    print(f"Tool: {tool_key} | HTTP {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json().get("response", {})
        print(f"Response keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")
        # Print a small sample
        print(json.dumps(data, indent=2)[:800])
    else:
        print(f"Error: {resp.text[:200]}")

fetch("options/iv-rank", "iv_rank")
fetch("options/net-drift", "net_drift")
fetch("options/exposure/strike", "exposure_by_strike")
fetch("options/max-pain", "max_pain")
fetch("options/open-interest/strike", "oi_by_strike")
fetch("options/net-flow", "net_flow")
fetch("options/order-flow/consolidated", "order_flow")
