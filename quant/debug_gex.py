"""Debug GEX by strike for MSFT to understand data structure."""
import json, pathlib
from curl_cffi import requests
from datetime import datetime, timezone

config = json.loads(pathlib.Path.home().joinpath(".quantdata-mcp/config.json").read_text())
TOKEN = config["auth_token"]
COOKIE = config["cookie"]
PAGE_ID = config["page_id"]
TOOLS = config["tools"]
BASE_URL = "https://core-lb-prod.quantdata.us/api"
USER_ID = "a7da66dc-7c6e-4e72-bc1e-555e686adc72"

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

now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
gex_id = TOOLS["gex_by_strike_ticker"]

# Update to MSFT
payload = {
    "id": gex_id,
    "userId": USER_ID,
    "filterGroupIds": [],
    "metadata": {
        "filter": {
            "contractType": {"filterOperationType": "EQUALS", "value": []},
            "ticker": {"filterOperationType": "EQUALS", "value": "MSFT"},
        },
        "type": "OPTIONS_EXPOSURE_BY_STRIKE_CHART",
    },
    "pageId": PAGE_ID,
    "createdTime": now_ms,
    "lastUpdatedTime": now_ms,
}
resp = session.put(f"{BASE_URL}/tool", json=payload, timeout=10)
print(f"Update: HTTP {resp.status_code}")

# Fetch
resp2 = session.get(f"{BASE_URL}/options/exposure/strike/{gex_id}", timeout=10)
print(f"Fetch: HTTP {resp2.status_code}")
if resp2.status_code == 200:
    data = resp2.json().get("response", {})
    print(f"Keys: {list(data.keys())}")
    for k, v in data.items():
        if isinstance(v, list):
            print(f"  {k}: {len(v)} items")
            if v:
                print(f"  Sample: {json.dumps(v[0])}")
        elif isinstance(v, dict):
            print(f"  {k}: {list(v.keys())}")
        else:
            print(f"  {k}: {v}")
else:
    print(resp2.text[:200])
