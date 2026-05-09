#!/usr/bin/env python3
"""
Fortress Dashboard — Pre-Trade Gate Checker
Runs the §8.0 composite pre-trade gate for one or more tickers.
Any failure requires explicit acknowledgment per Strategy §15.1.

Usage:
    python3 pre_trade_gate.py MSFT
    python3 pre_trade_gate.py MSFT AVGO GOOGL
    python3 pre_trade_gate.py --all-universe   # check all tickers in universe
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

GATE_ICONS = {True: "✅", False: "❌"}


def check_ticker(ticker):
    r = requests.get(
        f"{BASE}/api/manage/pre_trade_check",
        headers=HEADERS,
        params={"ticker": ticker},
        timeout=15,
    )
    if r.status_code == 200:
        return r.json()
    return {"error": f"HTTP {r.status_code}", "ticker": ticker}


def print_result(d):
    ticker = d.get("ticker", "?")
    verdict = d.get("verdict", "ERROR")
    reason = d.get("verdict_reason", "")
    gates = d.get("gates", {})

    verdict_icon = "✅ PROCEED" if verdict == "PROCEED" else "🚫 BLOCKED"
    print(f"\n  {ticker} — {verdict_icon}")
    print(f"  {reason}")

    if gates:
        print(f"\n  {'Gate':<22} {'Pass':<6} Detail")
        print(f"  {'─'*60}")
        for name, gate in gates.items():
            passed = gate.get("passed", False)
            detail = gate.get("detail", "")
            icon = GATE_ICONS[passed]
            print(f"  {name:<22} {icon}     {detail}")

    if d.get("acknowledgment_required"):
        print(f"\n  ⚠️  Acknowledgment required before entry (Strategy §15.1)")


def get_universe_tickers():
    r = requests.get(f"{BASE}/api/universe", headers=HEADERS, timeout=15)
    if r.status_code == 200:
        return [t.get("ticker") for t in r.json().get("tickers", []) if t.get("ticker")]
    return []


def main():
    parser = argparse.ArgumentParser(description="Fortress Pre-Trade Gate Checker")
    parser.add_argument("tickers", nargs="*", help="Tickers to check")
    parser.add_argument("--all-universe", action="store_true", help="Check all tickers in universe")
    args = parser.parse_args()

    print("\n" + "=" * 65)
    print("  FORTRESS PRE-TRADE GATE — Build Spec §8.0")
    print("=" * 65)

    tickers = [t.upper() for t in args.tickers]

    if args.all_universe:
        tickers = get_universe_tickers()
        if not tickers:
            print("No tickers in universe. Add tickers via the Universe tab first.")
            sys.exit(0)
        print(f"\n  Checking {len(tickers)} tickers from universe...")

    if not tickers:
        parser.print_help()
        sys.exit(1)

    proceed = []
    blocked = []

    for ticker in tickers:
        d = check_ticker(ticker)
        if "error" in d:
            print(f"\n  {ticker} — ❌ ERROR: {d['error']}")
            continue
        print_result(d)
        if d.get("verdict") == "PROCEED":
            proceed.append(ticker)
        else:
            blocked.append(ticker)

    if len(tickers) > 1:
        print(f"\n{'─'*65}")
        print(f"  Summary: {len(proceed)} PROCEED, {len(blocked)} BLOCKED")
        if proceed:
            print(f"  ✅ Cleared: {', '.join(proceed)}")
        if blocked:
            print(f"  🚫 Blocked: {', '.join(blocked)}")

    print()


if __name__ == "__main__":
    main()
