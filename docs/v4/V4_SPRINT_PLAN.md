# Fortress V4 — Sprint Plan
## From v8.15 Onward

**Prepared:** 2026-05-26
**Updated:** 2026-05-27 (post Sprint v8.24; added v8.26 sprint)
**Baseline:** Sprints v8.3–v8.14 complete (Groups A + B + most of C + partial D + E-01 + E-02)
**Current status:** v8.24 complete. Next: v8.23 (infra hardening) or v8.25 (Docker dev env).

---

## Completed Sprints

### ✅ Sprint v8.16 — Earnings Volatility + MCP Tier 1.5 (~2.5 hr)

| ID | Task | Status |
|---|---|---|
| C-04 | `GET /api/market/earnings-volatility/{ticker}` | ✅ Done |
| C-05 | Audit `get_capability` — add new endpoints | ✅ Done |
| G-01 | `get_portfolio_beta` MCP tool | ✅ Done |
| G-02 | `get_sector_exposure` MCP tool | ✅ Done |
| G-03 | `get_capital_efficiency` MCP tool | ✅ Done |
| G-04 | `get_earnings_volatility` MCP tool | ✅ Done |

---

### ✅ Sprint v8.17 — Portfolio + Earnings Widgets (~2.5 hr)

| ID | Task | Status |
|---|---|---|
| E-05 | BetaWeightedDeltaCard on Positions page | ✅ Done |
| E-06 | SectorExposureBar on Positions page | ✅ Done |
| E-07 | CapitalEfficiencyTable on Config / Strategy tab | ✅ Done |
| E-08 | EarningsVolatilityCompare on Candidates rows | ✅ Done |

---

### ✅ Sprint v8.18 — Dashboard Widgets + PCS Exposure (~2 hr)

| ID | Task | Status |
|---|---|---|
| C-06 | `GET /api/portfolio/pcs-exposure` backend | ✅ Done |
| E-03 | PCS Exposure badge on Dashboard KPI strip | ✅ Done |
| E-04 | Weekly pacing chart on Dashboard | ✅ Done |

---

### ✅ Sprint v8.19 — Pre-Trade Strategy Gates (~2 hr)

| ID | Task | Status |
|---|---|---|
| F-01 | PCS count cap gate (max 5) | ✅ Done |
| F-02 | Put notional cap gate (max $25K) | ✅ Done |
| F-03 | LEAP entry blackout 14d before earnings | ✅ Done |
| F-04 | Weekly pacing gate (advisory) | ✅ Done |
| F-05 | DTE exception registry | ✅ Done |

Gates added to both `pre_trade_check` and `pretrade_all`. Response now includes
`gates{}`, `hard_failures[]`, `advisories[]`, `acknowledgment_required`, `dte_exception_active`.

---

### ✅ Sprint v8.20 — HTTPS + Candidate UX (~1.5 hr)

| ID | Task | Status |
|---|---|---|
| E-12 | NOT READY failure reason chip on Candidates | ✅ Done |
| H-01 | Let's Encrypt HTTPS on nginx | ✅ Done — cert expires 2026-08-25 |
| H-02 | Update MCP FORTRESS_API_URL to https:// | ✅ Done — commit 9efa111 |

---

### ✅ Sprint v8.21 — MySQL Migrations (~2.5 hr)

| ID | Task | Status |
|---|---|---|
| D-03 | Config JSON → MySQL dual-write | ✅ Done — 115 rows; seeds on startup |
| D-07 | Journal JSON → MySQL migration | ✅ Done — MySQL-first reads, dual-write |
| D-06 | EOD snapshot writer + `/api/pnl/history` | ✅ Done — scheduler fires 16:10 ET Mon-Fri |

---

### ✅ Sprint v8.22 — Performance Page Widgets (~2 hr)

| ID | Task | Status |
|---|---|---|
| E-09 | Closed-loop P&L accordion on Journal tab | ✅ Done — pairs OPEN/CLOSE via FK; IV crush, DTE@close, days held |
| E-10 | Equity curve chart on P&L tab | ✅ Done — 90-day net-liq LineChart from portfolio_snapshots |

---

## Upcoming Sprints

### Sprint v8.23 — Infra Hardening (~3 hr)

**Goal:** Eliminate last two manual pain points: frontend CI and MySQL backup.

| ID | Task | Acceptance |
|---|---|---|
| H-04b | GitHub Actions CI for frontend auto-deploy | Push to main triggers pnpm build + rsync to /var/www/fortress-v4/ on VPS |
| H-05 | MySQL 8 daily backup cron on VPS | `mysqldump` to `/backups/mysql/` nightly; alert on failure; 7-day rotation |
| H-06 | Rollback procedure documented | V4 → V3 rollback steps tested; time-to-rollback < 10 min |

**Acceptance for sprint:** Frontend deploy is automatic on git push. `ls /backups/mysql/` shows at least one dump file.

---

### ✅ Sprint v8.24 — MCP Audit + Expansion (~2 hr)

**Goal:** Verify all live tools work against V4 endpoints; expand prompt library.

| ID | Task | Status |
|---|---|---|
| G-05 | Audit all MCP tools against V4 endpoints; fix broken tools | ✅ Done — 5 fixed, 3 new tools added, 64 total |
| G-06 | Expand tool count to 61+ | ✅ Done — 64 tools (46 read + 6 QD + 9 write + 3 order) |
| G-07 | Prompt library updated for V4 tool names | ✅ Done — server instructions updated to v4.0.0 |
| G-08 | MCP server version string to 4.0.0 | ✅ Done — FORTRESS_MCP_VERSION = "4.0.0"; GitHub repo initialized |

**Tools fixed:** get_ibkr_status (→ /api/ibkr/capability), pretrade_check (→ /api/manage/pre_trade_check),
get_position_limits + get_forward_pnl (legs-fetch pattern; iv_adj param).
**New tools:** get_pcs_exposure, get_pnl_history, get_version.
**Repo:** citychip/fortress-mcp initialized and pushed (commits 600284e + 38f7e73).

---

### Sprint v8.25 — Dev Environment (~2 hr)

| ID | Task | Acceptance |
|---|---|---|
| H-03 | Docker Compose for local dev | `docker compose up` starts API + frontend + MySQL + Redis + ibeam |

---


---

### Sprint v8.26 — Performance + Proactive Intelligence (~3.5 hr)

**Goal:** Bundle code splitting, proactive pacing alert, QuantData event auto-surfacing.

| ID | Task | Acceptance |
|---|---|---|
| H-07 | Frontend bundle code splitting | Vite chunk-size warning gone; initial JS ≤500 KB; no functional regression |
| E-13 | Proactive pacing "at-risk" signal on Dashboard | Dashboard shows amber/red banner when open positions near roll/exit window will likely consume remaining weekly capacity |
| A-09 | QuantData auto-surfacing of high-signal events | Premarket scheduler scans universe tickers for unusual OI change / order flow; events injected into morning brief response and surfaced on Dashboard alert strip |

**Acceptance for sprint:** Build produces no chunk-size warnings. Dashboard shows pacing-at-risk signal without manual MCP call. Morning brief includes QuantData signal summary when any universe ticker has unusual activity.

## Documentation (parallel)

| ID | Task | Target sprint |
|---|---|---|
| I-01 | V4_05_MCP_Spec.md — all tools documented | v8.24 |
| I-02 | V4_08_Developer_Guide.md — Docker setup | v8.25 |
| I-03 | fortress-api README updated for V4 | v8.23 |
| I-04 | V4_09_Operations_Notes.md committed to repo | v8.23 |

---

## Effort Summary

| Sprint | Goal | Est. Hours |
|---|---|---|
| v8.23 | Infra hardening (H-04b, H-05, H-06) | ~3 hr |
| ~~v8.24~~ | ~~MCP audit + prompt library~~ | ✅ Done |
| v8.25 | Docker Compose local dev (H-03) | ~2 hr |
| v8.26 | Bundle split + pacing alert + QD auto-surfacing | ~3.5 hr |
| Docs | I-01 through I-05 | ~3 hr |

**Total to full V4 production: ~12 hours remaining.**

---

## Completed Work Summary (v8.15–v8.22)

| Sprint | Primary Delivery |
|---|---|
| v8.16 | Earnings volatility endpoint + 4 MCP Tier 1.5 tools |
| v8.17 | Beta, sector, capital efficiency + earnings volatility widgets |
| v8.18 | PCS exposure backend + Dashboard pacing/exposure widgets |
| v8.19 | 5 pre-trade strategy enforcement gates |
| v8.20 | HTTPS/TLS + NOT READY reason chips on Candidates |
| v8.21 | Full MySQL migration: config + journal + EOD snapshot writer |
| v8.22 | Performance page: closed-loop P&L accordion + equity curve |
| v8.24 | MCP audit: 5 tools fixed, 3 new tools, 64 total, version 4.0.0 |

---

*V4_SPRINT_PLAN.md — living document. Update as sprints complete.*
