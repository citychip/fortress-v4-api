# Fortress Dashboard — API Backend (V4)

> A FastAPI backend for systematic options portfolio management. Connects to Interactive Brokers via the IBKR Web API, proxies QuantData market intelligence, and exposes a structured REST API consumed by the [Fortress React frontend](https://github.com/citychip/fortress-app) and the [Fortress MCP server](https://github.com/citychip/fortress-mcp).

![Dashboard Preview](docs/assets/dashboard_preview.webp)

---

## What It Does

Fortress is a personal trading operations platform built for options sellers who run systematic, rules-based strategies. The backend handles everything that requires server-side logic: portfolio state management, Greeks calculation, stop-loss and roll evaluation, workflow script execution, live market intelligence hydration, and QuantData API proxying for Claude.

The system is designed around a single-user, self-hosted model. It runs as a `systemd` service (`fortress-dashboard-v4`) on a Linux VPS on **port 8081**, sits behind an nginx reverse proxy on port 443 (HTTPS), and authenticates all requests with a bearer token.

---

## Architecture

```
Browser (React SPA)          Claude Desktop / Cowork
    │  HTTPS (443)                  │  HTTPS (443)
    ▼                               ▼
nginx reverse proxy  ←─────────────┘
    ├── /           → /var/www/fortress-v4  (static React build)
    └── /api/       → 127.0.0.1:8081        (FastAPI, localhost only)
                            │
                ┌───────────┼───────────────┬───────────────┐
                ▼           ▼               ▼               ▼
          IBKR Web API   QuantData.us   quant/*.json   /api/qd/*
          (port 5055)    (live scrape)  (file state)   (MCP proxy)
```

`/api/qd/*` routes proxy QuantData tool calls from the Fortress MCP server (running on Claude's machine) through the VPS backend, eliminating the need for QuantData credentials on the client side.

The backend is intentionally stateless at the HTTP layer — all persistent state lives in JSON files under `quant/`. This makes the system trivially portable and eliminates the need for a database.

---

## Key Features

| Category | What is included |
|---|---|
| **Portfolio** | Positions sync from IBKR, Greeks aggregation (delta/gamma/theta/vega), P&L tracking (realized + unrealized), beta-weighted delta, hedge coverage ratio |
| **Risk** | Multi-signal stop-loss evaluation (§6), roll candidate ranking (§5), post-earnings decision matrix (§10), pre-trade gate (§3.3 → §4 → §7) |
| **Market Intelligence** | GEX call/put walls, dark pool floors/ceilings, net drift, order flow sweeps, IV rank/percentile, max pain — all sourced from QuantData |
| **MCP Proxy** | 6 QuantData endpoints proxied for the Fortress MCP server (`/api/qd/*`) — no client-side QD credentials needed |
| **Workflow Scripts** | 8 Python workflow scripts (pre-market scanner, IV crush report, whale flow, dark pool alert, max pain, EOD review, entry scoring, position monitor) — executable from the dashboard UI |
| **Strategy** | Trader Persona cards (5 profiles), Volatility Regime Playbook matrix (IV × GEX), 24 configurable strategy parameters, signal mode (Strict / Advisory / Sandbox) |
| **Cockpits** | Action Center (per-ticker pre-trade cockpit), Build Center (leg construction + IBKR whatif), Portfolio Center (aggregate view), Approvals (human-in-the-loop order queue) |
| **Data** | Ticker universe management, earnings calendar, IBKR sync, file uploads, chart annotations |
| **Journal** | Trade logging with strategy tags and outcome tracking |

---

## External Data Dependencies

### Interactive Brokers (Required for live Greeks)

The portfolio sync and live Greeks rely on the **IBKR Web API** (REST-based, introduced in TWS 10.19+). Enable it in TWS under **Edit → Global Configuration → API → Settings**. The backend connects to `localhost:5055` by default.

If the IBKR Web API session is not established, the backend automatically falls back to Black-Scholes Greeks computed from yfinance prices. The active backend is reported in the `greeks_backend_used` field of every sync response.

### QuantData.us (Optional but strongly recommended)

The workflow scripts, candidate scanner, macro regime extraction, and chart overlays all depend on [QuantData.us](https://quantdata.us). Without it, the dashboard manages your portfolio and evaluates stops/rolls correctly, but the candidate scanner will be empty, the macro regime will show as "unknown", and the chart overlays will be missing.

Configure your QuantData Auth Token and Instance ID in **Settings → QuantData Auto-Login**. The JWT is stored server-side and refreshed automatically. The `/api/qd/*` proxy routes use the server-side JWT — Claude never needs separate QuantData credentials.

---

## Installation

### Prerequisites

- Ubuntu 22.04 or 24.04 VPS
- Python 3.10+
- nginx (for HTTPS + static file serving)
- Interactive Brokers account with TWS running and the IBKR Web API enabled on `localhost:5055`
- *(Optional)* QuantData.us API credentials

### Quick Start

```bash
git clone https://github.com/citychip/fortress-v4-api.git
cd fortress-v4-api
./install.sh
```

The install script creates a Python virtual environment, generates a secure `FORTRESS_API_TOKEN` and `FORTRESS_MCP_TOKEN`, installs the `fortress-dashboard-v4` systemd service, and copies the example config. The API will be available at `http://localhost:8081`.

To serve the React frontend over HTTPS, deploy the [fortress-app](https://github.com/citychip/fortress-app) build to `/var/www/fortress-v4` and configure nginx to proxy `/api/` to port 8081. A reference nginx config is included in `docs/04_VPS_Implementation_Guide_v1_5.md`.

### Authentication

The API uses two bearer tokens:

| Token | Used by | Env var |
|---|---|---|
| `FORTRESS_API_TOKEN` | Browser frontend | `FORTRESS_API_TOKEN` in `fortress_config.json` |
| `FORTRESS_MCP_TOKEN` | Fortress MCP server (Claude) | Set in Claude's MCP env config |

Both tokens are validated by `app/middleware.py`. The MCP token is read-only by default; write tools require `FORTRESS_MCP_ALLOW_WRITES=1` in the MCP environment.

### Configuration

After installation, open the dashboard in your browser and navigate to **Settings**. Under **Security**, enter your IBKR Account ID, enable the IBKR Web API toggle, and add your QuantData credentials if applicable. All configuration is stored in `quant/dashboard_settings.json` and can be exported/imported via the Settings backup feature.

---

## Project Structure

```
app/
  main.py              ← FastAPI app, router registration, CORS
  middleware.py        ← Bearer token auth (FORTRESS_API_TOKEN + FORTRESS_MCP_TOKEN)
  routes/
    briefing.py        ← Portfolio briefing endpoint
    candidates.py      ← IV crush candidate scanner
    chart.py           ← OHLCV candles + overlay levels
    ibkr.py            ← IBKR sync, session management, whatif preview
    manage.py          ← Universe, settings, script runner, hydration cache
    market_intelligence.py  ← QuantData scrape (GEX, DP, drift, order flow)
    options.py         ← Black-Scholes Greeks, option chain
    orders.py          ← Pending orders (Approvals queue)
    pnl.py             ← P&L summary (realized + unrealized)
    positions.py       ← Positions read/write
    qd.py              ← QuantData MCP proxy (iv-rank, net-drift, max-pain, order-flow, dark-pool, oi-change)
    run.py             ← Workflow script execution + result persistence
    ... (alerts, calendar, earnings, journal, playbook, settings, uploads)
  services/
    state.py           ← JSON file I/O helpers, pending orders persistence
    ibkr_sync_web.py   ← IBKR Web API sync (positions, Greeks, P&L)
    ibkr_sync_synthetic.py  ← BS-yfinance fallback Greeks
    chain.py           ← Option chain fetcher
    bs_fallback.py     ← Black-Scholes implementation
    roll.py            ← Roll candidate evaluation
    stop_loss.py       ← Multi-signal stop-loss evaluation
    config_store.py    ← Settings read/write
    ... (fx, ocr, playbook)
quant/
  dashboard_settings.json   ← Runtime configuration (gitignored)
  active_positions.json     ← Live portfolio state (gitignored)
  ticker_universe.json      ← Trading universe
  workflow_*.py             ← 8 workflow scripts
  master_orchestrator.py    ← Cron-driven workflow runner
scripts/                    ← Standalone analysis scripts
docs/                       ← Architecture and workflow documentation
cp-gateway/                 ← ibeam IBKR Client Portal gateway (Docker, optional)
```

---

## API Reference

All endpoints require `Authorization: Bearer <token>` except `/api/health`, `/api/token`, `/api/manage/hydrate-asset`, and `/api/manage/hydrated-assets`.

### Core Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/health` | Health check — returns `{"status": "ok", "version": "..."}` |
| `GET` | `/api/briefing` | Full portfolio briefing (positions, Greeks, regime, candidates) |
| `GET` | `/api/positions` | Current option book with Greeks |
| `POST` | `/api/ibkr/sync` | Trigger IBKR positions sync |
| `GET` | `/api/market-intelligence/{ticker}` | GEX, DP, drift, order flow for a ticker |
| `GET` | `/api/candidates` | IV crush candidate scanner results |
| `GET` | `/api/pnl` | P&L summary (realized + unrealized) |
| `GET` | `/api/options/greeks` | Black-Scholes Greeks for a given contract |
| `GET` | `/api/options/chain/{ticker}` | Option chain for a ticker |
| `POST` | `/api/run/{script_key}` | Execute a workflow script |
| `GET` | `/api/manage/settings` | Read all settings |
| `POST` | `/api/manage/settings` | Update a settings section |
| `GET` | `/api/orders/pending` | Pending order approval queue |
| `POST` | `/api/orders/pending` | Add an order to the approval queue |
| `PATCH` | `/api/orders/pending/{id}` | Approve or decline a pending order |

### QuantData MCP Proxy (`/api/qd/*`)

These endpoints proxy QuantData data through the VPS for the Fortress MCP server. They use the server-side QuantData JWT — the MCP client needs no separate QD credentials.

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/qd/iv-rank/{ticker}` | IV rank and percentile |
| `GET` | `/api/qd/net-drift/{ticker}` | Options net drift table |
| `GET` | `/api/qd/max-pain/{ticker}` | Max pain price by expiry |
| `GET` | `/api/qd/order-flow/{ticker}` | Consolidated options order flow |
| `GET` | `/api/qd/dark-pool/{ticker}` | Dark pool support/resistance levels |
| `GET` | `/api/qd/oi-change/{ticker}` | Open interest change by strike |

All `/api/qd/*` endpoints return `{"error": "...", "hint": "Settings → QuantData Auto-Login"}` if the server-side QuantData JWT is missing or expired.

Full request/response schemas are documented in `docs/02_Trading_Dashboard_Build_Spec_v1_8.md`.

---

## Documentation

| Document | Description |
|---|---|
| [Portfolio Strategy v3.7.2](docs/01_Portfolio_Strategy_v3_7_2.md) | Core trading logic, rules engine, and strategy parameters |
| [Dashboard Build Spec v1.8](docs/02_Trading_Dashboard_Build_Spec_v1_8.md) | Architecture, API design, and data flow |
| [Trading Workflow v2.8](docs/03_Trading_Workflow_v2_8.md) | Step-by-step trade execution workflow |
| [VPS Implementation Guide v1.5](docs/04_VPS_Implementation_Guide_v1_5.md) | Deployment, IBKR Web API setup, nginx config, security hardening |
| [Implementation Status](docs/05_Implementation_Status.md) | Current feature completion and known gaps |
| [MCP Workflow and Prompts v1.1](docs/07_MCP_Workflow_and_Prompts_v1_1.md) | How to use the MCP server with Claude Desktop |
| [Market Intelligence Skill v1.0](docs/08_Market_Intelligence_Skill_v1_0.md) | QuantData integration details |

---

## Changelog

| Version | Date | Summary |
|---|---|---|
| v4.2 | 2026-05-29 | qd.py: fixed per-ticker IV rank — added x-instance-id header, correct iv-rank response parsing (sessionDateToIVRankData), computed IVR from 52w HV window; workflow_01/05 migrated from QuantData IVR to yfinance ATM options IV + rolling HV IVR (eliminates QD per-ticker filter dependency); workflow_08 max pain migrated to yfinance options chain; all workflow scripts now save to quant/ directory; fortress_mcp.py: removed local QD credentials requirement, all qd_* tools proxy through server |
| v3.9 | 2026-05-27 | qd.py: dynamic QuantData tool ID discovery — fixes max_pain/order_flow/dark_pool/oi_change 404/503 after JWT refresh; MCP token auth; FORTRESS_MCP_TOKEN support in middleware |
| v3.8 | 2026-05-18 | VIX 30d sparkline + Macro Regime Gauge on Morning Brief; mini sparklines in Dashboard trade report rows |
| v3.7.2 | 2026-05-16 | Action Center, Build Center, Portfolio Center, Approvals cockpits; pending orders persistence; hydration cache endpoints; QuantData race condition fix; script result persistence |
| v3.7.1 | 2026-05-16 | Strategy Sandbox: DTE/Delta sliders, Recharts payoff diagram with GEX/DP reference lines, 6-metric panel, Export to Trade Builder; 23 vitest unit tests |
| v3.7 | 2026-05-15 | Strategy Workspace: Trader Persona cards, Volatility Regime Playbook matrix, 24 strategy parameters, signal mode, backup/restore |
| v3.6 | 2026-05-15 | Hydration pipeline: Python scripts POST GEX/DP/drift after execution; Market Intel overlays cached values with "Cached" badge |
| v3.5 | 2026-05-15 | Portfolio view: theta sign fix, alert badge counts, Auto-Roll. Orders: JSON copy on URGENT rows. Script Runner: terminal output, exit code, duration |
| v3.4 | 2026-05-14 | Analysis: Net Drift NaN fix, GEX Call Wall blank fix, Order Flow empty-state, per-ticker Position Risk Context panel |
| v3.0–3.3 | 2026-05-14 | Fortress V4 rebuild: FastAPI on port 8081, nginx 443 proxy, IBKR Web API, Morning Brief landing page |

---

## Related Repositories

| Repository | Description |
|---|---|
| [citychip/fortress-app](https://github.com/citychip/fortress-app) | React 19 + tRPC frontend — the dashboard UI |
| [citychip/fortress-mcp](https://github.com/citychip/fortress-mcp) | MCP server — connects Claude to the Fortress API with 64 tools |

---

## Deployment

After pulling changes to the VPS, restart the service:

```bash
cd /home/ubuntu/fortress-v4-api
git pull
sudo systemctl restart fortress-dashboard-v4
sudo systemctl status fortress-dashboard-v4
```

The service file is at `/etc/systemd/system/fortress-dashboard-v4.service`.

---

## Disclaimer

This software is for informational and educational purposes only. It is not financial advice. Trading options involves significant risk. Always verify data and candidates before executing trades in your brokerage account.
