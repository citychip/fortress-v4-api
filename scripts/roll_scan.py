#!/usr/bin/env python3
"""
Fortress Dashboard — Roll Candidate Scanner
Checks every active position for roll readiness (DTE, delta, P&L).
Prints a prioritised list of positions ready to roll.

Usage:
    python3 roll_scan.py
    python3 roll_scan.py --ticker MSFT    # single ticker
    python3 roll_scan.py --ready-only     # only show positions with candidates
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


def get_positions():
    r = requests.get(f"{BASE}/api/manage/positions", headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r.json().get("positions", [])


def check_roll(pos_id):
    r = requests.get(f"{BASE}/api/manage/roll/{pos_id}", headers=HEADERS, timeout=15)
    if r.status_code == 200:
        return r.json()
    return None


def main():
    parser = argparse.ArgumentParser(description="Fortress Roll Candidate Scanner")
    parser.add_argument("--ticker", help="Check a single ticker only")
    parser.add_argument("--ready-only", action="store_true", help="Only show positions with candidates")
    args = parser.parse_args()

    print("\n" + "=" * 70)
    print("  FORTRESS ROLL CANDIDATE SCAN")
    print("=" * 70)

    positions = get_positions()
    if args.ticker:
        positions = [p for p in positions if p.get("ticker", "").upper() == args.ticker.upper()]

    ready = []
    skipped = []

    print(f"\n{'Ticker':<8} {'Expiry':<10} {'DTE':<5} {'Delta':<8} {'Candidates':<12} {'Best Strike'}")
    print("-" * 70)

    for pos in positions:
        pos_id = pos.get("id", "")
        ticker = pos.get("ticker", "?")

        if not pos_id or "?" in pos_id:
            skipped.append(ticker)
            continue

        result = check_roll(pos_id)
        if not result:
            print(f"{ticker:<8} {'—':<10} {'—':<5} {'—':<8} {'ERROR':<12}")
            continue

        candidates = result.get("candidates", [])
        dte = result.get("current_dte", "—")
        delta = result.get("current_delta", "—")
        expiry = pos.get("expiry", "—") or "—"

        if isinstance(delta, float):
            delta_str = f"{delta:.3f}"
        else:
            delta_str = str(delta)

        if candidates:
            best = candidates[0]
            best_strike = best.get("strike", "?")
            best_expiry = best.get("expiry", "?")
            best_str = f"${best_strike} {best_expiry}"
            icon = "📋"
            ready.append({
                "ticker": ticker,
                "expiry": expiry,
                "dte": dte,
                "candidates": len(candidates),
                "best": best_str,
            })
        else:
            best_str = "—"
            icon = "  "

        if not args.ready_only or candidates:
            print(f"{ticker:<8} {expiry:<10} {str(dte):<5} {delta_str:<8} {icon} {len(candidates):<10} {best_str}")

    print("-" * 70)

    if skipped:
        print(f"\n  Skipped (unknown legs): {', '.join(skipped)}")

    if ready:
        print(f"\n  📋 {len(ready)} position(s) ready to roll:")
        for r in ready:
            print(f"     {r['ticker']} ({r['expiry']}, DTE={r['dte']}) — {r['candidates']} candidate(s), best: {r['best']}")
    else:
        print(f"\n  ✅ No positions ready to roll")

    print()


if __name__ == "__main__":
    main()
