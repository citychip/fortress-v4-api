# Parapet v5 — Redesign Proposal
**Date:** 2026-06-03 | **Status:** Draft for review | **Scope:** Sprint 13–15 roadmap

---

## 1. Strategic Context

Parapet's architectural premise is correct and should be preserved without compromise: Claude is the workflow engine; Parapet is the display and approval layer. This split is not a limitation — it is a deliberate design decision that keeps the frontend lean, maintainable, and fast-iterating.

The implication is that everything a user can ask Claude to do stays with Claude. Trade staging, scenario planning, morning briefing narration, strike selection, roll proposals — these belong in conversation, not in the UI. What belongs in Parapet is everything that benefits from persistent, glanceable, auto-refreshing display: portfolio state, P&L, pending orders awaiting approval, market regime context, system health, and configuration management.

The v4 dashboard (`fortress-v4-frontend`) demonstrates what happens when the frontend accumulates workflow logic: 159 files, ~50 dependencies, a full Express/tRPC/Drizzle/MySQL stack proxying a Python API that already handles everything. That complexity exists because v4 was built before Claude was the primary interface. Parapet must not repeat that trajectory.

**What stays Claude-only:**
- Trade Builder / leg construction (`stage_order` MCP tool)
- Morning briefing narration (`get_briefing` + Claude synthesis)
- Roll proposals and stop-loss evaluation (`get_roll_all`, `evaluate_roll`)
- Strike selection and pre-trade gates (`pretrade_check`, `options_greeks`)
- Scenario planning and post-earnings playbook
- Candidate deep-dives and strategy selection

**What belongs in Parapet:**
- Portfolio state at a glance — positions grouped by ticker/strategy, delta, DTE, NLV%
- P&L summary — unrealized/realized, by ticker, cross-checked against summary
- Pending orders — visual queue, approve/decline without touching Claude
- Market regime — SPY intel, regime score, earnings blackout calendar
- IV rank summary — per-universe-ticker IVR table (on-demand, not polling)
- System management — settings, alerts, scripts, universe, infrastructure

---

## 2. Current State Assessment

Parapet v1.1 (as of 2026-06-02) has five pages and is fundamentally sound. The architecture — React/Vite, CSS custom properties, three dependencies (react, react-dom, wouter), hand-rolled components — is the right call and should not change.

The gaps that matter for trading use are:

**Already fixed in Sprint 12:**
- Auto-refresh polling (30s Overview, 5m Portfolio/Market, 15s Orders)
- Near-expiry position flagging (DTE ≤ 7 = red, ≤ 14 = yellow) in Overview and Portfolio
- P&L cross-check (by-ticker sum vs summary total, with discrepancy warning)
- Module-level 30s GET cache in `api.ts`
- Type interfaces for five core shapes (BriefingData, PositionData, PnLData, OrderData, AlertData)
- IV Rank summary table in QuantData tab
- SystemPage split into components

**Remaining gaps for Sprint 13:**
- The intermittent `Cannot read properties of undefined (reading '0')` crash — origin unclear, needs investigation
- Candidates page is entirely absent — no passive way to monitor IVR without asking Claude
- No per-ticker deep dive display — if you want to see MSFT's net Greeks in one glance you have to ask Claude or navigate to the Legs tab and filter mentally
- The Overview positions table lacks the net theta column that PortfolioPage's StratRow already computes — useful information left off the at-a-glance view
- The Actions section in Overview just dumps the raw `briefing.actions` array with no urgency ordering or actionable structure

---

## 3. Proposed Page Structure

Five pages remain the right number. The proposal is to restructure and improve within that count rather than add pages.

| # | Page | Route | Primary purpose |
|---|---|---|---|
| 1 | Overview | `/` | Morning pulse: Net Liq, regime, active alerts, positions summary, near-expiry banners, IBKR health |
| 2 | Portfolio | `/portfolio` | Full position detail: strategy groups, legs, P&L, exposure, beta, journal |
| 3 | Market | `/market` | Regime context: SPY intel, earnings calendar, IV rank universe scan, QuantData status |
| 4 | Orders | `/orders` | Pending-order approval queue — the only write surface besides System |
| 5 | System | `/system` | Six tabs: Strategy · Settings · Alerts · Scripts · Infrastructure · Universe |

A sixth page — **Candidates** — is the most valuable missing addition. It warrants its own route rather than another tab in Market, because it's a distinct workflow step (scanning for entries) not a market context view.

| 6 | Candidates | `/candidates` | Read-only IVR screener: ranked list from `/api/candidates`, pre-trade gate status, earnings blackout, concentration state |

---

## 4. Per-Page Detailed Specification

### 4.1 Overview — Action-first redesign

**Current:** Net Liq stat bar → near-expiry banner → active alerts card → positions table → infrastructure dots → briefing actions card.

**Problem:** The Actions card at the bottom is the most time-sensitive section but lives last. The positions table is a useful summary but uses raw `getPositions()` which returns legs — the grouping logic is re-implemented inline rather than sharing the PortfolioPage's `groupTickerLegs` function. The stat bar omits net theta despite it being available from `getBriefing().greeks.portfolio_theta`.

**Proposed layout:**

1. **Stat bar** — Net Liq, Available, Δ portfolio, Θ/day, VIX, Regime, Pacing. Add theta from `briefing.greeks.portfolio_theta` (field already exists in the backend response). Color-code: theta green = income collecting, red = paying.

2. **Priority Actions banner** — rendered *before* positions, sourced from `briefing.actions`. Instead of dumping the raw array, parse the action type and render urgency-classified rows:
   - `type: "roll"` → amber row with ticker, strategy, reason
   - `type: "stop_loss"` → red row
   - `type: "new_entry"` → blue row
   This mirrors the Action Queue concept in TRADE_FLOW_REDESIGN.md but purely as display — no deep-link routing needed since Claude handles execution.

3. **Near-expiry banner** — keep as-is (already implemented well).

4. **Active alerts** — keep as-is.

5. **Positions summary table** — simplify. The current inline grouping logic (40+ lines) duplicates PortfolioPage. Extract a shared `groupByTicker()` utility to `src/lib/positions.ts` and use it in both pages. In the Overview table, show: Ticker | Strategy badge | Next Expiry + DTE | Net Δ | NLV% | Alert state. Add a "Θ/day" column using `netOf(legs, 'current_theta') * 100` — already computed in PortfolioPage's `StratRow` but not surfaced here.

6. **Infrastructure** — keep as-is (StatusDots are clean and informative).

**API calls:** `getBriefing()` + `getIbkrStatus()` + `getAlerts()` + `getPositions()`. All four already called; no new endpoints needed. Polling: 30s background (already implemented).

---

### 4.2 Portfolio — Polish, not rebuild

The Portfolio page is the most complete page in Parapet. The PositionsTab with `groupTickerLegs()` and `StratRow` is well-designed — the strategy pattern recognition (IC, PMCC, BPS, STR) correctly handles the actual book (MSFT PMCC, GOOGL BPS, META IC, TSM Strangle, V PCS).

**Remaining improvements:**

**Positions tab — add concentration warning to ticker header.** The `TickerSection` header already shows NLV% but doesn't flag it. Add inline coloring: NLV% > 50 = red (MSFT at 99% should be red), 20–50 = amber. This makes the MSFT concentration visible without asking Claude.

**Positions tab — show OTM buffer on short legs.** For BPS short puts, the buffer between current price and short strike is the most operationally relevant number. The backend `positions.py` has `short_strike` in the response. Compute buffer as `((price - short_strike) / price * 100)` where price comes from `getBriefing().account` or a lightweight per-ticker price fetch. For now, surface the raw short strike alongside a manual buffer note in the strategy description — the delta already signals proximity (delta -0.432 on the GOOGL BPS Jun26 = ⚠ ITM, already handled by `isItm` check in `BPS` branch).

**P&L tab — add forward P&L card.** Add `getForwardPnl()` as a fifth promise in the load call (it's already in `api.ts`). Display it as a simple card showing max profit, current P&L%, and days remaining per active position. The endpoint is `/api/options/forward-pnl` — this is the "what happens if I close now vs hold to expiry" data that v4's `ForwardPnLPanel` component renders. In Parapet, a simple table suffices: Ticker | Max Profit | Current Value | % Captured | DTE.

**Exposure tab — no changes needed.** Sector exposure and beta-by-ticker are rendered correctly and the data is clear.

**Journal tab — add timestamp display fix.** Currently shows `toLocaleDateString()` which omits time. Change to `toLocaleString()` with `{dateStyle:'short', timeStyle:'short'}` for better log readability.

**API calls:** `getPositions()` + `getPnl()` + `getSectorExposure()` + `getPortfolioBeta()` + `getJournal()` + `getForwardPnl()` (add). Polling: 5m background (already implemented).

---

### 4.3 Market — Add Candidates intel, keep structure

The Market page has three tabs: Market Intel, Earnings Calendar, and QuantData. All three are functional. The IVRankSection in the QuantData tab (load-on-demand, parallel fetches via `/api/qd/iv-rank/{ticker}`) is the most useful new addition from Sprint 12.

**Market Intel tab improvements:**

The current implementation fetches `getMarketIntel()` which calls `/api/market-intelligence` (defaults to SPY). This returns `regime.overall`, `regime.score`, `dp_floor`, `gex_call_wall`, `gex_put_wall`, `flip_level`, and `regime.signals[]`. The signals array rendering is good. What's missing is a signal about the current entry gate state — the regime score from `market_intelligence.regime.score` is shown, but there's no explicit "Entry gate: OPEN / CLOSED" badge derived from it. Add a prominent gate badge: `regime.score > 0 → green ENTRIES OPEN`, `regime.score ≤ 0 → red ENTRIES BLOCKED`. This is the most important single number for the morning workflow (Strategy §7 regime filter).

**Earnings Calendar tab — no changes needed.** DTE-sorted, status-colored, fetch-on-demand — correct.

**QuantData tab — known issues callout is correct.** The hardcoded `BROKEN_TOOLS` set for `exposure_by_strike` and `volatility_skew` should be updated once the GitHub issue is resolved and those tools confirm per-ticker functionality.

**API calls:** `getMarketIntel()` + `getCalendar()` + `getQuantDataReports()` + `getUniverse()`. Polling: 5m background (already implemented).

---

### 4.4 Orders — Minor UX improvement only

The Orders page is functionally complete. 15s polling catches staged orders promptly. The OrderCard component renders legs clearly with BUY/SELL coloring, limit price, quantity, notes, and max loss.

**One improvement:** Add a "Preview" section. When Claude stages an order, `preview_order()` has already been called and the IBKR whatif result (equity impact, margin, commission) is available as order metadata. If `order.preview` (or equivalent field) is populated, surface it in the OrderCard before the Approve/Decline buttons: "Equity impact: -$X | Commission: $Y | Margin: $Z". This gives the approver confirmation data without needing to re-run the preview in Claude.

Check the `PendingOrderCreate` model in `orders.py` — it stores `pop`, `max_profit`, `max_loss` at staging time. These are already rendered (`max_loss` is shown). Add `pop` (probability of profit): if `order.pop != null`, show "PoP: {(order.pop*100).toFixed(0)}%" in the header row. For the current GOOGL BPS roll (order id `75b3b3a0`), this would show PoP: 79% from the staging notes.

**API calls:** `getPendingOrders()`. Polling: 15s background (already implemented). Mutations: `approveOrder()` + `declineOrder()` (both implemented, invalidate cache on call).

---

### 4.5 Candidates — New page (Sprint 13)

This is the most impactful addition not yet built. Currently there is no way to passively monitor IVR candidates in Parapet — the user must ask Claude to run `get_candidates()` or `refresh_iv_data()`. A read-only candidates table fills this gap.

**Data source:** `GET /api/candidates` — already exists, already in use by v4's CandidatesPage. The response is `{ as_of, source, rows: CandidateRow[] }` where each row includes:
- `ticker`, `ivr`, `current_iv`, `hv20`, `spread_pp`, `price`, `signal`
- `can_trade` (boolean — gates: exclusion + earnings + concentration)
- `earnings_state` ("blackout" | "approaching" | "clear")
- `concentration_state` ("high" | "moderate" | "low")
- `days_to_earnings`, `concentration_pct`
- `exclusion_reason` if excluded

**Add to `api.ts`:**
```typescript
export interface CandidateRow {
  ticker: string;
  ivr: number | null;
  current_iv: number | null;
  hv20: number | null;
  spread_pp: number | null;
  price: number | null;
  signal: string;
  can_trade: boolean;
  earnings_state: 'blackout' | 'approaching' | 'clear';
  concentration_state: 'high' | 'moderate' | 'low';
  days_to_earnings: number | null;
  concentration_pct: number;
  excluded: boolean;
  exclusion_reason: string | null;
}
export const getCandidates = () =>
  req<{ as_of: string; source: string; rows: CandidateRow[] }>('/api/candidates');
```

**Page layout:** Single table, sorted by `ivr` descending. Columns:
- Ticker (monospace, bold)
- IVR — color-coded: ≥ 50 green, 25–50 amber, < 25 muted; "≥ 25 ✓" threshold marker
- IV% and HV20% — show the spread in pp (`spread_pp`) as a delta badge
- Price — muted, reference only
- Signal — pill badge: PRIME_CRUSH green, GOOD_SPREAD amber, otherwise muted
- Earnings — DTE badge: "blackout" red, "approaching" yellow, "clear" green
- Concentration — "high" red (blocks entry), "moderate" amber, "low" green
- Can Trade — single ✓/✗ icon combining all gates

**Header bar:** Shows `as_of` timestamp (data freshness visible at a glance), a "Refresh IV" button that calls `POST /api/run/iv_crush` (`runScript('iv_crush')`) to trigger `refresh_iv_data()` equivalent, and an IVR threshold indicator ("Entry gate: IVR > 25").

**Filtering:** Two filter buttons above the table — "Tradeable only" (hides blocked rows) and "IVR > 25" (hides low-IV rows). Implemented as client-side state filters on the fetched array. No server-side filtering needed.

**Sidebar entry:** Add "Candidates" nav item to `Sidebar.tsx` with a candidates icon (or use a simple grid icon). Place it between Market and Orders in the nav order.

**Polling:** On-demand only — data is from the IV crush report which runs on demand or on schedule, not live. Show `as_of` so the user knows when the scan ran. A "Refresh IV" button triggers a fresh scan; the table reloads after ~15 seconds.

**This page addresses the morning workflow step:** "Briefing → candidates: `get_candidates()` [fortress] for full-universe IV crush ranking. Pick top 2–3 by IVR and spread." Now that step has a visual, always-available surface without a Claude round-trip.

---

### 4.6 System — No structural changes needed

The six-tab System page (Strategy, Settings, Alerts, Scripts, Infrastructure, Universe) is complete and functional. The split into components (`StrategyTab`, `AlertsSection`, `InfraSection`, `UniverseSection`) happened in Sprint 12.

**Minor improvements only:**

- **Settings tab:** The `ibkr_auth_mode` toggle (iBeam vs OAuth) is implemented. Add a visual reminder in the Infrastructure tab that OAuth activation is pending weekend server restart — surfaced as a status card showing current `auth_mode` and the OAuth consumer key status.

- **Scripts tab:** The 11 scripts list is rendered with Run buttons. Add a "last run" timestamp per script if the backend returns it. The `runScript()` response likely includes a timestamp — check if `run.py` returns it and surface it in the UI.

- **Alerts tab:** Already has full CRUD. No changes needed.

- **Universe tab:** Ticker chips with exclude and add — working. No changes needed.

---

## 5. Design Principles

### Keep exactly as-is

**CSS custom properties for theming.** The current variable set — `--surface`, `--surface2`, `--border`, `--border2`, `--text`, `--muted`, `--accent`, `--green`, `--yellow`, `--red`, `--blue` — is coherent and consistently applied. Do not introduce Tailwind, do not introduce oklch colors (that's v4's system), do not add CSS-in-JS. The current approach renders in a single paint with no flash.

**Zero component library dependency.** The hand-rolled Card, StatRow, TabBar, Spinner, ErrorBanner, Layout, Sidebar components are ~200 lines total and cover every use case. Adding shadcn or Radix would more than double the dependency count for zero user-facing benefit. The v4 dashboard's 20+ Radix packages are a maintenance liability that Parapet avoids by design.

**Three dependencies only (react, react-dom, wouter).** This constraint is load-bearing. Every npm install is a future breaking change, a security advisory, and a decision to make. Defend it.

**Fire-and-forget fetch pattern with `Promise.allSettled`.** The current pattern — fetch all on mount, partial success OK, show whatever arrived — is correct for a monitoring dashboard. React Query's cache invalidation complexity is not needed when 30s polling + a module-level TTL cache covers the use case.

### Improve without breaking the model

**Extract shared utilities.** The `groupByTicker()` logic duplicated between OverviewPage and PortfolioPage should live in `src/lib/positions.ts`. Similarly, the `dte()` helper is defined separately in PortfolioPage and OverviewPage — consolidate into `api.ts` as an exported utility (or `src/lib/utils.ts`).

**Add `CandidateRow` interface** to `api.ts` alongside the existing five typed interfaces. This maintains the type safety pattern established in Sprint 12.

**Consistent error handling.** The `ErrorBanner` + `onRetry` pattern is correctly used on all pages. Keep it. The intermittent `Cannot read properties of undefined (reading '0')` crash should be investigated by adding null guards to all array indexing in PortfolioPage's `groupTickerLegs()` function — the most likely source given it accesses `lc[0]`, `sc[0]` etc. via `.find()` which can return undefined.

### Visual conventions from Strategy v3.8

The strategy document specifies explicit visual conventions that Parapet should mirror:
- Green = within all framework parameters
- Amber = approaching threshold (delta 0.30–0.35, concentration 30–50%, VIX > 25)
- Red = threshold crossed (delta > 0.35, concentration > 50%, DTE ≤ 7)

These are already partially implemented. The delta warning threshold in PortfolioPage's `StratRow` (`Math.abs(netDelta) > 0.35`) matches Strategy §5 exactly. The NLV% warnings at 50% match §7. Preserve this alignment — it means the UI directly reflects the strategy rules.

---

## 6. Implementation Priority

### Sprint 13 — Fix and complete (highest value)

**13-A: Fix the crash.** The `Cannot read properties of undefined (reading '0')` error is the only open defect. Audit PortfolioPage's `groupTickerLegs()` for unsafe array access patterns. Add defensive guards on all `.find()` results before property access. Priority 0 — a crashing dashboard is worse than a missing feature.

**13-B: Add Candidates page.** Implement `CandidatesPage.tsx` with `getCandidates()` API call and the table layout described in §4.5. Add the `CandidateRow` interface to `api.ts`. Add the sidebar entry. Estimated effort: 80–100 lines of new code, zero new dependencies. This is the highest-value addition for the daily workflow — replaces a Claude round-trip with a glanceable table.

**13-C: Overview Actions panel.** Restructure the bottom `briefing.actions` card to render urgency-ordered rows (roll = amber, stop_loss = red, new_entry = blue) instead of a raw JSON dump. The data is already being fetched. Estimated effort: 20–30 lines.

**13-D: Add PoP to OrderCard.** Surface `order.pop` in the Orders page header row. One line of conditional rendering. High information density for near-zero effort.

### Sprint 14 — Enrich display (medium value)

**14-A: Concentration coloring in PortfolioPage.** Color NLV% > 50% red in TickerSection header. Directly reflects MSFT's 99% concentration which is the portfolio's most critical risk parameter. Currently the number is shown but not flagged.

**14-B: Entry gate badge in MarketPage.** Add a prominent "ENTRIES OPEN / ENTRIES BLOCKED" badge derived from `intel.regime.score`. This is the regime gate from Strategy §7 made visually explicit.

**14-C: Forward P&L tab in Portfolio.** Add `getForwardPnl()` call and render as a simple table in the P&L tab. Provides "% of max profit captured" per position — the single most useful number for deciding whether to close early.

**14-D: Shared positions utility.** Extract `groupByTicker()` and `dte()` from PortfolioPage into `src/lib/positions.ts`. Refactor Overview to use it. Reduces code duplication and ensures consistent behavior.

### Sprint 15 — Polish and hardening (lower priority but real value)

**15-A: OAuth status card in Infrastructure.** Show `ibkr_auth_mode` and a status note about OAuth activation. When OAuth activates after the IBKR weekend server restart, this surfaces the transition clearly.

**15-B: Journal timestamp fix.** `toLocaleString()` with time component instead of `toLocaleDateString()`.

**15-C: Last-run timestamp on Scripts tab.** If `/api/run/scripts` returns last_run per script, surface it as a muted timestamp in the script row.

---

## 7. What Not to Build

These v4 features are explicitly superseded by Claude and should never be ported to Parapet:

**Trade Builder.** The `stage_order` MCP tool plus Claude's plain-English leg construction is strictly better — it has natural language input, automatic pre-trade gate execution, confirmation summary, and an audit trail. A UI form cannot match this. v4's 80KB TradeBuilderPage.tsx is a monument to what happens when you try.

**Strategy Sandbox / Scenario Planner.** Claude models scenarios in conversation. The payoff diagram in v4's StrategySandbox (`client/src/components/StrategySandbox.tsx`) exists because there was no other way to evaluate a trade interactively. Now there is.

**Morning Brief workflow page.** The MorningBriefPage.tsx in v4 (with price chart, IV heatmap, IBKR preview, SPY hedge coverage, roll candidates, post-earnings candidates) is entirely replaced by the `get_briefing` MCP prompt. The data is richer in Claude because it synthesizes across multiple endpoints with judgment.

**Persona Editor.** Claude's system prompt handles this. A UI for editing persona config is a self-referential novelty.

**AI Chat Box.** Claude Desktop is the chat interface. Embedding a chat surface in Parapet would create two parallel conversation contexts with no shared state.

**Analysis page (full version).** v4's AnalysisPage has price charts with Bollinger Bands, RSI, MACD, position overlay, GEX wall markers, IV term structure, vol analytics, and a Greeks summary panel. All of this is either available via Claude + QuantData MCP tools, or is a nice-to-have that adds charting dependencies (Recharts) Parapet deliberately avoids. The IV Rank table in Parapet's QuantData tab is the right level of market analysis for a display layer.

**Conditional Alerts system** (as described in TRADE_FLOW_REDESIGN.md). The full conditional alert system with alert types, post-order suggestions, and Action Queue badge integration is a significant build. The current Alerts tab (CRUD for simple alerts) covers the monitoring use case. Complex conditional logic belongs in Claude-initiated workflows, not in a frontend state machine.

---

## 8. Reference: Actual Portfolio Context

The following real positions should be used for testing any UI changes, as they exercise all the strategy group patterns the frontend must render:

| Ticker | Strategy | Display pattern | Key visual signal |
|---|---|---|---|
| MSFT | PMCC (×4 short, ×6 LEAP) | Multiple PMCC rows per ticker | NLV% 99% → red concentration |
| GOOGL | PMCC + BPS | Two strategy rows under one ticker | BPS delta -0.432 → ⚠ ITM badge |
| AMZN | PMCC | Single PMCC row | Normal |
| NVDA | PMCC | Roll pending | Monitor delta 0.398 → amber |
| META | IC | Four-leg IC display | $535P/$550P + $695C/$710C |
| TSM | STR | Two-leg strangle | $390P / $520C |
| V | PCS (×4) | BPS display | Normal |
| AMD | PCS | Near-expiry Jun26 | ≤ 14d yellow badge |
| MSFT | PCS | Near-expiry Jun18 | ≤ 14d yellow badge |
| OST | Stock | Single stock row | Muted display |

The groupTickerLegs() function correctly handles MSFT appearing with both PMCC and PCS legs — they are grouped under the same TickerSection but rendered as separate StratRows (PMCC badge + PCS badge). This multi-strategy-per-ticker display is load-bearing for the actual book and must be preserved.

---

## 9. Summary

Parapet's current implementation is approximately 85% complete for its intended scope. Sprint 12 addressed the most critical infrastructure gaps (polling, cache, types, near-expiry flags, P&L cross-check). The remaining work is additive rather than corrective.

The single highest-value addition is the Candidates page: a read-only IVR screener that replaces a Claude round-trip for the first step of the daily entry workflow. After that, the Overview Actions panel redesign makes the morning briefing output visible without asking Claude. Everything else is incremental polish that improves information density and visual alignment with the strategy rules.

The architectural constraint — three dependencies, no component library, Claude as the workflow engine — should be treated as a hard requirement, not a default to drift from. Every time a new dependency is proposed, the question is whether it provides user-visible value that cannot be achieved with the existing primitives. So far the answer has been no, and it is likely to remain so.
