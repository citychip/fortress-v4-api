import os
"""
Workflow 05: IV Crush Opportunity Report (v2 — Real HV)
Focus: Finds the richest premium-selling opportunities by comparing current IV to
       true Historical Volatility (HV) computed from 20-day and 30-day price returns.

HV is calculated as:
    HV = sqrt(252) * std(log(P[t]/P[t-1]) for last N days) * 100
    Source: yfinance daily close prices (90-day history)

This is the correct IV/HV spread — NOT a comparison of IV to its own minimum.
A high IV/HV spread means the options market is pricing in more vol than the
stock has actually realized — the premium-seller's edge.
"""

import json
import math
import pathlib
import time
from datetime import datetime, timezone, timedelta

import numpy as np
import yfinance as yf
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

TICKER_UNIVERSE_FILE = pathlib.Path.home() / "ticker_universe.json"
EARNINGS_FILE = pathlib.Path.home() / "earnings_blocklist.json"
POSITIONS_FILE = pathlib.Path.home() / "active_positions.json"
EARNINGS_BLACKOUT_DAYS = 10
CONCENTRATION_LIMIT_PCT = 50.0

def load_tickers() -> list[str]:
    try:
        data = json.loads(TICKER_UNIVERSE_FILE.read_text())
        return data.get("tier1", []) + data.get("tier2", [])
    except Exception as e:
        print(f"Warning: Could not load ticker universe: {e}")
        return ["MSFT", "AVGO", "NFLX", "VST", "GOOGL", "AMZN", "AMD", "MSTR", "META", "AAPL", "NVDA"]

ALL_TICKERS = load_tickers()

def check_earnings_days(ticker: str, today: datetime) -> str:
    try:
        data = json.loads(EARNINGS_FILE.read_text())
        entry = data.get("tickers", {}).get(ticker, {})
        edate_str = entry.get("next_earnings")
        if not edate_str: return "-"
        edate = datetime.strptime(edate_str, "%Y-%m-%d").replace(tzinfo=ET)
        days = (edate - today).days
        if 0 <= days <= EARNINGS_BLACKOUT_DAYS:
            return f"🚫 {days}d"
        elif days < 0:
            return "-"
        return f"{days}d"
    except Exception:
        return "-"

def check_concentration_risk(ticker: str) -> str:
    try:
        data = json.loads(POSITIONS_FILE.read_text())
        pct = sum(p.get("net_liq_pct", 0) for p in data.get("positions", []) if p.get("ticker") == ticker)
        if pct >= CONCENTRATION_LIMIT_PCT:
            return f"⚠️ {pct:.0f}%"
        return "-"
    except Exception:
        return "-"


def update_tool(tool_key: str, metadata: dict):
    tid = TOOLS.get(tool_key)
    if not tid:
        return
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    payload = {
        "id": tid, "userId": USER_ID, "filterGroupIds": [],
        "metadata": metadata, "pageId": PAGE_ID,
        "createdTime": now_ms, "lastUpdatedTime": now_ms,
    }
    try:
        session.put(f"{BASE_URL}/tool", json=payload, timeout=10)
    except Exception:
        pass


def fetch(endpoint: str, tool_key: str) -> dict:
    tid = TOOLS.get(tool_key)
    if not tid:
        return {}
    try:
        resp = session.get(f"{BASE_URL}/{endpoint}/{tid}", timeout=10)
        if resp.status_code == 200:
            return resp.json().get("response", {})
    except Exception:
        pass
    return {}


def compute_hv(ticker_symbol: str, window: int = 20) -> float:
    """
    Compute annualised Historical Volatility from daily log-returns.
    Uses yfinance for price history (90-day lookback to ensure enough data).
    Returns HV as a percentage (e.g. 33.4 for 33.4%).
    Returns 0.0 on failure.
    """
    try:
        # yfinance uses ^GSPC for SPX
        yf_symbol = "^GSPC" if ticker_symbol == "SPX" else ticker_symbol
        hist = yf.Ticker(yf_symbol).history(period="90d", auto_adjust=True)
        closes = hist["Close"].values
        if len(closes) < window + 2:
            return 0.0
        log_returns = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
        hv = math.sqrt(252) * float(np.std(log_returns[-window:])) * 100
        return round(hv, 2)
    except Exception:
        return 0.0


def get_iv_rank(ticker: str, today: str) -> dict:
    """Fetch IV Rank data from QuantData for a given ticker."""
    meta = {
        "filter": {
            "contractType": {"filterOperationType": "EQUALS", "value": []},
            "ticker": {"filterOperationType": "EQUALS", "value": ticker},
        },
        "lookBackPeriod": 365, "maturity": 30, "type": "OPTIONS_IV_RANK_CHART",
    }
    update_tool("iv_rank", meta)
    time.sleep(0.5)
    data = fetch("options/iv-rank", "iv_rank")
    if not data:
        return {}

    price = data.get("stockPriceInCents", 0) / 100
    ivr_map = data.get("sessionDateToIVRankData", {})
    today_data = ivr_map.get(today, {})
    ct_data = today_data.get("contractTypeToIVData", {})
    call_iv = ct_data.get("CALL", {})
    put_iv = ct_data.get("PUT", {})

    def calc_ivr(iv_dict):
        last = iv_dict.get("lastIV", 0)
        lo = iv_dict.get("windowMinIV", 0)
        hi = iv_dict.get("windowMaxIV", 1)
        return round((last - lo) / (hi - lo) * 100, 1) if hi > lo else 0.0

    call_ivr = calc_ivr(call_iv)
    put_ivr = calc_ivr(put_iv)
    avg_ivr = round((call_ivr + put_ivr) / 2, 1) if (call_ivr or put_ivr) else 0.0
    # lastIV is already in percentage form (e.g. 43.7 means 43.7%)
    current_iv = round((call_iv.get("lastIV", 0) + put_iv.get("lastIV", 0)) / 2, 2)

    return {"price": price, "ivr": avg_ivr, "current_iv": current_iv}


def classify_signal(ivr: float, current_iv: float, hv20: float, edays: str, conc: str) -> tuple[str, float]:
    """
    Classify the IV/HV opportunity.
    spread = current_iv - hv20  (both in percentage points)
    Returns (signal_label, spread).
    """
    spread = round(current_iv - hv20, 1)
    
    # Hard gates override the signal
    if "🚫" in edays:
        return "🚫 BLOCKED (EARNINGS)", spread
    if "⚠️" in conc:
        return "⚠️ BLOCKED (CONCENTRATION)", spread
        
    if ivr >= 50 and spread > 10:
        return "🔥 PRIME CRUSH", spread
    elif ivr >= 25 and spread > 5:
        return "✅ GOOD SPREAD", spread
    elif ivr >= 25 and spread > 0:
        return "⚠️ FAIR SPREAD", spread
    elif ivr >= 25:
        return "⚠️ IV HIGH / HV HIGH", spread
    else:
        return "❌ POOR SPREAD", spread


def main():
    today_et = datetime.now(ET)
    today_str = today_et.strftime("%Y-%m-%d")
    print("=" * 80)
    print(f"IV CRUSH OPPORTUNITY REPORT — {today_str}")
    print("HV Source: yfinance 20-day realized volatility (annualised)")
    print("=" * 80)

    results = []
    for ticker in ALL_TICKERS:
        print(f"  Scanning {ticker}...          ", end="\r")

        # Hard gates checks
        edays = check_earnings_days(ticker, today_et)
        conc = check_concentration_risk(ticker)

        # Step 1: Get real HV from price history
        hv20 = compute_hv(ticker, window=20)
        hv30 = compute_hv(ticker, window=30)

        # Step 2: Get current IV and IVR from QuantData
        iv_data = get_iv_rank(ticker, today_str)
        if not iv_data:
            continue

        price = iv_data["price"]
        ivr = iv_data["ivr"]
        current_iv = iv_data["current_iv"]

        # Step 3: Classify signal using real IV/HV spread
        signal, spread = classify_signal(ivr, current_iv, hv20, edays, conc)

        results.append({
            "ticker": ticker,
            "price": price,
            "ivr": ivr,
            "current_iv": current_iv,
            "hv20": hv20,
            "hv30": hv30,
            "spread": spread,
            "edays": edays,
            "conc": conc,
            "signal": signal,
        })

    print(" " * 50 + "\r", end="")

    # Sort: PRIME CRUSH first, then by spread descending
    results.sort(key=lambda x: (-1 if "PRIME" in x["signal"] else (1 if "BLOCKED" in x["signal"] else 0), -x["spread"]))

    table_rows = [
        [
            r["ticker"],
            f"${r['price']:.2f}",
            f"{r['ivr']:.1f}",
            f"{r['current_iv']:.1f}%",
            f"{r['hv20']:.1f}%",
            f"{r['spread']:+.1f}pp",
            r["edays"],
            r["conc"],
            r["signal"],
        ]
        for r in results
    ]
    headers = ["Ticker", "Price", "IVR", "Cur IV", "HV-20", "IV-HV Spread", "Days to ER", "Conc Risk", "Action / Signal"]

    print("\n" + tabulate(table_rows, headers=headers, tablefmt="pipe"))
    print("\nNotes:")
    print("  HV-20 / HV-30 = 20/30-day annualised Historical Volatility from daily log-returns (yfinance)")
    print("  IV-HV Spread  = Current IV minus HV-20 (positive = options overpriced vs realized vol)")
    print("  🔥 PRIME CRUSH = IVR ≥ 50 AND IV-HV Spread > 10pp — highest edge for premium selling")
    print("  ✅ GOOD SPREAD  = IVR ≥ 25 AND IV-HV Spread > 5pp  — solid entry opportunity")
    print("  ⚠️ FAIR SPREAD  = IVR ≥ 25 AND IV-HV Spread > 0pp  — marginal, reduce size")
    print("  ⚠️ IV HIGH/HV HIGH = IVR ≥ 25 but HV is also elevated — real vol risk, caution")
    print("  ❌ POOR SPREAD  = IVR < 25 — below strategy threshold, skip")

    # Save report
    out_dir = pathlib.Path(os.environ.get("FORTRESS_DATA_DIR", str(pathlib.Path.home() / "Fortress_Dashboard/quant")))
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"Workflow_05_IV_Crush_{today_str}.md"
    with open(out_path, "w") as f:
        f.write(f"# IV Crush Opportunity Report — {today_str}\n\n")
        f.write(f"**HV Source:** yfinance 20-day realized volatility (annualised log-return method)\n\n")
        f.write(tabulate(table_rows, headers=headers, tablefmt="pipe"))
        f.write("\n\n### Signal Definitions\n")
        f.write("- **🔥 PRIME CRUSH**: IVR ≥ 50 AND IV-HV Spread > 10pp — highest edge for premium selling\n")
        f.write("- **✅ GOOD SPREAD**: IVR ≥ 25 AND IV-HV Spread > 5pp — solid entry opportunity\n")
        f.write("- **⚠️ FAIR SPREAD**: IVR ≥ 25 AND IV-HV Spread > 0pp — marginal, reduce size\n")
        f.write("- **⚠️ IV HIGH / HV HIGH**: IVR ≥ 25 but HV is also elevated — real vol risk, caution\n")
        f.write("- **❌ POOR SPREAD**: IVR < 25 — below strategy threshold, skip\n")

    print(f"\nReport saved to: {out_path}")


if __name__ == "__main__":
    main()
