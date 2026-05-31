# Fortress Dashboard — Todo Backlog

**Updated:** May 18, 2026

---

## Completed (Sprint v7.x — May 2026)

| ID | Item | Resolved |
|---|---|---|
| ✅ O-01 | Candidates All-tab showed empty state when API returned 0 rows | Sprint v7.1 — frontend fallback shows all 19 universe tickers as monitoring rows |
| ✅ O-02 | QuantData credential refresh required SSH access | Sprint v7.1 — Settings → QuantData Credentials UI writes to both config files. Full runbook in `operations/04_Incident_Recovery_Playbook.md` §5 |
| ✅ O-03 | `chart.py` used deprecated `tool/OPTIONS_*` QuantData endpoints (400 errors, account revocation risk) | Sprint v7.1 — replaced with widget-UUID REST endpoints matching `market_intelligence.py` pattern |
| ✅ O-04 | Market Intel page crashed with `TypeError: Cannot read properties of null (reading 'toFixed')` | Sprint v7.1 — null guard on `current_price` |
| ✅ O-05 | Market Intel had no sort, no per-card refresh, no metric explanations | Sprint v7.1 — sort dropdown, per-card refresh button, and hover tooltips added |
| ✅ O-06 | Candidates All-tab only showed actionable signals; monitoring tickers not visible | Sprint v7.0 — All tab now shows full 19-ticker universe with actionable at top and monitoring below divider |
| ✅ O-07 | Documentation stale across 9 files after Sprint v7.x | May 18, 2026 — all docs updated to v3.7/Sprint v7.1 baseline |

---

## Active Backlog

### High Priority

| ID | Item | Notes |
|---|---|---|
| P-01 | **QuantData OAuth 2.0** — eliminate manual credential refresh entirely | QuantData may offer a proper OAuth flow. Investigate their API docs. Would remove the recurring O-02 class of incidents. |
| P-02 | **Automated IV Crush workflow schedule** — currently manual trigger only | Add a cron job on the VPS to run `workflow_05_iv_crush_report.py` at 09:00 ET on weekdays. Requires valid QuantData credentials. |

### Medium Priority

| ID | Item | Notes |
|---|---|---|
| P-03 | **IBKR OAuth 2.0** — eliminate CP Gateway daily push approval | IBKR is rolling out OAuth 2.0 for the Web API. Monitor their developer portal. |
| P-04 | **Strategy Workspace UI** — scenario planning | A page where the trader can model hypothetical positions (add/remove legs) and see the impact on portfolio Greeks, concentration, and delta bias before committing. |
| P-05 | **Vol analytics panel** — IV term structure, skew chart | Per-ticker IV term structure (30/60/90 DTE IV) and put/call skew chart. Requires QuantData IV history endpoint. |

### Low Priority

| ID | Item | Notes |
|---|---|---|
| P-06 | **Trade journal export** — CSV/PDF download | Allow exporting the journal to CSV or PDF for tax/review purposes. |
| P-07 | **Roll calculator UI** — interactive roll modeller | A modal on the Positions tab that shows the P&L impact of rolling a position to different strikes/expiries. |
| P-08 | **Multi-account support** — separate IBKR accounts | Currently assumes a single IBKR account. Would require account-level filtering on all position/Greeks endpoints. |

---

## Deferred / Won't Do

| ID | Item | Reason |
|---|---|---|
| D-01 | Real-time WebSocket streaming for Greeks | IBKR Web API polling at 60s is sufficient for the strategy's time horizon. WebSocket adds complexity without meaningful benefit. |
| D-02 | Mobile app | The dashboard is used at a desktop workstation. Responsive design improvements are sufficient. |

---

## Completed (V4 Sprints — May 26, 2026)

| ID | Item | Resolved |
|---|---|---|
| ✅ V4-K01 | OPRA 21-char symbol padding — silent wrong-greeks on option lookups | Sprint v8.6 — `app/services/opra.py` normalises all symbols at sync + load time |
| ✅ V4-K02 | Config backup/restore missing — any write could corrupt settings with no recovery | Sprint v8.4 — `POST /api/config/backup` + `POST /api/config/restore` + auto-backup on every write |
| ✅ V4-K04 | Journal close linkage — no FK between close and open trade entries | Sprint v8.8 — `POST /api/journal/close/{id}` stamps `open_entry_id`, `iv_crush_realized`, `dte_at_close`; back-links open entry |
| ✅ V4-P01 | Portfolio endpoints missing — no beta, sector-exposure, or capital-efficiency data | Sprint v8.5 — `GET /api/portfolio/beta`, `/sector-exposure`, `/capital-efficiency` |
| ✅ V4-P02 | APScheduler not wired — 8 workflows ran manually only | Sprint v8.3 — BackgroundScheduler auto-runs briefing, IBKR sync, backup, reports |
| ✅ V4-P03 | MySQL data layer not wired — `fortress_v4` DB existed but routes used JSON only | Sprint v8.7 — positions + greeks written on every IBKR sync; `GET /api/positions` reads MySQL first |
| ✅ V4-P04 | Null guard missing on `current_iv` / `current_theta` in PositionsPage | Hotfix — `!= null` guard applied to both V3 and V4 frontends |
| ✅ V4-CI | GitHub Actions CI/CD pipeline broken (SSH action CDN failure + GITHUB_TOKEN 403) | Fixed — inline SSH setup + `git pull` on VPS; all 4 repos now have working pipelines |

## Completed (V4 Sprints — May 30, 2026)

| ID | Item | Resolved |
|---|---|---|
| ✅ V4-K03 | IBKR upload retry | v8.10 — `POST /api/ibkr/upload/retry` + `retry_ibkr_sync()` MCP tool |
| ✅ V4-F01 | Forward P&L panel | v8.13 — wired to PositionsPage |
| ✅ V4-F02 | Regime label formatting | v8.12 — Title Case throughout |
| ✅ P-02 | Automated IV Crush + premarket schedule | v8.15/v8.16 — APScheduler at 07:00 ET and every 30 min |
| ✅ V4-QD | QuantData auto-refresh | v8.15 — `qd_refresh_session.py` runs daily at 06:00 ET |
| ✅ V4-SEC | Security hardening | 2026-05-30 — /api/token localhost-only, CORS restricted, sensitive files gitignored |
| ✅ V4-THEME | Colour constant deduplication | 2026-05-30 — `lib/theme.ts` single source of truth, 16 files updated |
| ✅ V4-MI | Market Intel portfolio/universe split | 2026-05-30 — portfolio tickers shown first with position badges |
| ✅ V4-MI-CACHE | Market Intel server-side cache | 2026-05-30 — 5-min TTL, Refresh All button |

## Active Backlog — V4 Remaining

| ID | Priority | Item | Notes |
|---|---|---|---|
| V4-QD-TICKER | Low | QuantData per-ticker proxy | Won't fix — architectural limitation. update_tool (PUT) pattern proven broken. Future path: per-ticker tool instances via POST /api/tool. See MASTER_DOC §6 |
| V4-F03 | Low | `qd_status()` MCP tool | 30m — check if QD credentials are valid before calling qd_* |
| V4-F04 | Low | Regime badge colour | 30m — red → amber/green based on direction |
| V4-F05 | Low | DTE countdown on Earnings rows | 30m |
| ~~V4-F06~~ | ✅ Done | Colour-coded Quick Nav cards (v8.18) | — |
| TF-12 | Medium | PMCC sub-clustering within ticker groups — pair long LEAP + short call visually as one spread unit, with heuristic leg-matching | Phase 2 backlog |
| V4-F07 | Medium | Split SettingsPage.tsx (1,692 lines) | 3h — extract sub-components |
| V4-F08 | Medium | Split AnalysisPage.tsx (1,469 lines) | 3h — extract sub-components |
| V4-F09 | Low | Standardise backend logging | 2h — print() → logger.* |
| V4-F10 | Low | Frontend unit tests | 1 day — msw-based hooks |
| V4-F11 | Low | MySQL migration alerts/journal | 2 days — currently JSON files |

## Completed (Session 2026-05-30 — v8.25)

| ID | Item | Resolved |
|---|---|---|
| ✅ FIX-01 | Null-guard on Net Liq / Excess Liq / Available Funds — showed `$NaN` when IBKR offline | `DashboardPage.tsx` — `!= null && !isNaN()` guard on all three StatCard values |
| ✅ FIX-02 | IBKR panel showed "Disconnected" when IBKR was live — `useIbkrStatus` called broken `/api/ibkr/status` route | `useApi.ts` — switched to `/api/ibkr/capability` |
| ✅ FIX-03 | Duplicate `stroke` JSX attribute on `<Line>` in StrategySandbox causing build warning | `StrategySandbox.tsx` — removed static `stroke={SB_CYAN}`, kept dynamic version |
| ✅ FIX-04 | Backend logging audit | All `app/` routes already use `logger.*`. CLI scripts use `print` intentionally. No changes needed. |

## Active Backlog — Trade Flow Redesign (v8.26–v8.32)

Full spec: `docs/TRADE_FLOW_REDESIGN.md`

| ID | Priority | Item | Phase |
|---|---|---|---|
| TF-01–05 | P1 | Deep-link wiring — Roll/Close/Add buttons, URL params, mode selector, state reset | Phase 1 |
| TF-10–11 | P2 | Collapsible position groups in Portfolio | Phase 2 |
| ~~TF-20–21~~ | ✅ Done | Move Strategy Sandbox from Analysis to Trade tab | Phase 3 — v8.28 |
| ~~TF-30–31~~ | ✅ Done | Action Queue in Briefing + sidebar badge | Phase 4 — v8.35 |
| ~~TF-40–43~~ | ✅ Done | Roll alternatives engine + IBKR chain + sandbox wiring | Phase 5 — v8.36–v8.40 |
| ~~TF-40–43~~ | ✅ Done | Roll alternatives engine (IBKR chain + scoring) | Phase 5 — v8.36–v8.40 |
| ~~TF-50–51~~ | ✅ Done | Strategy selector with live metrics | Phase 6 — v8.41–v8.43 |
| ~~TF-60–63~~ | ✅ Done | Conditional alerts system | Phase 7 — v8.44–v8.50 |

## Carried Over — Still Active

| ID | Priority | Item | Notes |
|---|---|---|---|
| TF-12 | Medium | PMCC sub-clustering within ticker groups — pair long LEAP + short call visually as one spread unit, with heuristic leg-matching | Phase 2 backlog |
| V4-F07 | Medium | Split SettingsPage.tsx (1,700+ lines) | Deferred |
| V4-F08 | Medium | Split AnalysisPage.tsx (1,470+ lines) | Deferred |
| V4-F10 | Low | Frontend unit tests (msw-based) | Deferred |
| V4-F11 | Low | MySQL migration alerts/journal | Deferred |
| V4-QD-TICKER | Low | QuantData per-ticker proxy | Won't fix — architectural limitation |



## Completed (v8.35 Phase 4 — 2026-05-31)

| ID | Item | Resolved |
|---|---|---|
| ✅ TF-30 | Action Queue deep-links in Briefing Priority Orders panel — each row gets colored Trade button | `DashboardPage.tsx` — stop-loss→close, roll→roll, alert→new mode |
| ✅ TF-31 | Sidebar Trade icon badge — red count badge shows urgent roll+stop-loss count | `App.tsx` — `useRollAll`+`useStopLossAll` in sidebar, badge on Trade path |


## Completed (v8.35–v8.40 Phase 4+5 — 2026-05-31)

| ID | Item | Resolved |
|---|---|---|
| ✅ TF-30 | Briefing Priority Orders rows — colored Trade deep-links (close/roll/new mode) | `DashboardPage.tsx` |
| ✅ TF-31 | Trade sidebar badge — red count of urgent roll+stop-loss actions | `App.tsx` |
| ✅ TF-40 | Roll alternatives engine backend — `GET /api/options/roll_candidates` | `app/routes/options.py` — Conservative/Balanced/Aggressive proposals |
| ✅ TF-41 | Roll alternatives panel in Trade tab (mode=roll) — 3 proposals with Use → button | `TradeBuilderPage.tsx` — inline below proposals |
| ✅ TF-42 | IBKR chain service — `app/services/ibkr_chain.py` — live bid/ask/IV via CP Gateway | IBKR-first, yfinance fallback; conid cache 1h, strikes cache 5min |
| ✅ TF-43 | Sandbox wired to roll proposal — Use → pre-fills strike + DTE in sandbox | `StrategySandbox.tsx` — `defaultStrike` + `defaultDte` props |
| ✅ FIX-07 | Sandbox credit per-share vs per-contract mismatch — max profit showed $5 not $500 | `buildPayoffData` — multiply credit by 100 |
| ✅ FIX-08 | Strike input spinner started from 0+1=1 — should start from effectiveStrike | `StrategySandbox.tsx` — `value={effectiveStrike}`, `step={5}` |
| ✅ FIX-09 | IBKR secdef/search secType nested in sections, not top-level | `ibkr_chain.py` — check `r.sections` for STK |

## Completed (v8.28–v8.34 Phase 3 — 2026-05-31)

| ID | Item | Resolved |
|---|---|---|
| ✅ TF-20 | Strategy Sandbox moved from Analysis tab to Trade tab as Step 5 | `TradeBuilderPage.tsx` — sandbox below RiskCalculator, live-wired to `selectedTicker` |
| ✅ TF-21 | Sandbox enriched: GEX call/put walls + DP floor + flip zone on payoff chart | `StrategySandbox.tsx` — scalar scalars from `regime.*`; `type="number"` on XAxis |
| ✅ TF-22 | Sandbox ticker selector hidden when Trade tab controls it (`hideTickerSelect` prop) | `StrategySandbox.tsx` — strategy selector spans full width when ticker hidden |
| ✅ TF-23 | Sandbox default strategy auto-set from mode (roll→PMCC, new+PMCC position→PMCC) | `TradeBuilderPage.tsx` — `sandboxDefault` computed from `positionContextMap` + `mode` |
| ✅ TF-24 | Strike inputs added to sandbox — short + long strike, live payoff/PoP/metrics update | `StrategySandbox.tsx` — `effectiveStrike` derived value; auto from delta, override by typing |
| ✅ TF-25 | Trade tab landing page — active positions panel + universe candidates panel | `TradeBuilderPage.tsx` — `TradeLanding` component replaces empty state |
| ✅ TF-26 | IVR shown for active positions in ticker dropdown | `TradeBuilderPage.tsx` — `positionContextMap` cross-references candidatesData for IVR |
| ✅ FIX-05 | Analysis page crash — `BarChart2` not imported, replaced with `BarChart3` | `AnalysisPage.tsx` — icon swap |
| ✅ FIX-06 | Sandbox TDZ crash — `useEffect` deps array referenced `sbSpot` before declaration | `StrategySandbox.tsx` — replaced with `effectiveStrike` useMemo after `sbSpot` |

## Completed (v8.27 Phase 2 — 2026-05-30)

| ID | Item | Resolved |
|---|---|---|
| ✅ TF-10 | Collapsible ticker groups — default collapsed, auto-expand on alerts | `PositionsPage.tsx` — `useState(group.alertCount > 0)` |
| ✅ TF-11 | Richer group header — alert dot, strike range, nearest short-leg DTE | `PositionsPage.tsx` — derived from option legs per group |

## Completed (v8.26 Phase 1 — 2026-05-30)

| ID | Item | Resolved |
|---|---|---|
| ✅ TF-01 | Roll + Build buttons deep-link to `/trade` with URL params | `PositionsPage.tsx` — two links fixed (leg-level Roll and group-level Build) |
| ✅ TF-02 | Trade tab reads `?ticker`, `?mode`, `?leg` from URL | `TradePage.tsx` — `useSearch()` + passes props with `key` for clean remount |
| ✅ TF-03 | Ticker dropdown shows active positions at top, urgency-ordered | `TradeBuilderPage.tsx` — `positionContextMap` built from positions + roll/stop data |
| ✅ TF-04 | Mode selector (New Entry / Add / Roll / Close) in Trade Builder | `TradeBuilderPage.tsx` — pills auto-set from `initialMode` prop |
| ✅ TF-05 | State reset on ticker/mode change | `TradeBuilderPage.tsx` — `useEffect` with `isFirstRender` ref guard |

## Completed (v8.41–v8.50 — 2026-05-31)

| ID | Item | Resolved |
|---|---|---|
| ✅ FIX-10 | Roll Balanced proposal deduped to same strike as Conservative | `options.py` — filter `available` candidates per profile before `min()` |
| ✅ FIX-11 | PMCC payoff shows unbounded loss above short strike | `StrategySandbox.tsx` — diagonal model: `leapIntrinsic - shortCallLoss + credit`; capped at `(sStrike-leapStrike)*100+credit` |
| ✅ FIX-12 | `setStrikeManual` undefined ref in delta slider `onValueChange` | `StrategySandbox.tsx` — replaced with `setSandboxStrike(0)` |
| ✅ TF-50 | Phase 6: Strategy Selector with Live Metrics | Backend: `GET /api/options/strategy_metrics` — BS pricing at Δ0.20 for PCS/CSP/PMCC/IC/Diagonal; regime score 0–5; recommended flag. Frontend: `StrategySelector` component in TradeBuilderPage Step 3 for new/add modes |
| ✅ TF-60 | Phase 7: Conditional Alerts backend | `app/routes/conditional_alerts.py` — CRUD on `conditional_alerts.json`; evaluate endpoint checks spot/P&L/DTE/delta; `/api/action-queue/summary` cached badge count |
| ✅ TF-61 | Phase 7: Sidebar badge uses summary endpoint | `App.tsx` — `useActionQueueSummary()` polls `/api/action-queue/summary` every 60s |
| ✅ TF-62 | Phase 7: `SetAlertButton` component | Inline popover with type/threshold/message fields; auto-message generation; toast feedback |
| ✅ TF-63 | Phase 7: Three alert UI surfaces | Briefing TopOrders (triggered alerts as rows + inline SetAlertButton), Portfolio TickerAlertsPanel (per-ticker list + snooze/delete), Trade Builder Step 6 (post-order alert suggestions) |
| ✅ TF-64 | Phase 7: Alert evaluation in APScheduler | `scheduler/runner.py` — in-process `_evaluate_conditional_alerts()` every 5min market hours, 30min off-hours/weekends |
| ✅ TF-65 | Phase 7: Evaluate Alerts in Scripts tab | `run.py` — `alert_eval` in-process entry; `ScriptsPage.tsx` — metadata + Run button |

## Carried Over — Still Active

| ID | Priority | Item | Notes |
|---|---|---|---|
| TF-12 | Medium | PMCC sub-clustering in Portfolio | Deferred |
| V4-F07 | Medium | Split SettingsPage.tsx (1,700+ lines) | Deferred |
| V4-F08 | Medium | Split AnalysisPage.tsx (1,470+ lines) | Deferred |
| V4-F10 | Low | Frontend unit tests | Deferred |
| V4-F11 | Low | MySQL migration alerts/journal | Deferred |
| V4-IBKR-CHAIN | Low | IBKR chain strikes month format + secdef/info verification | Deferred |
