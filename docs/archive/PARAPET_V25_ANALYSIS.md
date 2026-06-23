# Parapet v2.4 — Full Reanalysis & Recommendations
**2026-06-10 · Full source read (8,572 lines) + docs/PARAPET.md · Candidate backlog for Sprint 13+**

---

## Verdict

Parapet is in good shape for what it claims to be: a lean display + approval layer with Claude as the brain. The discipline has held — 3 runtime deps, lazy-loaded Recharts, 30s GET cache, `Promise.allSettled` resilience everywhere, localStorage-persisted UI state. The grouped position cards (PMCC/IC/BPS/STR detection) are the best view in the app.

The biggest problem is not a feature gap — it's that **the single most important action in an approval-layer app (approving orders) is hidden on an off-nav legacy route**. Second biggest: ~21% of `src/` is dead code. Third: strategy thresholds are hardcoded in the UI and will silently drift from the settings Claude manages via MCP.

---

## A. Critical findings

### A1. Order approval is buried (highest priority)
`OrdersPage.tsx` is the only place to approve/decline pending orders, but it's off the sidebar — reachable only by typing `/orders`. Worse, the amber "pending orders" badge sits on **System**, and clicking it lands on the System page, which has *no orders tab*. The badge promises something the destination doesn't deliver.

**Recommendation (revised 2026-06-10) — Claude is the approval surface; Parapet shows order status read-only:**
The MCP server already exposes `get_pending_orders` / `approve_order` / `decline_order` / `force_decline_order` / `expire_stale_orders` against the same backend endpoints, so approvals given in Claude are picked up by Parapet on its next poll automatically — the backend is the single source of truth and there is no separate state to reconcile (requires `FORTRESS_MCP_ALLOW_WRITES=1`). Approving in Claude is also strictly better UX: pretrade check → preview → approve in one conversation with full context.

Therefore: put a **read-only Pending Orders section** at the top of Triage — order, legs, age, backend status, and IBKR-reported status — with no approve/decline buttons. Move the amber count onto the Triage badge and delete the legacy `/orders` route. Note the historical pain (stuck `submitted` DAY orders) is post-approval IBKR lifecycle, not the approve action; surfacing IBKR's reported state per order, plus an EOD `expire_stale_orders` habit, addresses it better than any button placement.

### A2. Dead code — delete OverviewPage.tsx and PortfolioPage.tsx
Neither is imported in `App.tsx` or anywhere else (verified by grep). That's 1,772 lines (860 + 912) of stale v1.x code — 21% of src — that still contains old copies of `groupTickerLegs`, P&L logic, and the pre-v2.0 Triage tab. Anyone (including Claude in a future session) greping the codebase will hit stale implementations first. Delete both files; git history keeps them.

### A3. Hardcoded thresholds drift from Claude-managed settings
- `BriefingPage.tsx` `StratRow`: `deltaAct = 0.42`, `deltaWatch = 0.35`, `rollDte = 21` — hardcoded, while the page footer *renders the real values* from `settings.config.alerts`. If Claude updates thresholds via MCP, the per-row ⚑ badges lie.
- `PositionsPage.tsx` `ExposureTab`: `deltaTarget = 320` hardcoded (fixed units in #74, but the value itself should come from settings).

**Recommendation:** one `useSettings()` hook (module-level cached, like the API cache) and thread `alerts.delta_act_threshold`, `alerts.delta_watch_threshold`, `strategy.dte_roll_threshold`, and the β-wtd target through. This is the "Claude is the brain" principle applied to config: Parapet should never embed a strategy constant.

### A4. Two P&L truths
Briefing's P&L strip uses backend `getPnl()`; Positions > P&L computes client-side from legs (`costBasis + mv` / `mv − costBasis`). The two can disagree (backend includes realized, different cost-basis handling), and the user sees both within two clicks. Pick the backend as source of truth on both pages; keep the client calc only as a fallback when `/api/pnl` fails.

---

## B. Layout & information architecture

### B1. Proposed nav (still 6 items)

| Now | Proposed | Change |
|---|---|---|
| Briefing | Briefing | + pending-orders strip, + event horizon (see B2) |
| Triage | **Triage (+ Orders)** | absorbs pending order approval (A1) |
| Candidates | Candidates | unchanged |
| Market | Market | restructure Analytics tab (B3) |
| Positions | Positions | 6 tabs → 4 (B4) |
| System | System | + QuantData plumbing from Market; loses orders badge |

### B2. Briefing — make it answer the three morning questions in order
The page is close. Three adjustments:

1. **Regime banner above the stat bar.** "✓ ENTRIES OPEN / ✕ ENTRIES BLOCKED" is the #1 morning question and currently sits below the fold inside the collapsible Market Intel section. Promote just the banner (one line) to the top; leave the detail in the section.
2. **Pending orders strip.** If `getPendingOrders()` returns anything, show a one-line amber strip ("2 orders awaiting approval → Triage") between the stat bar and banners. The approval layer should surface approvals on its landing page.
3. **Event horizon chip row.** You manage entries around binary events (this week: CPI/PPI gating the AAPL LEAP). The backend already has the earnings calendar + economic context via `trade_report.macro`. A single row — "CPI Wed · PPI Thu · FOMC Jun 16-17 · NVDA earnings 21d" — would have encoded this week's "do NOT enter before PPI" rule visually. Data exists; this is one fetch + one chip row.

Also: `nlv_history` in localStorage is per-browser and lost on cache clear. The backend already has `/api/pnl/history`; persist NLV snapshots server-side (tiny backend addition) and the NLV Δ becomes durable + enables a real sparkline.

### B3. Market — invert the Analytics navigation
The merged Analytics tab now stacks: ticker chip bar (22 chips after the universe expansion — wraps to 3 rows) → GEX/skew or ladder for ONE ticker → divider → QuantData status → IV Rank board → known-issues → "query via Claude" card. That's a scan-target buried under a drill-down.

**Recommendation — scan first, drill second:**
- Make the **universe signal board the top of the tab**: one sortable table — Ticker · IVR (bar) · IV · IV-HV spread · Earnings DTE · Signal. It's the only view that answers "where is premium today?" across 22 names.
- Clicking a row opens the per-ticker GEX/Skew/Ladder detail below it (reuse the existing components; replace the 22-chip selector with row-click + a small search input).
- **Move QuantData plumbing** (connection status, tool count, config path, capability grid) to System > Settings > Connections, where `ConnectionsSection` already lives. Keep only the known-issues callout near the IVR table it discredits.

### B4. Positions — 6 tabs → 4
- **Trade Report tab: remove.** It's a third surface for the same signals — its stop-loss alerts duplicate Triage, its entry candidates duplicate Candidates. Fold "exit candidates" (the only unique content) into Triage as a small third section. The report itself remains a Claude/MCP artifact.
- **Merge Limits into Forward P&L → one "Risk" tab.** Same ticker selector, same position scope, and the KV cards (Max Profit / Max Loss / Net Premium / breakevens) are rendered nearly identically in both today. One tab: selector → KV cards → curve with IV-crush toggle → breakeven chips.
- **Add the grouped card view as tab 1 ("Overview").** The `TickerSection`/`StratRow` cards currently exist only on Briefing. Extract to `components/positions/` (also kills the BriefingPage duplication, see C1), make it Positions' first tab, and default Briefing's positions section to collapsed — Briefing gets shorter, Positions finally shows positions.

Result: **Overview · P&L · Exposure · Risk · Legs**.

### B5. Stat bar hierarchy
Ten equal-weight tiles flatten the signal. Two tiers: NLV (+Δ1d), Δ port, Θ/day, Regime rendered large; Available, Excess Liq, Vega, VIX, Pacing rendered at ~70% size in a second group. Zero new components — just two `StatRow` sizes.

---

## C. Code health (no behavior change)

### C1. Extract duplicated logic
| Duplicated | Locations | Target |
|---|---|---|
| `parseLocalSymbol` / `augmentLeg` | BriefingPage, PositionsPage (+ both dead files) | `lib/positions.ts` |
| `groupTickerLegs` / `StratRow` / `TickerSection` / `PositionsTab` | BriefingPage (+ dead files) | `components/positions/` |
| `KV` / `KVChip` (4 near-identical defs) | BriefingPage, MarketPage ×2, AnalyticsCharts | `components/KV.tsx` |
| Journal UI (two different implementations) | SystemPage `JournalTab` (good) vs OrdersPage (older) | dies with A1 (keep SystemPage's) |
| Badge pill styling (≥10 inline copies) | every page | `components/Badge.tsx` with `tone: 'red'|'yellow'|'green'|'muted'|'accent'` |
| verdict/urgency color maps | TriagePage, PositionsPage TradeReport | `lib/colors.ts` |

Estimated net deletion including A2: **~2,400 lines (−28%)** with zero functional change. This is the cheapest reliability win available.

### C2. Smaller items
- **ErrorBoundary only wraps the app root** — one render error blanks the whole dashboard. Wrap per-page in `App.tsx` (`<Route><ErrorBoundary label="briefing"><BriefingPage/></ErrorBoundary></Route>`); 10 minutes.
- **Market-status chip fetched once on mount** (`Layout.tsx`) — leave the app open through the 9:30 bell and it still says "Pre". Poll every 60s or compute client-side from the existing `isMarketHours()` logic.
- **In-page tab shortcut handlers (1–N)** in Market/Positions/System don't check `e.metaKey/ctrlKey` — Ctrl+1 (browser tab switch) also flips the in-page tab. Add the modifier guard Layout already has. They also re-register identical handlers; harmless, but the `TABS` closure means edits to tab order need both lists touched.
- **Candidates fan-out:** each 5-min load fires `getCandidates` + `pretrade_all` + `capital-efficiency` + N×`strategy_metrics` + 22×`earnings-volatility` ≈ 35–40 requests. Same for the Earnings Calendar tab. A backend `?enriched=1` batch param would cut this to 2–3 requests; until then, lengthen the earn-vol poll (it changes daily, not every 5 min).
- **Briefing polls 11 endpoints every 30s**, but settings / SPY hedge / DP floors / market intel move on minutes-to-hours timescales. Tier it: account+positions+pnl at 30s, the rest at 5 min. Meaningful load cut on the yfinance-backed routes.
- **`api.ts` types:** ~20 endpoints return `any`. The ones feeding logic (rollAll, stopLossAll, tradeReport, beta, sector) deserve interfaces — they're exactly the payloads whose field names you've already guessed wrong once (`net_credit ?? estimated_credit ?? credit_estimate` in TriagePage is the tell).
- Cosmetic: sidebar says "Fortress v5" (backend is v4 line); footer "backend :8081" could show live `/api/health` version instead.

---

## D. What I deliberately did NOT recommend
Per the "What NOT to build" list (Claude supersedes): no trade builder, no scenario planner, no chat box, no charting platform, no conditional-alert engine. Everything above is display, navigation, or plumbing — Claude stays the brain. `CLAUDE_ONLY_SECTIONS` remains untouched.

---

## E. Prioritized backlog (Sprint 13 candidates)

| # | Item | Section | Effort | Impact |
|---|---|---|---|---|
| #78 | Read-only Pending Orders status section in Triage (incl. IBKR-reported status); approvals via Claude/MCP; fix badge target; delete legacy route | A1 | M | ★★★ |
| #79 | Delete OverviewPage.tsx + PortfolioPage.tsx | A2 | XS | ★★★ |
| #80 | `useSettings()` hook; remove hardcoded 0.42/0.35/21/320 | A3 | S | ★★★ |
| #81 | Briefing: regime banner to top + pending-orders strip | B2 | S | ★★☆ |
| #82 | Positions: backend P&L as source of truth | A4 | S | ★★☆ |
| #83 | Extract positions/KV/Badge shared components (−2,400 lines) | C1 | M | ★★☆ |
| #84 | Market: signal board first, row-click drill-down, QD plumbing → System | B3 | M | ★★☆ |
| #85 | Positions: drop Trade Report tab, merge Limits+Forward P&L → Risk, add Overview tab | B4 | M | ★★☆ |
| #86 | Per-page ErrorBoundary | C2 | XS | ★★☆ |
| #87 | Briefing event-horizon chip row (earnings + macro events) | B2 | S | ★★☆ |
| #88 | Market-status chip: poll/compute instead of fetch-once | C2 | XS | ★☆☆ |
| #89 | Tiered Briefing polling (30s core / 5min intel) | C2 | S | ★☆☆ |
| #90 | NLV history server-side (backend + UI sparkline) | B2 | M | ★☆☆ |
| #91 | Modifier-key guard on in-page tab shortcuts | C2 | XS | ★☆☆ |
| #92 | Two-tier stat bar | B5 | S | ★☆☆ |
| #93 | Type the `any` API payloads that feed logic | C2 | M | ★☆☆ |

Suggested Sprint 13 cut: **#78–#83** (the three criticals + the two cheap structural wins). #84/#85 make a natural Sprint 14 since both reshape page internals.
