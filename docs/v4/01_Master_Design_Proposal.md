# Fortress V4 — Master Design Proposal

**Version:** 1.0  
**Date:** 2026-05-23  
**Status:** Proposal — Pre-implementation  
**Relationship to V3:** V3 documentation is preserved in `docs/` and remains the operational reference until V4 is deployed.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [What Investment2026 Added](#2-what-investment2026-added)
3. [Current State Assessment](#3-current-state-assessment)
4. [Design Goals](#4-design-goals)
5. [Phase Structure — The Golden Rule](#5-phase-structure--the-golden-rule)
6. [Phase 0 — Architecture Sign-Off](#6-phase-0--architecture-sign-off)
7. [Phase 1 — Design System](#7-phase-1--design-system)
8. [Phase 2 — Documentation](#8-phase-2--documentation)
9. [Phase 3 — Front-End](#9-phase-3--front-end)
10. [Phase 4 — Backend Coding](#10-phase-4--backend-coding)
11. [Phase 5 — MCP & Tooling](#11-phase-5--mcp--tooling)
12. [Phase 6 — Infrastructure](#12-phase-6--infrastructure)
13. [Migration Strategy](#13-migration-strategy)
14. [What Does Not Change](#14-what-does-not-change)
15. [Risk Register](#15-risk-register)
16. [Start Sequence & Timeline](#16-start-sequence--timeline)

---

## 1. Executive Summary

Fortress V4 is the full modular rebuild of the live options trading system comprising three GitHub repos — `fortress-api` (FastAPI/Python), `fortress-app` (React 19/tRPC), `fortress-mcp` (61 MCP tools) — running in production on a VPS.

The system works and is used daily. The V4 rebuild targets five architectural seams that will prevent the system from scaling:

| Seam | Symptom | V4 Fix |
|---|---|---|
| JSON files as state | No audit trail, no replay, no concurrent writes | MySQL 8 for all persistent state |
| Polling as transport | Render storms, stale data, race conditions | Redis pub/sub → SSE stream → reactive UI |
| Monolithic `state.py` | Every script imports directly; untestable | Four independent Python engines with ABC interfaces |
| No strategy-level analytics | Missing beta-weighting, sector exposure, capital efficiency | Four new Tier 1.5 API endpoints + dashboard widgets |
| Manual systemd ops | Fragile, dev/prod parity missing | Docker Compose dev, documented systemd prod |

**The governing constraint:** Architecture, design, documentation, and front-end are all separate phases from coding. Nothing in the production backend is touched until Phase 0 is signed off. No front-end component code is written until Phase 1 is complete.

---

## 2. What Investment2026 Added

Analysis of `C:\Users\cityc.000\OneDrive\_Stocks26\Investment2026` revealed content not captured in earlier analysis. These additions are fully incorporated into this proposal.

### 2.1 Four Tier 1.5 API Endpoints (from `08_Fortress_MCP_Proposal_v2.md`)

These were formally approved in Strategy v3.6 but absent from the V3 architecture. They are now first-class features in V4.

| Endpoint | MCP Tool | Purpose |
|---|---|---|
| `GET /api/manage/portfolio_beta` | `get_portfolio_beta_risk` | Beta-weighted delta vs SPY; hedge gap calculation |
| `GET /api/manage/sector_exposure` | `get_sector_exposure` | Net MV by GICS sector; flags >80% concentration |
| `GET /api/manage/capital_efficiency` | `get_capital_efficiency` | BP utilisation; annualised ROC per position |
| `GET /api/manage/earnings_volatility/{ticker}` | `get_earnings_volatility_data` | Implied move vs last 4 earnings actual moves; ratio |

### 2.2 Strategy-Level Risk Controls (from `01_Portfolio_Strategy_v3_6.md`)

| Control | Rule | Current State | V4 Action |
|---|---|---|---|
| PCS count cap | Max 5 concurrent PCS | Not tracked | Add `pcs_count` stat to Dashboard |
| Put-side notional | Max €25K (~30% NetLiq) | Not tracked | Add `put_notional_pct` to Dashboard |
| Weekly pacing | Max 2 new positions/week | Manual / memory | Add 8-week pacing chart to Briefing tab |
| LEAP entry blackout | 14 days before earnings | Only 10-day PCS blackout gated | Add separate LEAP gate (`leap_entry_blackout_days: 14`) |
| DTE exception registry | Known deliberate DTE exceptions (MSFT Dec'26 $480, VST Sep'26 $200) | No registry; roll evaluator flags these perpetually | `config.dte_exceptions[]` suppresses false roll alerts |

### 2.3 Engineering Fixes (from `0511/recommendations.md`)

| Fix | Description |
|---|---|
| OPRA capability test | Filter to `sec_type == "OPT"` legs only; stock legs cause false `opra_subscribed: false` |
| Config backup | Apply same `write_json` + timestamped-backup pattern to `config_store.save()` |
| Snapshot retry | Replace fixed 1.5s sleep in `ibkr_web/snapshot.py` with retry-with-backoff (3× at 500ms) |

### 2.4 Source-of-Truth Hierarchy (from `01_Portfolio_Strategy_v3_6.md §2.5`)

This formalises which data source governs each decision domain and must be reflected in the V4 architecture documentation.

| Domain | Authoritative Source |
|---|---|
| Position state, P&L, Greeks, margin | IBKR (live) |
| Technical analysis (price, MAs, support/resistance) | TradingView charts |
| Options market structure (IV/IVR, GEX, dark pool, OI walls) | QuantData |
| Live option chain (bid/ask, specific strikes) | IBKR option chain |
| Earnings dates | `earnings_blocklist.json` (manually maintained, cross-checked) |
| Active book composition | `active_positions.json` (synced from IBKR) |
| Decision rules | Portfolio Strategy v3.7 (this document always wins) |

### 2.5 Journal Closed-Loop P&L (from `0511/recommendations.md`)

Journal entries need a `close_id` foreign key linking close entries to their open entries, enabling the system to compute:
- P&L vs thesis
- IV crush realised vs expected
- DTE at close vs target
- Hold time per strategy type

This turns the Journal from a log into actual performance attribution. The V4 database schema adds this.

### 2.6 Prompt Library (from `09_MCP_Workflow_and_Prompts_v2.md`)

A 19-prompt daily workflow library covering every phase from morning startup through EOD signal. This is incorporated into `V4_05_MCP_Spec.md` and should ship with `fortress-mcp` as `examples/prompts/README.md`.

---

## 3. Current State Assessment

### What Is Running in Production

| Component | Status | Port | Notes |
|---|---|---|---|
| `fortress-api` (FastAPI) | ✅ Live | 8080 | 20 route files, JSON state, APScheduler |
| `fortress-app` (React 19 + tRPC) | ✅ Live | 3000 (nginx) | 8-page dashboard, Tailwind 4 |
| `fortress-mcp` (29 tools, V3) | ✅ Live | stdio | 20 Tier 1 read, 9 Tier 2 write (opt-in) — V4 target is 61 tools |
| IBKR CP Gateway (voyz/ibeam) | ✅ Live | 5000 | Docker |
| Master Orchestrator (APScheduler) | ✅ Live | — | 8 workflows, cron-scheduled |
| Hermes Agent | ✅ Running | — | Python agent + WebUI |

### Architecture Debt

| Problem | Root Cause | Impact |
|---|---|---|
| JSON files as state | `active_positions.json`, `alerts.json`, `journal.json`, `fortress_config.json` | No audit trail; manual restore risk; concurrent write race |
| Polling everywhere | 250ms–5min `setInterval` per component | Render storms; stale data on briefing page |
| `state.py` coupling | Every script and route imports directly | Cannot unit-test business logic; cascading failures |
| No Tier 1.5 endpoints | Portfolio_beta, sector_exposure, capital_efficiency, earnings_volatility not built | Key strategy controls invisible to Claude and dashboard |
| No HTTPS | HTTP on port 3000 | MCP connections not encrypted; no browser security headers |
| Secrets management | Bearer token managed via systemd env file | Requires SSH to rotate; no audit on changes |

---

## 4. Design Goals

| Goal | Why | How |
|---|---|---|
| Single source of truth | JSON files → no replay, no audit | MySQL for persistent state, Redis for cache |
| State-driven UI | Per-component polling → render storms | Central SSE stream → reactive context |
| Modular engines | `state.py` called by everything → fragile | Four independent Python packages, ABC interfaces |
| Strategy-complete analytics | Tier 1.5 gaps → blind spots in Claude sessions | Four new endpoints + dashboard widgets |
| Extensible | New strategies, brokers currently require code changes | Plugin registry pattern, versioned schemas |
| Security-first | HTTP only, bearer token in env | HTTPS mandatory, token rotation UI, audit log |
| Zero-downtime migration | React 19 + tRPC + 29 MCP tools in daily use (V3) | Backward-compatible API surface throughout |

---

## 5. Phase Structure — The Golden Rule

> **Architecture, design, documentation, and front-end are all separate phases from coding. Phases 0–2 produce no production code. Phase 3 produces front-end code against a mock API only. Phase 4 is the first time the Python backend is touched.**

```
Phase 0 — Architecture          →  Five ADRs, signed-off schema, API surface
Phase 1 — Design System         →  Token file, component catalogue, responsive grid spec
Phase 2 — Documentation         →  Updated doc suite, deprecated docs marked, new guides drafted
Phase 3 — Front-End             →  All 8 pages connected to mock API; SSE mock server
Phase 4 — Backend Coding        →  Four engines, MySQL, Redis, SSE, Tier 1.5 endpoints, tests
Phase 5 — MCP & Tooling         →  29 V3 tools audited, expanded to 61 tools (47 Tier 1 + 10 Tier 2 + 4 Tier 1.5), prompt library published
Phase 6 — Infrastructure        →  Docker Compose, HTTPS, CI/CD, live deploy
```

**Parallel work:** Phases 0, 1, and 2 can run concurrently. Phase 3 requires Phase 1 exit. Phase 4 requires Phase 0 exit. Phases 5 and 6 require Phase 4 exit.

---

## 6. Phase 0 — Architecture Sign-Off

**Goal:** Produce written, signed-off architecture decisions before any code is touched.  
**Entry gate:** None.  
**Exit deliverable:** Five ADRs + annotated database schema.

### Decisions Already Settled

The V4 architecture document (`V4_02_Architecture.md`) details the settled decisions. Summary:
- Four engines: Position, Market, Alert, Execution
- MySQL 8 for persistent state; Redis 7 for cache + pub/sub
- SQLAlchemy async + Alembic migrations
- APScheduler retained (not Celery — too heavy for single-trader VPS)
- All JSON files migrate to MySQL (one-time script)
- tRPC 11 stays on the front-end BFF
- Docker Compose for dev; systemd retained for production VPS

### Five ADRs Required

**ADR-01 — IBKR Data Path**  
`voyz/ibeam` REST (stable, current) vs `voyz/ibind` WebSocket (real-time, experimental).  
*Recommendation:* ibeam REST as primary. ibind WebSocket deferred to Phase 4+ as optional upgrade. Do not block Phase 4 on WebSocket.

**ADR-02 — QuantData Session Management**  
Manual credential refresh (current) vs Telegram-prompt + graceful fallback vs OAuth 2.0 (backlog P-01).  
*Recommendation:* Telegram-prompt + fallback in Phase 4. OAuth 2.0 deferred (requires QuantData to support it). Minimum viable fix eliminating the data blackout problem.

**ADR-03 — Event Sourcing Scope**  
Full event replay (event sourcing) vs current-state + audit log.  
*Recommendation:* Current-state + audit log is sufficient. Full event sourcing adds replay infrastructure not needed for single-trader system. Document as deferred.

**ADR-04 — JSON Migration Strategy**  
One-time migration script vs incremental dual-write period.  
*Recommendation:* One-time migration script with dry-run mode. ~19 live positions; risk is low. Dual-write adds complexity with no benefit at this scale.

**ADR-05 — Test Coverage Strategy**  
Full TDD vs integration tests only vs end-to-end only.  
*Recommendation:* Unit tests on engine business logic (strategy rules, PnL, alert evaluation) + integration tests for API routes. No browser end-to-end tests in V4. Target ≥80% coverage on engine packages.

### Database Schema Additions vs V3 Architecture Doc

The V3 architecture schema is sound. Three additions from Investment2026 analysis:

1. **`journal` table:** Add `close_id UUID NULL FK → journal(id)` to link close entries to their open entries for closed-loop P&L tracking.

2. **`config` table:** Add a documented `dte_exceptions` config key (JSON array of `{ticker, strike, expiry}` objects) to suppress false roll alerts on known deliberate DTE exceptions.

3. **`pcs_exposure` view (computed):** A MySQL view — not a table — that computes `{pcs_count, put_notional_usd}` from `positions` + `position_legs` WHERE `strategy = 'PCS'` AND `state = 'open'`. Used by the Position Engine to gate new PCS entries.

---

## 7. Phase 1 — Design System

**Goal:** Define the complete visual language before any front-end component code is written.  
**Entry gate:** Phase 0 ADRs complete (data shapes must be known before designing components).  
**Exit deliverable:** Token file, component catalogue with all states, responsive grid spec.

See `V4_03_Design_System.md` for the full specification. Summary:

### Visual Direction: Obsidian Edge

Selected from the three concepts documented in `Investment2026/Docs2/fortress_docs/ideas.md`. Dark background with layered surfaces, cyan interactive accent, amber/red/emerald severity hierarchy, JetBrains Mono for all financial data.

### Token Summary

| Category | Key Decisions |
|---|---|
| Background | `oklch(0.12 0.008 260)` — deep blue-black |
| Surfaces | Three levels (L1/L2/L3) for depth without heaviness |
| Accent | Cyan `oklch(0.80 0.15 200)` — interactive, active, focused |
| Severity | Amber (WARN) · Red (ACT/CRITICAL) · Emerald (SAFE) |
| Numbers | JetBrains Mono, `tabular-nums`, right-aligned |
| Motion | 150ms fast / 200ms standard / 300ms emphasis |

### New Components Required for V4 (vs V3 proposal)

These components are needed for the new Tier 1.5 features:

- **`BetaWeightedDeltaCard`** — Portfolio beta-weighted delta vs SPY, hedge gap indicator
- **`SectorExposureBar`** — Stacked bar of net MV by GICS sector, amber at >80%
- **`CapitalEfficiencyTable`** — ROC per position sorted ascending, BP utilisation gauge
- **`EarningsVolatilityCompare`** — Implied move vs historical 4-bar comparison chart
- **`PCSExposureBadge`** — Count badge: `3/5 PCS · €18K/€25K put notional`
- **`PacingChart`** — 8-week bar chart showing entries/week vs 2/week target

---

## 8. Phase 2 — Documentation

**Goal:** Rewrite and reorganise the documentation suite to reflect V4 before any code is written.  
**Entry gate:** Phase 0 ADRs complete.  
**Exit deliverable:** Updated reference docs, deprecated docs marked, new guides drafted.

### Document Status Table

| Document | Location | V4 Action |
|---|---|---|
| `01_Portfolio_Strategy_v3.7.md` | reference/ | **PRESERVE** — all engine thresholds derive from this |
| `02_Trading_Dashboard_Build_Spec_v2.0.md` | reference/ | **DEPRECATE** — point to V4 Architecture doc |
| `03_Trading_Workflow_v2.9.md` | reference/ | **PRESERVE** — 8 workflows produce same outputs |
| `04_VPS_Implementation_Guide_v1.6.md` | reference/ | **DEPRECATE** — Docker Compose guide replaces §3–§6 |
| `05_Implementation_Status.md` | reference/ | **REPLACE** — new V4 implementation tracker |
| `07_MCP_Workflow_and_Prompts_v1.3.md` | reference/ | **PRESERVE** through Phase 4; **UPDATE in Phase 5** to v1.4 |
| `08_Market_Intelligence_Skill_v1.1.md` | reference/ | **PRESERVE** — Market Engine must expose same data |
| `operations/03_Quick_Start_and_Daily_Cheatsheet.md` | reference/ | **PRESERVE** |
| `operations/04_Incident_Recovery_Playbook.md` | reference/ | **UPDATE** — add V4 recovery (Docker restart, Redis flush, Alembic rollback) |
| `review/10_Strategy_Review_Template.md` | reference/ | **PRESERVE** |
| `review/11_Todo_Backlog.md` | reference/ | **REPLACE** — superseded by `V4_04_Phase_Backlog.md` |
| `FORTRESS_V3_—_Your_Options_Trading_Command_Centre.pdf` | fortress/ | **DISCARD** — superseded by V4 |
| All `Docs2/fortress_docs/` files | Investment2026 | **ARCHIVE** — superseded by V4 equivalents |
| All `MCP/` files | Investment2026 | **ARCHIVE** — superseded by V4 |

### New Documents to Create (Phase 2)

| Document | Purpose |
|---|---|
| `V4_02_Architecture.md` | Full technical architecture — four engines, schema, API surface, deployment |
| `V4_03_Design_System.md` | Token file, component catalogue, responsive grid |
| `V4_04_Phase_Backlog.md` | All open items organised by phase with priority |
| `V4_05_MCP_Spec.md` | Updated MCP tool list (57 + new tools), prompt library, tier definitions |
| `V4_06_Operations_Guide.md` | Day-to-day V4 ops: Docker Compose, engine logs, credential rotation, sync triggers |
| `V4_07_Migration_Guide.md` | Step-by-step JSON → MySQL migration with dry-run, verification, and rollback |
| `V4_08_Developer_Guide.md` | How to add an alert rule, a data provider, a new MCP tool |
| `V4_09_Operations_Notes.md` | Extracted from `todo.md` — SSH key, deploy target, nav lock, common mistakes |

### Critical: Ops Notes Formalisation

The `todo.md` file contains essential operational knowledge buried in a "PERMANENT OPS NOTES" section. These must become `V4_09_Operations_Notes.md` and be committed to the `fortress-app` repo before the end of Phase 2. Knowledge in a local file that is not in version control is knowledge at risk.

---

## 9. Phase 3 — Front-End

**Goal:** Build all 8 pages of the React application against a mock API, with zero backend dependency.  
**Entry gate:** Phase 1 (design system + component catalogue complete).  
**Exit deliverable:** All pages implemented, connected to mock fixtures, SSE mock server running.

### Mock-First Principle

All tRPC procedures and REST endpoints are mocked using static fixture data generated directly from the live `active_positions.json`, `alerts.json`, and `journal.json` files. This decouples front-end work entirely from backend progress.

### Page-by-Page Plan

#### Dashboard (`/`) — Morning Brief
Status from analysis: Mostly complete. V4 additions:
- Replace 250ms polling with `MarketStateContext` (SSE stream)
- **New:** `PCSExposureBadge` — live count and put notional vs cap (`3/5 PCS · €18K/€25K`)
- **New:** `PacingChart` — 8-week entries/week bar chart below Portfolio Greeks
- **New:** Portfolio delta/theta/vega bar chart (miniature)
- **New:** VIX 30-day sparkline on Macro Regime Gate
- Per-ticker price sparkline vs GEX levels on trade report rows

#### Positions (`/positions`)
Status: Mostly complete. V4 additions:
- **New:** `BetaWeightedDeltaCard` — portfolio beta-weighted delta vs SPY at top of page
- **New:** `SectorExposureBar` — sector breakdown across all open positions
- Max Profit / Max Loss / Breakeven badges per position card (Gap 1 from backlog)
- Forward PnL simulator panel per accordion (Gap 2 — mock in Phase 3, wire in Phase 4)

#### Trade (`/trade`) — Scan / Candidates / Orders
Status: Candidates All-tab complete. V4 additions:
- **New:** `EarningsVolatilityCompare` widget accessible from Candidates rows
- NOT READY reasons per ticker (specific failure reason, not generic badge)
- Regime label normalisation (`STRONGLY_BULLISH` → `Strongly Bullish`) across all callsites

#### Analysis (`/analysis`)
Status: Complete. No new pages required for V4. Vol Surface 3D (Phase 3 optional — design in Phase 1, implement if capacity allows).

#### Performance (`/performance`) — P&L / Journal
Status: P&L sparkline gap. V4 additions:
- P&L history chart wired to mock fixture (backend endpoint in Phase 4)
- **New:** Journal closed-loop P&L view — shows each open entry with its linked close, computed P&L vs thesis, actual DTE at close

#### Market Intelligence (`/market-intel`)
Status: Complete (Sprint v7.1). V4: SSE stream replaces per-card polling.

#### Earnings (`/earnings`)
Status: Working. No V4 changes.

#### Config (`/config`) — Strategy / Settings / Scripts
Status: Complete. V4 addition:
- Engine health status row (Position / Market / Alert / Execution) with status dots
- **New:** `CapitalEfficiencyTable` on Strategy tab — ROC per position, BP utilisation

### SSE Integration

The SSE stream replaces all briefing/positions/alerts polling. Pattern already implemented in Sprint v4.0. In Phase 3, simulate with a mock SSE server (`npm run mock-sse`) that emits fixture events on a timer. Six event types:
`market_update` · `alert` · `order_update` · `session_expired` · `sync_completed` · `heartbeat`

### Front-End Quality Gates (must pass before Phase 4 handoff)

- [ ] No `.toFixed()` without null guard — grep check must return zero hits
- [ ] No bare `fetch()` without Authorization header — grep check
- [ ] All severity colours verified against WCAG 2.1 AA (≥4.5:1 on `--color-surface-1`)
- [ ] `prefers-reduced-motion` respected on all animations
- [ ] All mock data shapes match the Phase 0 API surface spec exactly

---

## 10. Phase 4 — Backend Coding

**Goal:** Implement the four engines, migrate JSON state to MySQL, wire SSE, build Tier 1.5 endpoints.  
**Entry gate:** Phase 0 ADRs signed off + Phase 2 Migration Guide written.  
**Exit deliverable:** All engines live, JSON deprecated, all existing endpoints passing, Tier 1.5 endpoints live, SSE stream live.

### Build Order

1. **Database layer** — Alembic, all tables from schema (including `journal.close_id` addition), migration script
2. **Position Engine** — Core. Everything depends on portfolio state.
3. **Market Engine** — Quote + vol + exposure. Provider registry. Redis caching.
4. **Alert Engine** — Rules, event queue, Telegram notifier. Depends on Position + Market.
5. **Execution Engine** — Pre-trade gate, order state machine, IBKR submit. Build last.
6. **Tier 1.5 endpoints** — Portfolio_beta, sector_exposure, capital_efficiency, earnings_volatility (all four)
7. **API routes** — Wire all routes to engines. Backward-compatible surface preserved.
8. **SSE stream** — Redis pub/sub → SSE endpoint. Replace polling.
9. **Workflow migration** — Refactor 8 scripts from `state.py` to engine calls.

### Engineering Fixes (From Investment2026)

These are Phase 4 items, not a separate phase — they are small fixes that go in alongside the engine work:

- **OPRA test fix:** Filter capability test to `sec_type == "OPT"` legs only
- **Config backup:** Apply `write_json` + timestamped-backup to `config_store.save()`
- **Snapshot retry:** Replace 1.5s sleep in `ibkr_web/snapshot.py` with retry-with-backoff (3× at 500ms)

### Tier 1.5 Endpoint Specifications

**`GET /api/manage/portfolio_beta`**  
Returns: `{beta_weighted_delta, spy_equivalent_shares, hedge_gap, positions: [{ticker, beta, raw_delta, beta_weighted_delta}]}`  
Source: yfinance for beta values; position engine for raw delta.

**`GET /api/manage/sector_exposure`**  
Returns: `{sectors: [{sector, net_mv, pct_of_netliq, tickers}], dominant_sector, dominant_pct, flag_threshold: 80}`  
Source: yfinance `info.sector` for GICS classification.

**`GET /api/manage/capital_efficiency`**  
Returns: `{buying_power_used_pct, idle_capital_usd, positions: [{ticker, margin_used, premium_collected_30d, roc_annualised}]}`  
Source: IBKR margin data + position engine.

**`GET /api/manage/earnings_volatility/{ticker}`**  
Returns: `{ticker, implied_move_pct, historical_moves: [...], avg_historical_move_pct, implied_vs_historical_ratio, recommendation}`  
Source: yfinance earnings_dates for historical; IBKR/QuantData ATM straddle for implied.

### Strategy-Level Gates (New in V4)

Two new pre-trade gate checks, implemented in `app/engines/execution/pre_trade_gate.py`:

```python
# New check: LEAP entry blackout (14 days, separate from PCS 10-day)
def _check_leap_entry_blackout(self, order: Order) -> CheckResult:
    if order.strategy in ["PMCC", "LEAPS"]:
        blackout_days = self.cfg("strategy.leap_entry_blackout_days", 14)
        earnings_date = self.earnings_engine.get_next_earnings(order.ticker)
        days_to_earnings = (earnings_date - date.today()).days
        if days_to_earnings <= blackout_days:
            return CheckResult.fail(f"Earnings in {days_to_earnings}d — LEAP entry blocked (§4)")
    return CheckResult.pass_()

# New check: DTE exception registry suppresses false roll alerts
def _is_dte_exception(self, position: Position) -> bool:
    exceptions = self.cfg("strategy.dte_exceptions", [])
    return any(
        e["ticker"] == position.ticker
        and e["strike"] == position.short_strike
        and e["expiry"] == position.short_expiry
        for e in exceptions
    )
```

### The Migration Moment

High-risk, plan carefully:
1. Run `scripts/migrate_json_to_db.py --dry-run` → verify expected row counts
2. Full backup of all JSON files to `data/archive/`
3. Pause IBKR sync
4. Run migration
5. Compare `GET /api/briefing` + `GET /api/positions` against pre-migration snapshots
6. Resume IBKR sync
7. Monitor 5 trading days before deleting JSON files

### Test Coverage

- Engine unit tests: ≥80% coverage on all engine packages
- Every alert rule: test case with fixture position + fixture market state
- Tier 1.5 endpoints: integration tests with mocked IBKR/QuantData adapters
- Migration script: tested against a copy of production JSON in a test database

---

## 11. Phase 5 — MCP & Tooling

**Goal:** Audit and update the 29 V3 MCP tools, expand to 61 total tools (47 Tier 1 + 10 Tier 2 + 4 new Tier 1.5), publish prompt library.  
**Entry gate:** Phase 4 complete.  
**Exit deliverable:** All tools verified against V4 API, new tools live, prompt library committed.

### Tool Audit

All 29 V3 tools are audited against V4 endpoints. The migration is backward-compatible. The 61-tool target adds 4 Tier 1.5 analytics tools and expands Tier 1 coverage. Audit verifies:
- Each tool's endpoint still exists and returns the same shape
- New additive fields do not break tool schemas
- Any tool relying on a JSON-file detail returns the same value from the engine

### New Tools Enabled by V4

| Tool | Depends On | Notes |
|---|---|---|
| `get_portfolio_beta_risk` | Tier 1.5 endpoint (Phase 4) | Beta-weighted delta vs SPY |
| `get_sector_exposure` | Tier 1.5 endpoint (Phase 4) | GICS sector breakdown |
| `get_capital_efficiency` | Tier 1.5 endpoint (Phase 4) | ROC per position |
| `get_earnings_volatility_data` | Tier 1.5 endpoint (Phase 4) | Implied vs historical move |
| `get_audit_log` | `audit_log` table (Phase 4) | Paginated audit trail |
| `get_pnl_history` | `pnl_history` table (Phase 4) | Historical daily PnL |
| `get_engine_health` | All four engines (Phase 4) | Health check per engine |
| `get_concentration_report` | Position Engine (Phase 4) | Full concentration analysis |

### Prompt Library

The full 19-prompt daily workflow library from `09_MCP_Workflow_and_Prompts_v2.md` is updated with V4 tool names and committed to `fortress-mcp/examples/prompts/README.md`. This covers all phases from morning startup through EOD signal, including the Tier 1.5 compound workflows.

---

## 12. Phase 6 — Infrastructure

**Goal:** Docker Compose production stack, HTTPS, CI/CD.  
**Entry gate:** Phase 4 complete.  
**Exit deliverable:** Docker stack live on VPS, HTTPS enabled, GitHub Actions CI running on all three repos.

### Stack

Services: `api`, `frontend`, `mysql`, `redis`, `ibkr-gateway`, `market-worker`, `alert-worker`

The existing `fortress-dashboard.service` systemd unit is retained as a fallback. It is not removed — it is the rollback target if Docker Compose has issues.

### HTTPS

Let's Encrypt via Certbot. nginx as TLS termination. Note: changing from HTTP to HTTPS breaks the MCP server's `FORTRESS_API_URL` for all connected Claude Desktop instances. Plan a coordinated credential update.

### CI/CD (GitHub Actions)

| Workflow | Trigger | Actions |
|---|---|---|
| `ci-api.yml` | Push to `main` or PR | `ruff` lint, `pytest`, `mypy` |
| `ci-app.yml` | Push to `main` or PR | `pnpm check`, `pnpm build` |
| `ci-mcp.yml` | Push to `main` or PR | `ruff` lint, MCP smoke tests |
| `deploy-api.yml` | Manual or push to `release` | SSH deploy, Docker Compose pull + up |

---

## 13. Migration Strategy

### Zero Downtime

Phases 0–3 are entirely non-destructive — no production VPS changes.

Phase 4 is additive: the four engines are built alongside `app/services/`. A config flag (`security.use_v4_engines: false`) gates each engine's switchover independently.

The JSON migration runs once on a Friday-after-close maintenance window. JSON files remain on disk as read-only backup for 5 trading days.

The front-end switchover is instantaneous: update `VITE_API_BASE` and redeploy.

### Rollback Plan

| Phase | Trigger | Action |
|---|---|---|
| Phase 4 engine switchover | Incorrect engine data | Set `use_v4_engines: false`; routes revert to legacy services |
| Phase 4 JSON migration | Data discrepancy within 5 days | Restore JSON from `data/archive/`; fix and re-run |
| Phase 6 Docker Compose | Container health check failing | `systemctl start fortress-dashboard.service` (kept as fallback) |

---

## 14. What Does Not Change

- **Portfolio Strategy v3.7** — Every rule, threshold, and entry/exit criterion is preserved exactly
- **8 sidebar navigation items** — Locked per ops notes (Dashboard · Market Intel · Positions · Trade · Analysis · Performance · Earnings · Config)
- **61 MCP tool names** — All 29 V3 tools preserved; 32 new tools added (Tier 1 expansion + 4 Tier 1.5); new tools are additive
- **8 automated workflow scripts** — Same schedules, same outputs (refactored to engine calls internally)
- **IBKR CP Gateway** — voyz/ibeam Docker container stays
- **Bearer token authentication** — Auth model unchanged in V4
- **tRPC BFF pattern** — Stays in `fortress-app/server/`

---

## 15. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| IBKR session expires during migration | High | Medium | Schedule migration Friday after close; ibeam auto-reconnects |
| QuantData credentials expire during development | Medium | Low | Settings UI refresh exists; Market Engine degrades to yfinance |
| MySQL migration produces incorrect data | Low | High | Dry-run + snapshot comparison; 5-day stability window |
| Phase 3 built against wrong mock data shape | Medium | Medium | Generate fixtures from live JSON, not synthetic data |
| Docker networking conflicts with existing services | Low | Medium | Non-overlapping subnets; dev Compose tested before prod |
| HTTPS change breaks MCP connections | High | **Medium** | Update `FORTRESS_API_URL` to `https://` in all Claude Desktop `claude_desktop_config.json` files **before** enabling HTTPS on nginx. See `V4_09_Operations_Notes.md` K-05 for config file path. |
| SSE stream drops in production | Medium | Low | Graceful fallback to HTTP polling already in Sprint v4.0 |
| Tier 1.5 yfinance sector data stale/incorrect | Medium | Low | Cache with 24h TTL; allow manual override in Settings |

---

## 16. Start Sequence & Timeline

| Week | Work |
|---|---|
| 1–2 | Phase 0: Write five ADRs + annotated schema |
| 2–3 | Phase 2 (parallel): Mark deprecated docs; draft V4_06 Operations Guide |
| 3–5 | Phase 1: Token file + component catalogue (focus on new Tier 1.5 components first) |
| 4–8 | Phase 3: Pages in order — Dashboard → Positions → Trade → Performance → rest |
| 5–9 | Phase 4: DB layer → Position Engine → Market Engine → Alert Engine → Execution Engine → Tier 1.5 → SSE |
| 9–10 | Phase 5: Tool audit, new tools, prompt library release |
| 10–11 | Phase 6: Docker Compose staging → production; HTTPS; CI/CD |

**Total: 11–12 weeks** from Phase 0 start to full V4 production deployment.

---

*Sources: `260523documentation/` (14 files) · `Quantplans/` (6 files) · `hermesdocs/` (11 files) · `Investment2026/` (full folder) · VPS live state 2026-05-23*
