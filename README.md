# Fortress Dashboard — API Backend (V4)

> A FastAPI backend for systematic options portfolio management. Connects to Interactive Brokers via ibind OAuth 1.0a (headless) or the IBKR CP Gateway, proxies QuantData market intelligence, and exposes a structured REST API consumed by the [Fortress React frontend](https://github.com/citychip/fortress-app) and the [Fortress MCP server](https://github.com/citychip/fortress-mcp).

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
        IBKR (ibind     QuantData.us   quant/*.json   /api/qd/*
        OAuth 1.0a      (live scrape)  (file state)   (MCP proxy)
        or CP Gateway)
```

**IBKR authentication** supports two modes, switchable via Settings → Security:

| Mode | How it works | Login required |
|---|---|---|
| **ibind OAuth 1.0a** *(recommended)* | Fully headless — RSA key pair + Diffie-Hellman session token, no browser interaction | Never (once IBKR activates the consumer key) |
| **CP Gateway** *(fallback)* | IBKR's Java gateway at `https://localhost:5000` requires a browser login session | Daily |

The active mode is controlled by the `ibkr_use_ibind_oauth` setting in **Settings → Security**. Switching it takes effect immediately — no service restart needed.

`/api/qd/*` routes proxy QuantData tool calls from the Fortress MCP server (running on Claude's machine) through the VPS backend, eliminating the need for QuantData credentials on the client side.

The backend is intentionally stateless at the HTTP layer — all persistent state lives in JSON files under `quant/`. This makes the system trivially portable and eliminates the need for a database.

---

## Authentication

All `/api/*` routes (except `/api/health`) require a Bearer token. **Two tokens are accepted:**

| Token | Set via | Used by |
|---|---|---|
| `FORTRESS_API_TOKEN` | systemd service file | Browser / React frontend |
| `FORTRESS_MCP_TOKEN` | systemd override.conf | Claude MCP server |

Either token grants full access. This allows the browser and Claude to use independent credentials without interfering with each other.

Set them in the systemd unit files:
```bash
# Main service file — browser token
Environment=FORTRESS_API_TOKEN=your_browser_token

# Override conf — MCP token (can be different)
Environment=FORTRESS_MCP_TOKEN=your_mcp_token
```

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

### Interactive Brokers

Fortress supports two authentication modes:

**ibind OAuth 1.0a (recommended — fully headless):**
1. Generate RSA key pairs and a DH prime (see [ibind OAuth docs](https://github.com/Voyz/ibind/wiki/OAuth-1.0a))
2. Register a consumer key at the [IBKR OAuth portal](https://ndcdyn.interactivebrokers.com/sso/Login?action=OAUTH)
3. Add credentials to the systemd override.conf (see *Installation* below)
4. Enable the toggle in **Settings → Security → IBKR Auth: Use ibind OAuth**
5. Wait for IBKR to activate your consumer key (happens at their weekend server restart — up to 2 weeks)

**CP Gateway (fallback — requires daily browser login):**
1. Download the [IBKR Client Portal Gateway](https://www.interactivebrokers.com/en/trading/ib-api.php)
2. Run it at `https://localhost:5000`
3. Log in via browser each day (add your IP to the allowlist in `conf.yaml` for direct access)
4. Keep `ibkr_use_ibind_oauth` set to OFF in Settings → Security

If neither IBKR session is established, the backend automatically falls back to Black-Scholes Greeks computed from yfinance prices.

### QuantData.us (Optional but strongly recommended)

The workflow scripts, candidate scanner, macro regime extraction, and chart overlays all depend on [QuantData.us](https://quantdata.us). Without it, the dashboard manages your portfolio and evaluates stops/rolls correctly, but the candidate scanner will be empty, the macro regime will show as unknown, and the chart overlays will be missing.

Configure your QuantData credentials in **Settings → QuantData Auto-Login**. The JWT is stored server-side and refreshed automatically. The `/api/qd/*` proxy routes use the server-side JWT — Claude never needs separate QuantData credentials.

---

## Installation

### Prerequisites

- Ubuntu 22.04 or 24.04 VPS
- Python 3.10+
- nginx (for HTTPS + static file serving)
- Interactive Brokers account

### Quick Setup

```bash
git clone https://github.com/citychip/fortress-v4-api.git /home/ubuntu/fortress-v4-api
cd /home/ubuntu/fortress-v4-api
python3 -m venv venv
venv/bin/pip install -r requirements.txt
venv/bin/pip install 'ibind[oauth]'   # for headless OAuth support
```

### systemd Service

```ini
[Unit]
Description=Fortress Dashboard V4 API
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/fortress-v4-api
ExecStart=/home/ubuntu/fortress-v4-api/venv/bin/python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8081
Restart=on-failure
RestartSec=10
Environment=FORTRESS_API_TOKEN=your_browser_token

[Install]
WantedBy=multi-user.target
```

### ibind OAuth 1.0a — Environment Variables

Add to `/etc/systemd/system/fortress-dashboard-v4.service.d/override.conf`:

```ini
[Service]
Environment=FORTRESS_MCP_TOKEN=your_mcp_token
Environment=IBIND_USE_OAUTH=True
Environment=IBIND_OAUTH1A_CONSUMER_KEY=YOURCKEY
Environment=IBIND_OAUTH1A_ACCESS_TOKEN=your_access_token
Environment=IBIND_OAUTH1A_ACCESS_TOKEN_SECRET=your_access_token_secret
Environment=IBIND_OAUTH1A_DH_PRIME=00abcd...hex...
Environment=IBIND_OAUTH1A_ENCRYPTION_KEY_FP=/path/to/private_encryption.pem
Environment=IBIND_OAUTH1A_SIGNATURE_KEY_FP=/path/to/private_signature.pem
Environment=IBIND_ACCOUNT_ID=U1234567
```

After editing:
```bash
sudo systemctl daemon-reload
sudo systemctl restart fortress-dashboard-v4
```

---

## API Reference

All endpoints require `Authorization: Bearer <token>` except `/api/health`, `/api/token`, `/api/manage/hydrate-asset`, and `/api/manage/hydrated-assets`. Both `FORTRESS_API_TOKEN` and `FORTRESS_MCP_TOKEN` are accepted.

### Core Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/health` | Health check — returns `{status: ok, version: ...}` |
| `GET` | `/api/briefing` | Full portfolio briefing (positions, Greeks, regime, candidates) |
| `GET` | `/api/positions` | Current option book with Greeks |
| `POST` | `/api/ibkr/sync` | Trigger IBKR positions sync |
| `GET` | `/api/ibkr/capability` | IBKR connection status (session, OPRA, account) |
| `GET` | `/api/market-intelligence?ticker=X` | GEX, DP, drift, order flow for a ticker |
| `GET` | `/api/candidates` | IV crush candidate scanner results |
| `GET` | `/api/pnl` | P&L summary (realized + unrealized) |
| `GET` | `/api/chart/{ticker}` | OHLCV candles + GEX/DP overlay levels |
| `GET` | `/api/options/greeks` | Black-Scholes Greeks for a given contract |
| `POST` | `/api/run/{script_key}` | Execute a workflow script |
| `GET` | `/api/settings` | Read all settings |
| `PUT` | `/api/settings/{section}` | Update a settings section |
| `GET` | `/api/orders/pending` | Pending order approval queue |
| `POST` | `/api/orders/pending` | Add an order to the approval queue |
| `PATCH` | `/api/orders/pending/{id}` | Approve or decline a pending order |
| `GET` | `/api/manage/stop_loss_all` | Stop-loss evaluation for all positions |
| `GET` | `/api/manage/roll_all` | Roll candidate evaluation for all positions |
| `GET` | `/api/manage/pretrade_all` | Pre-trade gate check for all universe tickers |

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

All `/api/qd/*` endpoints return `{error: ..., hint: Settings → QuantData Auto-Login}` if the server-side QuantData JWT is missing or expired. Tool IDs are read from `~/.quantdata-mcp/config.json` and support both dict and list formats.

---

## Settings Reference

Key settings in **Settings → Security**:

| Key | Type | Description |
|---|---|---|
| `use_ibkr_web_api` | boolean | Enable/disable all IBKR integration (falls back to yfinance when off) |
| `ibkr_use_ibind_oauth` | boolean | ON = ibind OAuth 1.0a (headless); OFF = CP Gateway (daily login) |
| `use_quantdata` | boolean | Enable/disable QuantData overlays and workflow scripts |
| `ibkr_auto_sync_enabled` | boolean | Auto-sync positions every N minutes (default: off) |
| `ibkr_account_id` | password | IBKR account number (e.g. U1234567) |

Changing `ibkr_use_ibind_oauth` takes effect immediately — the ibind client singleton is reset and the capability cache is invalidated.

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
| v4.0 | 2026-05-28 | ibind OAuth 1.0a integration (headless IBKR auth, no CP Gateway needed); dual-token middleware (FORTRESS_API_TOKEN + FORTRESS_MCP_TOKEN both accepted); ibkr_use_ibind_oauth toggle in Settings; QuantData QD proxy fixed (dict-format tool IDs, correct URL slugs for iv-rank/net-drift/max-pain); CP Gateway IP allowlist support |
| v3.9 | 2026-05-27 | qd.py: dynamic QuantData tool ID discovery — fixes max_pain/order_flow/dark_pool/oi_change 404/503 after JWT refresh; MCP token auth; FORTRESS_MCP_TOKEN support in middleware |
| v3.8 | 2026-05-18 | VIX 30d sparkline + Macro Regime Gauge on Morning Brief; mini sparklines in Dashboard trade report rows |
| v3.7.2 | 2026-05-16 | Action Center, Build Center, Portfolio Center, Approvals cockpits; pending orders persistence; hydration cache endpoints; QuantData race condition fix; script result persistence |
| v3.7.1 | 2026-05-16 | Strategy Sandbox: DTE/Delta sliders, Recharts payoff diagram with GEX/DP reference lines, 6-metric panel, Export to Trade Builder; 23 vitest unit tests |
| v3.7 | 2026-05-15 | Strategy Workspace: Trader Persona cards, Volatility Regime Playbook matrix, 24 strategy parameters, signal mode, backup/restore |
| v3.6 | 2026-05-15 | Hydration pipeline: Python scripts POST GEX/DP/drift after execution; Market Intel overlays cached values with Cached badge |
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

The systemd service file is at `/etc/systemd/system/fortress-dashboard-v4.service` and the override at `/etc/systemd/system/fortress-dashboard-v4.service.d/override.conf`.

---

## Disclaimer

This software is for informational and educational purposes only. It is not financial advice. Trading options involves significant risk. Always verify data and candidates before executing trades in your brokerage account.
