# Fortress v4 → Parapet: What to Reuse
**Analysis date: 2026-06-09 | Source: `citychip/fortress-v4-frontend` (port 80)**

---

## Summary

The v4 dashboard is a fully-featured React/TypeScript SPA that has been running and iterated for longer than Parapet. It shares the same backend (same FastAPI at :8081, same auth token). The design language is nearly identical — same dark palette, same OKLCH colors, same monospace-for-numbers philosophy. The main gap is that v4 has a richer set of **analytical components** that Parapet hasn't built yet.

Almost everything in v4 is directly portable. It uses Tailwind + shadcn/ui for layout (vs Parapet's plain CSS vars), but the business logic, API shapes, and data-rendering patterns all translate cleanly.

---

## Design System — Already Aligned

v4 uses a named colour constant module (`client/src/lib/theme.ts`). Parapet uses CSS vars. The actual values are the same palette:

| Parapet CSS var | v4 constant | Value |
|---|---|---|
| `--green` | `GREEN` | `oklch(0.72 0.18 145)` |
| `--red` | `RED` | `oklch(0.65 0.22 25)` |
| `--yellow` / `--amber` | `AMBER` | `oklch(0.78 0.18 85)` |
| `--accent` | `CYAN` | `oklch(0.80 0.15 200)` |
| `--muted` | `DIM` | `oklch(0.55 0.010 258)` |
| `--fg` | `BRIGHT` | `oklch(0.93 0.005 258)` |
| `--surface` | `CARD` | `oklch(0.17 0.010 258)` |
| `--surface2` | `CARD2` | `oklch(0.20 0.010 258)` |
| `--bg` | `BG` | `oklch(0.14 0.010 258)` |

v4 also defines `CARD3`, `FAINT`, `PURPLE`, and `_BG` opacity variants (e.g. `CYAN_BG = 'oklch(0.80 0.15 200 / 10%)'`) — worth adding to Parapet's CSS vars when needed.

v4 uses `font-mono-data` CSS class for every financial number. Parapet uses `.mono`. Functionally the same.

---

## Components Ready to Port (High Value)

### 1. ForwardPnLPanel — `client/src/components/ForwardPnLPanel.tsx`
**What it does:** Interactive P&L simulator inside a position row. Three sliders: target price (±30% of avg strike), target date (today → nearest expiry), IV adjustment (0.3× to 2.0×). Shows P&L-at-target badge + full P&L-vs-price Recharts LineChart. IV crush button sets IV to 0.6× to simulate post-earnings. Uses `/api/options/forward-pnl` endpoint.

**Port effort:** Medium. Needs Recharts. The `positionsToLegs()` helper and `LegInput` type also need porting from `PositionLimitsBadge.tsx`. The `/api/options/forward-pnl` endpoint already exists on the backend.

**Where to add in Parapet:** Inside the expandable row on `PositionsPage.tsx` (legs tab).

---

### 2. VolAnalyticsPanel — `client/src/components/VolAnalyticsPanel.tsx`
**What it does:** Three tabbed sub-panels using Recharts:
- **IV Skew chart** — call IV (green) vs put IV (red) by moneyness, spot ATM line
- **Term Structure chart** — ATM IV % vs DTE, dots at each expiry
- **ATM IV Ladder table** — per-expiry: call IV / put IV / avg / spread

**Port effort:** Low. Self-contained, uses same `/api/options/vol-analytics?ticker=` endpoint already in Parapet's api.ts. Replaces Parapet's current hand-drawn SVG.

**Where to add:** Replace SVG charts in the existing Options Analytics tab on `MarketPage.tsx`.

---

### 3. GreeksBar — `client/src/pages/PositionsPage.tsx` (~line 90)
**What it does:** Portfolio-level greeks card: delta / theta / vega tiles + a visual bias bar (bearish ←→ bullish) reading from beta-weighted delta. Uses data already in Parapet's briefing response (`greeks.*`).

**Port effort:** Very low. Pure display component, all data already fetched.

**Where to add:** Top of the P&L tab or as a header card on `PositionsPage.tsx`.

---

### 4. BetaWeightedDeltaCard — `client/src/pages/PositionsPage.tsx` (~line 175)
**What it does:** Large beta-weighted delta number + per-ticker contribution bar chart. Expandable. Uses `/api/manage/portfolio_beta` (already in Parapet's api.ts as `getPortfolioBeta()`).

**Port effort:** Low. Standalone card, data already available.

**Where to add:** Exposure tab on `PositionsPage.tsx`.

---

### 5. SectorExposureBar — `client/src/pages/PositionsPage.tsx` (~line 225)
**What it does:** Stacked horizontal bar showing NLV % by sector (11 sectors, each color-coded). Hover tooltip per sector. Amber breach badge. Uses `/api/manage/sector_exposure`.

**Port effort:** Low. Clean self-contained component. Endpoint already exists in Parapet's api.ts.

**Where to add:** Exposure tab on `PositionsPage.tsx`, below BetaWeightedDeltaCard.

---

### 6. MiniSparkline — `client/src/pages/DashboardPage.tsx` (~line 55)
**What it does:** 60×24px Recharts sparkline showing last 20 closes, colored green/red by trend direction. Used inline in candidate and position rows.

**Port effort:** Trivial (15 lines). Needs Recharts. Uses `getChartData(ticker)` — endpoint already exists.

**Where to add:** Candidates table rows (next to ticker name) and position accordion headers.

---

### 7. IvRankBar — `client/src/pages/CandidatesPage.tsx` (~line 85)
**What it does:** Visual progress bar + numeric value for IV rank. Colors: red ≥80, amber ≥threshold, grey below. More expressive than a plain number.

**Port effort:** Trivial (10 lines). Direct drop-in for IV Rank column on Candidates and the IV Rank signal board on Market.

---

### 8. IvHvCell — `client/src/pages/CandidatesPage.tsx` (~line 100)
**What it does:** Two-row cell: `39.1% / 22.3%` (IV / HV) on top, `+16.8pp spread` below with color coding. Shows IV richness visually.

**Port effort:** Trivial. Direct replacement for plain IV column on Candidates.

---

### 9. EarningsRow + DteBar — `client/src/pages/EarningsPage.tsx`
**What it does:** Full earnings calendar display — BLACKOUT/APPROACHING/CLEAR/PAST badges, DTE countdown bar, inline confirm/edit. Uses `/api/calendar`.

**Port effort:** Low-medium. Endpoint already in Parapet. The Outlook push feature can be omitted.

**Where to add:** New "Earnings" tab on `SystemPage.tsx` or `MarketPage.tsx`.

---

### 10. PoP Calculator — `client/src/pages/TradeBuilderPage.tsx` (~line 168)
**What it does:** Pure-JS Black-Scholes PoP using Abramowitz & Stegun normal CDF. `calcPoP(price, strike, iv, dte)` returns probability 0–1. Zero dependencies, 25 lines.

**Port effort:** Zero — copy-paste. No imports needed.

**Where to add:** Stage Trade form on `CandidatesPage.tsx` (show "PoP: 72%" next to the strike input).

---

### 11. STRATEGIES array + scoring — `client/src/pages/TradeBuilderPage.tsx` (~line 115)
**What it does:** Typed strategy definitions for CSP, PCS, Strangle, Iron Condor, Jade Lizard with `idealIvr`, `idealDte`, `regimeBias`, `maxProfit`/`maxLoss`. Used to rank strategies for a given ticker/regime.

**Port effort:** Very low. Copy the array + add simple scoring. Improves Stage Trade form to highlight which strategy fits current IV/regime.

---

### 12. ScenarioPlanner — `client/src/components/ScenarioPlanner.tsx`
**What it does:** Add hypothetical trades (ticker + strategy + qty + DTE) and see projected portfolio impact: delta/theta/vega/concentration deltas. Calls `/api/options/scenario-estimate`. Shows before/after metric cards.

**Port effort:** Medium-high. Backend needs `/api/options/scenario-estimate` (not yet in Parapet). Defer to Sprint 11+.

---

### 13. SSE stream hook — `client/src/hooks/useFortressStream.ts`
**What it does:** Subscribes to `/api/stream` (Server-Sent Events) instead of polling intervals. Feeds data into React state via EventSource. Fallback to HTTP on disconnect.

**Port effort:** Medium. Backend `/api/stream` SSE endpoint already exists (confirmed in todo.md). Would eliminate the current 30s polling loops in Parapet.

**Defer to:** Sprint 11+ (polish).

---

## Pages in v4 Not Yet in Parapet

| v4 Page | Route | What it has | Priority |
|---|---|---|---|
| `TradeBuilderPage` | `/trade` | Strategy suggester, PoP calc, roll alternatives panel, expiry finder | High |
| `AnalysisPage` | `/analysis` | Price chart + RSI/MACD/BB, strike overlays, earnings markers, VIX pause zone | Medium |
| `PnLPage` | `/pnl` | Per-leg P&L with sort/filter + history chart | Low (Parapet covers it) |
| `EarningsPage` | `/earnings` | Full CRUD earnings calendar | Medium |
| `StrategyPage` | `/strategy` | Persona cards, playbook matrix, parameter sliders, screener | Low (MCP covers it) |

---

## Key API Shape Learnings

v4's `useApi.ts` has the most complete TypeScript types for the backend. Types worth copying:

- **`EarningsHistoryEntry`** — `{ date, eps_actual, eps_estimate, revenue_actual, surprise_pct }` from `/api/calendar/{ticker}/history`
- **`RollProposal`** — `{ strike, expiry, credit, delta, dte, profile }` from `/api/manage/roll_candidates`
- **`LegInput`** — `{ ticker, right, strike, expiry, qty, is_long }` for forward P&L calls
- **`ChartLevels`** — strike lines (short call/put, long put, LEAP) from `/api/chart/{ticker}/levels`
- **`OrderFlowBar`** — from `/api/options/order_flow?ticker=`
- **`PnlHistoryRow`** — `{ date, cumulative_pnl, daily_pnl }` from `/api/manage/pnl_history`

---

## Tech Gaps to Close

| v4 has | Parapet has | Action |
|---|---|---|
| Recharts (LineChart, BarChart, ReferenceLine) | Hand-drawn SVG | `npm install recharts` — unlocks ForwardPnL + VolAnalytics |
| `CARD3`, `FAINT`, `PURPLE`, `CYAN_BG` etc. | Basic CSS vars | Add opacity variants to `index.css` when needed |
| `font-mono-data` for numbers | `.mono` for numbers | Fine as-is, just be consistent |
| SSE live stream | 30s polling | Add later (backend endpoint exists) |

---

## Recommended Sprint 10 Scope

**Session 1 — Charts upgrade**
1. `npm install recharts` in fortress-parapet
2. Port `VolAnalyticsPanel` into `MarketPage.tsx` Options Analytics tab (replaces SVG)
3. Port `MiniSparkline` into Candidates and Positions rows

**Session 2 — Positions depth**
4. Port `GreeksBar` + `BetaWeightedDeltaCard` + `SectorExposureBar` into `PositionsPage.tsx` Exposure tab
5. Port `ForwardPnLPanel` into the expandable leg row on PositionsPage
6. Port `IvRankBar` + `IvHvCell` into Candidates table
7. Add `calcPoP()` to Stage Trade form on CandidatesPage

Each session is a single deploy cycle. No backend changes needed for any of these.
