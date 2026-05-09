#!/usr/bin/env python3
"""
check_greeks_backend.py — Fortress Dashboard
Checks the active Greeks backend and OPRA subscription status.
Reports which backend is live, whether OPRA is active, and what
action (if any) is needed to restore live Greeks.

Usage:
    python3 check_greeks_backend.py [--watch]

Options:
    --watch     Repeat check every 60 seconds until Ctrl+C
"""

import sys
import time
import json
import pathlib
import urllib.request
import urllib.error
from datetime import datetime, timezone

API_URL = "http://localhost:8080"
TOKEN_FILE = pathlib.Path("/home/ubuntu/.fortress_api_token")


def get_token() -> str:
    env_token = __import__("os").environ.get("FORTRESS_API_TOKEN")
    if env_token:
        return env_token
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text().strip()
    raise RuntimeError("No bearer token found. Set FORTRESS_API_TOKEN or create ~/.fortress_api_token")


def api_get(path: str, token: str) -> dict:
    req = urllib.request.Request(
        f"{API_URL}{path}",
        headers={"Authorization": f"Bearer {token}"}
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def check(token: str) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'='*60}")
    print(f"  FORTRESS GREEKS BACKEND CHECK — {now}")
    print(f"{'='*60}")

    # --- Capability check ---
    try:
        cap = api_get("/api/ibkr/capability", token)
    except Exception as e:
        print(f"  ❌ Could not reach /api/ibkr/capability: {e}")
        return

    active = cap.get("active_backend", "unknown")
    fallback = cap.get("fallback_backend", "unknown")
    settings_val = cap.get("settings_value", "unknown")

    # Backend status line
    backend_icon = "✅" if active == "web_api" else ("🟡" if active == "bs_yfinance" else "❌")
    print(f"\n  Active backend   : {backend_icon} {active}")
    print(f"  Settings value   : {settings_val}")
    print(f"  Fallback backend : {fallback}")

    # --- CP Gateway (Web API) ---
    web = cap.get("web_api", {})
    sess = web.get("session_status", {})
    gw_reachable = sess.get("reachable", False)
    gw_connected = sess.get("connected", False)
    gw_authed = sess.get("authenticated", False)
    opra = web.get("opra_subscribed")
    opra_test = web.get("opra_test")

    print(f"\n  ── CP Gateway (Web API) ──────────────────────────────")
    print(f"  Reachable        : {'✅' if gw_reachable else '❌'} {gw_reachable}")
    print(f"  Connected        : {'✅' if gw_connected else '❌'} {gw_connected}")
    print(f"  Authenticated    : {'✅' if gw_authed else '❌'} {gw_authed}")

    if not gw_reachable:
        err = web.get("error") or sess.get("error", "unknown error")
        print(f"  Error            : {err}")

    # OPRA
    if opra is None:
        opra_icon = "⚠️ "
        opra_label = "Unknown (gateway not reachable)"
    elif opra:
        opra_icon = "✅"
        opra_label = "Active"
    else:
        opra_icon = "❌"
        opra_label = "Not subscribed / not detected"

    print(f"\n  ── OPRA Subscription ────────────────────────────────")
    print(f"  OPRA subscribed  : {opra_icon} {opra_label}")

    if opra_test:
        spy_delta = opra_test.get("spy_delta")
        spy_iv = opra_test.get("spy_iv_pct")
        test_ok = opra_test.get("ok", False)
        test_icon = "✅" if test_ok else "❌"
        print(f"  Live OPRA test   : {test_icon} SPY Δ={spy_delta}  IV={spy_iv}%")
    elif gw_reachable:
        print(f"  Live OPRA test   : ⚠️  Not run (gateway reachable but no test result)")

    # --- TWS Gateway ---
    tws = cap.get("tws_gateway", {})
    tws_reach = tws.get("reachable", False)
    print(f"\n  ── TWS Gateway ──────────────────────────────────────")
    print(f"  Reachable        : {'✅' if tws_reach else '❌'} {tws_reach}")
    if not tws_reach:
        print(f"  (Expected — TWS Gateway is decommissioned)")

    # --- Greeks coverage ---
    try:
        briefing = api_get("/api/briefing", token)
        greeks_src = briefing.get("greeks_source", "unknown")
        positions = briefing.get("positions", [])
        live_count = sum(1 for p in positions if p.get("greeks_source") == "live")
        bs_count = sum(1 for p in positions if p.get("greeks_source") in ("bs", "bs_yfinance"))
        total = len(positions)
        print(f"\n  ── Greeks Coverage ──────────────────────────────────")
        print(f"  Source           : {greeks_src}")
        print(f"  Live Greeks      : {live_count}/{total} positions")
        print(f"  BS fallback      : {bs_count}/{total} positions")
    except Exception as e:
        print(f"\n  ⚠️  Could not fetch briefing for Greeks coverage: {e}")

    # --- Summary & recommended action ---
    print(f"\n  ── Status & Action ──────────────────────────────────")
    if active == "web_api" and opra:
        print("  ✅ OPTIMAL — Web API live with OPRA. All Greeks are live.")
        action = None
    elif active == "web_api" and not opra:
        print("  🟡 PARTIAL — Web API connected but OPRA not active.")
        print("     Greeks are live but IV/vega may use BS fallback.")
        action = "Check OPRA subscription in IBKR account management."
    elif active == "bs_yfinance" and gw_reachable:
        print("  🟡 DEGRADED — Gateway reachable but backend resolved to BS.")
        action = "Check settings: set greeks_backend=web_api and restart service."
    elif active == "bs_yfinance":
        print("  🔴 FALLBACK — CP Gateway is down. Using Black-Scholes via yfinance.")
        print("     Greeks are estimated, not live market data.")
        action = "Restart CP Gateway: cd ~/Fortress_Dashboard && docker compose up -d ib-gateway"
    else:
        print(f"  ❓ UNKNOWN — active_backend={active}")
        action = "Check /api/ibkr/capability manually."

    if action:
        print(f"\n  Recommended action:")
        print(f"  → {action}")

    print(f"\n{'='*60}\n")


def main():
    watch = "--watch" in sys.argv
    token = get_token()

    if watch:
        print("Watching Greeks backend (Ctrl+C to stop)...")
        try:
            while True:
                check(token)
                time.sleep(60)
        except KeyboardInterrupt:
            print("\nStopped.")
    else:
        check(token)


if __name__ == "__main__":
    main()
