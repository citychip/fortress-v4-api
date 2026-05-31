# Fortress v4 — Sprint Plan
**Updated:** 2026-05-31 | **Current version:** v8.50

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
| Clustering | post-50 | Sub-clustering: PMCC, PCS, BCS, CCS, IC, STR/STD, CC + % NL column |
| Refactor | post-50 | AnalysisPage 1481→258 lines, SettingsPage 1725→108 lines |

---

## Sprint 8 — Nav Restructure + Portfolio Enhancements
**Goal:** 5-tab nav, eliminate Research tab, fold quick wins into same build pass.

### 8A — Nav restructure (Option A v2)
| Task | Detail |
|---|---|
| Sidebar: remove Research, demote Analysis | 5 items: Briefing · Portfolio · Trade · Analysis · Config. Analysis: no badge, no urgency styling |
| Briefing: add Overview \| Candidates sub-tabs | Candidates = ResearchPage content verbatim. No logic changes — pure relocation |
| Trade: remove TradeLanding, add minimal empty state | ~10 lines inline JSX: ticker dropdown + "Select a ticker to build a trade". Deep-links still land in Builder directly |
| Portfolio: Chart link on each ticker group header | Small chart icon → `/analysis?ticker=X` |
| Redirect `/research` → `/` | `<Navigate to="/" replace />` in Router |
| Redirect `/morning-brief` → `/` + retire MorningBriefPage | Page is 1069 lines, fully duplicated by Briefing post-restructure. Delete file, remove route |

### 8B — Portfolio quick wins (bundle with 8A)
| Task | Detail |
|---|---|
| Intraday P&L column on sub-cluster rows | Add `daily_pnl` from Position type. Color: green > 0, red < 0, dim = null. Slot after MV column |
| P&L summary stat on Portfolio header | Add day P&L + unrealized P&L as stat chips next to Total Mkt Val. Removes need to sub-tab into P&L for a quick check |
| Technical panels collapsed by default in Analysis | BollingerBandsPanel, RsiPanel, MacdPanel start collapsed. Click header to expand |

### 8C — Architecture (bundle with 8A)
| Task | Detail |
|---|---|
| Code splitting with React.lazy | Lazy-load AnalysisPage, SettingsPage, MorningBriefPage (if kept). Trivial after page splits. Cuts initial bundle ~400KB |
| 30s summary poll during market hours | `useActionQueueSummary`: detect market hours (9:30–16:00 ET) and use 30s interval, 60s otherwise |

**Estimated size:** 1 session  
**Risk:** Low — pure UI restructuring, zero backend

---

## Sprint 9 — Trade Builder Intelligence
**Goal:** Make Trade Builder smarter about risk, earnings, and post-trade actions.

| Task | Detail | Priority |
|---|---|---|
| Earnings warning banner | Prominent banner at top of Trade Builder when earnings < 14d (PMCC) or < 10d (PCS/CSP). Shows before Step 1. "⚠ MSFT earnings in 8 days — PMCC caution, PCS blocked" | High |
| Position sizing suggestion | In Step 4 risk calculator: "Suggested: N contracts (X% NL / $Y margin)" based on `excess_liq`, `net_liq`, `strategy.maxSingleNamePct`, and current ticker concentration. Read-only hint, user can override | High |
| Post-trade journal prompt | After "Add to Pending Orders": Step 7 offers a pre-filled journal entry (ticker, strategy, strikes, credit, date). One-click confirm or skip. Same pattern as post-order alerts in Phase 7 | High |
| "Mark actioned" on Action Queue rows | Snooze button on each Briefing Action Queue row. Hides for 4h (stored in sessionStorage). Prevents re-checking noise after acting on a roll/close | Medium |
| Sidebar pin/unpin toggle | Click the Fortress logo to lock sidebar expanded. State in localStorage. Removes hover-to-expand UX friction | Medium |

**Estimated size:** 1 session  
**Risk:** Low — all frontend, builds on existing patterns

---

## Sprint 10 — Config Restructure + UX Polish
**Goal:** Fix the Config junk-drawer problem, add keyboard navigation.

| Task | Detail | Priority |
|---|---|---|
| Move Strategy out of Config | Strategy (delta target, roll DTE, IVR minimums, signal mode) moves to Portfolio header as a collapsible "Strategy Rules" panel — trading params belong near positions, not admin. Config keeps: Settings, Scripts, Monitor | High |
| Config sub-tabs rename | After Strategy removal: Config becomes "System" — Settings · Scripts · Monitor. Three coherent admin tools | Medium |
| Keyboard shortcuts | `B` → Briefing, `P` → Portfolio, `T` → Trade, `A` → Analysis, `C` → Config, `Esc` → close panels. `useEffect` on keydown, ignore when input focused | Low |
| Status bar regime color | Regime text already colored. Add subtle background tint to the regime chip (red bg for Bearish, green bg for Bullish) for faster at-a-glance parsing | Low |

**Estimated size:** Half session  
**Risk:** Low

---

## Deferred Backlog

| Item | Why deferred |
|---|---|
| Browser notifications for critical alerts | Requires `Notification.requestPermission()` + permission UX. Valuable but not daily workflow |
| IBKR session auto-tickle (55min scheduler job) | Low priority — daily browser login is acceptable friction |
| MySQL migration for alerts/journal | JSON files work fine at current scale |
| Frontend unit tests (msw-based hooks) | Full day setup cost, low immediate value |
| IBKR chain OI (real OI via secdef/info per strike) | Adds latency, placeholder OI=100 is fine for roll scoring |

---

## Guiding principles

- **Deep-links first.** Every action (roll, close, new entry, alert) should be reachable in one click from its natural context. Never require the user to re-select something they already selected.
- **Badge = action required.** Only the Trade badge counts urgency. Analysis and Config badges are never warranted.
- **No junk drawers.** Every tab has a single clear purpose. If something doesn't have a clear home, it probably doesn't need a tab.
- **Backend zero for UI sprints.** UI restructuring never requires backend changes. If a sprint requires both, split them.
- **Page files stay under 400 lines.** Anything larger gets split before the next sprint.
