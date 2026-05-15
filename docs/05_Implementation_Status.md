# Implementation Status

**Snapshot date: 2026-05-15**
**Strategy version:** v3.6
**Dashboard version:** v3.6 backend (VPS) / v2 frontend (React/TypeScript, port 3000)

This document is a point-in-time snapshot of what is live, what is broken, and what is in the build queue. It is the one place in the documentation set where reality-vs-spec drift is allowed to be visible. For the full backlog, see `review/11_Todo_Backlog.md`.

---

## Live and Working

### Infrastructure

| Component | Status | Notes |
|---|---|---|
| VPS (srv1321374, 76.13.138.194) | Live | Ubuntu 22.04, 4GB RAM, 40GB SSD |
| CP Gateway (`voyz/ibeam`) | Live | Replaces legacy TWS gateway. Port 5000. Authenticated to U7453366. |
| `fortress-dashboard.service` | Live | FastAPI + uvicorn, port 8080 |
| `fortress_orchestrator.service` | Live | APScheduler, 10 scheduled scripts |
| nginx (v2 frontend) | Live | Serves React build at port 3000 |
| Python venv | Live | Python 3.14, all dependencies installed |
| GitHub Actions CI/CD | Live | Auto-deploys to VPS on push to `master` |

### Backend — Phases 1–6

| Feature | Endpoint | Status |
|---|---|---|
| Morning briefing | `GET /api/briefing` | Live |
| Per-leg positions | `GET /api/positions` | Live |
| Aggregated positions | `GET /api/manage/positions` | Live |
| IV crush candidates | `GET /api/candidates` | Live |
| Earnings calendar | `GET/PUT/POST/DELETE /api/calendar/*` | Live |
| Earnings auto-fetch | `POST /api/calendar/fetch-earnings` | Live — auth fix applied 2026-05-15 |
| Universe viewer + editor | `GET/POST/DELETE /api/universe/*` | Live |
| Alerts CRUD | `GET/POST/DELETE /api/alerts/*` | Live |
| Journal CRUD + metrics | `GET/POST/DELETE /api/journal/*` | Live |
| IBKR screenshot OCR | `POST /api/uploads/ibkr` | Live (legacy path) |
| TradingView chart upload | `POST /api/uploads/chart` | Live |
| Script runner | `POST /api/run/{script_key}` | Live |
| IBKR Web API sync | `POST /api/ibkr/sync` | Live — web_api backend active |
| IBKR capability check | `GET /api/ibkr/capability` | Live — returns session status, OPRA, backend mode |
| TradingView Lightweight Charts widget | `GET /api/chart/{ticker}` | Live |
| Stop-loss aggregator (4-level) | `GET /api/manage/stop_loss/{ticker}` | Live |
| Roll candidate evaluator | `GET /api/manage/roll/{ticker}` | Live |
| Post-earnings playbook | `POST /api/playbook/post_earnings` | Live |
| Jade Lizard credit gate | `POST /api/manage/validate_jade_lizard` | Live |
| SPY hedge coverage (USD) | `GET /api/manage/spy_hedge_coverage` | Live — classifier broadened 2026-05-15 |
| Pre-trade gate checker | New Trade tab | Live |
| Portfolio Greeks aggregation | Briefing tab | Live — all four Greeks live via OPRA (S-02 resolved) |
| EUR/USD FX conversion | All threshold checks | Live |
| BS-from-yfinance delta fallback | IBKR sync post-processing | Live |
| Hard exclusion gate (§3.3) | Pre-trade gate + candidates | Live |
| Per-leg IBKR records + aggregator | Positions + Manage tabs | Live |
| Settings tab + config_store | `GET/POST /api/settings/*` | Live — `fortress_config.json` is canonical |
| Backend dispatcher | `cfg("technical.greeks_backend")` | Live — {auto, web_api, bs_yfinance, tws_ibkr} |
| Live Strategy Narrative | `GET /api/settings/narrative` | Live |
| Security toggles + runtime guards | Settings → Security | Live |
| Trade Reports tab | `GET /api/manage/trade_report` | Live |
| Market Intelligence endpoint | `GET /api/market-intelligence` | Live |
| Trader Personas (5) + Strategy Catalogue (24) | `GET /api/settings/trader_presets` | Live |
| QuantData test | `POST /api/settings/test_quantdata` | Live |

### QuantData Workflow Scripts

| Script | Schedule | Status |
|---|---|---|
| `workflow_01_premarket_scanner.py` | Weekdays 09:00 ET | Live |
| `quantdata_daily.py` | Weekdays 09:35 ET | Live |
| `workflow_02_entry_scoring.py` | On-demand (before every entry) | Live |
| `workflow_03_position_monitor.py` | Weekdays 12:00 + 15:45 ET | Live |
| `workflow_04_eod_review.py` | Weekdays 16:15 ET | Live |
| `workflow_05_iv_crush_report.py` | Weekdays 09:35 ET | Live |
| `workflow_06_dark_pool_alert.py` | Weekdays 12:00 + 15:45 ET | Live |
| `workflow_07_whale_flow_report.py` | Weekdays 09:35 ET | Live |
| `workflow_08_max_pain_report.py` | Weekly Friday + on-demand | Live |
| `gex_oi_report.py` | On-demand | Live |

### MCP Scripts

| Script | Purpose | Status |
|---|---|---|
| `scripts/mcp_briefing.py` | Morning briefing via MCP | Live |
| `scripts/mcp_full_analysis.py` | Full ticker analysis via MCP | Live |
| `scripts/mcp_gex2.py` | GEX level extraction via MCP | Live |
| `scripts/mcp_position_analysis2.py` | Per-position analysis via MCP | Live |

### v2 Dashboard (React/TypeScript — port 3000)

| Feature | Page | Status |
|---|---|---|
| Trade Report panel with entry/stop/exit/roll/post-earnings sections | Dashboard | Live |
| Post-earnings candidates section with days-since badge and IVR chip | Dashboard | Live |
| Roll candidates DTE countdown ring (cyan, urgency badge) | Dashboard | Live |
| Summary count grid (6 columns incl. Post-Earnings) | Dashboard | Live |
| Greeks Summary panel (Net Δ/Γ/Θ/V, Avg IV, Leg count) | Analysis | Live |
| Earnings date overlay on price chart (amber dashed vertical line) | Analysis | Live |
| Deep-link navigation from Dashboard rows to Analysis with ticker pre-selected | Dashboard → Analysis | Live |
| Settings sync indicator (SyncBadge: Saving… / Saved ✓ / Sync failed) | Settings | Live |
| Connection Health panel — IBKR and QuantData ping tests with latency | Settings | Live |
| Null-safety hardening on all nullable `.toFixed()` calls | Dashboard | Live |

---

## Known Issues

| ID | Severity | Issue | Workaround |
|---|---|---|---|
| B-02 | Medium | qty=0 legs persist in sync list after position close | Workaround: manually remove from `active_positions.json`. Fix: post-sync filter in `ibkr_sync.py`. |
| B-05 | Low | Position notes disabled for IBKR-synced positions | Workaround: use Journal tab for trade notes. |

---

## Resolved Issues (since 2026-05-05)

| ID | Issue | Resolved |
|---|---|---|
| S-02 | Theta and vega showed as zero — IBKR Read-Only API not enabled | 2026-05-09 — CP Gateway + OPRA live |
| B-01 | Same as S-02 | 2026-05-09 |
| B-03 | SPY hedge coverage target now USD-native | 2026-05-05 |
| B-04 | Universe editor UI was partial | 2026-05-05 (D-20) |

---

## IBKR Web API — Option Chain Capability

The IB Gateway Web API (running at `localhost:5000`) supports full option chain access:

| Capability | Endpoint |
|---|---|
| Available expirations per ticker | `GET /v1/api/iserver/secdef/search?symbol=X&secType=STK` |
| Strikes per expiry | `GET /v1/api/iserver/secdef/strikes?conid=X&sectype=OPT&month=MMMYY` |
| Option conids (call and put per strike) | `GET /v1/api/iserver/secdef/info?conid=X&sectype=OPT&month=MMMYY&right=C&strike=Y` |
| Live market snapshot (bid, ask, last, mark, delta, gamma, theta, vega, IV%) | `GET /v1/api/iserver/marketdata/snapshot?conids=X,Y,Z&fields=84,86,7308,7309,7310,7311,7633` |

Batch snapshot supports up to ~100 conids per call. Requires a 2-second warm-up on first call per conid. This unlocks a live option chain viewer, pre-trade strike suggester, and IV surface heatmap as planned future features (see V-02, V-07, V-11 in Todo Backlog).
