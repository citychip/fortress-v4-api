# Parapet — Frontend Reference
**v2.9 · Updated 2026-06-21**

> **v2.9 (2026-06-21):** **Standalone risk chips.** (1) Per-ticker **`⚠ EX-DIV`**
> chip in the Positions `TickerSection` header (severity-colored red/amber), driven
> by `getExDiv()` → `assignment_risks` mapped to the short-call ticker (worst
> severity wins). (2) **`LIQ {grade}{spread%}`** chip in the Candidates gate cell,
> driven by `getCheckLiquidity(ticker)` (`liquidity_grade` + `tradeable_status`
> + `tradeable_spread_pct`), fetched **only for tradeable rows** since it hits the
> IBKR chain. New `api.ts`: `ExDivData`/`ExDivRisk`, `LiquidityData`,
> `getExDiv`, `getCheckLiquidity`.

> **v2.8 (2026-06-21, Sprint 16.1):** **Advisory caution UI.** Surfaces the backend
> advisory layer (`pre_trade_check`/`pretrade_all` → `caution`/`caution_flags` +
> `market_advisories`, all from the existing `getPretradeAll` — no new fetch). Two
> pieces: a **market-wide amber banner** (macro_defer / VIX-term backwardation),
> rendered only when amber, at the top of **Candidates** and **Triage**; and a
> per-row **`⚠ EX-DIV`** chip (shared `Badge`, `tone="yellow"`) in the Candidates
> gate cell next to the hard-gate badge, with a tooltip. Kept visually distinct from
> the red/green hard-gate verdict — advisory is non-blocking. New `api.ts` types:
> `Advisory`, `PretradeRow`, `PretradeAllData`.

> **v2.7 (2026-06-19):** New **data-source integrity badge** in the header on every
> page (`SourceBadge.tsx`). A shared `useIntegrity()` hook polls `getDataIntegrity()`
> (→ `/api/data-integrity`, falls back to `/api/ibkr/capability`) every 60s and drives
> three things: the badge itself (green ● Live / amber ▲ Delayed / red ■ No data), a
> **header-bar tint** (amber on fallback, red on down) applied in `Layout.tsx`, and a
> dashed **"↻ Restart gateway"** pill shown inline next to the badge when degraded
> (full `docker restart cp-gateway` / Sync steps on hover). This is the always-visible
> "are the numbers real-time?" signal — it reads the gateway, not the false-fresh
> `staleness` field. New `api.ts` exports: `getDataIntegrity`, `IntegrityData`/
> `IntegrityState` types. Files: components/SourceBadge.tsx (new), components/Layout.tsx,
> lib/api.ts. Tracked in `deploy_parapet.sh` FILES (and so auto-drift-checked by sync_check).

> **v2.6 (2026-06-18):** BriefingPage event-horizon row now consumes the
> catalyst gate's macro events (`getMacroEvents()` → `/api/options/macro-events`)
> with red/amber proximity coloring, plus a new amber "⚠ Catalyst defer" banner
> when `defer_advisory` is true (Strategy §4). TriagePage "Pending Orders" table
> and the Sidebar orders badge now show only **actionable** statuses
> (pending/submitted/failed) via the shared `actionableOrders()` helper in
> `lib/api.ts` — terminal records (expired/declined/filled) are hidden. New
> `api.ts` exports: `getMacroEvents`, `actionableOrders`, `MacroEvent`/
> `MacroEventsData` types. Files: lib/api.ts, pages/BriefingPage.tsx,
> pages/TriagePage.tsx, components/Sidebar.tsx.

---

## What Parapet Is

Parapet is the lean display and approval layer for Fortress. Claude (via MCP) is the primary workflow engine. Parapet = passive monitoring + order approval + settings management. It does not replicate Claude's analytical capabilities.

**Stack:** React 18 · TypeScript · Vite · Wouter · pure CSS (no component library)  
**Port:** 4000 (nginx) · Source: `~/fortress-parapet/src/`  
**Repo:** `citychip/fortress-parapet` (branch: `master`)

---

## Pages (6-page nav, v2.0+)

| Key | Route | Label | Keyboard |
|---|---|---|---|
| `b` | `/` | Briefing | `b` |
| `t` | `/triage` | Triage | `t` |
| `c` | `/candidates` | Candidates | `c` |
| `m` | `/market` | Market | `m` |
| `p` | `/positions` | Positions | `p` |
| `s` | `/system` | System | `s` |

Keyboard shortcuts fire on any keypress outside an input/textarea/select. Handled in `Layout.tsx`.

---

## Page Structure (tabs)

### Briefing `/` — single scroll, no tabs

Full morning dashboard in one page. Tiered polling (#89): account/positions/pnl/orders 30s; intel tier 5 min.

- **Regime banner at top (#81):** ✓ ENTRIES OPEN / ✕ ENTRIES BLOCKED — the first thing on the page
- **Pending-orders strip (#81):** amber, click navigates to Triage
- **Event horizon (#87):** chip row — earnings ≤14d from calendar (+ `intel.events` if backend provides)
- **Header action:** `⟳ Sync IBKR` button — calls `triggerIbkrSync()`, shows `⟳ Syncing…` while in-flight, then refreshes briefing data
- **Stat bar, two tiers (#92):** NLV (+1d Δ) · Δ port · Θ · Regime large; Available · Excess Liq · Vega · VIX · Pacing compact
- **Banners:** limited mode, concentration warnings, PCS exposure, priority actions
- **Market Intel section** (collapsible, localStorage-persisted): SPY/GEX, DP floors, SPY hedge, regime signals
- **Positions section** (collapsible, **default collapsed** since Sprint 13): grouped strategy cards — full view lives at Positions > Overview

### Triage `/triage` — ACT badge (red) + pending-orders badge (amber) in sidebar

Everything requiring a human decision today. 60s auto-refresh (pausable) + 15s pending-orders poll.

- **Pending Orders table (read-only, #78):** legs · qty · limit · backend status · IBKR-reported status · created · short id. Approvals happen via Claude/MCP (`approve_order` / `decline_order`, requires `FORTRESS_MCP_ALLOW_WRITES=1`). Parapet displays state; it does not act. Legacy `/orders` redirects here.
- ACT stop-loss banner (when actCount > 0)
- **Active Alerts card** (when ACT/WATCH alerts exist): State · Ticker · Condition · Threshold · Message
- Roll summary chips + sortable roll table
- Stop-loss summary chips + table (ACT → WATCH → SAFE, sorted)
- **Exit Candidates** (from `trade_report`, #85)

### Candidates `/candidates`

IV scan results. 5-min background poll.

- Sortable table: ticker · IVR bar · signal · gate (PROCEED/BLOCKED) · earnings state · capital efficiency · strategy recommendation · **Earn Move**
- Pretrade gate: PROCEED/BLOCKED derived from `getPretrade(ticker)`
- **Earn Move column:** implied move (`±X.X%` in accent color) + avg historical (`avg ±X.X%` in muted). Populated asynchronously via background `Promise.allSettled` after main load — table is usable immediately.

### Market `/market`

| Tab | Content |
|---|---|
| **Analytics** (default) | **Scan → drill (#84):** IV Rank universe signal board renders first (sortable, cached after hours); clicking a row loads that ticker's GEX & Skew / IV Ladder detail below. Known-issues callout sits between board and detail. QuantData plumbing (status, tool grid, config) lives in System > Settings > Connections, not here. |
| **Earnings Calendar** | Sortable ticker → next earnings → DTE → status → expected move / IV crush risk |
| **Universe** | Tier group management (add/remove/exclude tickers) |

### Positions `/positions`

Analytics for open positions. 5-min background poll. 5 tabs since Sprint 13 (#85).

| Tab | Content |
|---|---|
| **Overview** (default) | Grouped strategy cards (PMCC/IC/BPS/STR badges, Δ/Θ/Mkt Val, DTE, IVR pill) — shared component with Briefing |
| **P&L** | Backend `/api/pnl` as source of truth (#82, client-side fallback flagged) · bar chart · realised history |
| **Exposure** | β-wtd delta vs settings-driven target (#80) · sector mix · Δ contribution by ticker |
| **Risk** | Forward P&L curve per ticker/expiry, IV crush toggle (1.0×/0.6×), max profit/loss/net premium, breakevens with % from spot (absorbed Limits) |
| **Legs** | Sortable raw legs table with alert badge column + ticker filter input |

> Trade Report tab removed — stop-loss alerts live on Triage, entry candidates on Candidates, exit candidates folded into Triage.

### System `/system`

| Tab | Content |
|---|---|
| **Strategy** | Strategy doc (Claude-managed, display only) |
| **Settings** | Sub-tabs: **Connections** (IBKR gateway + sync + OAuth + ping tests) · **Config** (editable settings forms) |
| **Scripts** | Grouped scripts (Morning/Intraday/Evening/Other) + stdout panel |
| **Alerts** | Active alerts list with delete · Add Alert form (ticker / condition / threshold) |
| **Journal** | Reverse-chronological trade notes · textarea + Post button (⌘↵ shortcut) |

---

## Sidebar Badges

| Nav item | Badge | Poll interval | Source |
|---|---|---|---|
| Triage | 🔴 Red — ACT count | 5 min | `getStopLossAll()` → `summary.act + summary.act_immediately` |
| Triage | 🟡 Amber — pending orders (#78, moved from System) | 2 min | `getPendingOrders()` → `orders.length + pending.length` |

---

## Component Map

```
src/
├── App.tsx                    Routes (6 pages, per-page ErrorBoundary #86; /orders → /triage redirect)
├── main.tsx                   Entry point + ErrorBoundary
├── lib/
│   ├── api.ts                 All API calls + types (incl. RollAllData/StopLossAllData/BetaData/TradeReportData #93) + 30s GET cache
│   ├── positions.ts           dte/netOf/fmtStrike/parseLocalSymbol/augmentLeg/groupTickerLegs (#83)
│   ├── colors.ts              Shared verdict/urgency/alert color maps (#83)
│   └── useSettings.ts         useSettings()/useThresholds() — settings-driven thresholds (#80)
├── styles/global.css          CSS custom properties, base styles
├── components/
│   ├── Layout.tsx             Page shell (sidebar + header + refresh + keyboard shortcuts + 60s market chip poll #88; owns useIntegrity() → header tint + SourceBadge, v2.7)
│   ├── SourceBadge.tsx        Data-source integrity badge + useIntegrity() hook + headerTint()/integrityState() helpers + "↻ Restart gateway" pill (v2.7)
│   ├── Sidebar.tsx            6-item nav; Triage carries both badges (ACT red + orders amber, #78)
│   ├── Card.tsx               Surface container
│   ├── StatRow.tsx            Horizontal stat tiles (+ compact tier, #92)
│   ├── KV.tsx                 KV + KVChip stat chips (shared, #83)
│   ├── Badge.tsx              Semantic pill (tones: red/yellow/green/blue/accent/muted, #83)
│   ├── Tabs.tsx               TabBar component
│   ├── Sortable.tsx           useSortable hook + SortTh
│   ├── Spinner.tsx            Loading indicator
│   ├── ErrorBanner.tsx        Error display with retry
│   ├── ErrorBoundary.tsx      React render error containment
│   ├── positions/
│   │   └── PositionCards.tsx  TickerSection/StratRow/PositionsCardList — shared by Briefing + Positions Overview (#83)
│   └── system/
│       ├── StrategyTab.tsx    Strategy display (CLAUDE_ONLY_SECTIONS enforced)
│       ├── AlertsSection.tsx  Alert CRUD (wired into System > Alerts tab)
│       ├── InfraSection.tsx   IBKR status + sync + OAuth detail
│       ├── ScriptsSection.tsx Grouped scripts + stdout panel
│       ├── ConnectionsSection.tsx Ping tests + QuantData status/capabilities panel
│       └── UniverseSection.tsx    Tier groups, remove/exclude/restore
└── pages/
    ├── BriefingPage.tsx       Regime banner + orders strip + event horizon + 2-tier stats + intel + positions (collapsed)
    ├── TriagePage.tsx         Pending orders (read-only) + alerts + roll + stop-loss + exit candidates
    ├── CandidatesPage.tsx     IV scan + gate badges + strategy column + Earn Move column
    ├── MarketPage.tsx         Analytics (signal board → drill-down) + Earnings Calendar + Universe
    ├── PositionsPage.tsx      Overview + P&L + Exposure + Risk + Legs
    └── SystemPage.tsx         Strategy + Settings + Scripts + Alerts + Journal
```

---

## API Layer (`src/lib/api.ts`)

**Module-level GET cache:** 30-second TTL. Write operations (POST/DELETE/PATCH) invalidate the full cache.

**Core types:** `BriefingData` · `IbkrStatusData` · `IntegrityData`/`IntegrityState` · `PositionData` · `PnLData` · `OrderData` · `AlertData` · `CandidateRow` · `IvRankData` · `ForwardPnlData`

**Key endpoints:**

| Function | Endpoint |
|---|---|
| `getBriefing()` | `GET /api/briefing` |
| `getDataIntegrity()` | `GET /api/data-integrity` (→ falls back to `/api/ibkr/capability`) |
| `getPositions()` | `GET /api/positions` |
| `getCandidates()` | `GET /api/candidates` |
| `getIvRank(ticker)` | `GET /api/qd/iv-rank/{ticker}` |
| `getPendingOrders()` | `GET /api/orders/pending` |
| `approveOrder(id)` | `POST /api/orders/pending/{id}/approve` |
| `getSettings()` | `GET /api/settings` |
| `getForwardPnl(...)` | `GET /api/options/forward-pnl` |
| `getPositionLimits(ticker, legs)` | `GET /api/options/position-limits?ticker=&legs=` |
| `getJournal()` | `GET /api/journal` |
| `addJournalEntry(body)` | `POST /api/journal` |
| `getAlerts()` | `GET /api/alerts` |
| `addAlert(body)` | `POST /api/alerts` |
| `deleteAlert(id)` | `DELETE /api/alerts/{id}` |
| `getUniverse()` | `GET /api/universe` |
| `getSpyHedge()` | `GET /api/manage/spy_hedge_coverage` |
| `getDpFloorsGex(ticker)` | `GET /api/chart/{ticker}/levels` |
| `getRollAll()` | `GET /api/manage/roll_all` |
| `getStopLossAll()` | `GET /api/manage/stop_loss_all` |
| `getGex(ticker)` | `GET /api/options/gex/{ticker}` |
| `getVolSkew(ticker)` | `GET /api/options/vol-skew/{ticker}` |
| `getVolAnalytics(ticker)` | `GET /api/options/vol-analytics?ticker={ticker}` |
| `getTradeReport()` | `GET /api/manage/trade_report` |
| `getEarningsVolatility(ticker)` | `GET /api/market/earnings-volatility/{ticker}` |
| `getMarketIntel()` | `GET /api/market-intelligence` |
| `getPcsExposure()` | `GET /api/portfolio/pcs-exposure` |
| `triggerIbkrSync()` | `POST /api/ibkr/sync` |

---

## Auto-Refresh Intervals

| Page / component | Interval | Notes |
|---|---|---|
| Briefing | 30s | Silent background poll |
| Triage | 5 min | Silent |
| Candidates | 5 min | Silent |
| Market | 5 min | Silent |
| Positions | 5 min | Silent |
| Header data-source badge | 60s | `useIntegrity()` in Layout (v2.7) — drives badge + header tint + restart pill |
| Sidebar IBKR dot | 30s | Independent poll |
| Sidebar ACT badge | 5 min | `getStopLossAll()` |
| Sidebar orders badge | 2 min | `getPendingOrders()` |
| Market Vol Analytics | On demand | Load on ticker select |
| Positions Trade Report | On demand | Loads on tab activate |
| Positions Limits | On demand | Loads on ticker select |
| Alerts | On demand | Loads on tab activate |
| Journal | On demand | Loads on tab activate |
| Candidates Earn Move | Background | `Promise.allSettled` after main load |

---

## Positions Rendering (BriefingPage + PositionsPage)

`groupTickerLegs()` groups raw legs client-side:

1. **IC** — short call + long call (above) + short put + long put (below)
2. **PMCC** — long LEAP call (DTE > 90) + short call (higher strike)
3. **BPS** — short put + long put (lower strike)
4. **STR** — short call + short put (same expiry)
5. **LEG** — unpaired remainder

`augmentLeg()` / `parseLocalSymbol()` parses expiry/strike/right from IBKR `local_symbol` when the backend leaves them null.

---

## Collapsible Briefing Sections

State persisted to `localStorage` under key `'briefing_collapsed'` as `{ intel: boolean, positions: boolean }`.

`SectionHeader` component: chevron button (▼ rotates -90° when collapsed) + uppercase label + optional extra string. Conditional rendering (not CSS display toggle) to avoid React key conflicts.

---

## P&L Computation

Client-side in `PositionsPage.tsx` → `PnlTab`:
- Short leg: `pnl = costBasis + marketValue`
- Long leg: `pnl = marketValue - costBasis`
- `costBasis = avg_cost × |qty|`

---

## Sprint Log

Full sprint history (Sprints 1–13) lives in **`PARAPET_SPRINT.md`** — the single source for the per-item log and deploy notes.

**Current: v2.5 · Sprint 13 complete** (Triage read-only orders + MCP approvals, settings-driven thresholds, Positions 5-tab restructure, per-page ErrorBoundary; #90 server-side NLV history deferred to backend).

---

## Design Principles

1. **No component library.** CSS custom properties only.
2. **Three dependencies: react, react-dom, wouter.**
3. **Claude is the brain.** Parapet displays; Claude decides.
4. **500ms builds.** Complexity that extends build time is complexity that slows iteration.
5. **Lazy-load secondary tabs.** Journal, Trade Report, Vol Analytics, Alerts, Limits load on first click.
6. **Responsive.** Sidebar overlays on viewports < 900px; no horizontal scroll on page content.

## What NOT to build in Parapet

Superseded by Claude MCP:
- Trade Builder, Scenario Planner, Persona Editor, Strategy Sandbox, AI Chat Box
- Morning Brief workflow page, Conditional Alerts system, Full charting/analysis page

**`CLAUDE_ONLY_SECTIONS` is a feature, not a bug.**
Strategy parameters (delta targets, profit targets, roll rules) are locked from direct UI editing. Parapet displays; Claude edits via MCP with explicit confirmation.
