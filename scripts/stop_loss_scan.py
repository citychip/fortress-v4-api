#!/usr/bin/env python3
"""
Fortress Dashboard — Stop-Loss Scanner
Checks every active position against the 4-level stop-loss engine.
Prints a table of all positions with their stop-loss verdict and signals.

Usage:
    python3 stop_loss_scan.py
    python3 stop_loss_scan.py --ticker MSFT    # single ticker
    python3 stop_loss_scan.py --alerts-only    # only show non-SAFE positions
"""
import argparse
import os
import sys
from pathlib import Path

import requests

BASE = os.environ.get("FORTRESS_API_URL", "http://YOUR_VPS_IP:8080")
TOKEN = os.environ.get("FORTRESS_API_TOKEN", "")
if not TOKEN:
    token_file = Path.home() / ".fortress_api_token"
    if token_file.exists():
        TOKEN = token_file.read_text().strip()

if not TOKEN:
    print("ERROR: FORTRESS_API_TOKEN not set")
    sys.exit(1)

HEADERS = {"Authorization": f"Bearer {TOKEN}"}

VERDICT_ICONS = {
    "SAFE": "✅",
    "WATCH": "👁️",
    "SOFT_STOP": "⚠️",
    "HARD_STOP": "🛑",
    "CLOSE_NOW": "🔴",
}


def get_positions():
    r = requests.get(f"{BASE}/api/manage/positions", headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r.json().get("positions", [])


def check_stop_loss(pos_id):
    r = requests.get(f"{BASE}/api/manage/stop_loss/{pos_id}", headers=HEADERS, timeout=15)
    if r.status_code == 200:
        return r.json()
    return None


def main():
    parser = argparse.ArgumentParser(description="Fortress Stop-Loss Scanner")
    parser.add_argument("--ticker", help="Check a single ticker only")
    parser.add_argument("--alerts-only", action="store_true", help="Only show non-SAFE positions")
    args = parser.parse_args()

    print("\n" + "=" * 70)
    print("  FORTRESS STOP-LOSS SCAN")
    print("=" * 70)

    positions = get_positions()
    if args.ticker:
        positions = [p for p in positions if p.get("ticker", "").upper() == args.ticker.upper()]
        if not positions:
            print(f"No position found for ticker: {args.ticker}")
            sys.exit(0)

    alerts = []
    skipped = []

    print(f"\n{'Ticker':<8} {'Expiry':<10} {'Strike':<10} {'Verdict':<12} {'Signals'}")
    print("-" * 70)

    for pos in positions:
        pos_id = pos.get("id", "")
        ticker = pos.get("ticker", "?")

        # Skip positions with unknown legs (? in ID)
        if not pos_id or "?" in pos_id:
            skipped.append(ticker)
            continue

        result = check_stop_loss(pos_id)
        if not result:
            print(f"{ticker:<8} {'—':<10} {'—':<10} {'ERROR':<12} Could not retrieve")
            continue

        verdict = result.get("verdict", "UNKNOWN")
        signals = result.get("signals", [])
        expiry = pos.get("expiry", "—") or "—"
        strike = str(pos.get("short_strike", "—") or "—")
        icon = VERDICT_ICONS.get(verdict, "❓")

        signal_names = [s.get("name", s) if isinstance(s, dict) else str(s) for s in signals]
        signal_str = ", ".join(signal_names) if signal_names else "none"

        if not args.alerts_only or verdict != "SAFE":
            print(f"{ticker:<8} {expiry:<10} {strike:<10} {icon} {verdict:<10} {signal_str}")

        if verdict not in ("SAFE", None):
            alerts.append({
                "ticker": ticker,
                "verdict": verdict,
                "signals": signal_names,
                "expiry": expiry,
            })

    print("-" * 70)

    if skipped:
        print(f"\n  Skipped (unknown legs): {', '.join(skipped)}")

    if alerts:
        print(f"\n  ⚠️  {len(alerts)} position(s) require attention:")
        for a in alerts:
            print(f"     🔴 {a['ticker']} ({a['expiry']}) — {a['verdict']}: {', '.join(a['signals'])}")
    else:
        print(f"\n  ✅ All positions SAFE")

    print()


if __name__ == "__main__":
    main()
