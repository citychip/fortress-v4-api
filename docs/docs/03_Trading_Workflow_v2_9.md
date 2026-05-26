# Fortress Trading Workflow

**Version 2.9.0 — May 18, 2026**

Daily operating procedure for the Fortress V3 dashboard. This document describes what to do and when; the *why* lives in Strategy v3.7. The dashboard automates the data-gathering; this document governs the decisions.

**v2.9.0 changes from v2.8.0:** Updated for Fortress V3 React/tRPC frontend. QuantData credential refresh now via Settings → QuantData Credentials (no SSH required). Candidates All-tab now shows full 19-ticker universe. Market Intelligence page now has sort dropdown, per-card refresh, and metric tooltips. chart.py deprecated tool IDs removed — no more 400 errors on QuantData calls. References updated to Strategy v3.7.

---

## 1. Pre-Session Checklist (09:00–09:35 ET)

### 1.1 System Health

Open the Fortress Dashboard at `http://76.13.138.194:3000`. Verify:

- **Header status bar:** All three indicators (IBKR, SPY, VIX) are green or amber. A red IBKR badge means the gateway is disconnected — resolve before proceeding (see `operations/04_Incident_Recovery_Playbook.md` §2).
- **QuantData data freshness:** If the IV Rank Heatmap shows "no data" for all tickers, credentials have expired. Refresh via **Settings → QuantData Credentials** (see Playbook §5). Do not trade without QuantData data on entry days.
- **IBKR sync:** Navigate to the Dashboard tab. Verify the last sync timestamp is within the last 5 minutes. If not, click **Sync Now** or use the MCP: *"Sync IBKR."*

### 1.2 Morning Preflight (The Triad)

Run all three checks before looking at candidates. The triad determines whether today is a **management day** or an **entry day**.

**Check 1 — Briefing:**
Open the Dashboard tab. Review:
- Available Funds vs €17K floor
- Portfolio Delta vs ±200 target
- Concentration: MSFT must be <50% NetLiq. If breached, today is a management day regardless of signals.

**Check 2 — SPY Hedge Coverage:**
Navigate to Positions → SPY Hedge section. Target: $22K–$33K notional in SPY puts. If below $22K, add hedge before any new entries.

**Check 3 — Calendar:**
Check the Calendar tab for earnings on positions held. If any major position has earnings within 7 days, evaluate whether to close or reduce before the event.

**Pass criteria for entry day:** No stop-loss in `ACT` state, no earnings today on major positions, no hedge breach worse than already known, MSFT concentration <50%.

---

## 2. Market Open (09:35–10:00 ET)

Do not trade the first 30 minutes. Let overnight orders clear and opening volatility settle.

Monitor Net Drift on the Market Intelligence page to establish the opening flow bias. A strongly negative Net Drift in the first 30 minutes (even on a gap-up) is a warning sign.

---

## 3. Intraday Workflow

### 3.1 Macro Regime Validation (Entry days only)

Navigate to **Market Intel** (`/market-intel`). Use the **Sort dropdown** to order tickers by **Score ↓** (most bullish first).

For SPY specifically:
- Check the **GEX Flip Zone** — is the current price above or below it?
  - Above = positive gamma regime (stable, mean-reverting, dips bought)
  - Below = negative gamma regime (volatile, trend-following, selling accelerates)
- Check **Net Drift** — is options flow confirming the price direction?
- Check **DP Floor** — where is the nearest institutional support?

Hover over any metric box to see the tooltip explaining what the metric means.

### 3.2 Candidate Screening

Navigate to **Trade → Candidates** (`/trade`).

The **All tab** shows all 19 universe tickers:
- **Top section:** Actionable signals (STRONG_SELL, SELL, WATCH) with full candidate cards.
- **Below the "Universe — Monitoring (N)" divider:** Non-actionable tickers in compact monitoring rows.

The **Actionable tab** shows only STRONG_SELL/SELL signals.
The **Watch tab** shows only WATCH signals.

For each candidate with IVR > 50 and no earnings in the next 21 days:
1. Click the ticker to open the Analysis page for chart context.
2. Navigate to **Market Intel** and use the **per-card refresh button** (`↺`) to get the latest data for that ticker.
3. Check GEX walls for strike anchoring (short call strike near GEX call wall = resistance; short put strike near GEX put wall = support).
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

### 3.4 Strike Selection

Use the structural levels from Market Intelligence to anchor strikes:
- **Short call:** Target GEX call wall or first chart resistance above current price (7–10% OTM).
- **Short put:** Target GEX put wall or nearest heavy DP floor (5–8% OTM).
- Verify with the Analysis page chart overlay showing DP floors and GEX levels.

### 3.5 Position Management (Ongoing)

Check open positions for:
- **DTE ≤ 7:** Roll or close.
- **Short call delta ≥ 0.35:** Roll up/out.
- **Stop-loss breach (200% of credit):** Mechanical close — no exceptions.
- **Profit target (80% of credit):** Close early.

Use the MCP for roll evaluation: *"Evaluate roll on {TICKER} position."*

---

## 4. Post-Close (16:00–16:30 ET)

### 4.1 Journal

Log all trades placed today. Include:
- Strategy reasoning (why this ticker, why this strike, what the structural levels showed)
- Pre-trade gate results
- Any overrides and the justification

MCP: *"Log today's AMD PMCC entry to the journal: [reasoning]."*

### 4.2 EOD Review

For any position where mark-to-market changed more than 50% today:
- Run `evaluate_stop_loss` to check if the stop threshold is now closer.
- Run `evaluate_roll` to check if a roll is warranted.

### 4.3 Alerts

Set or update stop-loss alerts for any new positions entered today.

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

1. Dashboard → **Settings** → **QuantData Credentials** → **Update Credentials**
2. Open [v3.quantdata.us](https://v3.quantdata.us) → DevTools → Network → filter `core-lb-prod`
3. Copy `authorization` and `cookie` header values from any request
4. Paste into the Settings form → **Save Credentials**
5. Re-run IV Crush workflow:
   ```bash
   ssh ubuntu@76.13.138.194
   cd /home/ubuntu/Fortress_Dashboard && source venv/bin/activate
   python3 quant/workflow_05_iv_crush_report.py
   ```

Full procedure: `operations/04_Incident_Recovery_Playbook.md` §5.

---

## Document History

| Version | Date | Changes |
|---|---|---|
| 2.9.0 | 2026-05-18 | Fortress V3 React frontend. QuantData credential refresh via Settings UI. Candidates All-tab full universe. Market Intel sort/refresh/tooltips. chart.py fix noted. Strategy v3.7 references. |
| 2.8.0 | 2026-05-13 | Trade Reports tab. Phase 8 UX improvements. |
| 2.7.0 | 2026-05-09 | Security section. `use_ibkr_web_api` / `use_quantdata` toggles. |
| 2.6.0 | 2026-05-05 | MCP workflow integrated. Bearer token. CP Gateway primary. |
