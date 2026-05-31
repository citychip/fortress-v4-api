# Fortress v4 — Sprint Plan
**Updated:** 2026-05-31 | **Current version:** post-Sprint-10

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
| Sprint 9 | post-50 | Earnings banner, position sizing, journal prompt, mark actioned, config wiring, floor-anchored strikes, Briefing redesign |
| Sprint 10 | post-50 | Custom persona editor, Strategy tab restructure, System rename, sidebar pin, regime tint, Strategy Rules unified |

---

## Sprint 9 — Trade Builder Intelligence ✓ DONE
**Shipped:** 2026-05-31

| ID | Task | Status |
|---|---|---|
| S9-01 | Earnings warning banner (red ≤10d, amber ≤14d/≤21d, before Step 1) | ✓ Done |
| S9-02 | Position sizing suggestion (2% NL rule, clickable chip in Step 4) | ✓ Done |
| S9-03 | Post-trade journal prompt — Step 7 with textarea, POST /api/journal | ✓ Done |
| S9-04 | Mark actioned on Action Queue (✓ button; API snooze for cond alerts, session-dismiss for roll/stop) | ✓ Done |
| S9-05 | Sidebar pin/unpin | Deferred → Sprint 10 ✓ |
| S9-06 | Config → Trade Builder wiring (activeStrategies dim, targetDte sync live, deltaBuffer → strike, profitTarget hint) | ✓ Done |
| S9-07 | Floor/wall-anchored default short strike (snap to DP floor or GEX put wall ±12%, ⚓ label) | ✓ Done |

---

## Sprint 10 — Config Restructure + UX Polish ✓ DONE
**Shipped:** 2026-05-31

| ID | Task | Status |
|---|---|---|
| S10-00 | Sidebar pin/unpin — click Fortress logo, persisted to localStorage | ✓ Done |
| S10-01 | Strategy tab restructured — Trading sub-tab content moved into Strategy (Zones 2+3) | ✓ Done (revised scope) |
| S10-02 | Config → rename "System" in nav + ConfigPage | ✓ Done |
| S10-03 | Keyboard shortcuts | Deferred → Sprint 11 |
| S10-04 | Status bar regime colour tint (red=bearish, green=bullish, amber=neutral) | ✓ Done |
| S10-X1 | Custom persona editor — fork built-ins, edit with override tracking, diff/apply dialog | ✓ Done (added) |
| S10-X2 | Strategy Rules unified — replace slider section with 4-group number-input layout | ✓ Done (added) |

**Sprint 10 scope note:** S10-01b (remove StrategyPage) was replaced by a restructure that keeps StrategyPage but makes it the canonical "how I trade" configuration hub. Settings is now purely technical (Connections + System).

---

## Sprint 11 — Next

| ID | Task | Detail | Priority |
|---|---|---|---|
| S11-01 | Keyboard shortcuts | B→Briefing, P→Portfolio, T→Trade, A→Analysis, C→System, Esc→close panels. useEffect on keydown, ignore when input focused | Low |
| S11-02 | Move PersonaEditorPanel → Settings tab | Currently lives in StrategyPage. When further refactoring happens, move to Settings | Medium |
| S11-03 | Scenario planning (P-04) | Model hypothetical position, see impact on portfolio Greeks/concentration/delta bias before committing | Medium |

---

## Deferred Backlog

| Item | Why deferred |
|---|---|
| Browser notifications for critical alerts | Requires Notification.requestPermission() UX |
| IBKR session auto-tickle (55min) | Daily browser login is acceptable |
| MySQL migration for alerts/journal | JSON files work fine at current scale |
| Frontend unit tests (msw-based) | Full day setup, low immediate value |
| IBKR chain OI (real OI via secdef/info) | Latency cost not worth it; OI=100 placeholder fine |
| Vol analytics panel (P-05) | IV term structure, skew chart — needs QuantData IV history endpoint |

---

## Guiding principles

- **Deep-links first.** Every action (roll, close, new entry, alert) reachable in one click from natural context.
- **Badge = action required.** Only Trade badge counts urgency. Analysis/System badges never warranted.
- **No junk drawers.** Every tab has a single clear purpose. Strategy = how I trade. Settings = technical admin.
- **Backend zero for UI sprints.** If a sprint requires both, split them.
- **Page files stay under 400 lines.** Larger files get split before next sprint.
- **TradeLanding stays.** The active positions + universe candidates landing is the entry point to Trade — do not replace with a minimal empty state.
- **otmBufferColor lives in TechnicalPanels.tsx** — exported, imported by PriceChart. Don't re-inline.
- **StrategySection is the single source of truth** for all strategy parameters. No slider version. Lives in `components/settings/StrategySection.tsx`.
