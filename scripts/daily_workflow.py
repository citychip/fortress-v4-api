#!/usr/bin/env python3
"""
Fortress Dashboard — Daily Workflow Orchestrator
Runs the full daily workflow from §1 Pre-Market through §6 EOD Review.
Each phase can be run independently or all together.

Usage:
    python3 daily_workflow.py                    # full workflow
    python3 daily_workflow.py --phase premarket  # single phase
    python3 daily_workflow.py --phase open       # market open scripts
    python3 daily_workflow.py --phase monitor    # mid-day monitoring
    python3 daily_workflow.py --phase eod        # EOD review

Environment:
    FORTRESS_API_URL   — defaults to http://YOUR_VPS_IP:8080
    FORTRESS_API_TOKEN — required (or reads from ~/.fortress_api_token)
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

# ── Config ────────────────────────────────────────────────────────────────────
BASE = os.environ.get("FORTRESS_API_URL", "http://YOUR_VPS_IP:8080")
TOKEN = os.environ.get("FORTRESS_API_TOKEN", "")
if not TOKEN:
    token_file = Path.home() / ".fortress_api_token"
    if token_file.exists():
        TOKEN = token_file.read_text().strip()

if not TOKEN:
    print("ERROR: FORTRESS_API_TOKEN not set and ~/.fortress_api_token not found")
    sys.exit(1)

HEADERS = {"Authorization": f"Bearer {TOKEN}"}
RESULTS = {}

# ── Helpers ───────────────────────────────────────────────────────────────────
def api(method, path, **kwargs):
    url = f"{BASE}{path}"
    r = requests.request(method, url, headers=HEADERS, timeout=60, **kwargs)
    return r

def run_script(key, label=None):
    label = label or key
    print(f"  ▶ Running {label}...", end=" ", flush=True)
    t0 = time.time()
    r = api("POST", f"/api/run/{key}")
    elapsed = round(time.time() - t0, 1)
    if r.status_code == 200:
        d = r.json()
        exit_code = d.get("exit_code", "?")
        status = "✅" if exit_code == 0 else "⚠️"
        print(f"{status} exit={exit_code} ({elapsed}s)")
        RESULTS[label] = {"status": "PASS" if exit_code == 0 else "WARN", "elapsed": elapsed}
        return d
    else:
        print(f"❌ HTTP {r.status_code} ({elapsed}s)")
        RESULTS[label] = {"status": "FAIL", "http": r.status_code}
        return None

def section(title):
    print(f"\n{'─'*60}")
    print(f"  {title}")
    print(f"{'─'*60}")

# ── Phase 1: Pre-Market ───────────────────────────────────────────────────────
def phase_premarket():
    section("§1 PRE-MARKET")

    # 1.1 Sync IBKR positions
    print("  ▶ Syncing IBKR positions...", end=" ", flush=True)
    r = api("POST", "/api/ibkr/sync")
    if r.status_code == 200:
        d = r.json()
        print(f"✅ {d.get('positions_count', '?')} positions synced")
        RESULTS["ibkr_sync"] = {"status": "PASS", "positions": d.get("positions_count")}
    else:
        print(f"❌ HTTP {r.status_code}")
        RESULTS["ibkr_sync"] = {"status": "FAIL"}

    # 1.2 Check capability
    print("  ▶ Checking Greeks backend...", end=" ", flush=True)
    r = api("GET", "/api/ibkr/capability")
    if r.status_code == 200:
        d = r.json()
        backend = d.get("active_backend", "?")
        opra = d.get("opra_active", False)
        print(f"✅ backend={backend} opra={opra}")
        RESULTS["capability"] = {"status": "PASS", "backend": backend}
    else:
        print(f"❌ HTTP {r.status_code}")
        RESULTS["capability"] = {"status": "FAIL"}

    # 1.3 Morning briefing
    print("  ▶ Loading morning briefing...", end=" ", flush=True)
    r = api("GET", "/api/briefing")
    if r.status_code == 200:
        d = r.json()
        greeks = d.get("greeks", {}) or {}
        delta = greeks.get("portfolio_delta", "?")
        theta = greeks.get("portfolio_theta", "?")
        regime = (d.get("macro_regime") or {}).get("regime", "?")
        print(f"✅ Δ={delta} Θ={theta} regime={regime}")
        RESULTS["briefing"] = {"status": "PASS", "delta": delta, "theta": theta}
    else:
        print(f"❌ HTTP {r.status_code}")
        RESULTS["briefing"] = {"status": "FAIL"}

    # 1.4 Run premarket scanner
    run_script("premarket", "premarket_scanner")

# ── Phase 2: Market Open ──────────────────────────────────────────────────────
def phase_open():
    section("§2 MARKET OPEN")
    run_script("daily", "quantdata_daily_report")
    run_script("iv_crush", "iv_crush_scanner")
    run_script("whale_flow", "whale_flow_scanner")
    run_script("entry_scoring", "entry_scoring")
    run_script("gex_oi", "gex_oi_report")

# ── Phase 3: Trade Entry Check ────────────────────────────────────────────────
def phase_entry(tickers=None):
    section("§3 TRADE ENTRY GATE")
    tickers = tickers or ["MSFT", "AVGO", "GOOGL", "NVDA", "AAPL"]
    for ticker in tickers:
        print(f"  ▶ Pre-trade gate: {ticker}...", end=" ", flush=True)
        r = api("GET", f"/api/manage/pre_trade_check", params={"ticker": ticker})
        if r.status_code == 200:
            d = r.json()
            verdict = d.get("verdict", "?")
            failures = d.get("hard_failures", [])
            icon = "✅" if verdict == "PROCEED" else "🚫"
            detail = f"failures={failures}" if failures else "all gates clear"
            print(f"{icon} {verdict} — {detail}")
            RESULTS[f"pre_trade_{ticker}"] = {"status": "PASS", "verdict": verdict}
        else:
            print(f"❌ HTTP {r.status_code}")
            RESULTS[f"pre_trade_{ticker}"] = {"status": "FAIL"}

# ── Phase 4: Mid-Day Monitoring ───────────────────────────────────────────────
def phase_monitor():
    section("§4 MID-DAY MONITORING")
    run_script("position_monitor", "position_monitor")
    run_script("dark_pool_alert", "dark_pool_alert")

    # Stop-loss scan for all positions
    print("  ▶ Stop-loss scan (all positions)...", end=" ", flush=True)
    r = api("GET", "/api/manage/positions")
    if r.status_code == 200:
        positions = r.json().get("positions", [])
        alerts = []
        for pos in positions:
            pos_id = pos.get("id", "")
            if not pos_id or "?" in pos_id:
                continue
            r2 = api("GET", f"/api/manage/stop_loss/{pos_id}")
            if r2.status_code == 200:
                d = r2.json()
                if d.get("verdict") not in ("SAFE", None):
                    alerts.append(f"{pos.get('ticker')}: {d.get('verdict')}")
        if alerts:
            print(f"⚠️  {len(alerts)} alerts: {', '.join(alerts)}")
        else:
            print(f"✅ All {len(positions)} positions safe")
        RESULTS["stop_loss_scan"] = {"status": "PASS", "alerts": alerts}
    else:
        print(f"❌ HTTP {r.status_code}")
        RESULTS["stop_loss_scan"] = {"status": "FAIL"}

    # Roll candidates scan
    print("  ▶ Roll candidates scan...", end=" ", flush=True)
    r = api("GET", "/api/manage/positions")
    if r.status_code == 200:
        positions = r.json().get("positions", [])
        roll_ready = []
        for pos in positions:
            pos_id = pos.get("id", "")
            if not pos_id or "?" in pos_id:
                continue
            r2 = api("GET", f"/api/manage/roll/{pos_id}")
            if r2.status_code == 200:
                d = r2.json()
                if d.get("candidates"):
                    roll_ready.append(pos.get("ticker"))
        if roll_ready:
            print(f"📋 Roll candidates: {', '.join(roll_ready)}")
        else:
            print("✅ No positions ready to roll")
        RESULTS["roll_scan"] = {"status": "PASS", "roll_ready": roll_ready}
    else:
        print(f"❌ HTTP {r.status_code}")
        RESULTS["roll_scan"] = {"status": "FAIL"}

# ── Phase 5: SPY Hedge Check ──────────────────────────────────────────────────
def phase_hedge():
    section("§5 SPY HEDGE CHECK")
    print("  ▶ SPY hedge coverage...", end=" ", flush=True)
    r = api("GET", "/api/manage/spy_hedge_coverage")
    if r.status_code == 200:
        d = r.json()
        mv = d.get("hedge_market_value", 0)
        ok = d.get("coverage_ok", False)
        icon = "✅" if ok else "🔴"
        print(f"{icon} hedge_mv=${mv:,.0f} coverage_ok={ok}")
        RESULTS["spy_hedge"] = {"status": "PASS" if ok else "WARN", "hedge_mv": mv, "ok": ok}
    else:
        print(f"❌ HTTP {r.status_code}")
        RESULTS["spy_hedge"] = {"status": "FAIL"}

# ── Phase 6: EOD Review ───────────────────────────────────────────────────────
def phase_eod():
    section("§6 EOD REVIEW")
    run_script("eod_review", "eod_review")

    # Fetch earnings calendar
    print("  ▶ Refreshing earnings calendar...", end=" ", flush=True)
    r = api("POST", "/api/calendar/fetch-earnings")
    if r.status_code == 200:
        d = r.json()
        print(f"✅ fetched={d.get('fetched', 0)}")
        RESULTS["earnings_calendar"] = {"status": "PASS"}
    else:
        print(f"❌ HTTP {r.status_code}")
        RESULTS["earnings_calendar"] = {"status": "FAIL"}

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Fortress Daily Workflow Orchestrator")
    parser.add_argument("--phase", choices=["premarket", "open", "entry", "monitor", "hedge", "eod", "all"],
                        default="all", help="Which phase to run (default: all)")
    parser.add_argument("--tickers", nargs="+", help="Tickers for pre-trade gate check")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  FORTRESS DAILY WORKFLOW — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Phase: {args.phase.upper()}")
    print(f"{'='*60}")

    phase_map = {
        "premarket": phase_premarket,
        "open": phase_open,
        "entry": lambda: phase_entry(args.tickers),
        "monitor": phase_monitor,
        "hedge": phase_hedge,
        "eod": phase_eod,
    }

    if args.phase == "all":
        for fn in phase_map.values():
            fn()
    else:
        phase_map[args.phase]()

    # Summary
    section("SUMMARY")
    passed = sum(1 for v in RESULTS.values() if v.get("status") == "PASS")
    warned = sum(1 for v in RESULTS.values() if v.get("status") == "WARN")
    failed = sum(1 for v in RESULTS.values() if v.get("status") in ("FAIL", "ERROR"))
    print(f"  ✅ PASS: {passed}  ⚠️ WARN: {warned}  ❌ FAIL: {failed}  Total: {len(RESULTS)}")

    if warned or failed:
        print("\n  Items requiring attention:")
        for name, v in RESULTS.items():
            if v.get("status") in ("WARN", "FAIL", "ERROR"):
                print(f"    {'⚠️' if v['status'] == 'WARN' else '❌'} {name}: {v}")

    # Save results
    out_path = Path.home() / "daily_workflow_results.json"
    with open(out_path, "w") as f:
        json.dump({"run_at": datetime.now().isoformat(), "results": RESULTS}, f, indent=2)
    print(f"\n  Results saved to {out_path}")

if __name__ == "__main__":
    main()
