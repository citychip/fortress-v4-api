# Fortress v4 — Sprint Plan
**Updated:** 2026-05-31 | **Current version:** post-Sprint-8

---

## Completed

| Sprint | Version | What shipped |
|---|---|---|
| Phase 1 | v8.26 | Deep-link wiring — Roll/Close/Add buttons, URL params, mode selector |
| Phase 2 | v8.27 | Collapsible position groups, alert dot, strike range, DTE |
| Phase 3 | v8.28–34 | Strategy Sandbox → Trade tab, GEX/DP overlays, strike inputs |
| Phase 4 | v8.35 | Action Queue in Briefing, sidebar Trade badge |
| Phase 5 | v8.36–40 | Roll Alternatives engine (IBKR live chain + yfinance fallback) |
| Phase 6 | v8.41–43 | Strategy Selector with live metrics (BS pricing, regime score) |
| Phase 7 | v8.44–50 | Conditional Alerts system (CRUD, evaluate, scheduler, 3 UI surfaces) |
| Fixes | v8.41–50 | IBKR chain format + strike window + BS fallback; PMCC sandbox; dedup |
| Clustering | post-50 | Sub-clustering: PMCC, PCS, BCS, CCS, IC, STR/STD, CC + % NL + Day P&L columns |
| Refactor | post-50 | AnalysisPage 1481→258 lines, SettingsPage 1725→108 lines (11 sub-files) |
| Sprint 8 | post-50 | 5-tab nav, Candidates in Briefing, lazy loading, Portfolio P&L chips, Analysis panels collapsed, Chart link, bug fixes |

---

## Sprint 9 — Trade Builder Intelligence
**Goal:** Make Trade Builder smarter about risk, earnings, and post-trade actions.

| ID | Task | Detail | Priority |
|---|---|---|---|
| S9-01 | Earnings warning banner | Prominent banner at top of Trade Builder when earnings < 14d (PMCC) or < 10d (PCS/CSP). Shows before Step 1 | High |
| S9-02 | Position sizing suggestion | In Step 4 risk calculator: "Suggested: N contracts (X% NL / $Y margin)" using excess_liq, net_liq, maxSingleNamePct, current concentration | High |
| S9-03 | Post-trade journal prompt | After "Add to Pending Orders": Step 7 offers pre-filled journal entry (ticker, strategy, strikes, credit). One-click confirm or skip | High |
| S9-04 | Mark actioned on Action Queue | Snooze button on each Briefing Action Queue row. Hides for 4h (sessionStorage). Reduces morning re-checking noise | Medium |
| S9-05 | Sidebar pin/unpin toggle | Click Fortress logo to lock sidebar expanded. State in localStorage | Medium |

**Estimated size:** 1 session | **Risk:** Low

---

## Sprint 10 — Config Restructure + UX Polish
**Goal:** Fix Config junk-drawer, remove legacy pages, keyboard nav.

| ID | Task | Detail | Priority |
|---|---|---|---|
| S10-01b | Remove legacy StrategyPage | StrategyPage.tsx in Config predates Phase 3 — Sandbox is already in Trade. Remove Strategy sub-tab from Config entirely | High |
| S10-01 | Move Strategy settings out of Config | Delta target, roll DTE, IVR minimums, signal mode → collapsible "Strategy Rules" panel in Portfolio header. Config keeps: Settings · Scripts · Monitor | High |
| S10-02 | Config → rename "System" | After Strategy removal: Config becomes "System" — Settings · Scripts · Monitor | Medium |
| S10-03 | Keyboard shortcuts | B → Briefing, P → Portfolio, T → Trade, A → Analysis, C → Config, Esc → close panels. useEffect on keydown, ignore when input focused | Low |
| S10-04 | Status bar regime colour tint | Subtle background on regime chip (red=Bearish, green=Bullish) | Low |

**Estimated size:** Half session | **Risk:** Low

---

## Deferred Backlog

| Item | Why deferred |
|---|---|
| Browser notifications for critical alerts | Requires Notification.requestPermission() UX |
| IBKR session auto-tickle (55min) | Daily browser login is acceptable |
| MySQL migration for alerts/journal | JSON files work fine at current scale |
| Frontend unit tests (msw-based) | Full day setup, low immediate value |
| IBKR chain OI (real OI via secdef/info) | Latency cost not worth it; OI=100 placeholder fine |

---

## Guiding principles

- **Deep-links first.** Every action (roll, close, new entry, alert) reachable in one click from natural context.
- **Badge = action required.** Only Trade badge counts urgency. Analysis/Config badges never warranted.
- **No junk drawers.** Every tab has a single clear purpose.
- **Backend zero for UI sprints.** If a sprint requires both, split them.
- **Page files stay under 400 lines.** Larger files get split before next sprint.
- **TradeLanding stays.** The active positions + universe candidates landing is the entry point to Trade — do not replace with a minimal empty state.
- **otmBufferColor lives in TechnicalPanels.tsx** — exported, imported by PriceChart. Don't re-inline.
