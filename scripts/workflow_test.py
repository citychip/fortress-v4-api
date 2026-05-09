"""
Fortress Dashboard — Workflow Procedure Test Suite
Tests every procedure in 03_Trading_Workflow_v2_8.md against the live system.
"""
import json
import subprocess
import os
import sys
import requests
from pathlib import Path

# --- Config ---
BASE = "http://YOUR_VPS_IP:8080"
TOKEN_FILE = Path.home() / ".fortress_api_token"
# Read token from env, local file, or VPS
TOKEN = os.environ.get("FORTRESS_API_TOKEN", "")
if not TOKEN and TOKEN_FILE.exists():
    TOKEN = TOKEN_FILE.read_text().strip()
if not TOKEN:
    result = subprocess.run(
        ["ssh", "-i", str(Path.home() / ".ssh/fortress_vps"),
         "-o", "StrictHostKeyChecking=no",
         "ubuntu@YOUR_VPS_IP", "cat /home/ubuntu/.fortress_api_token"],
        capture_output=True, text=True
    )
    TOKEN = result.stdout.strip()
if not TOKEN:
    print("ERROR: Could not read token from env, ~/.fortress_api_token, or VPS")
    sys.exit(1)

HEADERS = {"Authorization": f"Bearer {TOKEN}"}

results = {}

def test(name, fn):
    try:
        status, detail = fn()
        results[name] = {"status": status, "detail": detail}
        icon = "✅" if status == "PASS" else ("⚠️" if status == "WARN" else "❌")
        print(f"{icon} {name}: {detail}")
    except Exception as e:
        results[name] = {"status": "ERROR", "detail": str(e)}
        print(f"💥 {name}: {e}")

# ─── Phase 1: Pre-Market ──────────────────────────────────────────────────────

def test_ibkr_sync():
    r = requests.post(f"{BASE}/api/ibkr/sync", headers=HEADERS, timeout=30)
    if r.status_code == 200:
        d = r.json()
        return "PASS", f"synced_at={d.get('synced_at','?')} positions={d.get('positions_count','?')}"
    return "FAIL", f"HTTP {r.status_code}: {r.text[:100]}"

def test_capability():
    r = requests.get(f"{BASE}/api/ibkr/capability", headers=HEADERS, timeout=15)
    if r.status_code == 200:
        d = r.json()
        backend = d.get("active_backend", "?")
        opra = d.get("opra_active", False)
        return "PASS", f"backend={backend} opra={opra}"
    return "FAIL", f"HTTP {r.status_code}"

def test_briefing():
    r = requests.get(f"{BASE}/api/briefing", headers=HEADERS, timeout=15)
    if r.status_code == 200:
        d = r.json()
        # Greeks are nested under "greeks" key
        greeks = d.get("greeks", {}) or {}
        delta = greeks.get("portfolio_delta", d.get("portfolio_delta", "?"))
        theta = greeks.get("portfolio_theta", d.get("portfolio_theta", "?"))
        regime = (d.get("macro_regime") or {}).get("regime", "?")
        return "PASS", f"delta={delta} theta={theta} regime={regime}"
    return "FAIL", f"HTTP {r.status_code}"

test("1.2 POST /api/ibkr/sync", test_ibkr_sync)
test("1.3 GET /api/ibkr/capability", test_capability)
test("1.4 GET /api/briefing", test_briefing)

# ─── Phase 2: Market Open ─────────────────────────────────────────────────────

def test_run_script(key, timeout=30):
    def fn():
        r = requests.post(f"{BASE}/api/run/{key}", headers=HEADERS, timeout=timeout)
        if r.status_code == 200:
            d = r.json()
            return "PASS", f"exit_code={d.get('exit_code','?')} duration={d.get('duration_seconds','?')}s"
        return "FAIL", f"HTTP {r.status_code}: {r.text[:150]}"
    return fn

# NOTE: /api/run/daily (quantdata_daily) is a long-running script (~2-3 min).
# It is tested with an extended timeout. If it times out in CI, this is expected.
test("2.1 POST /api/run/daily (quantdata_daily)", test_run_script("daily", timeout=180))
test("2.2 POST /api/run/iv_crush", test_run_script("iv_crush"))
test("2.3 POST /api/run/whale_flow", test_run_script("whale_flow"))

# ─── Phase 3: Trade Entry ─────────────────────────────────────────────────────

def test_pre_trade_gate():
    # Use AVGO (not MSFT) — MSFT is blocked by concentration, AVGO should PROCEED
    r = requests.get(f"{BASE}/api/manage/pre_trade_check", headers=HEADERS,
                     params={"ticker": "AVGO"}, timeout=15)
    if r.status_code == 200:
        d = r.json()
        return "PASS", f"verdict={d.get('verdict','?')} gates={list(d.get('gates',{}).keys())}"
    return "FAIL", f"HTTP {r.status_code}: {r.text[:150]}"

def test_entry_scoring():
    r = requests.post(f"{BASE}/api/run/entry_scoring", headers=HEADERS, timeout=30)
    if r.status_code == 200:
        d = r.json()
        return "PASS", f"exit_code={d.get('exit_code','?')}"
    return "FAIL", f"HTTP {r.status_code}: {r.text[:150]}"

def test_gex_oi():
    r = requests.post(f"{BASE}/api/run/gex_oi", headers=HEADERS, timeout=60)
    if r.status_code == 200:
        d = r.json()
        return "PASS", f"exit_code={d.get('exit_code','?')} duration={d.get('duration_seconds','?')}s"
    return "FAIL", f"HTTP {r.status_code}: {r.text[:150]}"

def test_jade_lizard():
    body = {
        "put_strike": 400.0,
        "call_short_strike": 445.0,
        "call_long_strike": 450.0,
        "put_credit": 3.50,
        "call_spread_credit": 1.80,
    }
    r = requests.post(f"{BASE}/api/manage/validate_jade_lizard",
                      headers=HEADERS, json=body, timeout=15)
    if r.status_code == 200:
        d = r.json()
        return "PASS", f"verdict={d.get('verdict','?')} total_credit={d.get('total_credit','?')} spread_width={d.get('call_spread_width','?')}"
    return "FAIL", f"HTTP {r.status_code}: {r.text[:200]}"

def test_playbook_post_earnings():
    # Minimal body — thesis is optional per the actual endpoint schema
    body = {
        "ticker": "AVGO",
        "gap_pct": -3.5,
        "iv_crush_pct": 28.0,
    }
    r = requests.post(f"{BASE}/api/playbook/post_earnings",
                      headers=HEADERS, json=body, timeout=30)
    if r.status_code == 200:
        d = r.json()
        return "PASS", f"verdict={d.get('verdict','?')} final_action={d.get('final_action','?')}"
    return "FAIL", f"HTTP {r.status_code}: {r.text[:200]}"

test("3.0 GET /api/manage/pre_trade_check (AVGO)", test_pre_trade_gate)
test("3.1 POST /api/run/entry_scoring", test_entry_scoring)
test("3.2 POST /api/run/gex_oi", test_gex_oi)
test("3.4a POST /api/manage/validate_jade_lizard", test_jade_lizard)
test("3.4b POST /api/playbook/post_earnings", test_playbook_post_earnings)

# ─── Phase 4: Mid-Day Monitoring ─────────────────────────────────────────────

def test_position_monitor():
    return test_run_script("position_monitor")()

def test_dark_pool_alert():
    return test_run_script("dark_pool_alert")()

def _get_clean_position_id():
    """Return the first position ID that has no unknown legs (no '?' in ID)."""
    r = requests.get(f"{BASE}/api/manage/positions", headers=HEADERS, timeout=15)
    if r.status_code != 200:
        return None, f"Could not get positions: HTTP {r.status_code}"
    positions = r.json().get("positions", [])
    for p in positions:
        pid = p.get("id", "")
        if pid and "?" not in pid:
            return pid, None
    return None, "No clean position IDs found (all have unknown legs)"

def test_stop_loss():
    pos_id, err = _get_clean_position_id()
    if not pos_id:
        return "WARN", err
    r2 = requests.get(f"{BASE}/api/manage/stop_loss/{pos_id}",
                      headers=HEADERS, timeout=15)
    if r2.status_code == 200:
        d = r2.json()
        return "PASS", f"ticker={d.get('ticker','?')} verdict={d.get('verdict','?')} signals={len(d.get('signals',[]))}"
    return "FAIL", f"HTTP {r2.status_code}: {r2.text[:200]}"

def test_roll():
    pos_id, err = _get_clean_position_id()
    if not pos_id:
        return "WARN", err
    r2 = requests.get(f"{BASE}/api/manage/roll/{pos_id}",
                      headers=HEADERS, timeout=15)
    if r2.status_code == 200:
        d = r2.json()
        return "PASS", f"ticker={d.get('ticker','?')} candidates={len(d.get('candidates',[]))}"
    return "FAIL", f"HTTP {r2.status_code}: {r2.text[:200]}"

test("4.1 POST /api/run/position_monitor", test_position_monitor)
test("4.2 POST /api/run/dark_pool_alert", test_dark_pool_alert)
test("4.3 GET /api/manage/stop_loss/{position_id}", test_stop_loss)
test("4.4 GET /api/manage/roll/{position_id}", test_roll)

# ─── Phase 5 / 6 ─────────────────────────────────────────────────────────────

def test_eod_review():
    return test_run_script("eod_review")()

def test_journal():
    r = requests.get(f"{BASE}/api/journal", headers=HEADERS, timeout=15)
    if r.status_code == 200:
        d = r.json()
        entries = d.get("entries", [])
        return "PASS", f"{len(entries)} journal entries"
    return "FAIL", f"HTTP {r.status_code}"

test("6.1 POST /api/run/eod_review", test_eod_review)
test("6.2 GET /api/journal", test_journal)

# ─── Weekly ───────────────────────────────────────────────────────────────────

def test_calendar():
    r = requests.get(f"{BASE}/api/calendar", headers=HEADERS, timeout=15)
    if r.status_code == 200:
        d = r.json()
        return "PASS", f"{len(d.get('events',[]))} calendar events"
    return "FAIL", f"HTTP {r.status_code}"

def test_fetch_earnings():
    r = requests.post(f"{BASE}/api/calendar/fetch-earnings", headers=HEADERS, timeout=30)
    if r.status_code == 200:
        d = r.json()
        return "PASS", f"fetched={d.get('fetched',0)} updated={d.get('updated',0)}"
    return "FAIL", f"HTTP {r.status_code}: {r.text[:150]}"

def test_spy_hedge():
    r = requests.get(f"{BASE}/api/manage/spy_hedge_coverage", headers=HEADERS, timeout=15)
    if r.status_code == 200:
        d = r.json()
        mv = d.get("hedge_market_value", 0)
        ok = d.get("coverage_ok", False)
        return "PASS", f"hedge_mv=${mv:,.0f} coverage_ok={ok}"
    return "FAIL", f"HTTP {r.status_code}: {r.text[:150]}"

def test_settings():
    r = requests.get(f"{BASE}/api/settings", headers=HEADERS, timeout=15)
    if r.status_code == 200:
        d = r.json()
        sections = list(d.get("config", {}).keys())
        return "PASS", f"sections={sections}"
    return "FAIL", f"HTTP {r.status_code}"

def test_universe():
    r = requests.get(f"{BASE}/api/universe", headers=HEADERS, timeout=15)
    if r.status_code == 200:
        d = r.json()
        tickers = d.get("tickers", [])
        return "PASS", f"{len(tickers)} tickers in universe"
    return "FAIL", f"HTTP {r.status_code}"

def test_max_pain():
    return test_run_script("max_pain")()

def test_premarket():
    return test_run_script("premarket", timeout=60)()

test("W.1 GET /api/calendar", test_calendar)
test("W.2 POST /api/calendar/fetch-earnings", test_fetch_earnings)
test("W.3 GET /api/manage/spy_hedge_coverage", test_spy_hedge)
test("W.4 GET /api/settings", test_settings)
test("W.5 GET /api/universe", test_universe)
test("W.6 POST /api/run/max_pain", test_max_pain)
test("W.7 POST /api/run/premarket", test_premarket)

# ─── Summary ─────────────────────────────────────────────────────────────────

print("\n" + "="*60)
print("SUMMARY")
print("="*60)
passed = sum(1 for v in results.values() if v["status"] == "PASS")
warned = sum(1 for v in results.values() if v["status"] == "WARN")
failed = sum(1 for v in results.values() if v["status"] in ("FAIL", "ERROR"))
print(f"✅ PASS: {passed}  ⚠️ WARN: {warned}  ❌ FAIL/ERROR: {failed}  Total: {len(results)}")
print()
if failed:
    print("FAILURES:")
    for name, v in results.items():
        if v["status"] in ("FAIL", "ERROR"):
            print(f"  ❌ {name}: {v['detail']}")

# Save results
with open("/home/ubuntu/workflow_test_results.json", "w") as f:
    json.dump(results, f, indent=2)
print("\nResults saved to /home/ubuntu/workflow_test_results.json")
