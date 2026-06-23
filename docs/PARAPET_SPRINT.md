# Parapet Sprint Planning

_Updated: 2026-06-21_

---

## v2.8 — Sprint 16.1 advisory caution UI (deployed 2026-06-21)

Surfaces the backend advisory layer (`pre_trade_check`/`pretrade_all` → `caution`/`caution_flags` + top-level `market_advisories`). All driven off the existing `getPretradeAll` call — **no new fetch**.

| Change | Files |
|---|---|
| `Advisory`/`PretradeRow`/`PretradeAllData` types; `getPretradeAll` re-typed | lib/api.ts |
| Market-wide amber banner (macro_defer / VIX-term backwardation, rendered only when amber) above the summary bar; per-row `⚠ EX-DIV` chip (shared `Badge`, `tone="yellow"`, tooltip) in the gate cell next to `GateBadge`; `cautionMap` + `marketAdv` state | pages/CandidatesPage.tsx |
| Same market-wide banner (managing positions in a defer/backwardation environment); reuses `getPretradeAll().market_advisories` | pages/TriagePage.tsx |

Design: advisory is **non-blocking** and visually distinct from the red/green hard-gate verdict (amber heads-up only). Verified: `deploy_parapet.sh` green — `tsc` clean, **778 modules**, nginx reloaded.

---

## v2.7 addendum — data-source integrity badge (deployed 2026-06-19)

First item off the 2026-06-18 optimization backlog: **gateway-down integrity guard + source badge**. Backend ships `GET /api/data-integrity` (live IBKR snapshot probe → `live`/`fallback`/`down`, bypassing the false-fresh `staleness` field — see `DATA_SOURCES.md` v1.4). Frontend:

| Change | Files |
|---|---|
| `getDataIntegrity()` + `IntegrityData`/`IntegrityState` types; falls back to `/api/ibkr/capability` if the route isn't deployed yet | lib/api.ts |
| `SourceBadge.tsx` (new) — always-visible top-bar badge (green ● Live / amber ▲ Delayed / red ■ No data); `useIntegrity()` 60s poll hook; `integrityState()`/`headerTint()` helpers; inline dashed "↻ Restart gateway" pill when degraded (full recovery steps on hover) | components/SourceBadge.tsx |
| Layout owns `useIntegrity()`, tints the header bar amber/red on degraded state, passes data to `<SourceBadge>` | components/Layout.tsx |
| Added `src/components/SourceBadge.tsx` to deploy FILES (and so auto-covered by `sync_check.sh`'s Parapet drift check) | deploy_parapet.sh |

Verified: prod `tsc && vite build` clean (777 modules); live route returned `{"integrity":"live","source":"ibkr","spot":746.94}`. Commit `0456102`.

---

## Sprint 13 (complete) — restructure per PARAPET_V25_ANALYSIS.md

Source analysis: `PARAPET_V25_ANALYSIS.md` (full reanalysis, items #78–#93, all approved).
Verified: `tsc --noEmit` clean + `vite build` clean (2026-06-10).

| # | Change | Files |
|---|---|---|
| #78 | **Orders → Triage, read-only.** Pending Orders status table at top of Triage (legs, qty, limit, backend status, IBKR-reported status, age, short id; 15s poll). Approvals happen via Claude/MCP (`approve_order` — needs `FORTRESS_MCP_ALLOW_WRITES=1`). Amber orders badge moved System → Triage (dual badge). `/orders` route now redirects to `/triage`; OrdersPage.tsx deleted | TriagePage.tsx, Sidebar.tsx, App.tsx |
| #79 | Deleted dead pages OverviewPage.tsx + PortfolioPage.tsx (1,772 lines, not routed since v2.0) | — |
| #80 | **`useSettings()` / `useThresholds()`** — Δ watch/act, roll DTE, β-wtd target, IVR min now read from `/api/settings` instead of hardcoded 0.35/0.42/21/320 (fallback defaults preserved) | lib/useSettings.ts (new), PositionCards.tsx, PositionsPage.tsx |
| #81 | Briefing: regime ENTRIES OPEN/BLOCKED banner promoted to top of page; amber pending-orders strip (click → Triage) | BriefingPage.tsx |
| #82 | Positions P&L: backend `/api/pnl` is source of truth; client-side leg math is fallback only (flagged in UI when used) | PositionsPage.tsx |
| #83 | **Shared extraction (−~2,400 lines net):** lib/positions.ts (dte/netOf/parseLocalSymbol/augmentLeg/groupTickerLegs), components/positions/PositionCards.tsx (TickerSection/StratRow/PositionsCardList), components/KV.tsx, components/Badge.tsx, lib/colors.ts | 6 new files; BriefingPage, PositionsPage, MarketPage, TriagePage slimmed |
| #84 | Market Analytics inverted: IV Rank signal board first (scan), row-click loads per-ticker GEX/Skew/Ladder detail below (drill). 22-chip selector removed. QuantData plumbing dropped from Market (already lives in System > Settings > Connections) | MarketPage.tsx |
| #85 | Positions: 6 tabs → 5 (Overview · P&L · Exposure · Risk · Legs). New Overview = grouped strategy cards (shared with Briefing). Limits merged into Risk (forward P&L curve + breakevens with %-from-spot). Trade Report tab removed; exit candidates folded into Triage | PositionsPage.tsx, TriagePage.tsx |
| #86 | Per-page ErrorBoundary — one page render error no longer blanks the app | App.tsx |
| #87 | Briefing event-horizon chip row: earnings within 14d from calendar (+ backend `intel.events` if provided) | BriefingPage.tsx |
| #88 | Market-status chip polls every 60s (was fetch-once-on-mount) | Layout.tsx |
| #89 | Tiered Briefing polling: account/positions/pnl/orders 30s; candidates/intel/hedge/DP/calendar 5 min | BriefingPage.tsx |
| #91 | Modifier-key guard on in-page 1–N tab shortcuts (Ctrl/Cmd/Alt no longer hijacked) | MarketPage, PositionsPage, SystemPage |
| #92 | Two-tier stat bar: NLV/Δ/Θ/Regime large; Available/Excess/Vega/VIX/Pacing compact (`StatRow compact` prop) | StatRow.tsx, BriefingPage.tsx |
| #93 | Typed API payloads feeding logic: RollAllData, StopLossAllData, BetaData, SectorRow, TradeReportData | api.ts |
| — | deploy_parapet.sh: new files added to FILES array + removal step for deleted pages | deploy_parapet.sh |

### v2.5.1 addendum — IV Rank data source replaced (deployed 2026-06-10)

QuantData's `iv_rank` is broken upstream — the ticker argument is ignored entirely (SPX/MSFT/NVDA return byte-identical payloads, verified via MCP). Replaced with backend route `GET /api/options/iv-rank/{ticker}` in `options_analytics.py`:

- **IV computation:** Yahoo's delayed feed zeroes bid/ask and fills `impliedVolatility` with placeholder junk, so the route never reads that column. It back-solves IV from `lastPrice` via Black-Scholes bisection (`_implied_vol`), median of the 5 nearest-to-spot strikes that traded (volume/OI > 0), per side, ~40 DTE monthly preferred, falls through 4 expiries. Verified live: MSFT 31.2% / NVDA 41.4% / AAPL 25.1% / V 24.1% / GE 41.6%.
- **Ranking:** `hv_proxy` (current IV within 52w rolling-HV20 range) until 60 daily snapshots accumulate in `~/fortress-v4-api/data/iv_history.json`, then auto-switches to true IV rank (`iv_snapshots`). Junk values (<1% or >500%) are never stored and purged on load.
- **Parapet:** `getIvRank()` tries the new route, falls back to legacy QD route; rows show a yellow *proxy* tag with snapshot progress tooltip. Commit `e9e9a50`.
- **Known limitation:** GEX and vol-skew routes still read Yahoo's IV column directly — same inversion fix applies, backlog item for Sprint 14.

**Deferred:** #90 (server-side NLV history) — needs a backend snapshot endpoint; Briefing still uses the localStorage stopgap, marked in code.

**Behavior changes to know about:** Briefing Positions section now defaults to *collapsed* (full card view lives at Positions > Overview). Default Positions tab is Overview. Approvals are no longer possible from the UI — use Claude.

---

## Sprint 12 (complete)

| # | Fix | Files |
|---|---|---|
| #73 | QuantData IV Rank table — documented upstream `iv_rank` bug (identical values per ticker when `expiration_date` passed) as a "Known issue" callout; not fixable in Parapet | MarketPage.tsx |
| #74 | Exposure tab β-wtd delta vs target — fixed units mismatch: target changed from 0.35 (per-position option-delta) to 320 (portfolio β-wtd delta, matches System > Strategy "β-wtd target") | PositionsPage.tsx |
| #75 | Vol Skew chart x-axis — switched to `type="number"` with `domain={['dataMin','dataMax']}` + `tickCount={8}` (was crushed one-tick-per-point); added `connectNulls` to bridge put/call gap near spot | AnalyticsCharts.tsx |
| #76 | Journal/Scripts timestamps — new `fmtDateTime()` helper (YYYY-MM-DD HH:MM:SS), replaces locale-dependent `toLocaleString()` | api.ts, SystemPage.tsx, components/system/ScriptsSection.tsx |
| #77 | Merged Market "QuantData" tab into "Analytics" tab as a "Universe Signals (QuantData)" section below the per-ticker GEX/Skew/Ladder view; Market now has 3 tabs (Analytics, Earnings Calendar, Universe) | MarketPage.tsx |
| — | Added `src/components/system/ScriptsSection.tsx` to deploy_parapet.sh file list (was missing) | deploy_parapet.sh |

---

## Current state — Sprint 11 (complete)

All shipped and live at `http://localhost:4000`.

| Sprint | Feature | Files |
|---|---|---|
| 3 | Market status chip (Open/Pre/Closed) | Layout.tsx |
| 3 | Pretrade gate column | CandidatesPage.tsx |
| 3 | Capital efficiency column | CandidatesPage.tsx |
| 3 | P&L history chart | PositionsPage.tsx |
| 3 | Vol Skew + GEX tab | MarketPage.tsx |
| 3 | **Nav redesign** — 6 pages, no tab duplication | App, Sidebar, Layout + 3 new pages |
| 3 | Briefing page | BriefingPage.tsx |
| 3 | Triage sidebar page | TriagePage.tsx |
| 3 | Positions page | PositionsPage.tsx |
| 3 | Market page (Intel → Universe) | MarketPage.tsx |
| 4 | #36 Pending orders amber badge on System | Sidebar.tsx |
| 4 | #37 Collapsible Briefing sections (localStorage) | BriefingPage.tsx |
| 4 | #38 Keyboard shortcuts b/t/c/m/p/s | Layout.tsx |
| 5 | #39 Journal tab in System page | SystemPage.tsx |
| 5 | #40 Vol Analytics tab in Market page | MarketPage.tsx, api.ts |
| 5 | #41 Trade Report tab in Positions page | PositionsPage.tsx, api.ts |
| 6 | #42 IBKR sync button on Briefing | BriefingPage.tsx |
| 6 | #43 Position Limits tab in Positions | PositionsPage.tsx, api.ts |
| 6 | #44 Alerts tab in System | SystemPage.tsx, api.ts |
| 6 | #45 Earnings volatility column on Candidates | CandidatesPage.tsx, api.ts |
| 7 | #46 Legs tab ticker filter | PositionsPage.tsx |
| 7 | #47 Mobile/narrow viewport sidebar | Layout.tsx |
| 7 | #48 Active alerts card on Triage | TriagePage.tsx |
| 8 | #49 Merge Options Analytics + Vol Analytics tab | MarketPage.tsx |
| 8 | #50 Toast notification system | Toast.tsx, ToastProvider, useToast hook |
| 8 | #51 Candidates expandable row (detail panel) | CandidatesPage.tsx |
| 8 | #52 Table sort persistence (localStorage) | Sortable.tsx |
| 9 | #53 Horizontal scroll on Triage alerts table | TriagePage.tsx |
| 9 | #54 In-page tab keyboard shortcuts (1–N keys) | MarketPage.tsx, PositionsPage.tsx, SystemPage.tsx |
| 9 | #55 P&L summary strip on Briefing | BriefingPage.tsx |
| 9 | #56 QuantData IV rank signal board (auto-load, sort, cache) | MarketPage.tsx |
| 9 | #57 Roll P&L column in Triage roll table | TriagePage.tsx, api.ts |
| 9 | #58 Stage trade inline form on Candidates | CandidatesPage.tsx, api.ts |
| 9+ | IV rank localStorage caching (persist after hours) | MarketPage.tsx |
| 10 | #59 Recharts v3 + VolSkewChart/VolSkewSvg → Recharts LineChart (interactive tooltips) | MarketPage.tsx, package.json |
| 10 | #60 ExposureTab: β-wtd delta vs target bar, stacked sector mix, per-sector bars, delta contribution bars | PositionsPage.tsx |
| 10 | #61 Black-Scholes PoP + 1-SD move in Stage Trade form | CandidatesPage.tsx |
| 11 | #62 Earnings volatility calendar (Expected Move + IV Crush Risk columns) | MarketPage.tsx |
| 11 | #63 Briefing NLV delta vs yesterday | BriefingPage.tsx |
| 11 | #64 Triage auto-refresh (60s, pause when hidden, toggle) | TriagePage.tsx |
| 11 | #65 Lazy-load Recharts via React.lazy/Suspense | MarketPage.tsx, components/AnalyticsCharts.tsx (new) |

---

## Sprint 3 — Nav Redesign (complete)

### Nav structure

| Page | Route | Replaces |
|---|---|---|
| Briefing | `/` | Overview + Market Intel + Positions rolled up |
| Triage | `/triage` | Was a tab inside Portfolio |
| Candidates | `/candidates` | Unchanged |
| Market | `/market` | Market Intel tab removed, Universe tab added |
| Positions | `/positions` | Portfolio renamed, Triage removed |
| System | `/system` | Unchanged |

---

## Sprint 4 — Safety + UX polish (complete)

### #36 — Pending orders badge · Sidebar · SAFETY

Polls `getPendingOrders()` every 2 min. Amber badge on System nav when count > 0.

### #37 — Collapsible Briefing sections · BriefingPage

Chevron toggle per section header. State in `localStorage` key `'briefing_collapsed'`.

### #38 — Keyboard shortcuts · Layout

| Key | Destination |
|---|---|
| `b` | Briefing |
| `t` | Triage |
| `c` | Candidates |
| `m` | Market |
| `p` | Positions |
| `s` | System |

Single `keydown` listener in Layout.tsx, ignores input/textarea/select focus.

---

## Sprint 5 — Data coverage (complete)

### #39 — Journal tab · System page

- New "Journal" tab (4th tab in SystemPage)
- Lazy-loads `getJournal()` on tab activate
- Reverse-chronological entry list with timestamps
- Textarea + Post button; cmd+Enter keyboard shortcut
- `addJournalEntry({ note, entry })` on submit
- API: `GET/POST /api/journal` (already existed in api.ts)

### #40 — Vol Analytics tab · Market page

- New 2nd tab in MarketPage ("Vol Analytics"), before Earnings Calendar
- Ticker selector chip bar (SPY first, then universe)
- Key chips: spot price, ATM IV at 0DTE, term slope direction/magnitude
- ATM IV Ladder table: expiry · DTE · ATM strike · call IV · put IV · avg IV · spread
- Full put/call skew SVG chart with spot line and ATM annotations
- API: `getVolAnalytics(ticker)` → `GET /api/options/vol-analytics?ticker=` (added to api.ts)

### #41 — Trade Report tab · Positions page

- New 5th tab in PositionsPage ("Trade Report")
- Macro header: regime badge + stop-alert count + entry count + exit count + refresh button
- Stop-loss alerts table: ticker · strategy · verdict badge (ACT/WATCH/SAFE) · signals · reasons
- Exit candidates table: ticker · action · market value · note
- Entry candidates table: IV rank (color-coded ≥50 green, ≥25 yellow) · days to earnings · concentration % · position state · action badge
- API: `getTradeReport()` → `GET /api/manage/trade_report` (added to api.ts)

---

## Sprint 6 — Portfolio depth + Alerts CRUD (complete)

### #42 — IBKR sync button · Briefing page header

- `⟳ Sync IBKR` button in Layout `action` prop slot on Briefing page only
- Calls `triggerIbkrSync()` (already existed in api.ts at line 334)
- `syncing` state: button shows `⟳ Syncing…` + green color while in-flight
- On success: silently calls `load(true)` to refresh briefing data
- No duplicate api.ts export needed (existing `triggerIbkrSync` reused)

### #43 — Position Limits tab · Positions page

- New 4th tab in PositionsPage: `P&L · Exposure · Forward P&L · Limits · Legs · Trade Report`
- `PositionLimitsTab` component: ticker chip selector (auto-built from loaded positions)
- Passes filtered legs array to `getPositionLimits(ticker, legs)`
- KV cards: Spot · Max Profit · Max Loss · Net Premium
- Breakevens card: each breakeven price + `X% from spot` annotation
- API: `getPositionLimits(ticker, legs)` → `GET /api/options/position-limits?ticker=&legs=` (added to api.ts)

### #44 — Alerts tab · System page

- New 4th tab in SystemPage: `Strategy · Settings · Scripts · Alerts · Journal`
- Lazy-loads `getAlerts()` on first tab activate
- Wires existing `AlertsSection` component (previously unused in Parapet)
- "Add Alert" card: ticker / condition / threshold inputs + Add button
- "Active Alerts" card: list with delete button per entry
- Handlers: `handleAddAlert()` → `addAlert()` then reload; `handleDeleteAlert(id)` → `deleteAlert(id)` then reload
- API: `getAlerts()` / `addAlert(body)` / `deleteAlert(id)` — all existed in api.ts

### #45 — Earnings volatility column · Candidates page

- New `Earn Move` column at right of candidates table
- Background `Promise.allSettled` fetch fires after main candidates + capital-efficiency load
- `earnVolMap: Map<ticker, { implied, avg }>` state populated asynchronously
- Cell renders: implied move in `var(--accent)` color (`±X.X%`) + avg historical in muted (`avg ±X.X%`)
- Gracefully handles null `implied_move_pct` (shows only avg when no liquid options data)
- Non-blocking: table is usable while earnings volatility fills in
- API: `getEarningsVolatility(ticker)` → `GET /api/market/earnings-volatility/{ticker}` (added to api.ts)

---

## Sprint 7 — UX polish (complete)

### #46 — Legs tab filter · PositionsPage

- Text input above the Legs table: `Filter by ticker…`
- Case-insensitive substring match on `ticker` field
- Shows `N of M` count when filter is active
- `✕ Clear` button resets the filter
- Filter applied before sort — sortable state preserved

### #47 — Mobile/narrow viewport · Layout

- `useNarrow(900)` hook: listens to `resize`, returns `true` when `window.innerWidth < 900`
- When narrow: sidebar becomes `position: fixed; z-index: 100`, slides in via `transform: translateX`
- `☰` hamburger button in header (left of title) opens the sidebar
- Semi-opaque backdrop (`rgba(0,0,0,0.45); z-index: 99`) closes the sidebar on click
- Sidebar auto-closes on navigation (watches `loc` from `useLocation`)
- Wide viewport: no change — sidebar renders as before (static)

### #48 — Active alerts on Triage · TriagePage

- `getAlerts()` added to the `Promise.allSettled` fetch in `load()`
- Filters for `state === 'act' | 'watch'` and renders a table card
- Card appears between the ACT stop-loss banner and the Roll Check section
- Columns: State badge · Ticker · Condition · Threshold · Message
- Invisible when no ACT/WATCH alerts (IIFE render pattern)

---

---

## Sprint 8 — Toast, Expandable Rows, Sort Persistence (complete)

### #49 — Merge Options Analytics + Vol Analytics · MarketPage
Consolidated two separate market tabs into one unified "Options Analytics" tab. Ticker selector + GEX chart + Vol Skew chart all in one view.

### #50 — Toast notification system
`Toast.tsx` + `ToastProvider` wrapper in `App.tsx`. `useToast()` hook exposes `showToast(msg, type)`. Auto-dismisses after 3s. Slide-in from top-right. Used by Stage Trade and other actions.

### #51 — Candidates expandable row
Click any candidate row to expand a detail panel. Shows full pre-trade signals, earnings vol details, and Stage Trade form.

### #52 — Table sort persistence (localStorage)
`Sortable.tsx` — `useSortable(storageKey)` hook. Saves sort column + direction to `sort:${storageKey}`. Survives page reload.

---

## Sprint 9 — Triage depth, Market polish, Stage trade (complete)

### #53 — Horizontal scroll · TriagePage
Wrapped active-alerts table in `overflowX: 'auto'` div (roll/stop-loss tables already had this).

### #54 — In-page tab keyboard shortcuts
`1`–`N` keys switch tabs within Market (1-4), Positions (1-6), System (1-5). `keydown` listener ignores input/select/textarea focus.

### #55 — P&L summary strip · BriefingPage
Second `StatRow` under the existing briefing stats. Shows Total P&L / Unrealized / Realized + ▲ Winner / ▼ Loser pulled from `getPnl()` `by_ticker` array. Color-coded green/red by sign.

### #56 — QuantData IV rank signal board · MarketPage
Replaced the static "Tool Capabilities" grid with a live IV rank table. Auto-loads on tab entry. Columns: Ticker · IV Rank · Current IV · 52w High · 52w Low · Call IV · Put IV. Sort toggle (IVR ▼/▲). IV Rank ≥25 = ✓ badge, ≥50 = green. Fixed `* 100` multiplication bug (backend already returns percentages).

**IV rank localStorage caching:** `saveCachedIvr` / `loadCachedIvr` helpers. Saves on every fetch with non-null `iv_rank`. Falls back to cache when live returns null (after hours). Cached rows show at 75% opacity with `M/DD HH:MM` label. Sort also uses cached IVR. Key: `ivr_cache:TICKER`.

### #57 — Roll P&L column · TriagePage
Background `evaluateRoll(ticker)` fires after roll data loads (urgent + warning positions). New "Roll P&L" column: net credit from roll estimate, color-coded green/red/muted.

### #58 — Stage trade inline form · CandidatesPage
"⊕ Stage Trade" button in expanded candidate row. Opens mini-form: strategy selector + target DTE input. Posts to `stageOrder()` → `POST /api/orders/stage`. Success shows toast + ✓ button state.

---

## Sprint 10 — Recharts + Visual Exposure + PoP (complete)

### #59 — Recharts v3 + Vol Skew charts · MarketPage

- `recharts: ^3.0.0` added to `package.json`; deploy script now runs `npm install` before build
- `VolSkewChart` (GEX/Skew view): SVG polyline → Recharts `LineChart` + `ResponsiveContainer`. Call IV (green), Put IV (red), Mid IV (sky). Interactive tooltip. Spot `ReferenceLine`. Removed ~60 lines of manual SVG coordinate math.
- `VolSkewSvg` (IV Ladder view): SVG → Recharts. Merges puts/calls into unified strike data array. Same tooltip/reference pattern.
- `connectNulls` removed (v3 breaking change: null → 0 rather than gap; gaps are correct for skew charts)

### #60 — ExposureTab · PositionsPage

New `ExposureTab` component (replaces inline JSX in the exposure tab):
- **Summary row:** β-weighted delta card (value + target 0.35 context + off-target label), visual delta-vs-target bar, stacked sector mix bar (8 OKLCH colors) with color legend
- **Sector breakdown:** horizontal bar per sector with fill proportional to % of portfolio; notional + ticker list below each bar
- **Delta contribution:** horizontal bar per ticker, green/red by direction, with beta and price annotations
- `SECTOR_COLORS` array defined at module level for consistent palette

### #61 — Black-Scholes PoP · CandidatesPage

Three pure-JS functions added above the page component:
- `normCDF(x)` — Abramowitz & Stegun approximation, no deps
- `calcPoP(spot, strike, dte, ivPct, r=0.045)` → probability stock closes above strike (PoP for short put)
- `calc1SD(spot, ivPct, dte)` → expected 1-SD move in $

Stage Trade form (in `CandidateDetail`) now shows a vol context strip when open:
- Expected 1-SD move: `±$X.XX (±Y.Y%)` — updates live as DTE input changes
- ATM PoP: green >55%, yellow >45%, red <45%

---

## Sprint 11 — Earnings vol, NLV delta, auto-refresh, bundle split (complete)

### #62 — Earnings volatility calendar · MarketPage (Earnings Calendar tab)

- `EarnVolEntry` type + `crushRisk()` helper: PRIME CRUSH (red, implied − avg ≥ 5pp) / ELEVATED (yellow, ≥ 2pp) / NORMAL (green)
- Background `Promise.allSettled` fetch of `getEarningsVolatility(ticker)` for every calendar ticker not in `{no_earnings, past}`, populates `earnVol: Map<ticker, EarnVolEntry>`
- Two new columns on the Earnings Calendar table: **Expected Move** (`±X.X%` implied in accent + `avg ±X.X%` muted) and **IV Crush Risk** (colored badge)
- Reuses existing `getEarningsVolatility` API (no new endpoint)

### #63 — NLV Δ vs yesterday · BriefingPage

- New `nlv_history` localStorage map: `{ 'YYYY-MM-DD': netLiq }`, pruned to last 30 days
- On each successful `getBriefing()` load: looks up the most recent prior-day snapshot, computes `$Δ` and `%Δ`, then saves today's NLV
- New "NLV Δ (1d)" stat in the top `StatRow`, shown only once a prior-day snapshot exists; green/red by sign

### #64 — Triage auto-refresh · TriagePage

- Replaced the fixed 5-minute poll with a 60s interval, gated on `document.visibilityState === 'visible'`
- Extra `visibilitychange` listener triggers an immediate background refresh when the tab regains focus
- `⟳ Auto 60s` / `⏸ Paused` toggle button in the page header (Layout `action` slot); preference persisted to `localStorage` (`triage_auto_refresh`)

### #65 — Lazy-load Recharts · MarketPage

- Extracted `GexChart`, `VolSkewChart`, `VolSkewSvg` (all Recharts-dependent) into new `src/components/AnalyticsCharts.tsx`
- MarketPage now imports them via `React.lazy(() => import('../components/AnalyticsCharts').then(...))`, wrapped in `<Suspense fallback={<Spinner/>}>`
- Removes the static `recharts` import from MarketPage's main chunk — Recharts (~688KB) now loads only when the Analytics tab's GEX/Skew view renders
- `KVChip` / `fmtGex` duplicated locally in the new chunk (small, avoids cross-chunk coupling)

---

## Deploy command

```bash
bash /mnt/c/Users/cityc.000/OneDrive/_Stocks26/2606Fortress/deploy_parapet.sh
```

## Files synced by deploy script (v2.3)

```
src/App.tsx
src/lib/api.ts
src/components/Layout.tsx
src/components/Sidebar.tsx
src/components/Sortable.tsx
src/components/Toast.tsx
src/components/AnalyticsCharts.tsx
src/components/system/UniverseSection.tsx
src/components/system/ConnectionsSection.tsx
src/pages/BriefingPage.tsx
src/pages/TriagePage.tsx
src/pages/PositionsPage.tsx
src/pages/CandidatesPage.tsx
src/pages/MarketPage.tsx
src/pages/SystemPage.tsx
```
