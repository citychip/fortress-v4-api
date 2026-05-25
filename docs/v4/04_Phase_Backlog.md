# Fortress V4 — Phase Backlog
## Full Sprint Backlog with Acceptance Criteria

**Version:** 4.0.0  
**Status:** Authoritative — living document, updated each sprint  
**Golden Rule:** Phases 0–2 (architecture, design, documentation) must be complete and signed off before any Phase 3–6 coding begins.

---

## How to Read This Document

Each item has:
- **ID** — unique, stable reference (phase-sequence)
- **Subject** — imperative action statement
- **Acceptance Criteria (AC)** — observable, testable conditions for "done"
- **Depends on** — blocking items that must be complete first
- **Notes** — context, edge cases, caveats

Status column: `[ ]` pending · `[~]` in progress · `[x]` done

---

## Phase 0 — Architecture

> Goal: Produce the full V4 technical specification. No code written in this phase.

| ID | Subject | Status |
|---|---|---|
| P0-01 | Write V4_01_Master_Design_Proposal.md | [x] |
| P0-02 | Write V4_02_Architecture.md | [x] |
| P0-03 | Write V4_03_Design_System.md | [x] |
| P0-04 | Write V4_04_Phase_Backlog.md (this doc) | [x] |
| P0-05 | Write V4_05_MCP_Spec.md | [x] |
| P0-06 | Write V4_06_Operations_Guide.md | [x] |
| P0-07 | Write V4_07_Migration_Guide.md | [x] |
| P0-08 | Write V4_08_Developer_Guide.md | [x] |
| P0-09 | Write V4_09_Operations_Notes.md | [x] |
| P0-10 | Publish V4 docs to `docs/v4/` in fortress-app repo | [ ] |

**Phase 0 exit criteria:** All 9 V4 documents present in `docs/v4/`. V3 documentation preserved in `docs/` (parent directory) as the operational reference. Document set reviewed by Steven.

---

## Phase 1 — Design System

> Goal: Finalisе the Obsidian Edge design system with token definitions, component library, and mockups for all 8 pages.

| ID | Subject | AC | Depends on | Notes |
|---|---|---|---|---|
| P1-01 | Define all CSS custom property tokens | `tokens.css` committed with full colour/spacing/type scale matching V4_03_Design_System.md | P0-03 | No Tailwind config used as token source of truth — CSS vars only |
| P1-02 | Build Button component (4 variants) | primary/secondary/ghost/danger all render; loading state shows spinner; disabled at 40% opacity; focus ring visible | P1-01 | |
| P1-03 | Build KPI Card component | Shows label/value/delta; positive/negative colouring; badge prop; skeleton state | P1-01 | |
| P1-04 | Build Data Table component | Sticky header; sortable columns; hover/selected row states; positive/negative cell colouring; inline action slot | P1-01 | |
| P1-05 | Build Badge / Status Pill | LIVE/CLOSED/WARNING/BREACH/NEW variants | P1-01 | |
| P1-06 | Build Alert Banner | Full-width; warning/danger variants; dismissible; pushes content down (no overlay) | P1-01 | |
| P1-07 | Build Modal component | Backdrop; 3 widths; focus management; Escape closes; aria-dialog; footer button slots | P1-01 | |
| P1-08 | Build Sidebar Navigation (8 items) | Active/hover states; locked 8-item structure; connection status chip | P1-01 | Nav structure LOCKED — no additions without explicit request |
| P1-09 | Build Toast Notification | 4 variants; auto-dismiss timing; stack limit 3; bottom-right position | P1-01 | |
| P1-10 | Build Input / Form Controls | Text, number, select, checkbox; error state; focus ring | P1-01 | Number inputs use JetBrains Mono |
| P1-11 | Build Chart theme wrapper | Token-based grid/axis/tooltip theming for Recharts | P1-01 | |
| P1-12 | Create page mockups / wireframes for all 8 pages | Annotated wireframe or Figma frame for Dashboard, Market Intel, Positions, Trade, Analysis, Performance, Earnings, Config | P1-01–P1-11 | Must show panel layout, component placement, and KPI strip |
| P1-13 | WCAG contrast audit | All text/bg pairs ≥ 4.5:1 (body) / 3:1 (large); automated tool evidence | P1-01 | |
| P1-14 | `prefers-reduced-motion` test | All animations fall back correctly; no flash or jarring instant jump | P1-02–P1-11 | |

**Phase 1 exit criteria:** All components pass visual review; contrast audit clean; mockups approved by Steven; no code beyond component library written.

---

## Phase 2 — Documentation

> Goal: Complete all developer-facing and operational documentation before any coding begins.

| ID | Subject | AC | Depends on | Notes |
|---|---|---|---|---|
| P2-01 | Complete V4_05_MCP_Spec.md | All 61 tools documented (47+10+4) with request/response schemas | P0-05 | Includes 4 new Tier 1.5 tools |
| P2-02 | Complete V4_06_Operations_Guide.md | Daily workflow, 8 APScheduler scripts, monitoring procedures | P0-06 | |
| P2-03 | Complete V4_07_Migration_Guide.md | Step-by-step JSON→MySQL migration with rollback | P0-07 | |
| P2-04 | Complete V4_08_Developer_Guide.md | Local setup, Docker Compose, env vars, test commands | P0-08 | |
| P2-05 | Complete V4_09_Operations_Notes.md | All permanent ops notes extracted from todo.md | P0-09 | Must be committed to fortress-api repo root |
| P2-06 | Write fortress-api README (V4) | Updated README reflecting V4 architecture, setup, and endpoints | P2-04 | |
| P2-07 | Write fortress-app README (V4) | Updated README reflecting tech stack, setup, and page structure | P2-04 | |
| P2-08 | Write fortress-mcp README (V4) | Updated README reflecting 61 tools, Tier 1.5 additions, environment setup | P2-01 | |
| P2-09 | Document OpenAPI spec for all V4 endpoints | `/openapi.json` accurately reflects all 10 new V4 endpoints with schemas | P0-02 | Auto-generated by FastAPI, but requires manual descriptions/examples |

**Phase 2 exit criteria:** All documentation complete and consistent with V4_02_Architecture.md; Steven reviews and approves.

---

## Phase 3 — Front-End Coding

> Prerequisite: Phases 0–2 complete. No front-end work starts until documentation and design are signed off.

### Setup

| ID | Subject | AC | Depends on |
|---|---|---|---|
| P3-00 | Build mock SSE server | `npm run mock-sse` emits all 6 event types (`market_update`, `alert`, `order_update`, `session_expired`, `sync_completed`, `heartbeat`) on configurable interval; fixture events match Phase 0 API surface shapes exactly | P0-02 |
| P3-01 | Upgrade to React 19 stable | All existing components render without deprecation warnings | Phase 2 complete |
| P3-02 | Upgrade to Tailwind 4 | CSS compiles cleanly; no v3 config syntax remaining | P3-01 |
| P3-03 | Set up tRPC 11 with SSE transport | Type-safe client/server connection; SSE subscription test passes | P3-01 |
| P3-04 | Implement SSE client hook `useSSEStream` | Hook connects, reconnects on drop, exposes typed event stream | P3-03 |

### Page Implementation

| ID | Subject | AC | Depends on |
|---|---|---|---|
| P3-05 | Dashboard page | KPI strip, SPY chart, greeks panel, positions table all load via SSE; delta chip live | P3-04 |
| P3-06 | Market Intel page | Order flow, dark pool, IV term structure, sector heat map tabs functional | P3-04 |
| P3-07 | Positions page | Sortable positions table; expand row shows legs; Roll/Stop-Loss actions open confirmation modal | P3-04 |
| P3-08 | Trade page | Pre-trade form with live check results (debounced); pending orders table; Approve/Decline | P3-04 |
| P3-09 | Analysis page | Greeks/Vol Skew/OI/Max Pain tabs; shared ticker state | P3-04 |
| P3-10 | Performance page | P&L equity curve; trade log table with filters | P3-04 |
| P3-11 | Earnings page | Calendar grid + list view; post-earnings review accordion | P3-04 |
| P3-12 | Config page | Sectioned form; inline section save; dangerous resets | P3-04 |

### Cross-cutting

| ID | Subject | AC | Depends on |
|---|---|---|---|
| P3-13 | Replace all polling with SSE subscriptions | Zero `setInterval` / `setTimeout` fetches in codebase; all real-time data via SSE | P3-04 |
| P3-14 | Implement bearer auth header on all tRPC calls | All requests include `Authorization: Bearer <token>`; 401 → redirect to login | P3-03 |
| P3-15 | Connection status chip in top bar | LIVE/RECONNECTING/OFFLINE states accurate; IBKR status shown | P3-04 |
| P3-16 | Alert banner system wired to SSE alerts | Banner appears/dismisses driven by alert stream; critical alerts non-dismissable | P3-04, P3-05 |
| P3-17 | Numeric formatting utility | `formatCurrency`, `formatDelta`, `formatGreek` helpers used consistently across all pages | P3-01 |
| P3-18 | Toast notification system | Globally accessible; wired to SSE error events and trade confirmations | P3-04 |

**Phase 3 exit criteria:** All 8 pages functional with live data; SSE connected; no polling; bearer auth working; visual matches Phase 1 mockups.

---

## Phase 4 — Backend Coding

> Prerequisite: Phases 0–2 complete. Front-end (Phase 3) may run in parallel after setup.

### Data Layer

| ID | Subject | AC | Depends on |
|---|---|---|---|
| P4-01 | Set up MySQL 8 with V4 schema | All tables from V4_02_Architecture.md created; migrations versioned (Alembic) | Phase 2 |
| P4-02 | Set up Redis 7 (cache + pub/sub) | Redis running; pub/sub test passes; cache hit/miss logged | Phase 2 |
| P4-03 | Implement `pcs_exposure` view | View returns correct exposure across all open PCS positions; unit test passes | P4-01 |
| P4-04 | Add `journal.close_id` FK migration | Alembic migration runs clean; FK constraint enforced | P4-01 |
| P4-05 | Migrate active_positions.json → MySQL | All existing positions loaded; no data loss; JSON file deprecated. **Script is idempotent: running it twice produces the same row count as running it once** (use `INSERT IGNORE` or existence check on ticker+opened_at) | P4-01 |
| P4-06 | Migrate alerts.json → MySQL | All existing alerts loaded; JSON file deprecated. Script is idempotent. | P4-01 |
| P4-07 | Migrate journal.json → MySQL | All existing journal entries loaded; close_id backfilled where deterministic. Script is idempotent. | P4-04 |
| P4-08 | Migrate fortress_config.json → MySQL config table | All config keys loaded; V4 new keys seeded with defaults. Script is idempotent. | P4-01 |
| P4-09 | Migrate ibkr_uploads.json → MySQL | Upload records loaded; JSON file deprecated. Script is idempotent. | P4-01 |

### Engine Implementation

| ID | Subject | AC | Depends on |
|---|---|---|---|
| P4-10 | Implement Position Engine | `pcs_exposure()`, `beta_weighted_delta()`, `capital_efficiency()` return correct values; unit tests pass | P4-01 |
| P4-11 | Implement Market Engine | `earnings_volatility()`, `get_sector()` return correct values; session management tracks open/close | P4-02 |
| P4-12 | Implement Alert Engine with PCS cap and weekly pacing rules | `PCSCapRule` fires at 4/5 positions; `WeeklyPacingRule` fires at 2 trades/week; both surfaced via SSE | P4-10 |
| P4-13 | Implement Execution Engine pre-trade gate | All 12 checks from PreTradeGate pass unit tests; blackout logic tested against known dates | P4-10, P4-11 |
| P4-14 | Wire APScheduler 8 workflows | All 8 scripts run on schedule; log output to `scheduler.log`; alerting on failure | P4-10–P4-13 |
| P4-14b | Wire `eod_review` workflow to write daily `pnl_history` row | Row inserted at EOD with `net_liquidation`, `day_pnl`, `realized_pnl`, `unrealized_pnl`, `portfolio_delta` from IBKR sync; unit test with mock IBKR data confirms correct row values | P4-10 |

### API Surface

| ID | Subject | AC | Depends on |
|---|---|---|---|
| P4-15 | Preserve all existing V3 endpoints | All 47 existing MCP-facing endpoints return identical response shapes; regression test suite passes | P4-01 |
| P4-16 | Add `/api/portfolio/beta` endpoint | Returns portfolio beta vs SPY; unit test with mock positions passes | P4-10 |
| P4-17 | Add `/api/portfolio/sector-exposure` endpoint | Returns sector breakdown by notional; tested | P4-11 |
| P4-18 | Add `/api/portfolio/capital-efficiency` endpoint | Returns capital efficiency ratio; tested | P4-10 |
| P4-19 | Add `/api/market/earnings-volatility` endpoint | Returns pre/post IV for earnings ticker; tested with mocked IBKR data | P4-11 |
| P4-20 | Add `/api/journal/close/{id}` endpoint | Links a closing trade to its opening trade via `close_id`; tested | P4-07 |
| P4-21 | Add `/api/config/backup` endpoint | Returns a timestamped JSON dump of all config; tested | P4-08 |
| P4-22 | Add `/api/config/restore` endpoint | Restores config from backup JSON; validates before write; tested | P4-08 |
| P4-23 | Add `/api/trade/dte-exception` endpoints (GET/POST/DELETE) | Full CRUD for DTE exception registry; tested | P4-13 |
| P4-24 | Add `/api/ibkr/upload/retry` endpoint | Retries last failed IBKR snapshot upload; tested | P4-09 |
| P4-25 | Fix OPRA symbol padding (K-01) | All IBKR option symbols normalised to 21-char OPRA format before processing; unit test confirms | P4-15 |
| P4-26 | Implement SSE stream endpoint `/api/stream` | Redis pub/sub → SSE; events: `position_update`, `alert_trigger`, `market_snapshot`, `order_status`, `scheduler_status` | P4-12, P4-14 |

**Phase 4 exit criteria:** All engines passing unit tests; all endpoints returning correct data; SSE stream delivering all event types; OPRA fix confirmed; migration complete and JSON files deprecated. **Rollback procedure tested on a staging copy: migration run, then rolled back, then re-run successfully.**

---

## Phase 5 — MCP & Tooling

> Prerequisite: Phase 4 backend complete and all endpoints live.

| ID | Subject | AC | Depends on |
|---|---|---|---|
| P5-01 | Audit all 29 V3 MCP tools against V4 endpoints, expand to 61 total | Every Tier 1/2 tool calling an endpoint gets tested; broken tools fixed; 32 new tools added (Tier 1 expansion + 4 Tier 1.5) | P4-15 |
| P5-02 | Implement `get_portfolio_beta` (Tier 1.5) | Tool calls `/api/portfolio/beta`; returns typed response; Claude integration test passes | P4-16 |
| P5-03 | Implement `get_sector_exposure` (Tier 1.5) | Tool calls `/api/portfolio/sector-exposure`; tested | P4-17 |
| P5-04 | Implement `get_capital_efficiency` (Tier 1.5) | Tool calls `/api/portfolio/capital-efficiency`; tested | P4-18 |
| P5-05 | Implement `get_earnings_volatility` (Tier 1.5) | Tool calls `/api/market/earnings-volatility`; tested | P4-19 |
| P5-06 | Update MCP server version string to 4.0.0 | `FORTRESS_MCP_VERSION` env var returns `4.0.0`; `get_capability` reflects new tools | P5-01–P5-05 |
| P5-07 | Update 19-prompt daily workflow library for V4 | All prompts reference V4 tool names, Tier 1.5 tools included, strategy v3.7 thresholds | P5-01–P5-05 |
| P5-08 | Update fortress-mcp README | Reflects 61 tools, Tier 1.5 section, installation instructions for V4 | P5-06, P5-07 |
| P5-09 | Integration smoke test: Claude → MCP → API | Full round-trip test: Claude calls 5 representative tools, gets correct live data | P5-06 |

**Phase 5 exit criteria:** All 61 tools functional; Tier 1.5 tools confirmed working end-to-end; prompt library updated.

---

## Phase 6 — Infrastructure

> Can be prepared in parallel with Phases 3–5. Must be complete before production deployment.

| ID | Subject | AC | Depends on |
|---|---|---|---|
| P6-01 | Write Docker Compose for local dev | `docker compose up` starts all services (API, frontend dev server, MySQL, Redis, ibeam); services interconnected | Phase 2 |
| P6-02 | Validate systemd unit for production VPS | `fortress-dashboard.service` updated for V4; starts cleanly on Ubuntu 7.0; confirmed running | P4-01 |
| P6-03 | MySQL 8 production setup on VPS | MySQL installed, secured, V4 schema applied, backup cron configured | P4-01 |
| P6-04 | Redis 7 production setup on VPS | Redis running as systemd service; persistence configured; maxmemory set | P4-02 |
| P6-05 | Set all required environment variables on VPS | All vars from V4_08_Developer_Guide.md confirmed present; no secrets in code | P6-02 |
| P6-06 | Configure NGINX reverse proxy | Serves static front-end; proxies `/api/*` to FastAPI; proxies `/api/stream` with SSE headers; HTTPS | P6-02 |
| P6-07 | ibeam (IBKR CP Gateway) Docker container | `voyz/ibeam` running on port 5000; auto-restarts; health check passes | P6-01 |
| P6-08 | Test production deployment end-to-end | Full deploy to `/var/www/fortress-v2/`; all 8 pages load; SSE stream live; IBKR connected | P6-01–P6-07 |
| P6-09 | Smoke test all 8 APScheduler workflows on VPS | Each script runs once manually; log output correct; no import errors | P6-08 |
| P6-10 | Confirm port 8081 remains closed | `ss -tlnp | grep 8081` returns empty on VPS | — | Already done (V3 API removed) |
| P6-11 | Document rollback procedure | Step-by-step tested rollback: stop V4, restore V3 backup, restart; time-to-rollback < 10 min | P6-08 |

**Phase 6 exit criteria:** Production environment fully functional; all services stable; rollback tested.

---

## Cross-Cutting Concerns (apply throughout all coding phases)

| ID | Subject | AC |
|---|---|---|
| CC-01 | Bearer auth on all `/api/*` endpoints | No endpoint reachable without valid token; 401 returned otherwise |
| CC-02 | Strategy v3.7 as governing document | All engine thresholds sourced from Portfolio_Strategy_v3_7.md; no hardcoded values that contradict it |
| CC-03 | Source-of-truth hierarchy respected | TradingView > IBKR > QuantData > Strategy doc; conflicts logged, not silently resolved |
| CC-04 | FORTRESS_MCP_ALLOW_WRITES=1 guard on all Tier 2 tools | Write tools fail-safe when env var absent; unit test confirms |
| CC-05 | No client-side polling | Zero `setInterval` data fetches; all real-time data via SSE subscription |
| CC-06 | Deploy target respected | All deployments go to `/var/www/fortress-v2/` only |
| CC-07 | Nav structure locked | 8 sidebar items only; any addition requires explicit user request |

---

## Known Issues (carry-forward from V3)

| ID | Issue | Phase to fix |
|---|---|---|
| K-01 | OPRA symbol padding inconsistency | Phase 4 (P4-25) |
| K-02 | Config not backed up before writes | Phase 4 (P4-21, P4-22) |
| K-03 | IBKR snapshot upload has no retry | Phase 4 (P4-24) |
| K-04 | Journal lacks closed-loop P&L linkage | Phase 4 (P4-07, P4-20) |
| K-05 | Orchestrator service unit pointed to wrong path (root vs `quant/` subdir) | Fixed 2026-05-23 — see `V4_09_Operations_Notes.md` K-05 |

---

*Fortress V4 Phase Backlog — living document. Update status column as items complete.*
