# Fortress Dashboard — Quick-Start & Daily Cheatsheet

**Version 1.8 — 2026-06-01**

One-page operational reference for live sessions. Open this first each morning.

---

## System URLs & Access

| Service | URL / Command | Notes |
|---|---|---|
| **Fortress V4 Dashboard** | `http://localhost` | Main interface (nginx → React) |
| Dashboard health | `GET http://localhost:8081/api/health` | Liveness check |
| IBKR Gateway | `GET http://localhost:8081/api/ibkr/status` | Connection + account |
| FastAPI docs | `http://localhost:8081/docs` | Auto-generated API docs |
| IBKR CP Gateway | `https://localhost:5000` | Daily login required |
| QuantData | `https://v3.quantdata.us` | For credential refresh |

---

## Morning Startup Sequence (5 minutes)

**1. Check system health**
```bash
sudo systemctl status fortress-dashboard-v4
```
MCP: `get_briefing()` — check Net Liq, regime, concentration, pacing, staleness.

> IBKR auto-sync is enabled (15 min). If `staleness.state = "stale"`, run `trigger_ibkr_sync()` manually.

**2. Morning Preflight (The Triad)**
MCP: *"Run my morning preflight: briefing, SPY hedge coverage, today's calendar, and any stop-loss signals in ACT state."*
- Briefing: account thresholds, MSFT concentration, portfolio delta vs target
- Hedge: SPY hedge coverage vs $20K–$30K target band
- Actions: any stop-loss triggers and earnings today

**3. Max pain + fresh IV (always)**
MCP: `run_script("max_pain")` + `refresh_iv_data()` — max pain pinning direction for full universe (~5s), fresh IV scan (~15s). Run both before looking at candidates.

**4. Macro + per-ticker intel (entry days only)**
MCP: *"SPY market intel, net drift, dark pool. Then per candidate: IV rank dual-confirm, vol skew, GEX walls, market intel, earnings vol."*
- SPY-level (quantdata MCP): `qd_get_net_drift("SPY")` + `qd_get_dark_pool_levels("SPY")` + `qd_get_order_flow("SPY", min_premium=100000)`
- SPY-level (fortress MCP): `get_market_intelligence("SPY")`
- Per-ticker — dual IV confirm (§4): `get_candidates()` [fortress] → `qd_get_iv_rank(t)` [quantdata] — both must confirm IVR > 25
- Per-ticker — vol skew gate (§5): `qd_get_volatility_skew(t)` [quantdata] — steep put skew = caution, document override
- Per-ticker — structure (fortress): `get_market_intelligence(t)` + `get_dp_floors_and_gex(t)` + `get_earnings_volatility(t)`
- Per-ticker — live GEX (market hours only): `qd_get_exposure_by_strike(t)` [quantdata] — primary strike anchor

---

## Key Thresholds

| Metric | Floor / Target | Action if breached |
|---|---|---|
| Available Funds | >$17K | Pause new entries |
| Portfolio Delta | ±200 | Hedge or trim |
| MSFT Concentration | <50% NetLiq | Do not add (currently at 97% — exception applies) |
| SPY Hedge | $20K–$30K notional | Buy puts to close gap |
| IV Rank (entry) | >25 | Minimum for premium selling; >50 = prime |
| DTE (short leg) | 21–45 DTE | Entry window |
| DTE (roll trigger) | ≤21 DTE | Roll or close |
| Delta (short call) | 0.25–0.30 | Entry target; roll if >0.35 |
| Stop-loss | 200% of credit | Mechanical close |
| Profit target | 80% of credit | Close early |

---

## Quick Commands (WSL)

```bash
# Service management
sudo systemctl restart fortress-dashboard-v4
sudo systemctl status fortress-dashboard-v4
journalctl -u fortress-dashboard-v4 -n 50 --no-pager

# Health check
curl http://localhost:8081/api/health

# Authenticated API call
TOKEN="07f03fb6e664859ac5e8113eaf1102ac43a3cb785c581af756671072b426db21"
curl -H "Authorization: Bearer $TOKEN" http://localhost:8081/api/briefing | python3 -m json.tool

# IBKR sync
curl -X POST -H "Authorization: Bearer $TOKEN" http://localhost:8081/api/ibkr/sync

# Re-run IV Crush workflow (or use MCP: refresh_iv_data())
cd ~/fortress-v4-api && source venv/bin/activate && python3 quant/workflow_05_iv_crush_report.py

# Frontend deploy after changes
cd ~/fortress-v4-frontend && npm run build
sudo cp -r dist/public/* /var/www/fortress-v4/ && sudo nginx -s reload
```

---

## QuantData Credential Refresh (when Market Intel shows no data)

**Automatic:** Runs daily at 06:00 ET via APScheduler (`qd_refresh_session.py`).

**Manual:**
1. Dashboard → **Settings → QuantData Auto-Login**
2. Or run: `cd ~/fortress-v4-api && venv/bin/python3 quant/qd_refresh_session.py`
3. After refresh: `sudo cp ~/.quantdata-mcp/config.json /root/.quantdata-mcp/config.json`
4. Restart service: `sudo systemctl restart fortress-dashboard-v4`

> The standalone `quantdata-mcp` server reads `~/.quantdata-mcp/config.json` directly. After a credential refresh, restart Claude Desktop to pick up the updated token.

---

## Incident Quick-Reference

| Symptom | First step |
|---|---|
| Dashboard unreachable | `sudo systemctl restart fortress-dashboard-v4` |
| IBKR amber / no Greeks | Login at `https://localhost:5000`, then `GET /api/ibkr/sync` |
| 502 Bad Gateway | `sudo systemctl restart fortress-dashboard-v4 && sudo nginx -s reload` |
| IV Rank / Market Intel blank | Run QuantData credential refresh (above) |
| Candidates shows 0 rows | MCP: `refresh_iv_data()` or run `workflow_05_iv_crush_report.py` |
| Positions empty after sync | Check CP Gateway session at `https://localhost:5000` |
| Fortress MCP not connecting | Fully quit and relaunch Claude Desktop |
| quantdata MCP not connecting | Check `~/.quantdata-mcp/config.json` token; restart Claude Desktop |

---

## Data Sources Quick Reference

> **Tested status 2026-06-01** — ✓ confirmed | ✗ widget-locked to SPX | ⏱ pending market-hours test

| What you need | Use this | MCP | Status |
|---|---|---|---|
| Per-ticker IV rank (live) | `qd_get_iv_rank(ticker)` | quantdata | ✓ confirmed |
| Per-ticker vol skew | `qd_get_volatility_skew(ticker)` | quantdata | ⏱ market hours only |
| Per-ticker GEX by strike | `qd_get_exposure_by_strike(ticker)` | quantdata | ⏱ market hours only |
| SPX order flow / sweeps | `qd_get_order_flow("SPY")` | quantdata | ✓ SPX only (widget-locked) |
| SPX dark pool floors | `qd_get_dark_pool_levels("SPY")` | quantdata | ✓ SPX only (widget-locked) |
| Per-ticker GEX walls (daily) | `get_dp_floors_and_gex(ticker)` | fortress | ✓ daily report (~12h) |
| Per-ticker IV skew (yfinance) | `get_vol_analytics(ticker)` | fortress | ✓ yfinance |
| IV crush candidates (universe) | `get_candidates()` / `refresh_iv_data()` | fortress | ✓ yfinance batch |
| Max pain + pin direction | `run_script("max_pain")` | fortress | ✓ yfinance batch |

---

## MCP Order Workflow (quick reference)

```
refresh_iv_data()                      # fresh IV scan (yfinance batch)
→ get_candidates()                     # find top 2-3 by IVR + spread
→ qd_get_iv_rank(ticker)               # dual IV confirm (Strategy §4)
→ qd_get_volatility_skew(ticker)       # vol skew gate (Strategy §5)
→ qd_get_exposure_by_strike(ticker)    # live GEX — primary strike anchor
→ pretrade_check(ticker, strategy)     # pre-trade gate
→ stage_order(ticker, strategy, legs, ...)
→ preview_order(order_id)              # IBKR whatif (no submission)
→ approve_order(order_id)             # submit to IBKR
```

All thresholds advisory — document overrides in journal.

All write tools require `FORTRESS_MCP_ALLOW_WRITES=1` in Claude Desktop config.

---

## Document History

| Version | Date | Changes |
|---|---|---|
| 1.8 | 2026-06-01 | Updated for Strategy v3.8.0. Step 4 updated with dual IV rank confirm and vol skew gate. MCP order workflow updated. GEX by strike added as primary strike anchor. Advisory framing noted. |
| 1.7 | 2026-06-01 | Standalone quantdata-mcp registered. qd_get_iv_rank confirmed per-ticker. Dark pool and order flow remain SPX widget-locked. |
| 1.6 | 2026-06-01 | Added run_script("max_pain") to morning preflight. Data sources table. Two-layer market intel (SPY qd_* + per-ticker yfinance). |
| 1.5 | 2026-06-01 | Added refresh_iv_data, stage_order/preview_order/approve_order workflow. IBKR auto-sync note. |
| 1.4 | 2026-05-30 | Full rewrite for V4 WSL deployment. Removed VPS references. Updated paths, ports, token, commands. Added auto-refresh note. |
| 1.3 | 2026-05-18 | Updated URLs for Fortress V3. Added QuantData credential refresh. |
