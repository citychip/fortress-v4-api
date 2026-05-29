# Fortress V4 — Reality Check
## What Is Actually Built vs What the Docs Say

**Prepared:** 2026-05-26 (original)
**Updated: 2026-05-29 (post Sprint v8.28 — ibind OAuth, dual-token auth, QD proxy fixes, pre-trade gate restore)
**Basis:** Live VPS audit — API calls, git log, file inspection, MySQL query
**Purpose:** Single source of truth on what exists today.

---

## Two Live Instances on VPS

| | V3 (Fallback) | V4 (Primary dev) |
|---|---|---|
| API port | 8080 | 8081 |
| App port | 3000 | 443 (HTTPS via nginx) |
| Path | `/home/ubuntu/fortress-api/` | `/home/ubuntu/fortress-v4-api/` |
| Service | `fortress-dashboard.service` | `fortress-dashboard-v4.service` |
| Data | JSON files | JSON + MySQL (positions/greeks/journal/config live in DB) |
| GitHub | — | `citychip/fortress-v4-api` (backend), `citychip/fortress-v4-frontend` (frontend) |
| TLS | HTTP only | HTTPS via Let's Encrypt on `srv1321374.hstgr.cloud` (exp 2026-08-25) |

V4 diverged significantly from V3 through Sprints v8.3–v8.24. V3 source archived at `citychip/fortress-v3-frontend`. `citychip/fortress-app` is archived.

---

## What Is Built and Working (post Sprint v8.22)

### Frontend

Deployed build: `/var/www/fortress-v4/` — served at `https://srv1321374.hstgr.cloud`

| Feature | Status | Sprint | Notes |
|---|---|---|---|
| 8-page navigation | ✅ Live | v8.0 | Dashboard, Market Intel, Positions, Trade, Analysis, Performance, Earnings, Config |
| Extended routes | ✅ Live | v8.12 | All 14 sub-routes wired in App.tsx |
| Dashboard / Morning Brief | ✅ Live | — | Portfolio snapshot, alerts, regime badge |
| PCS Exposure badge on Dashboard | ✅ Live | v8.18 | Shows X/5 spreads · $YK/$25K; breach/warning colors |
| Weekly pacing chart on Dashboard | ✅ Live | v8.18 | 8-week bar chart; current week amber at limit |
| Market Intelligence page | ✅ Live | v7.1 | Sort dropdown, per-card refresh, metric tooltips |
| Candidates page | ✅ Live | v8.14 | 11 rows with correct signals |
| NOT READY failure reasons | ✅ Live | v8.20 | Chip shows Earnings Xd / Conc. X% / Excluded / Not ready |
| Earnings Volatility expand row | ✅ Live | v8.17 | Implied vs historical move bar chart on Candidates expand |
| Positions page | ✅ Live | v8.12 | Greeks, stop-loss; null guard on LEAPS net_liq_pct |
| BetaWeightedDeltaCard | ✅ Live | v8.17 | SPY-equiv delta gauge + per-ticker breakdown |
| SectorExposureBar | ✅ Live | v8.17 | Stacked bar by sector; amber cap marker |
| Forward PnL accordion | ✅ Live | v8.10 | ForwardPnLPanel + PositionLimitsBadge |
| CapitalEfficiencyTable | ✅ Live | v8.17 | ROC per position; BP utilisation gauge |
| Performance page (P&L tab) | ✅ Live | — | Unrealised P&L by ticker, sortable/filterable |
| Equity curve chart | ✅ Live | v8.22 | 90-day net-liq line chart from portfolio_snapshots |
| Performance page (Journal tab) | ✅ Live | — | Journal entry list + metrics |
| Closed-loop P&L accordion | ✅ Live | v8.22 | Paired OPEN/CLOSE cards; IV crush, DTE@close, days held |
| Config page + Regression Dashboard | ✅ Live | v8.13 | Monitor uses window.location.origin; hyphen-aware bundle regex |
| Regime labels | ✅ Fixed | v8.11 | regimeInfo() across all 5 pages |

### Backend

| Feature | Status | Endpoint | Sprint |
|---|---|---|---|
| Bearer token auth | ✅ Live | all /api/* | — |
| Briefing | ✅ Live | GET /api/briefing | v8.2 |
| Positions (MySQL-first) | ✅ Live | GET /api/positions | v8.7 |
| Alerts | ✅ Live | GET /api/alerts, POST /api/alerts/ack/{id} | — |
| Market Intelligence | ✅ Live | GET /api/market-intelligence | — |
| Chart | ✅ Live | GET /api/chart/{ticker} | — |
| Candidates | ✅ Live | GET /api/candidates | v8.14 |
| Config CRUD | ✅ Live | GET/PATCH /api/config/{section} | — |
| Config backup/restore | ✅ Live | GET /api/config/backup, POST /api/config/restore | v8.4 |
| Config dual-write → MySQL | ✅ Live | config table; 115 rows | v8.21 |
| IBKR status + capability | ✅ Live | GET /api/ibkr/status, /api/ibkr/capability | — |
| IBKR upload retry | ✅ Live | POST /api/ibkr/upload/retry | v8.9 |
| SSE stream | ✅ Live | GET /api/stream | v4.0 |
| Position limits | ✅ Live | GET /api/options/position-limits | — |
| Forward PnL | ✅ Live | GET /api/options/forward-pnl | v8.10 |
| Scheduler status | ✅ Live | GET /api/scheduler/status | v8.3 |
| Portfolio beta | ✅ Live | GET /api/portfolio/beta | v8.5 |
| Sector exposure | ✅ Live | GET /api/portfolio/sector-exposure | v8.5 |
| Capital efficiency | ✅ Live | GET /api/portfolio/capital-efficiency | v8.5 |
| PCS exposure | ✅ Live | GET /api/portfolio/pcs-exposure | v8.18 |
| Earnings volatility | ✅ Live | GET /api/market/earnings-volatility/{ticker} | v8.16 |
| Journal close linkage | ✅ Live | POST /api/journal/close/{id} | v8.8 |
| Journal (MySQL-first) | ✅ Live | GET /api/journal — reads MySQL, falls back to JSON | v8.21 |
| Pre-trade check (9 gates) | ✅ Live | POST /api/manage/pre_trade_check | v8.19 |
| Pre-trade all (9 gates) | ✅ Live | GET /api/manage/pretrade_all | v8.19 |
| EOD snapshot write | ✅ Live | POST /api/pnl/snapshot | v8.21 |
| PnL history | ✅ Live | GET /api/pnl/history | v8.21 |
| DTE exception CRUD | ❌ Missing | — | — |
| Audit log | ❌ Missing | — | — |

### Strategy Enforcement Gates (pre-trade)

| Gate | Status | Sprint | Notes |
|---|---|---|---|
| F-01: PCS count cap (max 5) | ✅ Live | v8.19 | Hard block |
| F-02: PCS notional cap ($25K) | ✅ Live | v8.19 | Hard block |
| F-03: LEAP entry blackout (14d) | ✅ Live | v8.19 | Hard block |
| F-04: Weekly pacing (max 2/week) | ✅ Live | v8.19 | Advisory only |
| F-05: DTE exception registry | ✅ Live | v8.19 | Reads config.dte_exceptions[] |

### Scripts and Automation

| Feature | Status | Schedule |
|---|---|---|
| IBKR auto-sync | ✅ Live | Every 60s |
| Premarket scanner | ✅ Scheduled | 07:00 ET |
| IV Crush Monitor | ✅ Scheduled | Every 30 min (market hours) |
| Position Monitor | ✅ Scheduled | Every 5 min market hours |
| Dark Pool Alert | ✅ Scheduled | Every 15 min market hours |
| EOD Review | ✅ Scheduled | 16:05 ET |
| EOD Portfolio Snapshot | ✅ Scheduled | 16:10 ET Mon-Fri (direct callable) |
| Whale Flow Report | ✅ Scheduled | 08:00 ET + 12:00 ET |
| Max Pain Report | ✅ Scheduled | 09:00 ET + 14:00 ET |
| GEX/OI Update | ✅ Scheduled | 09:05 ET + 13:00 ET |

### Data Layer

| Feature | Status | Notes |
|---|---|---|
| JSON files | ✅ Live | active_positions.json, alerts.json, journal.json (fallback), fortress_config.json (fallback) |
| MySQL positions + greeks | ✅ Active | 19 positions, 2,750 greeks rows — written on every IBKR sync |
| MySQL config table | ✅ Active | 115 rows; dual-write on every config save; seeds from JSON on startup |
| MySQL journal table | ✅ Active | 2 rows; dual-write on every journal save; MySQL-first reads |
| MySQL portfolio_snapshots | ✅ Active | 1 row (2026-05-27); writes daily at 16:10 ET |
| MySQL sectors | ✅ Active | 10 rows |
| Redis | ✅ Live | Running; used by IBKR upload retry |
| Config auto-backup | ✅ Live | Pre-write backup on every config write; 10-file rotation |

### MCP

| Feature | Status | Notes |
|---|---|---|
| MCP server | ✅ Live | v4.0.0; 64 tools total |
| Tier 1 read-only tools | ✅ Live | 46 tools (incl. 3 new v8.24: get_pcs_exposure, get_pnl_history, get_version) |
| Tier 1b QuantData live tools | ✅ Live | 6 qd_* tools |
| Tier 2 write tools (env-gated) | ✅ Live | 9 tools (FORTRESS_MCP_ALLOW_WRITES=1) |
| Order management tools | ✅ Live | 3 tools (preview_order, approve_order, decline_order) |
| get_ibkr_status fix | ✅ Fixed | v8.24 — redirected to /api/ibkr/capability (status route has NameError) |
| pretrade_check fix | ✅ Fixed | v8.24 — now calls /api/manage/pre_trade_check (was calling wrong endpoint) |
| get_position_limits fix | ✅ Fixed | v8.24 — fetches legs from /api/positions; passes URL-encoded JSON |
| get_forward_pnl fix | ✅ Fixed | v8.24 — same legs-fetch pattern; iv_multiplier mapped to iv_adj |
| FORTRESS_API_URL | ✅ HTTPS | https://srv1321374.hstgr.cloud (v8.20) |
| FORTRESS_MCP_VERSION | ✅ 4.0.0 | v8.24 — constant added; server prompt updated |
| Prompt library | ✅ Updated | v8.24 — server instructions updated to "Fortress Dashboard MCP v4.0.0" |
| GitHub repo | ✅ Live | citychip/fortress-mcp (initialized v8.24); commits 600284e + 38f7e73 |

### Infrastructure

| Feature | Status | Notes |
|---|---|---|
| VPS (Ubuntu, systemd) | ✅ Live | 76.13.138.194 |
| nginx reverse proxy | ✅ Live | HTTPS on 443; HTTP 80/3001 redirect to HTTPS |
| Let's Encrypt TLS | ✅ Live | srv1321374.hstgr.cloud; cert expires 2026-08-25 |
| IBKR CP Gateway | ✅ Live | Native Java (cp-gateway.service), port 5000; ibind OAuth 1.0a installed (awaiting IBKR activation) |
| GitHub Actions — API | ✅ Live | Push to master auto-deploys via SSH |
| GitHub Actions — Frontend | ❌ Missing | Manual build + copy to /var/www/fortress-v4/ |
| Docker Compose (local dev) | ❌ Missing | |
| MySQL daily backup cron | ❌ Missing | H-05 not done |

---

## Remaining Open Gaps

- **H-04b** — GitHub Actions CI for frontend auto-deploy (manual build still required)
- **H-05** — MySQL daily backup cron on VPS
- **H-06** — Rollback procedure documented
- **H-03** — Docker Compose for local dev
- **I-01 through I-05** — remaining documentation gaps

---

## Source-of-Truth Hierarchy

1. This document (VPS-verified, 2026-05-27 post-v8.22)
2. `docs/v4/11_Upgrade_Plan.md` — sprint history
3. `docs/v4/04_Phase_Backlog.md` — canonical phase/backlog IDs
4. `docs/v4/02_System_Architecture.md` — target architecture
5. Portfolio Strategy v3.7 — trading rules (NEVER contradicted)
