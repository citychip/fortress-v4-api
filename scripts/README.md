# Fortress Dashboard — Scripts Catalogue

**Location:** `/opt/fortress-dashboard/scripts/`
**Last updated:** 2026-05-08
**Total scripts:** 12 Python files

All scripts connect to the live Fortress Dashboard API at `http://localhost:8080`.
They read the bearer token from `/home/ubuntu/.fortress_api_token` automatically.

---

## 1. Daily Workflow (run these every trading day)

| Script | Purpose | Usage |
|---|---|---|
| `daily_workflow.py` | Master orchestrator — full daily workflow: sync → briefing → stop-loss scan → roll scan → EOD report | `python3 daily_workflow.py` |
| `stop_loss_scan.py` | Scans all positions for stop-loss signals, prints prioritised action list | `python3 stop_loss_scan.py` |
| `roll_scan.py` | Scans all positions for roll candidates (DTE ≤ 21 or delta ≥ 0.35) | `python3 roll_scan.py` |
| `pre_trade_gate.py` | Interactive pre-trade gate checker — runs all 4 gates for any ticker | `python3 pre_trade_gate.py GOOGL` |
| `eod_report.py` | End-of-day portfolio summary — Greeks, P&L, stop-loss status, roll candidates | `python3 eod_report.py` |
| `check_greeks_backend.py` | Checks active Greeks backend, CP Gateway status, and OPRA subscription | `python3 check_greeks_backend.py` |
| | | `python3 check_greeks_backend.py --watch` (repeats every 60s) |

---

## 2. MCP Analysis (ad-hoc portfolio queries)

| Script | Purpose | Usage |
|---|---|---|
| `mcp_briefing.py` | Calls get_briefing, get_capability, get_alerts, get_positions via MCP | `python3 mcp_briefing.py` |
| `mcp_full_analysis.py` | Full portfolio analysis — all positions, Greeks, candidates, calendar | `python3 mcp_full_analysis.py` |
| `mcp_gex2.py` | Per-ticker GEX and DP floor data collection with detailed output | `python3 mcp_gex2.py` |
| `mcp_position_analysis2.py` | Stop-loss, roll, and pre-trade checks for each position via MCP | `python3 mcp_position_analysis2.py` |
| `verify_gex_final.py` | Verifies UNH, SPY, and SPX GEX data is parseable via MCP | `python3 verify_gex_final.py` |

---

## 3. Testing

| Script | Purpose | Usage |
|---|---|---|
| `workflow_test.py` | Full regression test suite — tests all 24 workflow procedures against the live API | `python3 workflow_test.py` |

---

## Environment

All scripts require:
- Python 3.x with `requests` installed (`pip install requests`)
- Bearer token at `/home/ubuntu/.fortress_api_token` (or `FORTRESS_API_TOKEN` env var)
- For MCP scripts: `mcp` and `httpx` packages (`pip install mcp httpx`)
- Network access to `http://localhost:8080` (run on the VPS) or `http://YOUR_VPS_IP:8080` (run remotely)

---

## Greeks Backend — Quick Reference

| Backend | When active | Greeks quality |
|---|---|---|
| `web_api` + OPRA | CP Gateway up + OPRA subscribed | ✅ Live market Greeks |
| `web_api` (no OPRA) | CP Gateway up, no OPRA | 🟡 Live but IV may use BS |
| `bs_yfinance` | CP Gateway down | 🔴 Estimated (Black-Scholes) |

To restore live Greeks: `cd ~/Fortress_Dashboard && docker compose up -d ib-gateway`
To check current state: `python3 scripts/check_greeks_backend.py`
