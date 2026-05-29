# Fortress Dashboard — Master Documentation
**Version: 4.2 | Date: 2026-05-29 | Status: Current**

This is the single authoritative document for the Fortress Trading Dashboard system. It supersedes all versioned sub-documents where they conflict. Read this before making any changes to the system.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Architecture](#2-architecture)
3. [Portfolio Strategy v3.7.2](#3-portfolio-strategy-v372)
4. [Workflow Scripts](#4-workflow-scripts)
5. [MCP Server — Claude Integration](#5-mcp-server--claude-integration)
6. [QuantData Integration](#6-quantdata-integration)
7. [IBKR Integration](#7-ibkr-integration)
8. [Deployment & Operations](#8-deployment--operations)
9. [Known Issues & Backlog](#9-known-issues--backlog)
10. [Changelog](#10-changelog)

---

## 1. System Overview

Fortress is a personal options trading operations platform. It manages a systematic, rules-based portfolio of PMCCs, put credit spreads, jade lizards, and a SPY hedge. The system handles portfolio state, Greeks, risk evaluation, workflow automation, and market intelligence — all connected to Claude via a 64-tool MCP server.

**Running environment:** WSL (Ubuntu) on Windows desktop. Not a VPS — the old VPS deployment docs are outdated.

**Current stack:**

| Component | Location | Status |
|---|---|---|
| FastAPI backend | `~/fortress-v4-api/` (WSL) | ✅ Running as `fortress-dashboard-v4.service` |
| React frontend | `~/fortress-v4-api/` (built) | ✅ Served by nginx |
| MCP server | `C:\Users\cityc.000\fortress_mcp\fortress_mcp.py` | ✅ Connected to Claude Desktop |
| IBKR (CP Gateway) | `https://localhost:5000` | ✅ Active (daily login) |
| IBKR (ibind OAuth) | configured | Pending IBKR activation |
| MySQL | WSL localhost | ✅ Active |
| QuantData | Server-side JWT | ✅ Active (per-ticker fix in progress) |

---

## 2. Architecture

```
Claude Desktop (Windows)
    │  stdio
    ▼
fortress_mcp.py  ← Python process, Windows
    │  HTTP Bearer token → localhost:8081
    ▼
FastAPI (fortress-dashboard-v4)  ← WSL Ubuntu
    │
    ├── IBKR  (ibind OAuth 1.0a [pending] or CP Gateway localhost:5000)
    ├── QuantData  (/api/qd/* proxy, server-side JWT)
    ├── MySQL  (journal, snapshots)
    └── quant/*.json  (positions, alerts, universe, config)

Browser (React SPA)
    │  HTTPS :443
    ▼
nginx → FastAPI localhost:8081
```

### Authentication

Two tokens are accepted for all `/api/*` routes:

| Token | Used by |
|---|---|
| `FORTRESS_API_TOKEN` | Browser / React frontend |
| `FORTRESS_MCP_TOKEN` | Claude MCP server |

Both are set in the systemd service override at `/etc/systemd/system/fortress-dashboard-v4.service`.

### Key Paths

| Path | Purpose |
|---|---|
| `~/fortress-v4-api/` | Backend + quant scripts |
| `~/fortress-v4-api/quant/` | State JSON files + workflow scripts + reports |
| `~/.quantdata-mcp/config.json` | QuantData JWT, tool IDs, page ID |
| `C:\Users\cityc.000\fortress_mcp\` | MCP server (Windows) |
| `C:\Users\cityc.000\AppData\Roaming\Claude\claude_desktop_config.json` | MCP config |

---

## 3. Portfolio Strategy v3.7.2

### 3.1 Governance

The trader decides. AI tools are analytical inputs, not decision sources. All hard rules below are non-negotiable. Tools may add safety; they may not subtract it. Strategy document overrides tool behavior overrides memory.

### 3.2 Active Strategies

**A. PMCC (Poor Man's Covered Call) — primary income**
- Long LEAP: ~640 DTE (Jan 2028), 25–30% ITM, delta 0.78–0.85
- Short call: 30–45 DTE, delta ~0.20, 7–10% OTM
- Strict 1:1 ratio — never hold uncovered LEAP

**B. Diagonal Spread — tactical**
- Long call 30–90 DTE + short call shorter DTE
- Primary use: post-earnings IV crush entry
- Entry: morning after earnings, IV crush ≥ 25% AND gap ±8%
- Long leg: delta 0.55–0.70 ATM/slightly ITM; short: delta 0.25–0.30 at first resistance
- Close at 50% max profit or roll short at 80% profit

**C. Put Credit Spread (PCS) — income**
- Short OTM put + long further-OTM put
- Short strike: delta 0.15–0.20; DTE: 30–45 days
- Max 5 open PCS positions; max put-side notional €25,000

**D. SPY Hedge — protective**
- Long SPY puts, market value $20,000–$30,000 at all times (when Net Liq > $50,000)
- New PMCC entries blocked if hedge MV < $20,000

**E. Jade Lizard — consolidation income**
- Short OTM call + short OTM put spread (no upside risk)
- Credit gate: total credit > width of put spread (enforced by dashboard)

### 3.3 Ticker Universe

**Tier 1 (primary, 15 tickers):** MSFT, AVGO, NFLX, VST, GOOGL, AMZN, AMD, MSTR, UNH, APP, LLY, TSM, V, MU, GEV

**Tier 2 (secondary, 3 tickers):** META, AAPL, NVDA

**Macro/Index:** SPX, SPY

**Hard exclusions:** COIN, HOOD, SMCI (regulatory risk); OST (ignored — display only if held)

**MSFT exception:** Concentration above 20% Net Liq acceptable (high-conviction core holding), subject to active SPY hedge.

### 3.4 Entry Rules

- Execute after 10:00 AM ET / 16:00 Amsterdam
- Limit orders at mid — never market orders, never chase
- IVR > 25 required before any new premium-selling position
- No new LEAP entries within 14 days of earnings
- No new put spreads within 10 days of earnings
- Bid/ask spread ≤ 10% of mid on both legs
- Open interest > 100 per leg

### 3.5 Short Call Management (PMCC)

- Take profit at 80% decay
- Roll if not 80% profit by 14–21 DTE
- Roll up-and-out if delta > 0.35 (critical threshold — tightened from 0.40 in v3.6)
- Never roll winners; never roll losers into earnings

**Delta thresholds:**

| Delta | Status | Action |
|---|---|---|
| ≤ 0.30 | Normal | No action |
| 0.30–0.35 | Approaching | Watch; consider rolling |
| > 0.35 | Critical | Roll within current week |

### 3.6 Exit Rules

- PCS: close at 50% profit or at 21 DTE regardless
- Jade Lizard: close at 50% max credit
- LEAPS: no mechanical target; exit on 200-day SMA breach (confirmed) or thesis change
- Never hold PCS through earnings

### 3.7 Risk Management

**Position sizing:**
- Max LEAP cost: $5,000 per position
- Max exposure per ticker: 20% Net Liq (MSFT exception)
- Max sector exposure: 40% Net Liq

**Concentration limits:**

| Level | Status | Action |
|---|---|---|
| < 20% | Normal | No restriction |
| 20–50% | Elevated | Explicit override required |
| > 50% | Critical | No new entries |

**Margin floors:**
- Minimum Excess Liquidity: $25,000 USD
- Minimum Available Funds: $17,000 USD

**Pacing:** Max 2 new positions per week; 3-day cooling-off after stop-loss event

**Market Regime:** No new entries when regime score ≤ 0 (neutral/bearish)

### 3.8 Stop-Loss Levels

| Level | Trigger | Action |
|---|---|---|
| L1 | 50% of credit received | Review |
| L2 | 75% of credit | Prepare to close |
| L3 | 100% of credit | Close |
| L4 | 150% of credit | Emergency close |

---

## 4. Workflow Scripts

All scripts live in `~/fortress-v4-api/quant/` and output reports to the same directory.

### Data Sources (v4.2)

| Script | IVR Source | IV Source | Other QD data |
|---|---|---|---|
| workflow_01 (premarket) | yfinance ATM options | yfinance rolling HV | None |
| workflow_05 (IV crush) | yfinance ATM options | yfinance rolling HV | None |
| workflow_08 (max pain) | N/A | N/A | yfinance options chain |
| workflow_02 (entry scoring) | N/A | N/A | QuantData GEX/OI/flow (broken — see §6) |
| workflow_06 (dark pool) | N/A | N/A | QuantData dark pool (broken — see §6) |
| workflow_07 (whale flow) | N/A | N/A | QuantData order flow (broken — see §6) |
| workflow_03 (position monitor) | N/A | yfinance | None |
| workflow_04 (EOD review) | N/A | N/A | None |

### Script Descriptions

**workflow_01_premarket_scanner.py** — Pre-market IVR scan across Tier 1/2 universe. Uses yfinance ATM options IV + 52-week rolling HV for IVR. Output: `Workflow_01_Scanner_YYYY-MM-DD.md`

**workflow_02_entry_scoring.py** — Structural entry scoring (GEX put walls, OI walls, dark pool floors, whale flow). Requires QuantData `update_tool` pattern. Currently returns empty data until QD per-ticker fix is implemented.

**workflow_03_position_monitor.py** — Monitors active positions for stop-loss/take-profit triggers. Uses IBKR + yfinance. Scheduled every 5 minutes during market hours.

**workflow_04_eod_review.py** — End-of-day review summary. Minimal QD dependency.

**workflow_05_iv_crush_report.py** — IV crush opportunity report. Uses yfinance ATM options IV + 52-week rolling HV. Generates the `candidates` data read by `/api/candidates`. Output: `Workflow_05_IV_Crush_YYYY-MM-DD.md`

**workflow_06_dark_pool_alert.py** — Dark pool floor proximity alerts for active positions. Uses QuantData `update_tool` + fetch. Currently returns empty data.

**workflow_07_whale_flow_report.py** — Whale order flow aggregation. Uses QuantData `order_flow_ticker` tool. Currently returns empty data.

**workflow_08_max_pain_report.py** — Max pain calculation from yfinance options chain (nearest 7–30 DTE expiry). Output: `Workflow_08_Max_Pain_YYYY-MM-DD.md`

### Candidates Pipeline

The `/api/candidates` endpoint reads from the most recent `Workflow_05_IV_Crush_*.md` report file. To refresh candidates: trigger `iv_crush` via MCP `run_script()` or dashboard Scripts page.

---

## 5. MCP Server — Claude Integration

**File:** `C:\Users\cityc.000\fortress_mcp\fortress_mcp.py`

**64 tools across 3 tiers:**

| Tier | Count | Description |
|---|---|---|
| Tier 1 | 45 | Read-only: briefing, positions, P&L, alerts, market intelligence, analytics |
| Tier 2 | 10 | Writes (enabled): alerts, journal, settings, IBKR sync, scripts, orders |
| QD (Tier 1b) | 6 | QuantData proxy: IV rank, dark pool, order flow, net drift, max pain, OI change |

**Always start with `get_briefing()`** — returns full portfolio situation including Net Liq, Greeks, regime, pacing, and required actions.

### QD Tools (v4.2 status)

All `qd_*` tools proxy through the server (`/api/qd/*`). No local QuantData credentials needed.

| Tool | Endpoint | Status |
|---|---|---|
| `qd_get_iv_rank(ticker)` | `/api/qd/iv-rank/{ticker}` | ⚠️ Returns default ticker (SPY) for all inputs — per-ticker fix pending |
| `qd_get_net_drift(ticker)` | `/api/qd/net-drift/{ticker}` | ⚠️ Same issue |
| `qd_get_max_pain(ticker)` | `/api/qd/max-pain/{ticker}` | ⚠️ Same issue |
| `qd_get_order_flow(ticker)` | `/api/qd/order-flow/{ticker}` | ⚠️ Same issue |
| `qd_get_dark_pool_levels(ticker)` | `/api/qd/dark-pool/{ticker}` | ⚠️ Same issue |
| `qd_get_oi_change(ticker)` | `/api/qd/oi-change/{ticker}` | ⚠️ Same issue |

**Root cause:** QuantData tool instances are saved per-ticker. The `/options/iv-rank/{tool_id}` endpoint returns data for whatever ticker was saved as the default (SPY). Fetching data for a different ticker requires first updating the tool's filter via `PUT /api/tool` with the ticker metadata — the `update_tool` step used in the workflow scripts. This step is not yet implemented in the server proxy (`app/routes/qd.py`).

**Fix needed:** Add `update_tool()` call to `_qd_get()` in `app/routes/qd.py` before fetching, mirroring the pattern in `workflow_05_iv_crush_report.py::get_iv_rank()`.

### MCP Configuration

`%APPDATA%\Claude\claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "fortress-dashboard": {
      "command": "C:\\Python314\\python.exe",
      "args": ["C:\\Users\\cityc.000\\fortress_mcp\\fortress_mcp.py"],
      "env": {
        "FORTRESS_API_URL": "http://localhost:8081",
        "FORTRESS_API_TOKEN": "07f03fb6e664859ac5e8113eaf1102ac43a3cb785c581af756671072b426db21",
        "FORTRESS_MCP_ALLOW_WRITES": "1"
      }
    }
  }
}
```

---

## 6. QuantData Integration

### Credentials

Stored at `~/.quantdata-mcp/config.json` (ubuntu) and `/root/.quantdata-mcp/config.json` (root). Structure:

```json
{
  "auth_token": "Bearer eyJ...",
  "instance_id": "...",
  "user_id": "...",
  "page_id": "2ef8b3c4-0910-42f9-b5e2-844377432e8c",
  "tools": {
    "iv_rank": "bba7d9df-...",
    "net_drift": "e227225d-...",
    "max_pain": "f4b0762c-...",
    "order_flow": "91d68ebf-...",
    "dark_pool_levels": "8d8cf588-...",
    "oi_change": "8a1830ea-..."
  },
  "fortress_api_token": "07f03fb6..."
}
```

The `fortress_api_token` field is used by workflow scripts to call `/api/candidates` (since scripts run under the service user and can't read the systemd env vars directly).

### Per-Ticker Data Fix (Pending)

QuantData uses a two-step pattern to fetch per-ticker data:
1. `PUT https://core-lb-prod.quantdata.us/api/tool` — update tool's filter metadata (sets ticker + date)
2. `GET https://core-lb-prod.quantdata.us/api/options/{slug}/{tool_id}` — fetch data

The workflow scripts implement this correctly via `update_tool()`. The server proxy (`app/routes/qd.py`) currently skips step 1, so all QD proxy endpoints return data for the default ticker (SPY).

**Fix location:** `app/routes/qd.py::_qd_get()` — add `update_tool()` equivalent before the GET request.

### Session Refresh

When QuantData sessions expire, re-login via **Settings → QuantData Auto-Login** in the dashboard. The new JWT is written to `~/.quantdata-mcp/config.json` automatically. After refresh, copy to root: `sudo cp ~/.quantdata-mcp/config.json /root/.quantdata-mcp/config.json`.

---

## 7. IBKR Integration

### Active Mode: CP Gateway (daily login required)

```
https://localhost:5000  (IBKR CP Gateway Java process)
```

Login via browser daily. The dashboard Settings page shows connection status. If `competing_sessions: true` appears, log out from all other IBKR sessions.

### Pending Mode: ibind OAuth 1.0a (headless)

Configured but pending IBKR activation of the consumer key (happens at their weekend server restart, up to 2 weeks). Toggle in **Settings → Security → IBKR Auth: Use ibind OAuth**.

### Greeks Fallback

If IBKR session is not established, Greeks fall back to Black-Scholes via yfinance prices. Briefing will show `backend: bs_yfinance`.

---

## 8. Deployment & Operations

### Service Management

```bash
# Restart after code changes
sudo systemctl restart fortress-dashboard-v4

# Check status
sudo systemctl status fortress-dashboard-v4

# View logs (last 50 lines)
journalctl -u fortress-dashboard-v4 -n 50 --no-pager
```

### Service File

`/etc/systemd/system/fortress-dashboard-v4.service` + override at `.../fortress-dashboard-v4.service.d/override.conf`

Key env vars in override:
- `FORTRESS_API_TOKEN` — browser/MCP auth token
- `FORTRESS_MCP_TOKEN` — separate MCP token (optional; both tokens accepted)
- `FORTRESS_MCP_ALLOW_WRITES=1` — enables write tools
- `IBIND_*` — OAuth credentials for headless IBKR auth

### After Code Changes

```bash
cd ~/fortress-v4-api
# make changes
sudo systemctl restart fortress-dashboard-v4
# Claude Desktop: fully quit and relaunch to pick up fortress_mcp.py changes
```

### Port Map

| Port | Service |
|---|---|
| 8081 | FastAPI (direct) |
| 443 | nginx HTTPS → FastAPI |
| 5000 | IBKR CP Gateway |
| 3306 | MySQL (localhost only) |

### Daily Operations Checklist

1. Verify IBKR session via **Settings → Connection Health**
2. Trigger IBKR sync if positions are stale
3. Run `premarket` script via MCP or dashboard for IVR scan
4. Check `get_briefing()` — review regime, pacing, actions
5. Consult candidates scan before any new entry

---

## 9. Known Issues & Backlog

### Active Issues

| ID | Issue | Impact | Fix |
|---|---|---|---|
| QD-01 | `qd_*` MCP tools return default ticker (SPY) for all inputs | All QD proxy tools return SPY data | Add `update_tool()` step to `app/routes/qd.py::_qd_get()` |
| QD-02 | workflow_02, 06, 07 use QuantData per-ticker data and return empty results | Entry scoring, dark pool alerts, whale flow non-functional | Add `update_tool()` + proper session to server proxy; OR rewrite using alternative sources |
| IBKR-01 | ibind OAuth 1.0a pending IBKR activation | Currently requires daily CP Gateway login | Await IBKR weekend restart |
| DATA-01 | `ticker_universe.json` not present at `~/ticker_universe.json` | Workflow scripts fall back to hardcoded ticker list | Copy from `quant/ticker_universe.json` or create at expected path |

### Pending Improvements (from review backlog)

- Fix `qd_*` per-ticker proxy (QD-01) — implement `update_tool` in `app/routes/qd.py`
- Fix workflow_02/06/07 QuantData data fetching (QD-02)
- Add IBKR snapshot retry endpoint (K-03)
- Implement journal closed-loop P&L linkage (K-04)
- `ticker_universe.json` path alignment (scripts expect `~/` but file is in `~/fortress-v4-api/quant/`)
- Stale docs cleanup: consolidate versioned doc files, remove `.bak` files

### Repository Status

| Repo | Status |
|---|---|
| `citychip/fortress-v4-api` | ✅ Active — backend + quant scripts |
| `citychip/fortress-mcp` | ✅ Active — MCP server |
| `citychip/fortress-v4-frontend` | ✅ Active — React UI |
| `citychip/fortress-install` | ✅ Active — install scripts |
| `citychip/fortress-wsl-install` | ✅ Active — WSL install |
| `citychip/quantdata-mcp` | ⚠️ Keep for reference — proper QD per-ticker filter implementation |
| `citychip/fortress-api` | 🗑️ Deleted |
| `citychip/fortress-app` | 🗑️ Deleted |
| `citychip/fortress-v3-frontend` | 🗑️ Deleted |

---

## 10. Changelog

| Version | Date | Summary |
|---|---|---|
| v4.2 | 2026-05-29 | qd.py: x-instance-id header, iv-rank response parsing (sessionDateToIVRankData), IVR from 52w HV window, dict-format tool ID support; workflow_01/05: yfinance ATM options IV + rolling HV IVR (removes QuantData IVR dependency); workflow_08: yfinance max pain from options chain; all scripts output to quant/; fortress_mcp.py: qd_* tools proxy through server — no local QD credentials needed |
| v4.1 | 2026-05-29 | WSL local deployment; dual-token middleware; trpc prefs path fix |
| v4.0 | 2026-05-28 | ibind OAuth 1.0a (headless IBKR); dual-token auth (FORTRESS_API_TOKEN + FORTRESS_MCP_TOKEN); ibkr_use_ibind_oauth toggle; QD proxy fixed (dict tool IDs, correct URL slugs); CP Gateway IP allowlist |
| v3.9 | 2026-05-27 | qd.py dynamic tool ID discovery; FORTRESS_MCP_TOKEN support |
| v3.8 | 2026-05-18 | VIX 30d sparkline + Macro Regime Gauge; mini sparklines in trade report |
| v3.7.2 | 2026-05-16 | Action Center, Build Center, Portfolio Center, Approvals cockpits; pending orders; hydration cache; script result persistence |
| v3.7 | 2026-05-15 | Strategy Workspace: Trader Persona cards, Volatility Regime Playbook, 24 strategy params, signal mode, backup/restore |
| v3.6 | 2026-05-15 | Hydration pipeline; Market Intel cached overlays |
| v3.0–3.5 | 2026-05-14/15 | Fortress V4 rebuild on FastAPI 8081, nginx, IBKR Web API |

---

*This document is maintained at `docs/FORTRESS_V4_MASTER_DOC.md`. Update after every significant system change.*
