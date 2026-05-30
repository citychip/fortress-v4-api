import os
"""
Workflow 02: Trade Entry Scoring Engine (v2 — Earnings & Concentration Enforced)
Focus: Evaluates the structural safety of potential put spread entries.

Checks (in order):
  0. HARD GATES (automatic reject regardless of score):
     - Earnings Blackout: within 10 days of next earnings date (v3.2 §4)
     - Concentration Override: ticker already ≥ 50% of NetLiq (v3.2 §7)
  1. Dark Pool Hard Floor: is there a strong DP floor within 15% below price?
  2. GEX Put Walls: are there gamma support levels below current price?
  3. OI Put Walls: are there open interest pinning levels below current price?
  4. Whale Flow: is net premium flow call-heavy (bullish alignment)?

Scoring: 0-4 points -> Grade A (Execute) / B (Acceptable) / C (Caution) / F (Reject)
Hard gates override the score — a ticker blocked by earnings or concentration is REJECTED
regardless of structural score.
"""

import json
import math
import pathlib
import sys
import time
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

_QUANT_DIR = pathlib.Path(__file__).parent
EARNINGS_FILE = _QUANT_DIR / "earnings_blocklist.json"
POSITIONS_FILE = _QUANT_DIR / "active_positions.json"
EARNINGS_BLACKOUT_DAYS = 10
CONCENTRATION_LIMIT_PCT = 50.0  # v3.2 §7: High-Concentration Override threshold


# ─── Helper: Load earnings blocklist ──────────────────────────────────────────

def check_earnings_blackout(ticker: str, today: datetime) -> tuple[bool, str]:
    """
    Returns (is_blocked, reason_string).
    Blocked if next earnings is within EARNINGS_BLACKOUT_DAYS calendar days.
    """
    try:
        data = json.loads(EARNINGS_FILE.read_text())
        entry = data.get("tickers", {}).get(ticker, {})
        earnings_date_str = entry.get("next_earnings")
        if not earnings_date_str:
            return False, ""
        earnings_date = datetime.strptime(earnings_date_str, "%Y-%m-%d").replace(tzinfo=ET)
        days_to_earnings = (earnings_date - today).days
        if 0 <= days_to_earnings <= EARNINGS_BLACKOUT_DAYS:
            confirmed = "✓ confirmed" if entry.get("confirmed") else "unconfirmed"
            return True, (
                f"EARNINGS BLACKOUT: {ticker} reports in {days_to_earnings} day(s) "
                f"({earnings_date_str}, {confirmed}). "
                f"10-day rule active — no new entries."
            )
        elif days_to_earnings < 0:
            return False, f"Note: earnings date {earnings_date_str} is in the past — update earnings_blocklist.json"
        return False, f"Next earnings: {earnings_date_str} ({days_to_earnings} days away — clear)"
    except Exception as e:
        return False, f"Warning: Could not check earnings for {ticker}: {e}"


# ─── Helper: Check concentration ──────────────────────────────────────────────

def check_concentration(ticker: str) -> tuple[bool, str, float]:
    """
    Returns (is_blocked, reason_string, current_pct).
    Blocked if ticker's existing positions already represent ≥ CONCENTRATION_LIMIT_PCT of NetLiq.
    """
    try:
        data = json.loads(POSITIONS_FILE.read_text())
        positions = data.get("positions", [])
        ticker_pct = sum(p.get("net_liq_pct", 0) for p in positions if p.get("ticker") == ticker)
        if ticker_pct >= CONCENTRATION_LIMIT_PCT:
            return True, (
                f"CONCENTRATION OVERRIDE: {ticker} is already {ticker_pct:.1f}% of NetLiq "
                f"(limit: {CONCENTRATION_LIMIT_PCT:.0f}%). "
                f"v3.2 §7 requires additional override conditions before adding more."
            ), ticker_pct
        return False, f"Concentration: {ticker_pct:.1f}% of NetLiq (limit: {CONCENTRATION_LIMIT_PCT:.0f}% — clear)", ticker_pct
    except Exception as e:
        return False, f"Warning: Could not check concentration for {ticker}: {e}", 0.0


# ─── API helpers ──────────────────────────────────────────────────────────────

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


def extract_gex_put_walls(data: dict) -> list[float]:
    """Extract top put GEX support strikes below current price."""
    exp_map = data.get("expirationDateToStrikePriceInCentsToContractExposureMap", {})
    strike_totals: dict[float, float] = {}
    for _, strikes in exp_map.items():
        for sc, ct_data in strikes.items():
            s = int(sc) / 100
            strike_totals[s] = strike_totals.get(s, 0) + ct_data.get("PUT", 0)
    # Negative PUT GEX = dealer short gamma = support
    sorted_s = sorted(strike_totals.items(), key=lambda x: x[1])
    return [s for s, v in sorted_s if v < 0][:3]


def extract_oi_put_walls(data: dict) -> list[float]:
    """Extract top put OI strikes."""
    oi_map = data.get("strikePricesInCentsToPutCallOpenInterest", {})
    put_oi = {int(sc) / 100: d.get("putOpenInterest", 0) for sc, d in oi_map.items()}
    return [s for s, v in sorted(put_oi.items(), key=lambda x: x[1], reverse=True)][:3]


# ─── Main scoring function ────────────────────────────────────────────────────

def main(ticker: str):
    today_et = datetime.now(ET)
    today_str = today_et.strftime("%Y-%m-%d")
    start_90d = (today_et - timedelta(days=90)).strftime("%Y-%m-%d")

    print("\n" + "=" * 65)
    print(f"  ENTRY SCORING ENGINE — {ticker}  ({today_str})")
    print("=" * 65)

    # ── HARD GATE 1: Earnings Blackout ────────────────────────────────────────
    earnings_blocked, earnings_msg = check_earnings_blackout(ticker, today_et)
    print(f"\n[GATE 1] Earnings: {earnings_msg}")
    if earnings_blocked:
        print("\n" + "🚫 " * 20)
        print(f"  HARD REJECT — {ticker} is inside the 10-day earnings blackout window.")
        print(f"  No new entries permitted regardless of structural score.")
        print("🚫 " * 20)
        
        # Log hard reject
        log_dir = pathlib.Path.home() / "quantdata_reports"
        log_dir.mkdir(exist_ok=True)
        with open(log_dir / f"hard_rejects_{today_str}.log", "a") as f:
            f.write(f"[{datetime.now(ET).isoformat()}] REJECT: {ticker} | Reason: Earnings Blackout\n")
        return

    # ── HARD GATE 2: Concentration Override ───────────────────────────────────
    conc_blocked, conc_msg, conc_pct = check_concentration(ticker)
    print(f"[GATE 2] Concentration: {conc_msg}")
    if conc_blocked:
        if "--override" in sys.argv:
            print("\n" + "⚠️ " * 20)
            print(f"  OVERRIDE ACTIVE — {ticker} concentration at {conc_pct:.1f}% exceeds {CONCENTRATION_LIMIT_PCT:.0f}% limit.")
            print(f"  Proceeding to structural scoring per user override flag.")
            print("⚠️ " * 20)
        else:
            print("\n" + "🚫 " * 20)
            print(f"  HARD REJECT — {ticker} concentration at {conc_pct:.1f}% exceeds {CONCENTRATION_LIMIT_PCT:.0f}% limit.")
            print("  Standard entry blocked. Override requires (manually confirmed):")
            print("    1. Post-earnings gap 5-8%")
            print("    2. Thesis health confirmed")
            print("    3. IV crush > 25%")
            print("  Re-run with --override flag if all three are true.")
            print("🚫 " * 20)
            
            # Log hard reject
            log_dir = pathlib.Path(__file__).parent
            with open(log_dir / f"hard_rejects_{today_str}.log", "a") as f:
                f.write(f"[{datetime.now(ET).isoformat()}] REJECT: {ticker} | Reason: Concentration {conc_pct:.1f}% >= {CONCENTRATION_LIMIT_PCT}%\n")
            return

    print("\n  Proceeding to structural scoring...\n")

    # ── STRUCTURAL DATA COLLECTION ────────────────────────────────────────────

    # GEX
    gex_meta = {
        "filter": {
            "expirationDate": {"filterOperationType": "EQUALS"},
            "ticker": {"filterOperationType": "EQUALS", "value": ticker},
        },
        "greekModeType": "GAMMA", "isNet": True,
        "representationModeType": "PER_ONE_PERCENT_MOVE",
        "type": "OPTIONS_EXPOSURE_BY_STRIKE_CHART",
    }
    update_tool("exposure_by_strike", gex_meta)
    time.sleep(0.5)
    gex_data = fetch("options/exposure/strike", "exposure_by_strike")
    put_walls = extract_gex_put_walls(gex_data) if gex_data else []

    # OI
    oi_meta = {
        "filter": {
            "expirationDate": {"filterOperationType": "EQUALS"},
            "ticker": {"filterOperationType": "EQUALS", "value": ticker},
        },
        "type": "OPTIONS_OPEN_INTEREST_BY_STRIKE_CHART",
    }
    update_tool("oi_by_strike", oi_meta)
    time.sleep(0.5)
    oi_data = fetch("options/open-interest/strike", "oi_by_strike")
    put_oi = extract_oi_put_walls(oi_data) if oi_data else []

    # Dark Pool
    dp_id = TOOLS.get("dark_pool_levels")
    dp_levels: list[float] = []
    price = 0.0
    if dp_id:
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        dp_payload = {
            "id": dp_id, "userId": USER_ID, "filterGroupIds": [],
            "metadata": {
                "tableMetadata": {"sort": {"field": "PRICE_IN_CENTS", "sortDirectionType": "DESCENDING"}},
                "filter": {"ticker": {"filterOperationType": "EQUALS", "value": ticker}},
                "maximumLevelCount": 50,
                "sessionDateStart": start_90d, "sessionDateEnd": today_str,
                "type": "DARK_POOL_LEVELS_TABLE",
            },
            "pageId": PAGE_ID, "createdTime": now_ms, "lastUpdatedTime": now_ms,
        }
        try:
            session.put(f"{BASE_URL}/tool", json=dp_payload, timeout=10)
            time.sleep(0.5)
            dp_data = fetch("equities/dark-pool/levels", "dark_pool_levels")
            if dp_data:
                price = dp_data.get("stockPriceInCents", 0) / 100
                levels_map = dp_data.get("priceInCentsToDarkPoolLevelDataSumModelMap", {})
                sorted_levels = sorted(
                    levels_map.items(),
                    key=lambda x: x[1].get("notionalValueInCentsSum", 0),
                    reverse=True,
                )
                dp_levels = [int(k) / 100 for k, _ in sorted_levels[:3]]
        except Exception:
            pass

    # Whale Flow
    flow_meta = {
        "filter": {
            "contractType": {"filterOperationType": "EQUALS", "value": []},
            "ticker": {"filterOperationType": "EQUALS", "value": ticker},
        },
        "type": "OPTIONS_NET_FLOW_CHART",
    }
    update_tool("net_flow", flow_meta)
    time.sleep(0.5)
    flow_data = fetch("options/net-flow", "net_flow")
    bias = "NEUTRAL"
    if flow_data:
        entries = flow_data.get("netFlow", [])
        if entries:
            call_total = sum(e[1] for e in entries if len(e) > 1)
            put_total = sum(e[2] for e in entries if len(e) > 2)
            bias = "🟢 CALL-HEAVY" if call_total > put_total else "🔴 PUT-HEAVY"

    # ── SCORING ───────────────────────────────────────────────────────────────

    print(f"  Current Price: ${price:.2f}")
    print("-" * 65)

    score = 0
    max_score = 4

    # Check 1: Dark Pool Hard Floor
    top_dp = dp_levels[0] if dp_levels else 0
    dp_dist = ((price - top_dp) / price * 100) if price and top_dp else 0
    if 0 < dp_dist < 15:
        print(f"  ✅ [+1] DP Hard Floor: ${top_dp:.2f} ({dp_dist:.1f}% below price) — valid Thesis Stop")
        score += 1
    elif top_dp:
        print(f"  ❌ [+0] DP Hard Floor: ${top_dp:.2f} ({dp_dist:.1f}% below price) — too far or absent")
    else:
        print(f"  ❌ [+0] DP Hard Floor: No significant level found")

    # Check 2: GEX Put Walls
    gex_support = any(s < price for s in put_walls)
    if gex_support:
        below = [f"${s:.0f}" for s in put_walls if s < price]
        print(f"  ✅ [+1] GEX Put Walls: {', '.join(below)} — gamma support below price")
        score += 1
    else:
        print(f"  ❌ [+0] GEX Put Walls: {put_walls} — no gamma support below price")

    # Check 3: OI Put Walls
    oi_support = any(s < price for s in put_oi)
    if oi_support:
        below = [f"${s:.0f}" for s in put_oi if s < price]
        print(f"  ✅ [+1] OI Put Walls: {', '.join(below)} — open interest pinning support")
        score += 1
    else:
        print(f"  ❌ [+0] OI Put Walls: {put_oi} — no pinning support below price")

    # Check 4: Whale Flow
    if "CALL-HEAVY" in bias:
        print(f"  ✅ [+1] Whale Flow: {bias} — bullish alignment with put spread entry")
        score += 1
    else:
        print(f"  ❌ [+0] Whale Flow: {bias} — bearish flow, wait for reversal")

    # ── VERDICT ───────────────────────────────────────────────────────────────
    print("-" * 65)
    if score == 4:
        grade, action = "A", "EXECUTE — All four structural checks passed."
    elif score == 3:
        grade, action = "B", "ACCEPTABLE — Proceed with reduced size (50% of normal)."
    elif score == 2:
        grade, action = "C", "CAUTION — Weak structure. Wait for improvement."
    else:
        grade, action = "F", "REJECT — Insufficient structural support. Skip."

    print(f"\n  FINAL SCORE: {score}/{max_score}  |  Grade: {grade}  |  {action}")

    if score >= 3 and top_dp:
        print(f"\n  Thesis Stop: ${top_dp:.2f} (Dark Pool Hard Floor)")
        print(f"  Suggested short strike: below ${top_dp:.2f}")
        print(f"  DTE target: 30–45 days (per v3.2 §4)")

    print("=" * 65 + "\n")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        main(sys.argv[1].upper())
    else:
        print("Usage: python3 workflow_02_entry_scoring.py <TICKER>")
        print("Example: python3 workflow_02_entry_scoring.py MSFT")
