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
import sys
import time
from datetime import datetime, timezone, timedelta

import numpy as np
import yfinance as yf
from tabulate import tabulate

ET = timezone(timedelta(hours=-4))

# ── IBKR-first IV sourcing (Sprint 18.1 / 18.2) ───────────────────────────────
# Root cause of the all-rows-POOR-SPREAD bug: this scanner read yfinance's raw
# `impliedVolatility` column (placeholder junk ~1e-5..0.03 on the delayed feed)
# → every current_iv ~0% → every IV-HV spread bogus. IV now comes from the shared
# quant/iv_source module: backend /api/options/iv-rank (iv_source: ibkr →
# BS-inversion → hv_proxy — the canonical path) → band-guarded yfinance fallback
# → reject junk. The helpers live in ONE place (18.2) so workflow_01 and
# workflow_05 can't drift apart again (that drift is how 18.1/18.2 happened).
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from iv_source import (
    get_atm_iv,
    backend_iv_rank as _backend_iv_rank,
    yf_atm_iv as _yf_atm_iv,
    prefetch_backend_iv as _prefetch_backend_iv,
    MIN_SANE_IV_PCT, MAX_SANE_IV_PCT,
)

_QUANT_DIR = pathlib.Path(__file__).parent
TICKER_UNIVERSE_FILE = _QUANT_DIR / "ticker_universe.json"
EARNINGS_FILE = _QUANT_DIR / "earnings_blocklist.json"
POSITIONS_FILE = _QUANT_DIR / "active_positions.json"
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


def get_iv_rank(ticker: str, today: str, _unused: dict = None) -> dict:
    """
    IBKR-first IV + IVR for the scanner. Prefers the backend /api/options/iv-rank
    route (real IBKR IV + canonical IVR); falls back to band-guarded yfinance IV
    with an HV-range IVR proxy. Returns {} (ticker skipped) when no trustworthy IV
    is available — it NEVER emits a junk ~0% reading (the Sprint 18.1 guard).
    """
    try:
        yf_symbol = "^GSPC" if ticker == "SPX" else ticker
        t = yf.Ticker(yf_symbol)
        price = t.fast_info.get("lastPrice") or t.fast_info.get("previousClose", 0)

        be = _backend_iv_rank(ticker)
        current_iv = be.get("current_iv") or _yf_atm_iv(yf_symbol)
        if not current_iv or current_iv < MIN_SANE_IV_PCT:
            return {}   # no trustworthy IV → skip; do NOT emit junk
        iv_source = be.get("iv_source", "yfinance_bs")

        # Prefer the backend's canonical IVR; else HV-range proxy on a sane IV.
        ivr = be.get("ivr")
        if ivr is None:
            hist = t.history(period="1y", auto_adjust=True)["Close"].values
            if len(hist) < 22:
                return {}
            weekly_ivs = []
            for i in range(20, len(hist)):
                chunk = hist[i-20:i]
                log_rets = [math.log(chunk[j] / chunk[j-1]) for j in range(1, len(chunk))]
                hv = math.sqrt(252) * float(np.std(log_rets)) * 100
                weekly_ivs.append(hv)
            iv_min, iv_max = min(weekly_ivs), max(weekly_ivs)
            ivr = round((current_iv - iv_min) / (iv_max - iv_min) * 100, 1) if iv_max > iv_min else 0.0
        ivr = max(0.0, min(100.0, float(ivr)))
        return {"price": price, "ivr": ivr, "current_iv": current_iv, "iv_source": iv_source}
    except Exception:
        return {}


def _vrp_thresholds() -> tuple[float, float]:
    """VRP (IV−HV20) spread thresholds for the signal, from cfg (Sprint 19.3) with
    fallback to the codified defaults if config isn't importable in this context."""
    g, f = 5.0, 0.0
    try:
        from app.services.config_store import cfg
        g = float(cfg("strategy.vrp_good_spread_pp", g))
        f = float(cfg("strategy.vrp_fair_spread_pp", f))
    except Exception:
        pass
    return g, f


def classify_signal(ivr: float, current_iv: float, hv20: float, edays: str, conc: str) -> tuple[str, float]:
    """
    Classify the IV/HV opportunity. spread = current_iv − hv20 (percentage points).
    GOOD/FAIR spread cut-offs come from cfg("strategy.vrp_*") (Sprint 19.3).
    Returns (signal_label, spread).
    """
    spread = round(current_iv - hv20, 1)
    vrp_good, vrp_fair = _vrp_thresholds()

    # Hard gates override the signal
    if "🚫" in edays:
        return "🚫 BLOCKED (EARNINGS)", spread
    if "⚠️" in conc:
        return "⚠️ BLOCKED (CONCENTRATION)", spread

    if ivr >= 50 and spread > vrp_good + 5:
        return "🔥 PRIME CRUSH", spread
    elif ivr >= 25 and spread > vrp_good:
        return "✅ GOOD SPREAD", spread
    elif ivr >= 25 and spread > vrp_fair:
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

    # Warm the IBKR-first IV cache for all tickers concurrently up front, so the
    # per-ticker loop below is fast (avoids the sequential-backend-call timeout).
    _prefetch_backend_iv(ALL_TICKERS)

    results = []
    for ticker in ALL_TICKERS:
        print(f"  Scanning {ticker}...          ", end="\r")

        # Hard gates checks
        edays = check_earnings_days(ticker, today_et)
        conc = check_concentration_risk(ticker)

        # Step 1: Get real HV from price history
        hv20 = compute_hv(ticker, window=20)
        hv30 = compute_hv(ticker, window=30)

        # Step 2: Get current IV and IVR from yfinance options chain
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
            "iv_source": iv_data.get("iv_source", "unknown"),
        })

    print(" " * 50 + "\r", end="")

    # ── IV-feed health guard (Sprint 18.1) ────────────────────────────────────
    # Fail LOUD instead of silently tagging every row POOR SPREAD when the IV
    # feed is dead (the original bug). Degraded = no rows got trustworthy IV, or
    # nothing came from the IBKR-first backend path.
    n_total = len(ALL_TICKERS)
    n_iv = len(results)
    n_ibkr = sum(1 for r in results if "ibkr" in (r.get("iv_source") or "").lower())
    iv_degraded = (n_iv == 0) or (n_ibkr == 0)
    if iv_degraded:
        print("\n" + "!" * 80)
        if n_iv == 0:
            print("⚠  IV FEED DEGRADED — no trustworthy IV for ANY ticker "
                  f"({n_total} scanned). Backend /api/options/iv-rank and the "
                  "band-guarded yfinance fallback both failed. Candidate signals "
                  "are NOT reliable — do not screen entries off this run. Check "
                  "the gateway (get_ibkr_status) and re-run refresh_iv_data.")
        else:
            print(f"⚠  IV FEED DEGRADED — {n_iv}/{n_total} tickers priced but "
                  "0 from the IBKR backend path (all fell back to yfinance). IVR "
                  "may be a proxy; treat signals with caution and check the gateway.")
        print("!" * 80)

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
        f.write("**IV Source:** IBKR-first via backend /api/options/iv-rank (BS-inversion / hv_proxy fallback)\n\n")
        if iv_degraded:
            f.write("> ⚠ **IV FEED DEGRADED** — IV could not be sourced from the IBKR backend "
                    "path for this run; signals below are unreliable. Check the gateway and re-run.\n\n")
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
