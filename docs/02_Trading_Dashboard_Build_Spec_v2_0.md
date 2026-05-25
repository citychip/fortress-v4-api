# Fortress Dashboard — Build Specification

**Version 2.0 — May 18, 2026**

Technical specification for the Fortress V3 dashboard. Covers the React frontend architecture, Python backend API contract, database schema, and deployment topology.

**v2.0 changes from v1.9.1:** Full rewrite for Fortress V3 (React 19 + Tailwind 4 + tRPC 11). Sprint v7.x features documented: Market Intel sort/refresh/tooltips, Candidates All-tab monitoring split, QuantData credentials manager in Settings. chart.py deprecated tool IDs removed. All API endpoints verified against live VPS.

---

## 1. Architecture Overview

```
Browser (React 19 + Tailwind 4 + tRPC 11)
    │
    ├── nginx (port 3000) ──→ static files: /app/static/
    │                    └──→ /api/* proxy → Python backend (port 8080)
    │
Python Backend (FastAPI, port 8080)
    ├── /api/briefing
    ├── /api/positions
    ├── /api/candidates
    ├── /api/market-intelligence
    ├── /api/chart
    ├── /api/settings
    ├── /api/ibkr/*
    └── /api/manage/*
         │
         ├── IBKR Web API (CP Gateway, port 5000)
         ├── QuantData REST API (core-lb-prod.quantdata.us)
         └── yFinance (price/chain fallback)
```

**Source:** `/home/ubuntu/fortress-v2/` (React app, built with `pnpm build`)
**Deployed static files:** `/home/ubuntu/Fortress_Dashboard/app/static/`
**Python backend:** `/home/ubuntu/Fortress_Dashboard/app/`

---

## 2. Frontend — Page Map

| Route | Component | Purpose |
|---|---|---|
| `/` | `DashboardPage` | Portfolio overview, briefing, alerts |
| `/trade` | `TradePage` → `CandidatesPage` | IV Rank Heatmap, Candidates screener |
| `/market-intel` | `MarketIntelPage` | Per-ticker GEX/DP/Net Drift cards |
| `/analysis` | `AnalysisPage` | Chart overlays with DP floors + GEX levels |
| `/positions` | `PositionsPage` | Open positions, Greeks, stop-loss status |
| `/settings` | `SettingsPage` | Strategy config, alerts, QuantData credentials |
| `/journal` | `JournalPage` | Trade journal entries |
| `/reports` | `ReportsPage` | Trade evaluation reports |

---

## 3. API Contract

All endpoints require `Authorization: Bearer <token>` except `/api/health`.

### 3.1 Core Endpoints

#### `GET /api/health`
No auth. Returns `{"status": "ok", "version": "..."}`.

#### `GET /api/briefing`
Returns portfolio summary: account metrics, concentration, delta bias, alerts, staleness state.

```json
{
  "account": {
    "net_liquidation": 123456.78,
    "available_funds": 45678.90,
    "portfolio_delta": -127.4
  },
  "concentration": [
    {"ticker": "MSFT", "pct_netliq": 0.71, "flag": "CRITICAL"}
  ],
  "alerts": [...],
  "staleness": {"state": "fresh", "age_minutes": 3}
}
```

#### `GET /api/positions`
Returns all open positions with per-leg Greeks and stop-loss status.

#### `GET /api/candidates`
Returns IV Crush workflow results: `rows` array of candidate tickers with IVR, signal, and entry criteria.

```json
{
  "rows": [
    {
      "ticker": "AMD",
      "ivr": 67.4,
      "signal": "STRONG_SELL",
      "iv_30d": 0.42,
      "earnings_days": 45,
      "concentration_state": "ok"
    }
  ],
  "generated_at": "2026-05-18T09:00:00Z",
  "source_file": "Workflow_05_IV_Crush_2026-05-18.md"
}
```

#### `GET /api/market-intelligence?ticker={TICKER}`
Returns full regime analysis for a single ticker.

```json
{
  "ticker": "SPY",
  "current_price": 527.43,
  "regime": {
    "overall": "mildly_bullish",
    "score": 2,
    "gamma_regime": "positive",
    "flip_zone": 519.0
  },
  "gex": {
    "call_wall": 530.0,
    "put_wall": 510.0,
    "net_gex_bn": 1.24
  },
  "dark_pool": {
    "floors": [
      {"price": 522.0, "notional_bn": 2.1, "label": "Major Support"}
    ],
    "ceiling": 535.0
  },
  "net_drift": {
    "value_mm": 142.3,
    "bias": "bullish"
  },
  "trade_setups": [
    {
      "name": "Gamma Pin",
      "type": "iron_condor",
      "short_call": 530.0,
      "short_put": 510.0,
      "confidence": "high"
    }
  ]
}
```

#### `GET /api/chart?ticker={TICKER}&period={PERIOD}`
Returns OHLCV data with DP floor and GEX overlay levels for the Analysis page chart.

#### `GET /api/settings`
Returns current strategy configuration.

#### `POST /api/settings`
Updates strategy configuration sections.

#### `POST /api/settings/quantdata-credentials`
Updates QuantData `auth_token` and `cookie` in `/home/ubuntu/.quantdata-mcp/config.json`.

```json
// Request body
{
  "auth_token": "Bearer eyJ...",
  "cookie": "session=...; __cf_bm=..."
}
// Response
{
  "success": true,
  "message": "QuantData credentials updated successfully",
  "updated_at": "2026-05-18T14:32:00Z"
}
```

#### `GET /api/settings/quantdata-credentials/status`
Returns masked credential status (first 20 chars of token, last updated timestamp, boolean `has_credentials`).

#### `POST /api/ibkr/sync`
Triggers a full IBKR position sync. Long-running (~60s). Returns sync result.

#### `GET /api/ibkr/status`
Returns CP Gateway connection status.

---

## 4. QuantData API Integration

All QuantData calls use widget-UUID REST endpoints. The deprecated `tool/OPTIONS_*` tool IDs were removed in Sprint v7.1.

| Data | Endpoint | File |
|---|---|---|
| GEX by strike | `GET /api/options/exposure/strike/{uuid}?ticker={ticker}` | `market_intelligence.py` |
| Dark Pool levels | `GET /api/equities/dark-pool/levels/{uuid}?ticker={ticker}` | `market_intelligence.py` |
| Net Drift | `GET /api/options/net-drift/{uuid}?ticker={ticker}` | `market_intelligence.py` |
| Order flow | `GET /api/options/order-flow/consolidated?ticker={ticker}` | `chart.py` |
| IV Rank | `GET /api/options/iv-rank/{uuid}?ticker={ticker}` | `workflow_05_iv_crush_report.py` |

Widget UUIDs are stored in `/home/ubuntu/.quantdata-mcp/config.json` under `widget_ids`.

**Credential management:** Credentials are stored in `/home/ubuntu/.quantdata-mcp/config.json` (`auth_token`, `cookie`). Refresh via **Settings → QuantData Credentials** in the dashboard UI.

---

## 5. Candidates Page — Sprint v7.0/7.1 Architecture

### All Tab Logic

The All tab renders all 19 universe tickers in two sections:

1. **Actionable section** (top): Tickers with `signal` in `["STRONG_SELL", "SELL", "WATCH"]`. Rendered as full `CandidateRowItem` components with the Analyse button.
2. **Monitoring divider**: `"Universe — Monitoring (N)"` header separating the two sections.
3. **Monitoring section** (below divider): Tickers with no actionable signal. Rendered as `MonitoringRow` components (muted, opacity 0.65, no Analyse button, monitoring chip).

**Fallback behaviour (Sprint v7.1):** When the `/api/candidates` endpoint returns `rows: []` (e.g., QuantData credentials expired), the frontend falls back to showing all 19 universe tickers as monitoring rows with `—` placeholder values. This ensures the All tab is never empty.

### IV Rank Heatmap

The IV Rank Heatmap at the top of the Trade page shows a 4×5 grid of all 19 universe tickers with colour-coded IVR values:
- Red (≥70): HIGH
- Amber (50–69): ELEVATED
- Green (30–49): NORMAL
- Grey (<30): LOW

---

## 6. Market Intelligence Page — Sprint v7.1 Features

### Sort Dropdown

A `<Select>` component in the page header allows sorting all ticker cards by:
- **Score ↓** (default): `regime.score` descending
- **Score ↑**: `regime.score` ascending
- **Bias**: Grouped bullish → neutral → bearish
- **Alphabetical**: A–Z

Sort state is local to the page (not persisted).

### Per-Card Refresh

Each `TickerIntelCard` has a `↺` `<Button>` in the header row. On click, it calls `GET /api/market-intelligence?ticker={ticker}` for only that card and updates its local state. The button shows a `Loader2` spinner while the request is in flight.

### Metric Tooltips

Each `MetricBox` component accepts a `tooltip` prop. A `?` badge is shown next to the metric label. On hover, a `<Tooltip>` (shadcn/ui) shows the explanation string. Tooltips are defined inline in the `TickerIntelCard` component.

---

## 7. Settings Page — QuantData Credentials Section

The `QuantDataCredentialsSection` component (inserted after `ConnectionHealthSection`) provides:

1. **Status row:** Masked token preview (first 20 chars), last updated timestamp, green/red dot.
2. **Update Credentials button:** Opens an inline form with `auth_token` and `cookie` textarea fields.
3. **Step-by-step instructions:** Inline guide for extracting credentials from QuantData DevTools.
4. **Save button:** POSTs to `/api/settings/quantdata-credentials`. Shows success/error toast.

---

## 8. Deployment

### Build

```bash
cd /home/ubuntu/fortress-v2
pnpm build
# Output: dist/
```

### Deploy to VPS

```bash
scp -i ~/.ssh/fortress_vps -r dist/* ubuntu@76.13.138.194:/home/ubuntu/Fortress_Dashboard/app/static/
ssh ubuntu@76.13.138.194 "sudo systemctl restart nginx"
```

### VPS Service

```
/etc/systemd/system/fortress-dashboard.service
/etc/systemd/system/fortress-dashboard.service.d/override.conf  ← env vars (token, QD creds path)
```

Start: `sudo systemctl start fortress-dashboard`
Logs: `journalctl -u fortress-dashboard -f`

---

## Document History

| Version | Date | Changes |
|---|---|---|
| 2.0 | 2026-05-18 | Full rewrite for Fortress V3. Sprint v7.x features. QuantData widget-UUID endpoints. Credentials manager spec. Candidates All-tab architecture. Market Intel sort/refresh/tooltip spec. |
| 1.9.1 | 2026-05-13 | Market Intelligence endpoint added. Trade Reports tab. |
| 1.9.0 | 2026-05-09 | Security section. Bearer token. CP Gateway primary path. |
| 1.8.0 | 2026-05-05 | MCP server. 28 tools. IBKR Web API. |
