#!/usr/bin/env python3
"""
Fortress Dashboard — EOD Portfolio Report
Generates a formatted end-of-day summary: positions, Greeks, alerts,
stop-loss scan, roll candidates, and SPY hedge status.

Usage:
    python3 eod_report.py
    python3 eod_report.py --save              # save to ~/eod_YYYY-MM-DD.md
    python3 eod_report.py --save --open       # save and open in terminal pager
"""
import argparse
import os
import sys
from datetime import datetime
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
TODAY = datetime.now().strftime("%Y-%m-%d")
NOW = datetime.now().strftime("%Y-%m-%d %H:%M")


def api_get(path, params=None):
    r = requests.get(f"{BASE}{path}", headers=HEADERS, params=params, timeout=20)
    if r.status_code == 200:
        return r.json()
    return {}


def api_post(path):
    r = requests.post(f"{BASE}{path}", headers=HEADERS, timeout=60)
    if r.status_code == 200:
        return r.json()
    return {}


def build_report():
    lines = []

    def h1(t): lines.append(f"\n# {t}")
    def h2(t): lines.append(f"\n## {t}")
    def h3(t): lines.append(f"\n### {t}")
    def row(*cols): lines.append("| " + " | ".join(str(c) for c in cols) + " |")
    def sep(*cols): lines.append("| " + " | ".join("---" for _ in cols) + " |")
    def blank(): lines.append("")
    def text(t): lines.append(t)

    h1(f"Fortress EOD Report — {TODAY}")
    text(f"*Generated: {NOW}*")

    # ── Briefing ──────────────────────────────────────────────────────────────
    h2("Portfolio State")
    briefing = api_get("/api/briefing")
    greeks = briefing.get("greeks", {}) or {}
    account = briefing.get("account", {}) or {}
    macro = briefing.get("macro_regime", {}) or {}
    pacing = briefing.get("pacing", {}) or {}

    row("Metric", "Value")
    sep("Metric", "Value")
    row("Net Liquidation", f"${account.get('net_liq', 0):,.0f}")
    row("Portfolio Delta", greeks.get("portfolio_delta", "—"))
    row("Portfolio Theta", greeks.get("portfolio_theta", "—"))
    row("Portfolio Vega", greeks.get("portfolio_vega", "—"))
    row("Macro Regime", macro.get("regime", "—"))
    row("VIX", f"{macro.get('vix', '—')} ({macro.get('vix_state', '—')})")
    row("Pacing", f"{pacing.get('entries_this_week', 0)} / {pacing.get('max_per_week', 2)} this week")
    row("Sync Staleness", briefing.get("staleness", {}).get("label", "—") if isinstance(briefing.get("staleness"), dict) else briefing.get("staleness", "—"))

    # ── Positions ─────────────────────────────────────────────────────────────
    h2("Positions")
    pos_data = api_get("/api/manage/positions")
    positions = pos_data.get("positions", [])

    row("Ticker", "Expiry", "Strike", "Delta", "NLV %", "Alert")
    sep("Ticker", "Expiry", "Strike", "Delta", "NLV %", "Alert")
    for p in positions:
        ticker = p.get("ticker", "?")
        expiry = p.get("expiry", "—") or "—"
        strike = p.get("short_strike", "—") or "—"
        delta = p.get("current_delta", "—")
        delta_str = f"{delta:.3f}" if isinstance(delta, float) else str(delta)
        nlv = p.get("net_liq_pct", "—")
        nlv_str = f"{nlv:.1f}%" if isinstance(nlv, float) else str(nlv)
        alert = p.get("alert_state", "—") or "—"
        row(ticker, expiry, strike, delta_str, nlv_str, alert)

    # ── Stop-Loss Scan ────────────────────────────────────────────────────────
    h2("Stop-Loss Scan")
    sl_alerts = []
    for pos in positions:
        pos_id = pos.get("id", "")
        if not pos_id or "?" in pos_id:
            continue
        result = api_get(f"/api/manage/stop_loss/{pos_id}")
        verdict = result.get("verdict", "UNKNOWN")
        if verdict not in ("SAFE", None, "UNKNOWN"):
            sl_alerts.append((pos.get("ticker"), verdict, result.get("signals", [])))

    if sl_alerts:
        row("Ticker", "Verdict", "Signals")
        sep("Ticker", "Verdict", "Signals")
        for ticker, verdict, signals in sl_alerts:
            signal_names = [s.get("name", s) if isinstance(s, dict) else str(s) for s in signals]
            row(ticker, f"⚠️ {verdict}", ", ".join(signal_names))
    else:
        text("\n✅ All positions SAFE — no stop-loss signals.")

    # ── Roll Candidates ───────────────────────────────────────────────────────
    h2("Roll Candidates")
    roll_ready = []
    for pos in positions:
        pos_id = pos.get("id", "")
        if not pos_id or "?" in pos_id:
            continue
        result = api_get(f"/api/manage/roll/{pos_id}")
        candidates = result.get("candidates", [])
        if candidates:
            best = candidates[0]
            roll_ready.append((pos.get("ticker"), pos.get("expiry"), result.get("current_dte"), best))

    if roll_ready:
        row("Ticker", "Current Expiry", "DTE", "Best Roll Strike", "Best Roll Expiry")
        sep("Ticker", "Current Expiry", "DTE", "Best Roll Strike", "Best Roll Expiry")
        for ticker, expiry, dte, best in roll_ready:
            row(ticker, expiry or "—", dte or "—", best.get("strike", "?"), best.get("expiry", "?"))
    else:
        text("\n✅ No positions ready to roll.")

    # ── SPY Hedge ─────────────────────────────────────────────────────────────
    h2("SPY Hedge Coverage")
    hedge = api_get("/api/manage/spy_hedge_coverage")
    mv = hedge.get("hedge_market_value", 0)
    ok = hedge.get("coverage_ok", False)
    target_min = hedge.get("target_min", 20000)
    target_max = hedge.get("target_max", 30000)
    icon = "✅" if ok else "🔴"
    text(f"\n{icon} Hedge MV: ${mv:,.0f} (target: ${target_min:,}–${target_max:,})")
    if not ok:
        text(f"\n**ACTION REQUIRED:** Rebuild SPY hedge to ${target_min:,}–${target_max:,} notional.")

    # ── Alerts ────────────────────────────────────────────────────────────────
    h2("Active Alerts")
    alerts_data = api_get("/api/alerts")
    alerts = alerts_data.get("alerts", [])
    if alerts:
        row("Ticker", "Type", "Message")
        sep("Ticker", "Type", "Message")
        for a in alerts:
            row(a.get("ticker", "?"), a.get("type", "?"), a.get("message", "?"))
    else:
        text("\n✅ No active alerts.")

    # ── Actions ───────────────────────────────────────────────────────────────
    h2("Recommended Actions")
    actions = briefing.get("actions", [])
    if actions:
        for i, action in enumerate(actions, 1):
            ticker = action.get("ticker", "")
            cta = action.get("cta", "")
            reason = action.get("reason", "")
            priority = action.get("priority", "")
            prefix = "🔴" if priority == "high" else ("🟡" if priority == "medium" else "🟢")
            text(f"\n{i}. {prefix} **{ticker}** — {cta}: {reason}")
    else:
        text("\n✅ No recommended actions.")

    blank()
    text("---")
    text(f"*Fortress Dashboard · {NOW} · Strategy v3.6*")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Fortress EOD Report Generator")
    parser.add_argument("--save", action="store_true", help="Save report to ~/eod_YYYY-MM-DD.md")
    parser.add_argument("--open", action="store_true", help="Open saved report in pager")
    args = parser.parse_args()

    print("Generating EOD report...", flush=True)
    report = build_report()

    print(report)

    if args.save:
        out_path = Path.home() / f"eod_{TODAY}.md"
        out_path.write_text(report)
        print(f"\n✅ Report saved to {out_path}")
        if args.open:
            os.system(f"less {out_path}")


if __name__ == "__main__":
    main()
