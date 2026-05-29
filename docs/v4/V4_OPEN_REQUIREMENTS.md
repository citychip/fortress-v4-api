# Fortress V4 — Open Requirements
## All Requirements With Current Status

**Prepared:** 2026-05-26
**Updated:** 2026-05-27 (post Sprint v8.24; added A-09, E-13, H-07)
**Governing rule:** Portfolio Strategy v3.7 wins over everything.

Status: `[ ]` not started · `[~]` in progress · `[x]` done

---

## Group A — Automation and Scheduling

| ID | Requirement | Status | Sprint |
|---|---|---|---|
| A-01 | APScheduler wired into FastAPI lifespan | [x] | v8.3 |
| A-02 | Premarket scanner at 07:00 ET | [x] | v8.3 |
| A-03 | IV Crush Monitor every 30 min (earnings window) | [x] | v8.3 |
| A-04 | Position Monitor every 5 min during market hours | [x] | v8.3 |
| A-05 | Dark Pool Alert every 15 min during market hours | [x] | v8.3 |
| A-06 | EOD Review at 16:05 ET | [x] | v8.3 |
| A-07 | Whale Flow Report at 08:00 ET and 12:00 ET | [x] | v8.3 |
| A-08 | Max Pain Report at 09:00 ET and 14:00 ET | [x] | v8.3 |

| A-09 | QuantData auto-surfacing: scan universe tickers at premarket for unusual OI change / order flow; push high-signal events into morning brief and Dashboard alert strip | [ ] | Future |

**Group A: A-01–A-08 complete. A-09 not started.**

---

## Group B — Data Safety and Config

| ID | Requirement | Status | Sprint |
|---|---|---|---|
| B-01 | `GET /api/config/backup` endpoint | [x] | v8.4 |
| B-02 | `POST /api/config/restore` endpoint | [x] | v8.4 |
| B-03 | Auto-backup before every config write | [x] | v8.4 |
| B-04 | Rotate: keep last 10 backups only | [x] | v8.4 |
| B-05 | OPRA 21-character symbol normalisation | [x] | v8.6 |

**Group B: complete.**

---

## Group C — Portfolio Analytics Endpoints

| ID | Requirement | Status | Sprint | Notes |
|---|---|---|---|---|
| C-01 | `GET /api/portfolio/beta` | [x] | v8.5 | Returns beta_weighted_delta, spy_price, component_betas, as_of |
| C-02 | `GET /api/portfolio/sector-exposure` | [x] | v8.5 | Returns sectors, concentration_max_pct, breach, as_of |
| C-03 | `GET /api/portfolio/capital-efficiency` | [x] | v8.5 | Returns capital_efficiency, by_position, threshold, as_of |
| C-04 | `GET /api/market/earnings-volatility/{ticker}` | [x] | v8.16 | implied_move_pct, historical_moves[], ratio |
| C-05 | `get_capability` reflects new endpoints | [x] | v8.16 | Audited; capability response updated |
| C-06 | `GET /api/portfolio/pcs-exposure` | [x] | v8.18 | Bull-put spread count/notional vs caps |

**Group C: complete.**

---

## Group D — Data Layer Migration

| ID | Requirement | Status | Sprint | Notes |
|---|---|---|---|---|
| D-01 | MySQL connector + env vars set | [x] | Pre-v8.3 | pymysql live; DATABASE_URL in systemd |
| D-02 | Positions upserted to MySQL after every IBKR sync | [x] | v8.7 | 19 rows confirmed |
| D-03 | Migrate config to MySQL `config` table | [x] | v8.21 | 115 rows; dual-write on every save; seeds on startup |
| D-04 | `GET /api/positions` falls back to JSON if DB unavailable | [x] | v8.7 | Graceful degradation implemented |
| D-05 | Redis installed and running on VPS | [x] | Pre-v8.3 | redis-cli ping returns PONG |
| D-06 | `portfolio_snapshots` populated nightly by EOD scheduler | [x] | v8.21 | POST /api/pnl/snapshot; scheduler fires 16:10 ET Mon-Fri |
| D-07 | Migrate `journal.json` to MySQL `journal` table | [x] | v8.21 | MySQL-first reads; dual-write on every save |
| D-08 | `POST /api/journal/close/{id}` endpoint | [x] | v8.8 | Links close→open; stamps iv_crush_realized, dte_at_close |
| D-09 | `iv_crush_realized` and `dte_at_close` on journal close entries | [x] | v8.8 | In JournalCloseLink model |
| D-10 | `POST /api/ibkr/upload/retry` endpoint | [x] | v8.9 | Redis-backed; confirmed working |

**Group D: complete.**

---

## Group E — Frontend Features

| ID | Requirement | Status | Sprint | Notes |
|---|---|---|---|---|
| E-01 | Forward P&L panel wired on position accordion | [x] | v8.10 | ForwardPnLPanel + PositionLimitsBadge in PositionsPage |
| E-02 | Regime label normalisation across all pages | [x] | v8.11 | regimeInfo() used across 5 pages |
| E-03 | PCS Exposure badge on Dashboard | [x] | v8.18 | X/5 spreads · $YK/$25K; breach/warning colors |
| E-04 | Pacing chart on Dashboard | [x] | v8.18 | 8-week bar; current week amber at 2 entries |
| E-05 | BetaWeightedDeltaCard on Positions page | [x] | v8.17 | SPY-equiv delta gauge + per-ticker breakdown |
| E-06 | SectorExposureBar on Positions page | [x] | v8.17 | Stacked bar by GICS sector; amber cap marker |
| E-07 | CapitalEfficiencyTable on Config / Strategy tab | [x] | v8.17 | Sorted ROC per position; BP utilisation gauge |
| E-08 | EarningsVolatilityCompare on Candidates rows | [x] | v8.17 | Inline expand: implied vs historical move bars + ratio |
| E-09 | Journal closed-loop P&L view on Performance page | [x] | v8.22 | ClosedLoopAccordion with OPEN/CLOSE pairs; IV crush, DTE@close |
| E-10 | P&L history chart on Performance page | [x] | v8.22 | 90-day net-liq equity curve from portfolio_snapshots |
| E-11 | Engine health row in Config / Monitor | [ ] | Phase 4+ | Blocked on engines |
| E-12 | NOT READY reason per Candidates ticker | [x] | v8.20 | Chip shows Earnings Xd / Conc. X% / Excluded / Not ready |

| E-13 | Proactive pacing "at-risk" signal on Dashboard — forward-looking alert when current open positions near roll/exit window will likely fill remaining weekly capacity before week ends | [ ] | Future |

**Group E: E-01 through E-10 and E-12 done. E-11 deferred. E-13 not started.**

---

## Group F — Strategy Rule Enforcement

| ID | Requirement | Status | Sprint | Notes |
|---|---|---|---|---|
| F-01 | PCS count cap gate (max 5) in pre-trade checks | [x] | v8.19 | Hard block at 5th spread |
| F-02 | Put notional cap gate (max $25K) in pre-trade checks | [x] | v8.19 | Hard block |
| F-03 | LEAP entry blackout 14 days before earnings | [x] | v8.19 | Uses `leap_entry_blackout_days` config key |
| F-04 | Weekly pacing gate (advisory, max 2/week) | [x] | v8.19 | Advisory in `advisories[]`; not a hard block |
| F-05 | DTE exception registry — suppress false roll alerts | [x] | v8.19 | Reads `config.dte_exceptions[]` |
| F-06 | OPRA capability filter: sec_type == OPT legs only | [x] | v8.6 | Stock legs no longer trigger false negatives |
| F-07 | Config backup applied to config_store.save() | [x] | v8.4 | Every config write path auto-backs up |

**Group F: complete.**

---

## Group G — MCP Expansion

| ID | Requirement | Status | Sprint | Notes |
|---|---|---|---|---|
| G-01 | `get_portfolio_beta` tool | [x] | v8.16 | Calls /api/portfolio/beta |
| G-02 | `get_sector_exposure` tool | [x] | v8.16 | Calls /api/portfolio/sector-exposure |
| G-03 | `get_capital_efficiency` tool | [x] | v8.16 | Calls /api/portfolio/capital-efficiency |
| G-04 | `get_earnings_volatility` tool | [x] | v8.16 | Calls /api/market/earnings-volatility |
| G-05 | Audit all MCP tools against V4 endpoints; fix broken tools | [x] | v8.24 | 5 tools fixed; 3 new tools added; 64 total |
| G-06 | Expand to 61+ total tools | [x] | v8.24 | 64 tools live (exceeded target) |
| G-07 | Prompt library updated for V4 tools | [x] | v8.24 | Server instructions updated to v4.0.0 |
| G-08 | MCP server version to 4.0.0 | [x] | v8.24 | FORTRESS_MCP_VERSION = "4.0.0" |

**Group G: complete.**

---

## Group H — Infrastructure

| ID | Requirement | Status | Sprint | Notes |
|---|---|---|---|---|
| H-01 | HTTPS / TLS on nginx | [x] | v8.20 | Let's Encrypt on srv1321374.hstgr.cloud; expires 2026-08-25 |
| H-02 | Update MCP FORTRESS_API_URL to https:// | [x] | v8.20 | MCP default URL updated; commit 9efa111 |
| H-03 | Docker Compose for local dev | [ ] | Future | |
| H-04b | GitHub Actions CI for frontend auto-deploy | [ ] | Next | Manual build still required |
| H-05 | MySQL backups configured on VPS | [ ] | Next | |
| H-06 | Rollback procedure documented and tested | [ ] | Next | |

| H-07 | Frontend bundle code splitting — dynamic imports to reduce initial JS payload from 1.55 MB to ≤500 KB per chunk; eliminates Vite chunk-size warning on every build | [ ] | v8.26 |

**Group H: H-01/H-02 done. H-03/H-04b/H-05/H-06/H-07 remaining.**

---

## Group I — Documentation Gaps

| ID | Requirement | Status | Notes |
|---|---|---|---|
| I-01 | V4_05_MCP_Spec.md — all tools documented | [ ] | Skeleton exists; Tier 1.5 entries missing |
| I-02 | V4_08_Developer_Guide.md — local Docker setup | [ ] | Skeleton exists |
| I-03 | fortress-api README updated for V4 | [ ] | |
| I-04 | V4_09_Operations_Notes.md committed to repo | [ ] | |
| I-05 | OpenAPI spec descriptions complete | [ ] | |
| I-06 | V4_REALITY_CHECK.md kept current | [x] | Updated 2026-05-27 post-v8.24 |
| I-07 | V4_OPEN_REQUIREMENTS.md kept current | [x] | This document |
| I-08 | V4_SPRINT_PLAN.md maintained | [x] | See V4_SPRINT_PLAN.md |

---

## Deferred / Won't Do

| Item | Reason |
|---|---|
| Full engine refactor (separate classes) | Inline logic works. Refactor after MySQL migration is solid. |
| SSE via Redis pub/sub | Current SSE works. No user-visible benefit until scale demands it. |
| WebSocket real-time IBKR streaming | 60s polling fits the strategy time horizon. |
| Full event sourcing / replay | Overkill for single-trader system. |
| Multi-account IBKR | Not in scope. |
| Mobile app | Desktop only. |
| QuantData OAuth 2.0 | Requires QuantData to support it; manual refresh via UI is the mitigation. |
| E-11 (engine health row) | Blocked on engine refactor; no ETA. |

---

## Priority Order — What to Build Next

1. **H-04b** — GitHub Actions CI for frontend (~1 hr) — eliminates manual deploy step
2. **H-05** — MySQL daily backup cron (~30 min) — data safety
3. **H-06** — Rollback procedure documented (~1 hr)
4. **H-07** — Bundle code splitting (~1 hr) — fixes build warning; faster cold load
5. **H-03** — Docker Compose for local dev (~2 hr)
6. **E-13** — Proactive pacing alert (~1 hr) — forward-looking week-capacity signal
7. **A-09** — QuantData auto-surfacing (~1.5 hr) — high-signal events into morning brief / dashboard
8. **I-01 through I-05** — documentation gaps (~3 hr)

**Estimated hours to fully complete V4 production:** ~12 hr

---

*Supersedes V4_OPEN_REQUIREMENTS.md updated 2026-05-27 (post-v8.24)*
