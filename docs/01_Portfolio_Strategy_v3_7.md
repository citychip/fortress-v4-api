# Portfolio Management Strategy
**Version 3.7.3 — May 31, 2026**

v3.7.3 adds §5 and §2C strike anchoring rule (DP floor / GEX put wall), §8 Trade Builder workflow updated to reflect Sprint 9 UI enhancements. Trading rules otherwise unchanged from v3.7.2.

---

## 1. Governance

The decision-maker is you, the trader. AI tools are analytical inputs, not decision sources. When another AI recommends a trade, flag it before executing so it can be evaluated against the active strategy. Before every execution, verify ticker, earnings date, strike direction, and limit price. The framework is flexible — open to any strategy or rotation as long as the trade is profitable and fits the rules below.

---

## 2. Active Strategies

### A. Poor Man's Covered Call (PMCC) — primary

The primary income strategy. The long leg uses LEAPS approximately 640 DTE (Jan 2028 cycle), 25–30% ITM, targeting delta 0.78–0.85. The short leg uses monthly calls 30–45 DTE, delta approximately 0.20, 7–10% OTM. Coverage is strict 1:1 short-to-LEAP ratio — never hold an uncovered LEAP.

### B. Diagonal Spreads — tactical

Structure: long call 30–90 DTE plus short call at shorter DTE. Used for directional tactical plays, not income generation. Decay profile differs from PMCC and requires shorter-horizon monitoring.

#### Post-Earnings Diagonal Playbook (primary use case for Strategy B)

Entry trigger: morning after earnings, when IV crush ≥ 25% AND stock gap within ±8%. Entry timing: place order between 10:00–11:00 AM ET on the day after earnings. Long leg: 30–90 DTE call, delta 0.55–0.70, at or near current price (ATM or slightly ITM). Short leg: 14–21 DTE call, delta 0.25–0.30, at first resistance level above current price. Target net debit: ≤ 50% of the long leg's value. Exit: close the entire diagonal at 50% of max profit, or roll the short leg when it reaches 80% profit. Never enter a new diagonal within 10 days of the next earnings date for that ticker.

### C. Put Credit Spreads — income

Structure: sell OTM put + buy further-OTM put as protection. Short strike: delta 0.15–0.20 (80–85% probability of expiring worthless), anchored below the nearest DP floor or GEX put wall when one falls within 12% of the delta-computed strike. This ensures the short put is sold below structural support — if price holds above the floor, the spread expires worthless. DTE: 30–45 days at entry.

### D. SPY Hedge — protective

Maintain SPY put hedge with market value $20,000–$30,000 USD at all times when total portfolio Net Liq exceeds $50,000. Dashboard enforces this gate: if hedge MV falls below $20,000, new PMCC entries are blocked until the hedge is restored. Hedge MV tracked live from IBKR via CP Gateway.

### E. Jade Lizard — consolidation income

Structure: short OTM call + short OTM put spread (no upside risk, defined downside risk). Use when the underlying is in a consolidation range and IV is elevated. Credit gate enforced by dashboard: total credit received must exceed the width of the put spread. Dashboard validator rejects the structure if this condition is not met.

### 2.5 Source-of-Truth Hierarchy

When sources conflict, the hierarchy is: **this strategy document > tool behavior > memory**. If a tool produces a recommendation that contradicts a rule here, the rule wins. If memory contains a rule that contradicts this document, this document wins. Tools may add safety beyond what this document requires; they may not subtract safety.

---

## 3. Name Universe

### 3.1 Core Holdings (standing instruction)

MSFT is a high-conviction core holding. Concentration above 20% Net Liq is acceptable for MSFT specifically, subject to the High-Concentration Entry Override in §7. All other names follow standard concentration limits.

### 3.2 Approved for New Entries

**Tier 1 — High IV, primary candidates (15 tickers):** MSFT, AVGO, NFLX, VST, GOOGL, AMZN, AMD, MSTR, UNH, APP, LLY, TSM, V, MU, GEV.

**Tier 2 — Moderate IV, secondary candidates (3 tickers):** META, AAPL, NVDA.

**Macro / Index — benchmark and hedge instruments (2 tickers):** SPX, SPY.

Non-tech candidates for future consideration: Healthcare (UNH, LLY), Financials (MS, GS, JPM), Energy (XOM, OXY).

### 3.3 Excluded

Hard exclusions enforced by the dashboard via `ticker_universe.json` `excluded` array:

- **Regulatory risk:** COIN, HOOD, SMCI — until legal clouds clear.
- **PMCC-incompatible:** Small-caps with thin option chains (e.g., LKFN).
- **Ignored entirely:** OST. Display in book if held; never recommend.

### 3.4 Universe as Signal, Not Law

Outside-universe names are explorable when a setup demonstrably exceeds universe candidates. Documentation in the journal is required. All quality filters in §4 still apply. All hard exclusions in §3.3 remain blocked regardless.

---

## 4. Entry Rules

### Timing

Execute after 10:00 AM ET / 16:00 Amsterdam — avoid opening volatility. On Opex Fridays, trade cautiously and expect wider spreads. Wait 3–5 days for IV normalisation after news-driven spikes. Use limit orders at mid, walk up/down patiently. Do not pay ask or chase fills.

### Earnings Discipline

Verify earnings date before every new entry — non-negotiable. No new LEAP entries within 2 weeks of ticker earnings. No new put spreads within 10 days of ticker earnings. Post-earnings IV crush morning (next day) is the preferred LEAP entry window. Entry trigger for post-earnings: IV crush ≥ 25% AND stock gap within ±8%. Hold existing positions through earnings — PMCC is designed for this.

### Quality Filters

Bid/ask spread ≤ 10% of mid on both legs. Open interest > 100 per leg. Underlying daily option volume: > 1K contracts (credit spreads), > 10K (LEAPS preferred). IV Rank: confirm IVR > 25 before entering new premium-selling positions.

---

## 5. Short Call Management (PMCC)

### Strike Selection

Primary rule: delta 0.20–0.25 on short call at entry. GEX/DP override (short calls): if a GEX call wall falls within 12% above the delta-computed strike, prefer a strike just below the wall — price tends to pin at GEX call walls, maximising probability of the short expiring worthless. Chart override: if a strike within the target delta range sits at or just above a well-defined chart resistance level, prefer the chart-aligned strike. Chart undershoot: if the natural delta strike is in clear air, consider moving one strike closer only if the chart shows a clean rejection level there.

For short puts (PCS/CSP): anchor strike $5 below the nearest DP floor or GEX put wall within 12% of the delta strike. The dashboard Trade Builder auto-suggests this level with an ⚓ indicator.

### Management Rules

Take profit at 80%: close short call when value decays to approximately 20% of credit received. Time-based roll rule: if the short call has not reached 80% profit by 14–21 DTE, close it anyway and re-sell a fresh short at 30–45 DTE. Roll up-and-out if the short becomes ITM, targeting net credit. Never roll winners. Never roll losers into earnings. Never roll on strong-underlying days.

### DTE Discipline

Short calls 30–45 DTE at entry. 90+ DTE shorts capture 3–5× less total premium over the holding period. 7–10% OTM for low-IV names. Before selling any short call > 60 DTE: explicitly state the reason and acknowledge theta inefficiency.

### Delta Drift Monitoring

Short call delta drifts upward as the underlying rallies. Monitoring delta after entry is part of active position management.

**Delta thresholds (v3.6):**

| Delta range | Status | Action |
|---|---|---|
| ≤ 0.30 | Normal | No special action required |
| 0.30–0.35 | Approaching ATM | Watch closely; consider rolling on next strong-down day or at next 80% profit |
| > 0.35 | Critical Gamma Risk | Roll up-and-out within the current trading week, or close if rolling for credit is not achievable |

The dashboard reads the critical threshold from `cfg("strategy.delta_critical_threshold")` — tunable in Settings without a code deploy. The threshold was tightened from 0.40 to 0.35 in v3.6 based on operational learning that 0.40 surfaces the position too late.

**Interaction with existing rules:** if 14–21 DTE approaches and delta is > 0.30, prioritise rolling. If delta is > 0.35 AND today is a strong-up day, wait one session then roll. If delta is > 0.35 AND earnings is within 10 days, close instead of roll.

---

## 6. Exit Rules

### Put Credit Spreads

Close at 50% profit. If the spread reaches 21 DTE without hitting the profit target, close it regardless. Never hold a put spread through earnings.

### Jade Lizard

Close the entire structure at 50% of max credit. If the short call is threatened (delta > 0.30), close the call leg first and evaluate the put spread independently.

### LEAPS Profit-Taking

No mechanical profit target on LEAPS — these are long-term positions. Evaluate exit only when: (a) the thesis has changed materially, (b) the underlying has broken the 200-day SMA on strong volume, or (c) concentration has grown to a level that requires trimming per §7.

### LEAPS Stop-Loss / Thesis Break

The 200-day SMA breach is the primary stop-loss signal for LEAPS. A breach is confirmed when: (1) the underlying closes below the 200 SMA on above-average volume, AND (2) the breach is not immediately recovered within 1–2 sessions. On confirmation, close the LEAP. Do not average down into a broken thesis.

---

## 7. Risk Management

### Position Sizing (USD)

Maximum new LEAP cost: $5,000 per position. Maximum total exposure per ticker: 20% of Net Liq (exception: MSFT per §3.1). Maximum sector exposure: 40% of Net Liq.

### Concentration

| Concentration | Status | Action |
|---|---|---|
| < 20% Net Liq | Normal | No restriction |
| 20–50% Net Liq | Elevated | New entries require explicit override |
| > 50% Net Liq | Critical | No new entries; consider trimming |

MSFT exception: concentration above 20% is acceptable given high-conviction thesis, subject to active SPY hedge per §2.D.

### High-Concentration Entry Override

When a ticker is above 20% Net Liq, a new entry requires: (1) explicit acknowledgement of concentration, (2) confirmation that the SPY hedge is in place, (3) confirmation that the new entry does not push the ticker above 50% Net Liq.

### Pacing (Cooling-Off Target)

No more than 2 new positions per week under normal conditions. After a stop-loss event, observe a 3-day cooling-off period before the next new entry.

### Market Regime Filters

The dashboard synthesises a Macro Regime Score from -5 to +5 using SPY GEX walls, dark pool floors, and net drift data from QuantData. New entries are gated when the regime score is ≤ 0 (neutral or bearish). The threshold is configurable via Settings (`regime_entry_threshold`).

| Regime Score | Status | Entry Gate |
|---|---|---|
| > 0 | Bullish / Neutral | Entries permitted |
| 0 | Neutral | No new entries |
| < 0 | Bearish | No new entries |

### Margin Discipline (USD)

Minimum Excess Liquidity: $17,000 USD at all times. Minimum Available Funds: $25,000 USD before any new position. These floors are configurable via Settings (`excess_liq_min_usd`, `available_funds_min_usd`). The dashboard reads live values from IBKR via CP Gateway and blocks new entries if either floor is breached.

### Prohibited Actions

Never hold uncovered LEAPS. Never sell naked puts (credit spreads only — exception: Jade Lizard short put per §2.E). Never use SPY shares for hedging (options only). Never sell puts on names in clear downtrend. Never enter LEAP or put-spread positions on names with active DOJ/SEC investigations.

---

## 8. Workflow

### Before Every New Trade

1. Open the Fortress V3 dashboard → Trade page → Morning Brief for the prioritised action list.
2. Review the Candidates tab: check the Actionable sub-tab for STRONG_SELL/SELL signals, and the Watch sub-tab for borderline candidates. The All tab shows the full 19-ticker universe — actionable signals at top, monitoring rows below.
3. Pull the Market Intelligence page for the target ticker: review GEX Call/Put Wall, Dark Pool Floor/Ceiling, Net Drift, and Directional Bias score. Use the sort dropdown (Score ↓) to identify the strongest setups.
4. Pull the live option chain from IBKR (CP Gateway snapshot).
5. Pull the Clean Decision Chart from TradingView (see §9).
6. Verify the earnings date on the ticker — use the dashboard Earnings page or `earnings_blocklist.json`.
7. Select strikes using real bid/ask/delta data and chart structure.
8. Confirm the structure matches the intended strategy and that all quality filters in §4 are met.
9. Verify limit price direction and magnitude relative to bid/mid/ask.
10. Submit as limit order; work patiently.

### Daily Routine

Morning: open the dashboard Dashboard page — check Net Liq, Excess Liq, Daily P&L, and the Macro Regime Score. Review the Morning Brief for any URGENT STOP-LOSS or NEW_ENTRY signals. Place orders after 10:00 AM ET. Monitor fills; walk limits patiently. End of day: sync IBKR positions via the Sync IBKR button; note any issues in the journal.

### Weekly Routine

Sunday or Monday morning: review Clean Decision Charts (TradingView) for each active LEAP position. Flag any 200-day MA breaks immediately — stop-loss signal inputs per §6. Identify any positions approaching roll windows (14–21 DTE on short calls) via the Portfolio page DTE triage badges. Review the Market Intelligence page for regime shifts across the full universe.

---

## 9. Chart Setup & Review (TradingView Workflow)

Unchanged from v3.5. Clean Decision Chart for strategic decisions; Signal/Timing Chart retained for tactical use. The Analysis page in the Fortress V3 dashboard overlays your open positions directly onto the price chart — short call/put strikes, LEAP entry level, GEX walls, and earnings markers are all visible without leaving the dashboard.

---

## 10. Post-Earnings Entry Playbook

Unchanged from v3.5. Gap × IV crush matrix:

| Gap range | Rule | Verdict |
|---|---|---|
| Gap up > 5% | Missed move, IV will be low | PASS |
| +2 to +5% | Buy if IV crush > 30% | CONDITIONAL |
| Flat ±2% | Buy if IV crush > 25% | CONDITIONAL |
| −3 to −8% | PRIME ENTRY zone (assuming thesis intact) | PRIME ENTRY |
| −8 to −15% | Evaluate fundamentals before entry | EVALUATE |
| Gap down > 15% | Thesis likely broken | PASS |
| IV crush < 20% (any gap) | Premium not crushing — no edge | PASS (override) |

High-concentration filter, execution timing, and put-credit-spread post-earnings rules unchanged.

---

## 11. Current Book Snapshot

Live state in `active_positions.json`. Refreshed via CP Gateway Web API sync (preferred) or OCR upload fallback. The Portfolio page in the Fortress V3 dashboard shows all open legs with live Greeks, alerts, and concentration metrics.

---

## 12. Open Items & Pipeline

Continue MSFT high-conviction concentration, offset by SPY hedge (§2.D) — note current MSFT concentration is 97.1% (above the 20% normal threshold; acceptable per §3.1 MSFT exception with active hedge). Maintain `earnings_blocklist.json` — auto-fetcher available via the Earnings page. Review Settings tab thresholds quarterly — tunable without code deploy. Refresh QuantData credentials via **Settings → QuantData Auto-Login** when session expires. Re-run `workflow_05_iv_crush_report.py` to regenerate Candidates data. QuantData per-ticker proxy fix (QD-01) is pending — `qd_*` MCP tools currently return SPY data for all tickers.

---

## 13. Calendar Events (Next 30 Days)

Live calendar maintained in `earnings_blocklist.json` and visible in the dashboard Earnings page.

---

## 14. Change Log

- **v3.7.3 (May 31, 2026):** §2C and §5 strike selection updated — short put strikes now anchored $5 below nearest DP floor or GEX put wall (within 12% of delta strike). Trade Builder auto-suggests and labels anchored strikes with ⚓. §8 Trade Builder workflow updated: earnings warning banner (red ≤10d, amber ≤14d), position sizing suggestion (2% NL rule), post-trade journal prompt (Step 7), action queue mark-as-done.
- **v3.7.2 (May 29, 2026):** §15.6 tool stack updated — V4 WSL local deployment replaces VPS; yfinance ATM options IV + rolling HV replaces QuantData per-ticker IVR in workflow_01/05; workflow_08 max pain from yfinance options chain; ibind OAuth 1.0a IBKR auth added (pending activation); fortress_mcp.py server-side QD proxy. §12 open items updated with QD-01 known issue.
- **v3.7 (May 18, 2026):** §15.6 tool stack updated — Fortress V3 React/tRPC frontend replaces legacy Python/Jinja dashboard. §8 workflow updated to reference Candidates All-view (full 19-ticker universe with monitoring fallback), Market Intelligence sort/refresh/tooltip enhancements, and QuantData credentials manager in Settings. §15.6 QuantData MCP integration formalised: widget-UUID REST endpoints replace deprecated `tool/OPTIONS_*` calls; `chart.py` fixed (GEX walls, DP levels, order flow now use correct endpoints). §7 Market Regime Filters table added for clarity.
- **v3.6 (May 5, 2026):** §5 Critical Gamma threshold tightened from 0.40 to **0.35**. §7 margin floors normalised to USD. §15.6 tool stack updated — CP Gateway via voyz/ibeam is the live broker integration.
- **v3.5 (May 4, 2026):** §2.D SPY hedge MV tracker enforcement; §2.E Jade Lizard credit gate enforcement.
- **v3.4 (May 1, 2026):** §5 Delta Drift Monitoring; §15.1 Signaling vs. Blocking principle.
- **v3.3 (May 1, 2026):** §2.5 Source-of-Truth Hierarchy; §3.4 Universe as Signal, Not Law; §15 How the Framework is Enforced.
- **v3.2 (Apr 27, 2026):** §7 High-Concentration Entry Override.
- **v3.1 (Apr 24, 2026):** §5 DTE Discipline subsection.
- **v3.0 (Apr 24, 2026):** Definitive merge of v1.2 and v2.1. Added Strategy E (Jade Lizard). Added §10 Post-Earnings Entry Playbook.
- (Earlier) v1.0–v1.2 covered initial PMCC + diagonals + put credit spreads; merged into v3.0.

---

## 15. How the Framework is Enforced

### 15.1 Signaling vs. Blocking

No tool blocks a trade. Tools warn; humans decide. Discipline is a human responsibility, not a software-enforced state. Every button in the dashboard is technically clickable; every script can be overridden; every alert can be dismissed.

**What tools do:** surface relevant data (IV/HV spread, dark pool floors, earnings dates, concentration percentages); flag rule conflicts visually — amber for warnings, red for critical conditions; pre-fill recommended actions for human review; log decisions and outcomes; refuse to execute actions that violate hard rules in the absence of an explicit override flag.

**What tools do not do:** disable trade-execution paths in IBKR; block the user from clicking past a warning; auto-correct the book or auto-trim concentrated positions; override your judgment when judgment differs from the framework.

**Visual conventions:** Green = position or candidate is within all framework parameters. Amber = parameter approaching a threshold (e.g., delta 0.30–0.35, position 30–50% concentration, VIX above 25). Red = parameter has crossed a critical threshold (e.g., delta > 0.35, position > 50% concentration, dark pool floor broken).

### 15.2 Enforcement Layers

| Layer | How rules are applied |
|---|---|
| Manual checklist | Pre-trade workflow in §8. Each step verified by the trader. |
| Code-enforced gates | Dashboard pre-trade gate (§3.3 exclusion, §4 earnings, §7 concentration, §7 VIX). `workflow_02_entry_scoring.py` rejects within 10-day blackout. Jade Lizard validator rejects if credit ≤ width. |
| Surfacing & alerts | Daily QuantData Summary, IV Crush Report, Dark Pool Alert. Profit-take alerts. Dashboard surfaces all of the above. |
| Decision logic helpers | Stop-loss aggregator (§6 multi-signal), roll evaluator (§5), post-earnings playbook (§10), Jade Lizard validator (§2.E), SPY hedge coverage (§2.D). |

### 15.3 Authority Hierarchy When Sources Conflict

**Strategy document > Tool behavior > Memory.** If a tool produces a recommendation that contradicts a rule in this document, the rule wins. If memory contains a rule that contradicts this document, this document wins.

### 15.4 What This Means for Tool Development

Tools may add safety beyond what this document requires. They may not subtract safety. Tools may surface information faster than manual review. They may not bypass review entirely. If a tool's behavior diverges from the strategy document, the tool is wrong and gets corrected.

### 15.5 Review Cadence

Strategy document: review quarterly or after significant outcome events. Tool stack: review monthly — tools should evolve faster than strategy. Memory: review weekly.

### 15.6 Tool Stack Inventory (v4.2, May 2026)

**Frontend — Fortress V4 Dashboard (React/tRPC)**

React 19 + TypeScript + Tailwind CSS SPA. Runs locally on WSL, served via nginx at `https://localhost`. Key pages:

| Page | Function |
|---|---|
| Dashboard | Macro Regime Score, Net Liq, Daily P&L, Morning Brief, Priority Orders |
| Trade → Candidates | IV Rank screener — yfinance-based IVR, full universe |
| Trade → Market Intelligence | Per-ticker GEX walls, dark pool levels, net drift, directional bias |
| Trade → Analysis | Price chart with position overlays, Greeks summary |
| Portfolio | Per-leg Greeks, DTE triage, concentration alerts, roll prompts |
| Earnings | Earnings calendar, blackout windows |
| Settings | Strategy parameters, ticker universe, IBKR auth mode, QuantData login |

**Backend — Python/FastAPI (WSL)**

REST API at `http://localhost:8081/api/`. Two tokens accepted: `FORTRESS_API_TOKEN` (browser) and `FORTRESS_MCP_TOKEN` (Claude). Running as `fortress-dashboard-v4.service` (systemd). Key endpoints: `/api/briefing`, `/api/candidates`, `/api/market-intelligence`, `/api/positions`, `/api/alerts`, `/api/manage/roll_all`, `/api/manage/stop_loss_all`, `/api/qd/*` (QuantData proxy).

**QuantData Integration**

Credentials at `~/.quantdata-mcp/config.json` (auth_token, instance_id, page_id, tool UUIDs). Refreshed via **Settings → QuantData Auto-Login**. The `/api/qd/*` proxy endpoints serve QuantData data to the MCP — no client-side QD credentials needed. Note: per-ticker data for MCP `qd_*` tools returns the default ticker (SPY) until the `update_tool` server-side fix is implemented.

**IVR / IV Source (v4.2)**

workflow_01 and workflow_05 use yfinance ATM options chain IV + 52-week rolling HV for IVR calculation. This replaces the previous QuantData per-ticker dependency. Max pain (workflow_08) also uses yfinance options chain.

**Broker Integration — IBKR**

- **CP Gateway** (active, requires daily browser login): `https://localhost:5000`
- **ibind OAuth 1.0a** (configured, pending IBKR activation): fully headless, no daily login
- Toggle in **Settings → Security → IBKR Auth: Use ibind OAuth**
- Greeks backend: `web_api` (CP Gateway + OPRA, preferred) → `bs_yfinance` (fallback)

**Claude MCP Server**

`fortress_mcp.py` at `C:\Users\cityc.000\fortress_mcp\` (Windows). 64 tools. Start with `get_briefing()`. Write tools enabled by default (`FORTRESS_MCP_ALLOW_WRITES=1`). All `qd_*` tools proxy through the server.

**Workflow Scripts**

`workflow_01` through `workflow_08` in `~/fortress-v4-api/quant/`. Reports saved to same directory. Run via dashboard Scripts page, MCP `run_script()`, or APScheduler (automated).

**State Files**

All in `~/fortress-v4-api/quant/`: `active_positions.json`, `earnings_blocklist.json`, `ticker_universe.json`, `alerts.json`, `journal.json`, `chart_annotations.json`, `fortress_config.json`.

**TradingView**

Charting and alert delivery. Clean Decision Chart for strategic decisions; Signal/Timing Chart for tactical use.

— End of document —
