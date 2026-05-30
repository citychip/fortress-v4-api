# Fortress v4 — Trade Flow Redesign Proposal
**Date:** 2026-05-30 | **Status:** Approved for build

---

## Problem Statement

The current 6-tab layout (Briefing → Portfolio → Research → Trade → Analysis → Config) has four UX friction points:

1. **Roll button** on Portfolio navigates to an empty Trade Builder — user must re-select the ticker they just clicked on.
2. **Trade Builder dropdown** shows tickers with no context — no OTM buffer, DTE, delta, or urgency signal.
3. **Analysis and Research** duplicate per-ticker data, creating redundant stops in the workflow.
4. **Strategy Sandbox** lives in Analysis, but belongs in Trade — it's a pre-trade optimiser, not a research tool.
5. **No way to scale into existing positions or enter undeployed universe tickers** from the Trade tab.
6. **Strategy selection is opaque** — no live comparison of available strategies by risk/reward before committing.
7. **Conditional alerts** (price targets, profit thresholds, DTE countdowns) have no UX surface — they exist only in Config and are disconnected from position context.

---

## Revised Tab Architecture

| Tab | Status | Change summary |
|---|---|---|
| Briefing | ★ Redesigned | Add Action Queue panel to Overview |
| Portfolio | ★ Redesigned | Add collapsible groups + deep-link Roll/Close buttons |
| Research | Unchanged | New-entry scanner only (already correct scope) |
| Trade | ★★ Major redesign | Context dropdown, mode selector, roll proposals, sandbox |
| Analysis | Trimmed | Remove sandbox; keep chart + vol |
| Config | Unchanged | — |

---

## Tab-by-Tab Specification

### 1. Briefing — Action Queue panel

Add a persistent **Action Queue** as the first section of the Overview sub-tab.

**Data sources:** `get_roll_all()`, `get_stop_loss_all()`, `get_forward_pnl()`, `get_candidates()`

**Display:** Prioritised rows, ordered by urgency:
- 🔴 Critical — OTM buffer < 5% or stop-loss triggered → Roll or Close
- 🟠 Watch — OTM buffer 5–10% → Monitor
- 🟢 Close for profit — position at ≥80% max profit → Close
- 🔵 New entry — IVR candidate passing pre-trade gate → Enter

Each row shows: ticker, position type, recommended action, key metric (OTM buffer / profit %). One-click **"→ Trade"** button that deep-links with all parameters pre-set.

**Badge:** Action Queue count appears as a badge on the sidebar Briefing icon, visible from any tab.

---

### 2. Portfolio — deep-link wiring + collapsible groups

**Collapsible position groups:**
- Grouped by ticker + strategy (e.g. MSFT PMCC = one card)
- Header shows: net delta, concentration %, strike range, expiry, alert state dot
- Expanded: individual legs with per-leg delta, DTE, market value
- Summary bar (PMCC): net theta/day, unrealised P&L, roll threshold

**Roll button** → navigates to:
```
/trade?ticker=MSFT&mode=roll&leg=aug21_475c
```
Trade tab receives ticker, leg ID, mode. Zero re-selection.

**Close button** → navigates to:
```
/trade?ticker=MSFT&mode=close&leg=aug21_475c
```
Order preview pre-populated with the close order.

---

### 3. Research — no change

Scope is already correct: IVR scanner, candidates list, pre-trade gate. Each candidate row has a **"→ Trade"** button that deep-links with `mode=new`.

Per-ticker depth (chart, vol) is not duplicated here — it lives in Trade as context and in Analysis as research.

---

### 4. Trade — complete redesign

This is the unified order construction hub for all order types: new entry, roll, and close.

**Layout (3 panels):**

#### Top bar
- **Ticker selector** — dropdown showing all universe tickers, split into two groups:
  - *Active positions* (top, ordered by urgency 🔴→🟠→🟢): shows OTM buffer %, DTE, delta, alert state.
  - *Undeployed universe tickers* (below divider): shows IVR, regime suitability, no active position.
  - Pre-selected on arrival via deep-link.
- **Mode selector** — `New Entry | Add | Roll | Close`. Auto-set from deep-link param. "Add" appears when a ticker with an existing position is selected in New Entry mode.

#### Left panel — proposal / sandbox
- **Roll mode:** System fetches IBKR options chain for the ticker, evaluates roll candidates, and presents **3 proposals**:
  - Conservative — wider strike, shorter extension, smaller credit
  - Balanced — recommended option, best credit-to-risk ratio
  - Aggressive — maximum credit, tighter buffer
  - Each proposal shows: new strike, new expiry, net credit/debit, new OTM buffer %, new delta, DTE change.
- **New Entry / Add mode:** System presents a **strategy selector** with live metrics for each available strategy (PMCC, PCS, naked put, diagonal). For each strategy: estimated credit, required margin, max risk, probability of profit, IVR suitability score. User selects a strategy; sandbox loads it. System flags preferred strategy based on current IVR + regime but does not force the choice. In Add mode, the existing position is shown as context and the sandbox models the combined result (existing legs + new leg).
- **Close mode:** Shows current position value, profit %, and close order details.
- **Strategy Sandbox** (moved from Analysis): pre-loaded with selected proposal. User adjusts sliders (strike, expiry, qty) to optimise. Payoff diagram updates live.

#### Right panel — live options chain (collapsible)
- IBKR options chain for the selected ticker and relevant expiry.
- Allows manual strike selection if user disagrees with proposals.
- Shows bid/ask, delta, IV, OI for each strike.

#### Bottom bar — order preview + queue
- Live order preview: legs, quantities, estimated credit/debit, margin impact.
- **Add to Queue** → sends to order queue (same queue as before).
- Order queue tab remains inside Trade.
- **Set follow-up alerts** — optional step after building an order. System pre-suggests relevant alerts (e.g. profit target, delta breach, DTE countdown) based on the strategy. User confirms or adjusts.

---

### 5. Conditional Alerts — new system

Alerts are forward-looking triggers that feed back into the Action Queue when fired. They are set from three surfaces and managed in Portfolio and Config.

**Alert types:**
- **Price ≥/≤ X** — e.g. "MSFT reaches $450 → consider rolling 475C up"
- **P&L % ≥ X** — e.g. "position at 50% profit → close"
- **DTE ≤ X days** — e.g. "21 DTE → review roll"
- **Delta ≥ X** — e.g. "short call delta exceeds 0.35 → roll threshold breached"
- **Conditional entry** — e.g. "MSFT pulls back to $400 → consider adding LEAP" (appears as 🔵 in Action Queue)

**Where alerts are set:**
1. **Inline recommendations** — any suggestion in Briefing, Action Queue, or chat briefing has a one-click "Set Alert" button. Pre-fills trigger type and value. User confirms in two clicks.
2. **Portfolio position groups** — each group has a collapsible Alerts sub-section showing active alerts with edit/delete. Add button scopes the alert to that position.
3. **Trade tab (post-order)** — after submitting an order, system pre-suggests follow-up alerts (profit target, delta breach, DTE countdown). User confirms or skips.

**When triggered:**
- Alert fires → appears in Action Queue with urgency level and one-click "→ Trade" deep-link.
- Badge count on sidebar increments.
- No separate notifications system required — Action Queue is the single surface.

---

### 6. Analysis — trimmed

**Remove:** Strategy Sandbox (moving to Trade).

**Keep:** Chart, vol analytics, GEX levels, dark pool data, market intelligence synthesis. Becomes a pure research/charting tool accessed via the 🔬 icon from Research or directly via the sidebar.

---

## End-to-End Flows

### Roll flow (from Portfolio)
```
Portfolio: MSFT 475C ⚠️ (0.8% OTM)
  → click Roll
  → /trade?ticker=MSFT&mode=roll&leg=aug21_475c
  → Trade tab: ticker set, mode=Roll, current leg shown
  → system fetches IBKR chain, scores 3 proposals
  → user selects Balanced: "Buy 475C / Sell Sep 500C, net $1.20 credit"
  → sandbox loads proposal, user adjusts if needed
  → order preview confirms legs + credit
  → submit → order queue
```

### Roll flow (from Action Queue)
```
Briefing: Action Queue → MSFT Aug21 475C 🔴 CRITICAL
  → click → Trade
  → same flow as above, one click from morning overview
```

### New entry flow (undeployed universe ticker)
```
Briefing / Research: TSM IVR 87.6 🔥
  → click → Trade
  → /trade?ticker=TSM&mode=new
  → strategy selector: PCS (recommended ✓) vs PMCC vs diagonal — live metrics for each
  → user selects PCS
  → sandbox pre-loaded with suggestion
  → user optimises → submit
  → system suggests follow-up alerts: "Set alert at 50% profit / DTE ≤ 21"
```

### Add-to-position flow
```
Portfolio: NVDA PMCC (1× LEAP, 1× short call)
  → click Add
  → /trade?ticker=NVDA&mode=add
  → existing position shown as context (1× 170C LEAP, 1× 230C short)
  → strategy selector: add LEAP / add short call / add PCS overlay
  → sandbox models combined result (existing + new)
  → submit → set follow-up alerts
```

### Close flow
```
Portfolio: AMD PCS at 77% profit → click Close
  → /trade?ticker=AMD&mode=close&leg=jun26_380p
  → order preview: buy back spread at market/limit
  → confirm → submit
```

---

## Build Order

### Phase 1 — Deep-link wiring (routing fix)
- Add Roll / Close / Add buttons to Portfolio position groups
- Parse `?ticker`, `?mode`, `?leg` URL params in Trade tab
- Ticker dropdown: active positions (with context, ordered by urgency) + undeployed universe tickers below divider
- Mode selector: New Entry / Add / Roll / Close — auto-set from deep-link param
- State reset on ticker/mode change: flush leg, order preview, proposals, and sandbox state (guardrail)
- **No sandbox yet — just correct routing and context**

### Phase 2 — Collapsible position groups
- Portfolio positions grouped by ticker + strategy
- Collapsible cards with aggregate header + leg detail rows

### Phase 3 — Move Sandbox to Trade
- Extract sandbox from AnalysisPage into Trade tab
- Remove from Analysis
- Connect sandbox to selected ticker and mode on arrival

### Phase 4 — Action Queue in Briefing
- Wire `get_roll_all()` + `get_stop_loss_all()` + `get_candidates()` into a prioritised action panel
- Each row deep-links to Trade
- Badge count on sidebar icon

### Phase 5 — Roll alternatives engine
- Backend: fetch IBKR options chain for ticker + expiry range
- Expiry matching: nearest-match to target DTE (e.g. 45d), rounded to highest-OI monthly/weekly cycle (guardrail)
- Score candidates: net credit, new OTM buffer, delta, DTE extension
- Return top 3 as Conservative / Balanced / Aggressive
- Frontend: display proposals, connect selected proposal to sandbox

### Phase 6 — Strategy selector (New Entry / Add modes)
- For each available strategy (PMCC, PCS, naked put, diagonal): compute estimated credit, margin, max risk, PoP, IVR suitability score using live data
- Display as a comparison panel; flag recommended strategy based on current IVR + regime
- In Add mode: show existing position as context; sandbox models combined result

### Phase 7 — Conditional alerts system
- Backend: `/api/action-queue/summary` — lightweight cached endpoint returning alert count integer (60s cache)
- Alert types: price ≥/≤, P&L %, DTE ≤, delta ≥, conditional entry
- Frontend surfaces: inline "Set Alert" button on any recommendation; Portfolio position group alerts sub-section; post-order alert suggestion step in Trade tab
- Triggered alerts feed into Action Queue with urgency level and "→ Trade" deep-link
- Badge count on sidebar polls `/api/action-queue/summary` only (not full recalculation)

---

## Notes

- All order types (roll, close, new entry, add, conditional entry) flow through the same order queue.
- Roll proposals are based on live IBKR options chain data + strategy rules (min OTM buffer, max delta, credit preference).
- Expiry matching uses nearest-match to target DTE, rounded to highest-OI cycle — never exact-match (guardrail).
- State resets on every ticker/mode change in Trade tab — no stale leg params carry over (guardrail).
- Sidebar badge polls a single cached integer endpoint, not the full portfolio calculation (guardrail).
- The Action Queue replaces the need to manually run `get_roll_all()` each morning — it surfaces automatically.
- Conditional entry alerts (e.g. "add LEAP if MSFT pulls back to $400") appear as 🔵 in Action Queue when triggered.
- Analysis tab remains accessible via sidebar and 🔬 deep-link; it just no longer contains the sandbox.
