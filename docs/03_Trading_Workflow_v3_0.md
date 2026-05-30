# Fortress Trading Workflow
**Version 3.0.0 — May 30, 2026**

Daily operating procedure for the Fortress V4 dashboard. This document describes what to do and when; the *why* lives in Strategy v3.7. The dashboard automates the data-gathering; this document governs the decisions.

**v3.0.0 changes from v2.9.0:** Full navigation redesign (v8.21–v8.24). The dashboard now maps the UI directly to the trading workflow — tabs flow left to right through a session. All page references updated. Settings reorganised into sub-tabs. Strategy Sandbox moved to Analyse tab. IBKR gateway controls added to Briefing.

---

## Navigation Overview

The sidebar has 6 primary tabs in workflow order:

| Tab | Path | Purpose |
|---|---|---|
| **Briefing** | `/` | Pre-session hub: account health, macro regime, market intel, earnings |
| **Portfolio** | `/portfolio` | Manage open positions, P&L, trade journal |
| **Research** | `/research` | IV crush candidates, pre-trade gate screening |
| **Trade** | `/trade` | Order builder and execution queue |
| **Analysis** | `/analysis` | Ticker deep-dive, chart levels, Strategy Sandbox |
| **Config** | `/config` | Strategy settings, connections, scripts |

---

## 1. Pre-Session Checklist (09:00–09:35 ET)

### 1.1 System Health

Open the Fortress Dashboard at `http://localhost`. Verify:

- **Header status bar:** All three indicators (IBKR, SPY, VIX) are green or amber. A red IBKR badge means the gateway is disconnected — use the **Briefing → Overview → IBKR panel** (Start/Restart buttons) to resolve. See `operations/04_Incident_Recovery_Playbook.md` §2.
- **QuantData data freshness:** If candidates show "no data", credentials have expired. Refresh via **Config → Settings → Connections → QuantData Credentials**. Do not trade without QuantData data on entry days.
- **IBKR sync:** On the **Briefing** tab (Overview), check the IBKR panel — last sync timestamp should be within the last 5 minutes. If not, click **Sync Now**.

### 1.2 Morning Preflight (The Triad)

All three checks live on the **Briefing** tab. Run them before looking at candidates.

**Check 1 — Account Overview (Briefing → Overview):**
- Available Funds vs $17K floor
- Portfolio Delta vs ±200 target
- Concentration: MSFT must be <50% NetLiq. If breached, today is a management day regardless of signals.
- Weekly pacing: entries used this week vs max 5.

**Check 2 — SPY Hedge Coverage (Briefing → Overview):**
SPY Hedge Coverage bar is visible in the Overview. Target: $22K–$33K notional in SPY puts. If below $22K, add hedge before any new entries.

**Check 3 — Earnings Calendar (Briefing → Earnings tab):**
Switch to the **Earnings** sub-tab within Briefing. Check for earnings on positions held within the next 7 days. If any major position has earnings within 7 days, evaluate whether to close or reduce.

**Pass criteria for entry day:** No stop-loss in `ACT` state, no earnings today on major positions, no hedge breach worse than already known, MSFT concentration <50%.

---

## 2. Market Open (09:35–10:00 ET)

Do not trade the first 30 minutes. Let overnight orders clear and opening volatility settle.

Monitor Net Drift on the **Briefing → Market Intel** tab to establish the opening flow bias. A strongly negative Net Drift in the first 30 minutes (even on a gap-up) is a warning sign.

---

## 3. Intraday Workflow

### 3.1 Macro Regime Validation (Entry days only)

Navigate to **Briefing → Market Intel tab**. Use the **Sort dropdown** to order tickers by **Score ↓** (most bullish first).

For SPY specifically:
- Check the **GEX Flip Zone** — is the current price above or below it?
  - Above = positive gamma regime (stable, mean-reverting, dips bought)
  - Below = negative gamma regime (volatile, trend-following, selling accelerates)
- Check **Net Drift** — is options flow confirming the price direction?
- Check **DP Floor** — where is the nearest institutional support?

### 3.2 Candidate Screening

Navigate to **Research** (`/research`).

The **All tab** shows all universe tickers:
- **Top section:** Actionable signals (STRONG_SELL, SELL, WATCH) with full candidate cards.
- **Below the "Universe — Monitoring (N)" divider:** Non-actionable tickers in compact monitoring rows.

The **Actionable tab** shows only STRONG_SELL/SELL signals.
The **Watch tab** shows only WATCH signals.

For each candidate with IVR > 50 and no earnings in the next 21 days:
1. Click the 🔬 **microscope icon** on the candidate row to jump to the **Analysis** tab with that ticker pre-loaded.
2. On the **Analysis** page, check the chart and use the **Market Intel panel** for GEX walls and DP floors.
3. Use the **Strategy Sandbox** (bottom of Analysis page) to simulate the payoff curve for your chosen strategy.
4. Run the pre-trade gate via MCP: *"Pre-trade check on {TICKER} for {STRATEGY}."*

### 3.3 Pre-Trade Gate (Mandatory)

Before any new entry, the following five gates must all pass:

| Gate | Check | Source |
|---|---|---|
| §3.3 Exclusion | Ticker not in excluded list | `pretrade_check` |
| §4 Earnings Blackout | No earnings within 21 days | `pretrade_check` |
| §7 Concentration | Adding this position won't breach concentration limits | `pretrade_check` |
| §7 VIX | VIX within acceptable range for the strategy | `pretrade_check` |
| §5 LEAP Blackout | Not within 90 days of LEAP expiry on existing position | `pretrade_check` |

A failing gate does not automatically block — but requires explicit acknowledgement before proceeding.

### 3.4 Strike Selection and Sandbox

On the **Analysis** tab (`/analysis?ticker=XYZ`):
- Use the **chart overlay** to identify DP floors and GEX walls visually.
- **Short call:** Target GEX call wall or first chart resistance above current price (7–10% OTM).
- **Short put:** Target GEX put wall or nearest heavy DP floor (5–8% OTM).
- Use the **Strategy Sandbox** (collapsible at the bottom) to simulate the payoff curve, PoP, and theta estimate. Click **Export to Trade Builder** to push the contract parameters directly to the Trade tab.

### 3.5 Order Execution

Navigate to **Trade** (`/trade`).
- **Trade Builder tab:** Contract parameters pre-populated if you used Export from Sandbox.
- Set limit price at mid. Walk up/down patiently — do not pay ask or chase fills.
- Execute after 10:00 AM ET only.
- Review in **Orders tab** after submission.

### 3.6 Position Management (Ongoing)

Navigate to **Portfolio** (`/portfolio`) → **Positions tab**.

Check open positions for:
- **DTE ≤ 7:** Roll or close.
- **Short call delta ≥ 0.35:** Roll up/out.
- **Stop-loss breach (200% of credit):** Mechanical close — no exceptions.
- **Profit target (80% of credit):** Close early.

Use the MCP for roll evaluation: *"Evaluate roll on {TICKER} position."*

---

## 4. Post-Close (16:00–16:30 ET)

### 4.1 Journal

Navigate to **Portfolio → Journal tab**.

Log all trades placed today. Include:
- Strategy reasoning (why this ticker, why this strike, what the structural levels showed)
- Pre-trade gate results
- Any overrides and the justification

MCP: *"Log today's AMD PMCC entry to the journal: [reasoning]."*

### 4.2 EOD Review

Navigate to **Portfolio → P&L tab** for mark-to-market summary.

For any position where mark-to-market changed more than 50% today:
- Run `evaluate_stop_loss` to check if the stop threshold is now closer.
- Run `evaluate_roll` to check if a roll is warranted.

### 4.3 Alerts

Set or update stop-loss alerts for any new positions entered today via MCP or the Portfolio → Positions tab.

---

## 5. Weekly Workflow (Sunday ~18:00 ET)

### 5.1 Full Portfolio Audit

MCP: *"Run a full portfolio audit: briefing, all positions, concentration breakdown, SPY hedge coverage, and current Greeks. Then for each position over 10% of NetLiq, run evaluate_roll and tell me three concrete options to reduce concentration."*

### 5.2 Strategy Review

Use the `review/10_Strategy_Review_Template.md` template. Key questions:
- Is the portfolio delta bias within ±200?
- Is MSFT concentration trending down?
- Is the SPY hedge within the $22K–$33K band?
- Are there any positions approaching the 21-DTE roll window?

### 5.3 Backlog Review

Open `review/11_Todo_Backlog.md`. Identify any P-01/P-02 priority items that can be addressed this week.

---

## 6. QuantData Credential Refresh (When Required)

When IV Rank Heatmap shows "no data" or Candidates shows 0 rows:
1. Navigate to **Config → Settings → Connections tab → QuantData Credentials → Update Credentials**
2. Open [v3.quantdata.us](https://v3.quantdata.us) → DevTools → Network → filter `core-lb-prod`
3. Copy `authorization` (click 👁 to reveal) and `cookie` header values from any request
4. Paste into the Settings form → **Save Credentials**
5. Re-run IV Crush workflow via **Config → Scripts → iv_crush** or MCP: `run_script("iv_crush")`

Full procedure: `operations/04_Incident_Recovery_Playbook.md` §5.

---

## 7. IBKR Gateway Management

The CP Gateway runs as a Docker container (`cp-gateway`). Controls are in **Briefing → Overview → IBKR panel**:
- **Start / Stop / Restart** buttons control the Docker container directly.
- **Sync Now** pulls fresh positions from the live gateway session.
- The gateway requires a **daily browser login** at `https://localhost:5000`.

If the IBKR badge shows red (disconnected): click Restart, then log in via browser, then Sync Now.

---

## Document History

| Version | Date | Changes |
|---|---|---|
| 3.0.0 | 2026-05-30 | Full navigation redesign. Tabs: Briefing · Portfolio · Research · Trade · Analysis · Config. All page references updated. Strategy Sandbox in Analysis tab. IBKR gateway controls in Briefing. Settings sub-tabs. Workflow doc reflects v4 WSL deployment. |
| 2.9.0 | 2026-05-18 | Fortress V3 React frontend. QuantData credential refresh via Settings UI. Candidates All-tab full universe. |
| 2.8.0 | 2026-05-13 | Trade Reports tab. Phase 8 UX improvements. |
| 2.7.0 | 2026-05-09 | Security section. `use_ibkr_web_api` / `use_quantdata` toggles. |
| 2.6.0 | 2026-05-05 | MCP workflow integrated. Bearer token. CP Gateway primary. |
