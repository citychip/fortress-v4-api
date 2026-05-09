"""
Create new QuantData tool instances for the four new pipeline modules:
1. Per-ticker GEX & OI (reuse existing tools, already switchable)
2. Dark Pool Levels (new tool per ticker — we'll use one switchable tool)
3. Dark Flow / Whale Sweeps (new tool — switchable per ticker)
4. HV vs IV — derived from IV Rank data (no new tool needed, computed)

We need to create:
  - dark_pool_levels: DARK_POOL_LEVELS_TABLE (switchable ticker)
  - dark_flow: DARK_FLOW_CHART (switchable ticker)
  - net_flow_ticker: OPTIONS_NET_FLOW_CHART (switchable ticker for Whale Flow)
  - order_flow_ticker: OPTIONS_ORDER_FLOW_CONSOLIDATED_TABLE (switchable ticker)
"""

import json
import pathlib
import uuid
from datetime import datetime, timezone, timedelta
from curl_cffi import requests

CONFIG_PATH = pathlib.Path.home() / ".quantdata-mcp" / "config.json"
config = json.loads(CONFIG_PATH.read_text())
TOKEN = config["auth_token"]
COOKIE = config["cookie"]
PAGE_ID = config["page_id"]
BASE_URL = "https://core-lb-prod.quantdata.us/api"
USER_ID = "a7da66dc-7c6e-4e72-bc1e-555e686adc72"

ET = timezone(timedelta(hours=-4))
today = datetime.now(ET).strftime("%Y-%m-%d")
start_90d = (datetime.now(ET) - timedelta(days=90)).strftime("%Y-%m-%d")

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


def create_tool(tool_type: str, metadata: dict, name: str) -> str | None:
    """Create a new tool on the MCP Agentic Page and return its ID."""
    tool_id = str(uuid.uuid4())
    payload = {
        "id": tool_id,
        "userId": USER_ID,
        "filterGroupIds": [],
        "metadata": {**metadata, "type": tool_type},
        "pageId": PAGE_ID,
        "createdTime": now_ms,
        "lastUpdatedTime": now_ms,
    }
    resp = session.post(f"{BASE_URL}/tool", json=payload, timeout=10)
    if resp.status_code == 200:
        returned_id = resp.json()["response"]["toolDTO"]["id"]
        print(f"  ✅ Created {name}: {returned_id[:12]}...")
        return returned_id
    else:
        print(f"  ❌ Failed {name}: HTTP {resp.status_code} — {resp.text[:100]}")
        return None


# New tools to create
new_tools = {}

print("Creating new QuantData tool instances...")

# 1. Dark Pool Levels (switchable ticker, 90-day lookback)
dp_id = create_tool(
    "DARK_POOL_LEVELS_TABLE",
    {
        "tableMetadata": {"sort": {"field": "PRICE_IN_CENTS", "sortDirectionType": "DESCENDING"}},
        "filter": {"ticker": {"filterOperationType": "EQUALS", "value": "SPY"}},
        "maximumLevelCount": 50,
        "sessionDateStart": start_90d,
        "sessionDateEnd": today,
    },
    "dark_pool_levels"
)
if dp_id:
    new_tools["dark_pool_levels"] = dp_id

# 2. Dark Flow Chart (switchable ticker)
df_id = create_tool(
    "DARK_FLOW_CHART",
    {
        "filter": {"ticker": {"filterOperationType": "EQUALS", "value": "SPY"}},
    },
    "dark_flow"
)
if df_id:
    new_tools["dark_flow"] = df_id

# 3. Per-ticker Net Flow (switchable ticker — for Whale Flow)
nf_id = create_tool(
    "OPTIONS_NET_FLOW_CHART",
    {
        "filter": {
            "contractType": {"filterOperationType": "EQUALS", "value": []},
            "ticker": {"filterOperationType": "EQUALS", "value": "SPY"},
        },
    },
    "net_flow_ticker"
)
if nf_id:
    new_tools["net_flow_ticker"] = nf_id

# 4. Per-ticker Order Flow (switchable ticker — for Whale Sweeps)
of_id = create_tool(
    "OPTIONS_ORDER_FLOW_CONSOLIDATED_TABLE",
    {
        "filter": {
            "contractType": {"filterOperationType": "EQUALS", "value": []},
            "ticker": {"filterOperationType": "EQUALS", "value": "SPY"},
        },
    },
    "order_flow_ticker"
)
if of_id:
    new_tools["order_flow_ticker"] = of_id

# 5. Per-ticker GEX by Strike (switchable ticker)
gex_ticker_id = create_tool(
    "OPTIONS_EXPOSURE_BY_STRIKE_CHART",
    {
        "filter": {
            "contractType": {"filterOperationType": "EQUALS", "value": []},
            "ticker": {"filterOperationType": "EQUALS", "value": "SPY"},
            "exposureType": {"filterOperationType": "EQUALS", "value": "GEX"},
        },
    },
    "gex_by_strike_ticker"
)
if gex_ticker_id:
    new_tools["gex_by_strike_ticker"] = gex_ticker_id

# 6. Per-ticker OI by Strike (switchable ticker)
oi_ticker_id = create_tool(
    "OPTIONS_OPEN_INTEREST_BY_STRIKE_CHART",
    {
        "filter": {
            "contractType": {"filterOperationType": "EQUALS", "value": []},
            "ticker": {"filterOperationType": "EQUALS", "value": "SPY"},
        },
    },
    "oi_by_strike_ticker"
)
if oi_ticker_id:
    new_tools["oi_by_strike_ticker"] = oi_ticker_id

# Update config with new tools
config["tools"].update(new_tools)
CONFIG_PATH.write_text(json.dumps(config, indent=2))
print(f"\nConfig updated with {len(new_tools)} new tools.")
print("New tools:", list(new_tools.keys()))
