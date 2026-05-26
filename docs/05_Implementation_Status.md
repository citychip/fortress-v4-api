# Fortress Dashboard — Implementation Status

**Snapshot:** May 18, 2026 | **Strategy:** v3.7 | **Dashboard:** Fortress V3 (React/tRPC) | **Build Spec:** v2.0

---

## Live Components

| Component | Status | Version | Notes |
|---|---|---|---|
| **Fortress V3 Frontend** | ✅ Live | React 19 + Tailwind 4 + tRPC 11 | Served on port 3000 via nginx. Source: `/home/ubuntu/fortress-v2/`. |
| **Python Backend (FastAPI)** | ✅ Live | v1.9.x | `fortress-dashboard.service` on port 8080. |
| Bearer token auth | ✅ Live | — | All `/api/*` endpoints require `Authorization: Bearer <token>`. |
| CP Gateway (voyz/ibeam) | ✅ Live | latest | Docker container. IBKR Web API primary broker path. |
| IBKR Greeks | ✅ Live | Web API | Δ/Γ/Θ/V live when OPRA subscribed. BS fallback when session expires. |
| MCP server | ✅ Live | v1.2 | 29 tools. Installed in Claude Desktop. Repo: `citychip/fortress-mcp`. |
| Market Intelligence endpoint | ✅ Live | — | `/api/market-intelligence` — GEX, DP floors, Net Drift, regime score. |
| Market Intelligence UI | ✅ Live | Sprint v7.1 | Sort dropdown (Score/Bias/Alpha), per-card refresh, metric tooltips. |
| Candidates All-tab | ✅ Live | Sprint v7.0 | Full 19-ticker universe. Actionable at top; monitoring below divider. |
| Candidates fallback | ✅ Live | Sprint v7.1 | All 19 tickers shown even when API returns 0 rows (placeholder rows). |
| Settings — QuantData Credentials | ✅ Live | Sprint v7.1 | Update `auth_token` + `cookie` from the Settings tab. No SSH required. |
| QuantData API calls | ✅ Fixed | Sprint v7.1 | `chart.py` now uses widget-UUID REST endpoints. Deprecated `tool/OPTIONS_*` calls removed. |
| IV Rank Heatmap | ✅ Live | — | Requires valid QuantData credentials. Shows "no data" when expired. |
| IV Crush workflow | ✅ Live | — | `workflow_05_iv_crush_report.py`. Requires valid QuantData session. |
| Trade Reports tab | ✅ Live | Phase 8 | Evaluation reports for new trades, rolls, buys, sells. |
| Journal auto-populate | ✅ Live | Phase 5/6 | Auto-populates from IBKR sync. |
| IBKR auto-sync | ✅ Live | Phase 5/6 | Background task. 60-second polling. |
| Pre-trade matrix | ✅ Live | Phase 5/6 | Batch stop-loss/roll tables. |
| Settings tab | ✅ Live | v1.8.2 | Five sections: Security, Strategy, Alerts, Technical, UI. |
| Security toggles | ✅ Live | v1.8.2 | `use_ibkr_web_api` and `use_quantdata` with amber banners. |

---

## Known Issues

| ID | Severity | Component | Description | Status |
|---|---|---|---|---|
| K-01 | Medium | QuantData session | `auth_token` and `cookie` expire periodically (days to weeks). When expired, IV Rank Heatmap, Candidates, and chart DP/GEX overlays show no data. | **Mitigated** — Settings → QuantData Credentials UI allows refresh without SSH. |
| K-02 | Low | IV Crush workflow | Workflow skips tickers where QuantData returns no data (expired session). Generates empty `rows: []`. | **Mitigated** — Candidates All-tab now shows placeholder rows when API returns 0 rows. |
| K-03 | Low | CP Gateway | Session expires every ~24h. ibeam re-authenticates automatically; requires IBKR Mobile push approval. | **By design** — future OAuth 2.0 migration would eliminate this. |
| K-04 | Low | Market Intel current_price | `current_price` is null outside market hours (yfinance). | **Fixed** — null guard added in Sprint v7.1. Shows `—` instead of crashing. |

---

## Resolved Items (Sprint v7.x)

| ID | Item | Resolution |
|---|---|---|
| O-01 | Candidates All-tab showed empty state when API returned 0 rows | Fixed — frontend fallback shows all 19 universe tickers as monitoring rows |
| O-02 | QuantData credential refresh required SSH access | Fixed — Settings → QuantData Credentials UI writes to both config files |
| O-03 | `chart.py` used deprecated `tool/OPTIONS_*` QuantData endpoints (400 errors, account revocation risk) | Fixed — replaced with widget-UUID REST endpoints matching `market_intelligence.py` pattern |
| O-04 | Market Intel page crashed with `TypeError: Cannot read properties of null (reading 'toFixed')` | Fixed — null guard on `current_price` |
| O-05 | Market Intel had no sort, no per-card refresh, no metric explanations | Fixed — sort dropdown, per-card refresh button, and hover tooltips added |

---

## Pending / Pipeline

| ID | Priority | Item |
|---|---|---|
| P-01 | High | QuantData OAuth 2.0 — eliminate manual credential refresh entirely |
| P-02 | Medium | Automated IV Crush workflow schedule (cron) — currently manual trigger only |
| P-03 | Medium | IBKR OAuth 2.0 — eliminate CP Gateway daily push approval |
| P-04 | Low | Strategy Workspace — scenario planning UI |
| P-05 | Low | Vol analytics panel — IV term structure, skew chart |

---

## Version History

| Date | Version | Summary |
|---|---|---|
| 2026-05-18 | Sprint v7.1 | Market Intel tooltips/refresh/sort. Candidates fallback. QuantData credentials UI. chart.py fix. |
| 2026-05-17 | Sprint v7.0 | Candidates All-tab redesign: actionable at top, monitoring below divider. |
| 2026-05-15 | Sprint v6.x | Market Intel null crash fix. IV Crush workflow debugging. |
| 2026-05-13 | Phase 8 | Trade Reports tab. UX improvements A-M. |
| 2026-05-09 | v1.8.2 | Security section in Settings. `use_ibkr_web_api` / `use_quantdata` toggles. |
| 2026-05-05 | v1.8 | MCP server (29 tools). Bearer token. CP Gateway primary. |

---

## V4 Dashboard (Port 8081) — Sprint Progress

**Snapshot:** May 26, 2026 | **V4 Backend:** FastAPI + SQLAlchemy + MySQL | **V4 Frontend:** React + Vite

### Completed Sprints

| Sprint | Feature | Status | Key Files |
|---|---|---|---|
| Pre-coding | MySQL connector, env vars, APScheduler pkg in V4 venv | ✅ Done | `/etc/systemd/system/fortress-dashboard-v4.service` |
| **v8.3** | APScheduler — 8 auto workflows (briefing, sync, backup, reports) | ✅ Done | `app/scheduler/runner.py`, `app/routes/scheduler.py` |
| **v8.4** | Config backup/restore + auto-backup on every write (K-02) | ✅ Done | `app/routes/config_store.py` |
| **v8.5** | Portfolio endpoints — beta, sector-exposure, capital-efficiency | ✅ Done | `app/routes/portfolio.py` |
| **v8.6** | OPRA symbol padding — 21-char normalisation on all option legs (K-01) | ✅ Done | `app/services/opra.py`, `ibkr_sync_web.py`, `state.py` |
| **v8.7** | MySQL data layer — positions + greeks write on sync; MySQL-first read | ✅ Done | `app/services/db_v4.py`, `app/services/models_v4.py`, `app/routes/positions.py` |
| **v8.8** | Journal close linkage — `POST /api/journal/close/{id}` links close→open (K-04) | ✅ Done | `app/routes/journal.py` |

### Remaining Sprints

| Sprint | Feature | Est. |
|---|---|---|
| **v8.9** | IBKR upload retry — Redis-backed `POST /api/ibkr/upload/retry` (K-03) | ~45 min |
| **v8.10** | Forward P&L panel — wire `GET /api/options/forward-pnl` to PositionsPage UI | ~1.5 hr |
| **v8.11** | Regime label formatting — replace `SNAKE_CASE` with human-readable labels | ~30 min |

### V4 Known Issues (current)

| ID | Description | Status |
|---|---|---|
| K-01 | OPRA 21-char symbol padding | ✅ Fixed — Sprint v8.6 |
| K-02 | Config backup/restore missing | ✅ Fixed — Sprint v8.4 |
| K-03 | IBKR upload retry missing | ⏳ Sprint v8.9 |
| K-04 | Journal close_id linkage | ✅ Fixed — Sprint v8.8 |

### CI/CD

| Component | Status |
|---|---|
| GitHub Actions — `fortress-v4-api` | ✅ Live — push to `main` auto-deploys via SSH + `git pull` + service restart |
| GitHub Actions — `fortress-v4-frontend` | ⏳ Not yet wired |

