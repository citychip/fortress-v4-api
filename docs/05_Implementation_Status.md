# Fortress Dashboard — Implementation Status

**Snapshot:** May 19, 2026 | **Strategy:** v3.7 | **Dashboard:** Fortress V3 (React/tRPC) | **Build Spec:** v2.0

---

## Live Components

| Component | Status | Version | Notes |
|---|---|---|---|
| **Fortress V3 Frontend** | ✅ Live | React 19 + Tailwind 4 + tRPC 11 | Served on port 3000 via nginx. Source: `/home/ubuntu/fortress-v2/`. Web root: `/var/www/fortress-v2/`. |
| **Python Backend (FastAPI)** | ✅ Live | v1.9.x | `fortress-dashboard.service` on port 8080. |
| Bearer token auth | ✅ Live | — | All `/api/*` endpoints require `Authorization: Bearer <token>`. |
| CP Gateway (voyz/ibeam) | ✅ Live | latest | Docker container. IBKR Web API primary broker path. |
| IBKR Greeks | ✅ Live | Web API | Δ/Γ/Θ/V live when OPRA subscribed. BS fallback when session expires. |
| MCP server | ✅ Live | v1.2 | 29 tools. Installed in Claude Desktop. Repo: `citychip/fortress-mcp`. |
| Market Intelligence endpoint | ✅ Live | — | `/api/market-intelligence` — GEX, DP floors, Net Drift, regime score. `curl_cffi` Cloudflare bypass. |
| Market Intelligence UI | ✅ Live | Sprint v7.1 | Sort dropdown (Score/Bias/Alpha), per-card refresh, metric tooltips. |
| Candidates All-tab | ✅ Live | Sprint v7.0 | Full 19-ticker universe. Actionable at top; monitoring below divider. |
| Candidates fallback | ✅ Live | Sprint v7.1 | All 19 tickers shown even when API returns 0 rows (placeholder rows). |
| Settings — QuantData Login | ✅ Live | Sprint v7.2 | Email + password login in Settings tab. Calls `/api/settings/quantdata_login_refresh`. Returns SPY IV Rank as live proof. No DevTools required. |
| QuantData auto-refresh (cron) | ✅ Live | Sprint v7.2 | `qd_refresh_session.py` runs daily at 06:00 UTC. Logs to `/var/log/qd_refresh.log`. |
| QuantData API calls | ✅ Fixed | Sprint v7.1 | `market_intelligence.py` uses `curl_cffi` with Chrome impersonation. `chart.py` uses widget-UUID REST endpoints. |
| IV Rank Heatmap | ✅ Live | — | Requires valid QuantData credentials. Shows "no data" when expired. |
| IV Crush workflow | ✅ Live | — | `workflow_05_iv_crush_report.py`. Requires valid QuantData session. |
| Trade Reports tab | ✅ Live | Phase 8 | Evaluation reports for new trades, rolls, buys, sells. |
| Journal auto-populate | ✅ Live | Phase 5/6 | Auto-populates from IBKR sync. |
| IBKR auto-sync | ✅ Live | Phase 5/6 | Background task. 60-second polling. |
| Pre-trade matrix | ✅ Live | Phase 5/6 | Batch stop-loss/roll tables. |
| Settings tab | ✅ Live | v1.8.2+ | Sections: General, API Connection, Connection Health, QuantData Credentials, Ticker Universe, Data Refresh, Server Settings, Backup & Restore, Security. |
| Security toggles | ✅ Live | v1.8.2 | `use_ibkr_web_api` and `use_quantdata` with amber banners. |

---

## Known Issues

| ID | Severity | Component | Description | Status |
|---|---|---|---|---|
| K-01 | ~~Medium~~ | ~~QuantData session~~ | ~~`auth_token` and `cookie` expire periodically. IV Rank, Candidates, and chart overlays show no data.~~ | **Resolved** — Daily cron auto-refresh at 06:00 UTC. Manual refresh via Settings email/password login. No DevTools required. |
| K-02 | Low | IV Crush workflow | Workflow skips tickers where QuantData returns no data. Generates empty `rows: []`. | **Mitigated** — Candidates All-tab shows placeholder rows when API returns 0 rows. |
| K-03 | Low | CP Gateway | Session expires every ~24h. ibeam re-authenticates automatically; requires IBKR Mobile push approval. | **By design** — future OAuth 2.0 migration would eliminate this. |
| K-04 | Low | Market Intel current_price | `current_price` is null outside market hours (yfinance). | **Fixed** — null guard added in Sprint v7.1. Shows `—` instead of crashing. |
| K-05 | Low | Market Intel GEX/DP/drift | GEX, dark pool, and net drift fields are null in market-intelligence response. QuantData widget endpoints return 401 despite valid JWT. Root cause: widget endpoints require a live browser session cookie in addition to the JWT. | **Under investigation** — IV Rank (tool endpoint) works. Widget endpoints use a different auth path. |

---

## Resolved Items

| ID | Item | Resolution |
|---|---|---|
| O-01 | Candidates All-tab showed empty state when API returned 0 rows | Fixed — frontend fallback shows all 19 universe tickers as monitoring rows |
| O-02 | QuantData credential refresh required SSH + DevTools | Fixed — Settings email/password login + daily cron auto-refresh |
| O-03 | `chart.py` used deprecated `tool/OPTIONS_*` QuantData endpoints (400 errors) | Fixed — replaced with widget-UUID REST endpoints |
| O-04 | Market Intel page crashed with `TypeError: Cannot read properties of null` | Fixed — null guard on `current_price` |
| O-05 | Market Intel had no sort, no per-card refresh, no metric explanations | Fixed — sort dropdown, per-card refresh button, and hover tooltips added |
| O-06 | `market_intelligence.py` used plain `requests` — blocked by Cloudflare (HTTP 401) | Fixed — patched to use `curl_cffi` with Chrome impersonation |
| O-07 | React build deployed to wrong path (`app/static/`) | Fixed — correct path is `/var/www/fortress-v2/` (nginx web root) |

---

## Pending / Pipeline

| ID | Priority | Item |
|---|---|---|
| P-01 | Medium | Resolve QuantData widget endpoint 401 — GEX/DP/drift fields in market-intelligence. Investigate whether widget endpoints require a separate browser session cookie vs JWT. |
| P-02 | Medium | Automated IV Crush workflow schedule (cron) — currently manual trigger only |
| P-03 | Medium | IBKR OAuth 2.0 — eliminate CP Gateway daily push approval |
| P-04 | Low | Strategy Workspace — scenario planning UI |
| P-05 | Low | Vol analytics panel — IV term structure, skew chart |

---

## Version History

| Date | Version | Summary |
|---|---|---|
| 2026-05-19 | Sprint v7.2 | QuantData email/password login in Settings. Daily cron auto-refresh. `curl_cffi` patch for market_intelligence.py. Correct React deploy path confirmed (`/var/www/fortress-v2/`). K-01 resolved. |
| 2026-05-18 | Sprint v7.1 | Market Intel tooltips/refresh/sort. Candidates fallback. QuantData credentials UI. chart.py fix. |
| 2026-05-17 | Sprint v7.0 | Candidates All-tab redesign: actionable at top, monitoring below divider. |
| 2026-05-15 | Sprint v6.x | Market Intel null crash fix. IV Crush workflow debugging. |
| 2026-05-13 | Phase 8 | Trade Reports tab. UX improvements A-M. |
| 2026-05-09 | v1.8.2 | Security section in Settings. `use_ibkr_web_api` / `use_quantdata` toggles. |
| 2026-05-05 | v1.8 | MCP server (29 tools). Bearer token. CP Gateway primary. |
