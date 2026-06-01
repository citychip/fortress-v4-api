# Fortress — Session Handoff
**Date:** 2026-06-01 (updated end-of-session) | **For:** Next Cowork session

---

## System Overview

Fortress is a personal options trading dashboard running **entirely on WSL (Ubuntu) on Windows**. No VPS.

**Stack:**
- Backend: FastAPI at `http://localhost:8081` — `~/fortress-v4-api/` (WSL)
- **Fortress v4 frontend:** React/Vite, nginx at `http://localhost:80` — `~/fortress-v4-frontend/` (WSL)
- **Parapet (v5) frontend:** React/Vite, nginx at `http://localhost:4000` — `~/fortress-parapet/` (WSL)
- MCP server: `C:\Users\cityc.000\fortress_mcp\fortress_mcp.py` (Windows)
- IBKR: CP Gateway Docker (`voyz/ibeam:latest`, name: `cp-gateway`) at `https://localhost:5000` (daily browser login)
- QuantData: JWT at `~/.quantdata-mcp/config.json`

**Service management:**
```bash
sudo systemctl restart fortress-dashboard-v4
sudo systemctl status fortress-dashboard-v4
journalctl -u fortress-dashboard-v4 -n 50 --no-pager
```

**API token:** `07f03fb6e664859ac5e8113eaf1102ac43a3cb785c581af756671072b426db21`

---

## Two Dashboards — Parallel Development

Both dashboards share the **same backend** (`localhost:8081`) and credentials. They serve different purposes and are developed in parallel.

### Fortress v4 — `http://localhost:80`
- **Scope:** Full-featured legacy dashboard. Workflow engine, Trade Builder, Scenario Planner, Strategy Sandbox, Persona Editor.
- **Status:** Stable, production. Deprioritised for new feature work — maintained but not actively extended.
- **Repo:** `citychip/fortress-v4-frontend` (branch: `main`)
- **Deploy:** `cd ~/fortress-v4-frontend && npm run build && sudo cp -r dist/public/* /var/www/fortress-v4/ && sudo nginx -s reload`

### Parapet (v5) — `http://localhost:4000`
- **Scope:** Lean display + control layer. Claude (via MCP) is the primary workflow engine. Dashboard = passive monitoring, settings management, orders approval, portfolio insight.
- **Status:** Active development. v1.0 built and deployed 2026-06-01.
- **Repo:** `citychip/fortress-parapet` (branch: `master`)
- **Deploy:** `cd ~/fortress-parapet && npm run build && sudo cp -r dist/* /var/www/fortress-parapet/ && sudo nginx -s reload`
- **5 pages:** Overview · Portfolio · Market · Orders · System

**The strategic intent:** over time, Parapet replaces v4 as the primary dashboard. v4 stays available as a fallback. New frontend features go into Parapet.

---

## GitHub Repos

| Repo | Branch | Purpose |
|---|---|---|
| `citychip/fortress-v4-api` | `main` | Backend, quant scripts, docs |
| `citychip/fortress-mcp` | `master` | MCP server for Claude (v4.2.0) |
| `citychip/fortress-v4-frontend` | `main` | Fortress v4 dashboard (port 80) |
| `citychip/fortress-parapet` | `master` | Parapet v5 dashboard (port 4000) |

**Git auth token:** stored in WSL git remote URLs — do not paste here.

Set remotes on WSL (replace TOKEN with your GitHub PAT):
```bash
git -C ~/fortress-v4-api remote set-url origin https://citychip:TOKEN@github.com/citychip/fortress-v4-api.git
git -C ~/fortress-v4-frontend remote set-url origin https://citychip:TOKEN@github.com/citychip/fortress-v4-frontend.git
git -C ~/fortress-parapet remote set-url origin https://citychip:TOKEN@github.com/citychip/fortress-parapet.git
```

---

## Key File Paths

| What | Path |
|---|---|
| Backend routes | `~/fortress-v4-api/app/routes/` |
| Briefing route | `~/fortress-v4-api/app/routes/briefing.py` |
| Vol analytics | `~/fortress-v4-api/app/routes/options.py` |
| Scheduler | `~/fortress-v4-api/app/scheduler/runner.py` |
| **Parapet source** | `~/fortress-parapet/src/` |
| Parapet pages | `~/fortress-parapet/src/pages/` |
| Parapet API client | `~/fortress-parapet/src/lib/api.ts` |
| Parapet nginx conf | `~/fortress-parapet/nginx/parapet.conf` → `/etc/nginx/sites-available/fortress-parapet` |
| v4 frontend pages | `~/fortress-v4-frontend/client/src/pages/` |
| v4 theme constants | `~/fortress-v4-frontend/client/src/lib/theme.ts` |
| MCP server (Windows) | `C:\Users\cityc.000\fortress_mcp\fortress_mcp.py` |
| Sprint plan | `~/fortress-v4-api/docs/SPRINT_PLAN.md` |
| Daily cheatsheet | `~/fortress-v4-api/docs/operations/03_Quick_Start_and_Daily_Cheatsheet.md` |
| MCP workflow playbook | `~/fortress-v4-api/docs/07_MCP_Workflow_and_Prompts_v1_3.md` |

---

## Parapet — Current State (v1.0, 2026-06-01)

| Page | Status | Notes |
|---|---|---|
| Overview | ✓ Working | Net Liq, Available, Δ portfolio, VIX, Regime, Pacing. Positions grouped by ticker. IBKR status. |
| Portfolio | ✓ Working | Positions, Legs, P&L, Exposure (beta by ticker), Journal |
| Market | ✓ Working | SPY price, regime signals, Earnings Calendar (sorted by DTE with status badges), QuantData tab. |
| Orders | ✓ Working | Approve/decline pending orders. Filters to pending-only. Stage via Claude, approve in Claude or dashboard. |
| System | ✓ Working | Settings (editable except Strategy — Claude-only). Alerts CRUD. Scripts (11 scripts with Run buttons). Infrastructure. Universe. |

**Known gaps:**
- P&L tab: populates but verify totals are correct
- S12-04: stage_order leg-builder — workflow tested end-to-end ✓. Next: formalize as a documented prompt pattern.
- S12-03: Vol analytics QuantData IV (backend, deferred)
- S12-01: Keyboard shortcuts v4 (deferred — v4 in maintenance)

---

## v4 Navigation Architecture

| Tab | Path | Contents |
|---|---|---|
| **Briefing** | `/` | Overview · Market Intel · Earnings |
| **Portfolio** | `/portfolio` | Positions · P&L · Journal |
| **Trade** | `/trade` | Scenario Planner · Trade Builder · Orders |
| **Analysis** | `/analysis` | Chart · Vol Analytics |
| **System** | `/config` | Strategy · Settings · Scripts · Monitor |

---

## ⚡ IMMEDIATE ACTION REQUIRED — Next Session

**QuantData market-hours test (priority 1):**
During market hours, run:
```
qd_set_page_date(date="2026-06-02", ticker="AAPL", expiration_date="2026-06-20")
qd_get_exposure_by_strike()
qd_get_volatility_skew()
```
If both return AAPL data (price ~$306, not $7,600): update §5 strike selection workflow in docs and commit. If still broken: log in quantdata-mcp GitHub issues.

~~**Commit docs to GitHub** — done ✓~~

---

## What Was Done This Session (2026-06-01)

### Strategic reframe
- Aligned on Claude as primary trade workflow engine
- Fortress v4: retained for settings, monitoring, deep portfolio insight
- Parapet (v5): new lean dashboard, display + control layer, Claude handles decisions/execution

### Parapet v1.0 — built and deployed
- Full 5-page React/Vite dashboard built from scratch
- Deployed to WSL nginx at port 4000
- Repo created: `citychip/fortress-parapet`
- Pages: Overview, Portfolio, Market, Orders, System (with editable settings)
- All pages pulling live data from existing backend

### Standalone quantdata-mcp integrated
- Installed `quantdata-mcp` v0.5.0 on WSL (`~/.local/bin/quantdata-mcp`)
- Registered as second MCP server in `claude_desktop_config.json` (alongside fortress-dashboard)
- Refreshed QuantData JWT — new token active, setup completed (26 widget tools registered)
- Removed 6 broken qd_* proxy tools from `fortress_mcp.py` → v4.2.0
- **Confirmed working per-ticker:** `qd_get_iv_rank(ticker)` ✓
- **SPX widget-locked (bug):** `qd_get_dark_pool_levels`, `qd_get_order_flow` — still return SPX regardless of ticker
- **Pending market-hours test:** `qd_get_volatility_skew`, `qd_get_exposure_by_strike` — return empty outside market hours

### Strategy v3.8.0 drafted and published
- Advisory-system framing added throughout (§1, §15.1)
- Dual IV rank gate: yfinance + QuantData must both confirm IVR > 25 before entry (§4)
- Vol skew gate: check `qd_get_volatility_skew` before call-side entries (§5)
- Live GEX by strike as primary short-strike anchor, pending market-hours test (§5)
- Delta entry/roll split codified: 0.25–0.30 entry target, 0.35 roll trigger (§5)
- MSFT formal de-risking plan: target below 50% NLQ by Dec 2026 (§7)
- Tool stack updated for v4.2.0 and quantdata-mcp (§15.6)

### Dashboard settings aligned with Strategy v3.8.0
Updated via MCP: delta thresholds (0.25/0.30/0.35), DTE roll trigger (21), profit target (80%), concentration limits (20%/50%), IVR min entry (25), alert thresholds.

### Documentation updated and published
- `01_Portfolio_Strategy_v3_8.md` — published to `fortress-v4-api/docs/` ✓
- `07_MCP_Workflow_and_Prompts_v1_3.md` → v1.7 — published ✓
- `03_Quick_Start_and_Daily_Cheatsheet.md` → v1.8 — published ✓
- `fortress_mcp/README.md` — updated and published (v4.2.0) ✓

### Portfolio state confirmed
- Net Liq $96,729 | Available $28,935 | VIX 16.08 | Regime Bearish | Pacing 0/5
- **NVDA rolled ✓** — C250 Aug21, delta 0.345
- **MSFT rolled ✓** — C525 Aug21, delta 0.264
- All positions below 0.35 delta threshold

---

## Current Portfolio State

| Ticker | Strategy | Short Strike | Expiry | Delta | Key concern |
|---|---|---|---|---|---|
| MSFT | PMCC | 525C | Aug21 | 0.264 | 99% concentration — no new entries. Short call rolled to 525. |
| GOOGL | PMCC | 410C | Jul17 | 0.249 | Fine |
| AMZN | PMCC | 285C | Jul17 | 0.291 | Monitor |
| NVDA | PMCC | 250C | Aug21 | 0.345 ✓ | Rolled. Delta back inside threshold. |
| META | IC | 695C | Jul17 | 0.206 | Below 200-SMA, wings fine |
| TSM | Strangle | 520C | Jul17 | 0.209 | Clean |
| V | PCS | 300P | Jul17 | -0.197 | Fine |
| AMD | PCS | 380P | Jun26 | -0.060 | Fine |
| OST | Stock | — | — | — | Delisted, ignore |

---

## Sprint Roadmap

**Sprint 12 — Active**

QuantData / Strategy:
- [ ] S12-QD1: Market-hours test — `qd_get_volatility_skew` + `qd_get_exposure_by_strike` per-ticker
- [ ] S12-QD2: If confirmed: update §5 strike selection + §2.8 workflow, commit docs
- [ ] S12-QD3: Investigate dark pool / order flow SPX widget lock — quantdata-mcp issue

Parapet:
- [x] S12-P1: Scripts endpoint fixed — `/api/run/scripts` + `/api/run/{key}`
- [x] S12-P2: Portfolio Positions, Legs, P&L, Sector Exposure, Beta — all populating
- [x] S12-P3: Earnings Calendar fixed — correct structure rendered, sorted by DTE
- [x] S12-P4: Settings thresholds fixed via MCP (delta, DTE, profit target, concentration)
- [x] S12-P5: Order approve/decline endpoints fixed in Parapet
- [x] S12-P6: Claude stage→approve workflow tested end-to-end

v4 / Backend:
- [ ] S12-02: Re-verify NVDA in tier1 universe
- [ ] S12-01: Keyboard shortcuts (B/P/T/A/C/Esc) — v4
- [x] S12-03: Vol analytics — QuantData IV rank confirmed per-ticker via quantdata-mcp
- [ ] S12-04: stage_order leg-builder — formalize as documented prompt pattern (workflow works, needs write-up)

Docs:
- [x] Strategy v3.8.0, workflow v1.7, cheatsheet v1.8 — published to fortress-v4-api ✓
- [x] fortress-mcp v4.2.0 — published ✓

---

## Important Notes

**Parapet-specific:**
- After Parapet change: `cd ~/fortress-parapet && npm run build && sudo cp -r dist/* /var/www/fortress-parapet/`
- API calls use relative `/api/` paths — proxied by nginx to backend at :8081
- `.env.local` on WSL: `VITE_API_BASE=` (empty) + `VITE_API_TOKEN=...`
- Strategy section in Settings is read-only by design — edit via Claude
- Git branch is `master` (not `main`)

**General:**
- After backend change: `sudo systemctl restart fortress-dashboard-v4`
- After v4 frontend change: build + copy + nginx reload
- After MCP change: fully quit and relaunch Claude Desktop
- MCP write tools: require `FORTRESS_MCP_ALLOW_WRITES=1` in Claude Desktop config
- `qd_get_iv_rank(ticker)` ✓ confirmed per-ticker via standalone quantdata-mcp
- `qd_get_dark_pool_levels` / `qd_get_order_flow` — still SPX widget-locked
- `qd_get_volatility_skew` / `qd_get_exposure_by_strike` — pending market-hours test
- QuantData token refresh: `quantdata-mcp setup --auth-token "eyJ..." --instance-id "8f0803f4-1e64-40bf-8c18-e277a60ab45b"` then restart Claude Desktop
- stage_order: POST /api/orders/pending — all leg fields required: ticker, sec_type, right, strike, expiry, action, ratio
- NVDA (not NVDIA) is the correct ticker in tier1

---

## Strategy Quick Reference (v3.8.0)

- All thresholds advisory — signals for review, not automatic triggers
- IVR > 25 before any new entry — dual confirm: yfinance (`get_candidates`) + QuantData (`qd_get_iv_rank`)
- Vol skew check before call-side entries: `qd_get_volatility_skew` — steep put skew = document override
- Short strike anchor: live GEX call wall (`qd_get_exposure_by_strike`) → delta 0.25–0.30 → chart
- Delta: enter at 0.25–0.30 | watch at 0.30–0.35 | roll trigger > 0.35
- No new entries within 10 days of earnings (PCS) or 14 days (LEAP)
- Execute after 10:00 AM ET | Max 5 new positions per week
- MSFT: 99% concentration — no new entries | de-risking target: below 50% NLQ by Dec 2026
- NVDA rolled ✓ C250 Aug21, delta 0.345
- MSFT rolled ✓ C525 Aug21, delta 0.264
- **MSFT price ~$460 vs SMA ~$456 — monitor closely**
