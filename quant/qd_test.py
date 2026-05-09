"""Test all QuantData API endpoints using the saved config and cookie auth."""
import json
import pathlib
from datetime import datetime, timezone
from curl_cffi import requests

# Load config
config = json.loads(pathlib.Path.home().joinpath(".quantdata-mcp/config.json").read_text())
TOKEN = config["auth_token"]
COOKIE = config["cookie"]
PAGE_ID = config["page_id"]
TOOLS = config["tools"]
BASE_URL = "https://core-lb-prod.quantdata.us/api"

HEADERS = {
    "accept": "application/json",
    "authorization": TOKEN,
    "cookie": COOKIE,
    "origin": "https://v3.quantdata.us",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "content-type": "application/json",
}

session = requests.Session(impersonate="chrome110")
session.headers.update(HEADERS)

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")

# Step 1: Set page filter to SPX / today
print(f"Setting page filter: SPX / {TODAY}...")
filter_payload = {
    "id": PAGE_ID,
    "sessionDate": {"filterOperationType": "EQUALS", "value": TODAY},
    "expirationDate": {"filterOperationType": "EQUALS", "value": TODAY},
    "ticker": {"filterOperationType": "EQUALS", "value": ["SPX"]},
}
resp = session.put(f"{BASE_URL}/page/filter", json=filter_payload, timeout=10)
print(f"  Page filter: HTTP {resp.status_code} — {resp.text[:100]}")

# Step 2: Test IV rank
print("\nTesting IV Rank (SPX)...")
iv_tool_id = TOOLS["iv_rank"]
resp = session.get(f"{BASE_URL}/options/iv-rank/{iv_tool_id}", timeout=15)
print(f"  HTTP {resp.status_code}")
if resp.status_code == 200:
    data = resp.json()
    r = data.get("response", {})
    print(f"  Keys: {list(r.keys())}")
    price = r.get("stockPriceInCents", 0) / 100
    print(f"  Stock price: ${price:.2f}")
    ivr_data = r.get("sessionDateToIVRankData", {})
    today_ivr = ivr_data.get(TODAY, {})
    print(f"  IVR today: {today_ivr}")
else:
    print(f"  Error: {resp.text[:200]}")

# Step 3: Test max pain
print("\nTesting Max Pain (SPX)...")
mp_tool_id = TOOLS["max_pain"]
resp = session.get(f"{BASE_URL}/options/max-pain/{mp_tool_id}", timeout=15)
print(f"  HTTP {resp.status_code}")
if resp.status_code == 200:
    data = resp.json()
    r = data.get("response", {})
    print(f"  Keys: {list(r.keys())}")
    mp = r.get("maxPainInCents", 0) / 100
    price = r.get("stockPriceInCents", 0) / 100
    print(f"  Max Pain: ${mp:.2f}, Current Price: ${price:.2f}")
else:
    print(f"  Error: {resp.text[:200]}")

# Step 4: Test net drift
print("\nTesting Net Drift (SPX)...")
nd_tool_id = TOOLS["net_drift"]
resp = session.get(f"{BASE_URL}/options/net-drift/{nd_tool_id}", timeout=15)
print(f"  HTTP {resp.status_code}")
if resp.status_code == 200:
    data = resp.json()
    r = data.get("response", {})
    print(f"  Keys: {list(r.keys())}")
    entries = r.get("netDriftEntries", [])
    if entries:
        last = entries[-1]
        print(f"  Latest drift entry: {last}")
else:
    print(f"  Error: {resp.text[:200]}")

# Step 5: Test exposure by strike (GEX)
print("\nTesting Exposure by Strike (SPX)...")
gex_tool_id = TOOLS["exposure_by_strike"]
resp = session.get(f"{BASE_URL}/options/exposure/strike/{gex_tool_id}", timeout=15)
print(f"  HTTP {resp.status_code}")
if resp.status_code == 200:
    data = resp.json()
    r = data.get("response", {})
    print(f"  Keys: {list(r.keys())}")
    price = r.get("stockPriceInCents", 0) / 100
    strikes = r.get("strikePriceToExposureData", {})
    print(f"  Current price: ${price:.2f}, Strike count: {len(strikes)}")
else:
    print(f"  Error: {resp.text[:200]}")

print("\nAll tests complete.")
