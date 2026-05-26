# Portfolio Management Strategy

**Your Name — YOUR_IBKR_ACCOUNT_ID**
**Version 3.6 — May 5, 2026**

v3.6 formalises two operational changes adopted into the dashboard:
(1) §5 short-call Critical Gamma threshold tightened from 0.40 to **0.35**;
(2) §7 margin floors and §2.D hedge target normalised to **USD** (the broker's reporting currency), with EUR equivalents shown as supplementary information only. v3.5's §2.D / §2.E dashboard-enforcement requirements preserved. v3.4's Signaling-vs-Blocking principle preserved.

---

## 1. Governance

- **Decision-maker:** You (the trader). AI tools are analytical inputs, not decision sources.
- **Multi-AI inputs:** When another AI recommends a trade, flag it before executing so it can be evaluated against the active strategy.
- **Pre-execution check:** Discuss new plays before acting. Verify ticker, earnings date, strike direction, and limit price before submitting.
- **Flexibility:** Open to any strategy or rotation as long as the trade is profitable and fits the framework.

---

## 2. Active Strategies

### A. Poor Man's Covered Call (PMCC) — primary

- **Long leg:** LEAPS ~640 DTE (Jan 2028), 25–30% ITM, delta 0.78–0.85.
- **Short leg:** Monthly calls 30–45 DTE, delta ~0.20, 7–10% OTM.
- **Coverage:** Strict 1:1 short-to-LEAP ratio. Never hold an uncovered LEAP.

### B. Diagonal Spreads — tactical

- **Structure:** Long call 30–90 DTE + short call shorter DTE.
- **Use case:** Directional tactical plays, not income generation.
- **Management:** Different decay profile than PMCC — requires shorter-horizon monitoring.

#### Post-Earnings Diagonal Playbook (primary use case for Strategy B)

- **Entry trigger:** morning after earnings, when IV crush ≥25% AND stock gap within ±8%.
- **Entry timing:** place order between 10:00–11:00 AM ET on the day after earnings.
- **Long leg:** 30–90 DTE call, delta 0.55–0.70, at or near the current price (ATM or slightly ITM).
- **Short leg:** 14–21 DTE call, delta 0.25–0.30, at first resistance level above current price.
- **Target net debit:** ≤50% of the long leg's value (the short leg should cover at least half the cost).
- **Exit:** close the entire diagonal at 50% of max profit, or roll the short leg when it reaches 80% profit.
- **Earnings window:** never enter a new diagonal within 10 days of the next earnings date for that ticker.
- **Pre-planning:** identify the target ticker and entry conditions before earnings. Do not decide in real time.

### C. Put Credit Spreads — income

- **Structure:** Sell OTM put + buy further-OTM put as protection.
- **Short strike:** Delta 0.15–0.20 (80–85% probability of expiring worthless).
- **DTE:** 30–45 days at entry.
- **Spread width:** $5 for sub-$100 stocks; $10 for $100–$300; $15–20 for $300+.

### D. SPY Hedge — protective

- **Enforcement (v3.5):** Dashboard tracks net market value of SPY hedge positions against the target band and flags `coverage_ok`. See `/api/manage/spy_hedge_coverage`.
- **Sizing target (USD-normalised in v3.6):** $20K–$30K of net market value, midpoint ~$25K. Stored as `cfg("strategy.spy_hedge_min_usd")` / `spy_hedge_max_usd` in config_store. (Roughly equivalent to the historical €20–30K target at current FX; the dashboard now stores and compares in USD natively.)
- **Structure:** SPY put debit spread, 60 DTE, ~4% OTM short strike, $40 wide.
- **Sizing:** 1–2 spreads to protect ~$20K–$30K of book drawdown.
- **Purpose:** Offset the portfolio-wide bullish bias rather than reduce concentrated positions.

### E. Jade Lizard — consolidation income

- **Enforcement (v3.5):** Dashboard pre-trade gate strictly validates that total credit > call spread width before allowing execution. See `/api/manage/validate_jade_lizard`.
- **Structure:** Short OTM put (uncovered) + short OTM call spread (bear call spread) on the same expiry.
- **Defining rule:** total credit received must exceed the width of the call spread. This eliminates all upside risk.
- **Use case:** high-conviction names in sideways consolidation or slow drift higher.
- **Eligible names:** Tier 1 only (MSFT, AVGO, NFLX, VST, GOOGL, AMZN). No Jade Lizards on Tier 2 or non-core names.
- **Short put strike:** at or below the 50-day MA. Must represent a level where you would genuinely add to the position.
- **Call spread:** short strike at first meaningful resistance; long strike $10–20 above. Short call delta ≤0.25.
- **DTE:** 30–45 days at entry.
- **Credit requirement:** total credit > call spread width.
- **Earnings window:** no new Jade Lizards within 10 days of ticker earnings.
- **Max concurrent Jade Lizards:** 2 (counts toward the 5-spread put-side cap in §7).

### 2.5 Source-of-Truth Hierarchy

Per v3.3 — when sources disagree, this hierarchy governs which is correct.

| Domain | Authoritative source | Notes |
|---|---|---|
| Position state, P&L, Greeks, margin | IBKR (via CP Gateway Web API in v3.6; live and screenshots) | All trade-level decisions reference IBKR. |
| Stock price, support/resistance, MAs, trend | TradingView charts | No technical analysis without a TradingView chart. |
| Options market structure, IV/IVR, GEX, dark pool, OI walls | QuantData reports | Daily QuantData Summary, GEX & OI Profile Report, IV Crush Opportunity Report. |
| Live option chain data (bid/ask/delta/OI for specific strikes) | IBKR option chain via Web API (preferred), yfinance (fallback) | |
| Earnings dates and event calendar | `earnings_blocklist.json` (manual + auto-fetcher) | |
| Active book composition and concentration | `active_positions.json` (synced from IBKR via Web API or OCR) | |
| Strategy rules (this document) | Portfolio Strategy v3.x | If a tool's behavior contradicts a rule, the rule wins. See §15. |

---

## 3. Name Universe

### 3.1 Core Holdings (standing instruction)

AAPL, NVDA, MSFT, META, MSTR, AVGO, AMZN.

### 3.2 Approved for New Entries

- **Tier 1 (high IV, clean thesis):** AMD, NFLX, AVGO, MSFT, VST, MSTR, GOOGL, AMZN.
- **Tier 2 (moderate IV):** META, AAPL, NVDA.
- **Non-tech candidates:** Healthcare (UNH, LLY), Financials (MS, GS, JPM), Energy (XOM, OXY).

### 3.3 Excluded

Hard exclusions enforced by the dashboard via `ticker_universe.json` `excluded` array:

- **Regulatory risk:** COIN, HOOD, SMCI until legal clouds clear.
- **PMCC-incompatible:** Small-caps with thin option chains (e.g., LKFN).
- **Ignored entirely:** OST. Display in book if held; never recommend.

### 3.4 Universe as Signal, Not Law

Per v3.3 — outside-universe names explorable when setup demonstrably exceeds universe candidates. Documentation requirement in journal. All quality filters in §4 still apply. All hard exclusions in §3.3 remain blocked regardless.

---

## 4. Entry Rules

### Timing

- Execute after 10:00 AM ET / 16:00 Amsterdam — avoid opening volatility.
- Opex Fridays: trade cautiously, expect wider spreads.
- Wait 3–5 days for IV normalization after news-driven spikes.
- Use limit orders at mid, walk up/down patiently. Do not pay ask or chase fills.

### Earnings Discipline

- Verify earnings date before every new entry — non-negotiable.
- No new LEAP entries within 2 weeks of ticker earnings.
- No new put spreads within 10 days of ticker earnings.
- Post-earnings IV crush morning (next day) is preferred LEAP entry window.
- Entry trigger for post-earnings: IV crush ≥25% AND stock gap within ±8%.
- Hold existing positions through earnings — PMCC is designed for this.

### Quality Filters

- Bid/ask spread ≤10% of mid on both legs.
- Open interest >100 per leg.
- Underlying daily option volume: >1K contracts (credit spreads), >10K (LEAPS preferred).
- IV Rank: Confirm IVR > 25 before entering new premium-selling positions.

---

## 5. Short Call Management (PMCC)

### Strike Selection

- **Primary rule:** Delta 0.20–0.25 on short call at entry.
- **Chart override:** If a strike within the target delta range sits at or just above a well-defined chart resistance level, prefer the chart-aligned strike.
- **Chart undershoot:** If the natural delta strike is in clear air, consider moving one strike closer only if chart shows a clean rejection level there.

### Management Rules

- **Take profit at 80%:** Close short call when value decays to ~20% of credit received.
- **Time-based roll rule:** If short call has not reached 80% profit by 14–21 DTE, close it anyway and re-sell a fresh short at 30–45 DTE.
- **Roll up-and-out:** If short becomes ITM, roll to higher strike and later expiry, targeting net credit.
- **Never roll winners.**
- **Never roll losers into earnings.**
- **Never roll on strong-underlying days.**

### DTE Discipline

- Short calls 30–45 DTE at entry. 90+ DTE shorts capture 3–5× less total premium over the holding period.
- 7–10% OTM for low-IV names.
- Existing far-dated exceptions: MSFT Dec'26 $480, MSFT Sep'18 $520, VST Sep'26 $200 — pending review.
- Before selling any short call >60 DTE: explicitly state the reason and acknowledge theta inefficiency.

### Delta Drift Monitoring

Short call delta drifts upward as the underlying rallies. Monitoring delta after entry is part of active position management.

#### Delta thresholds (revised in v3.6)

- **≤0.30:** Normal range. No special action.
- **0.30–0.35:** Approaching ATM. Watch closely. Consider rolling on next strong-down day or at next 80% profit opportunity.
- **>0.35:** Critical Gamma Risk. The position is materially exposed to gamma whip. Roll up-and-out within the current trading week, or close if rolling for credit isn't achievable.

**Why 0.35 (vs the 0.40 threshold in v3.4):** Practice has shown that by the time a short reaches 0.40, the gamma exposure has often already produced a meaningful adverse move. Tightening to 0.35 forces the review one delta-bin earlier and gives more room to roll for credit before the position becomes structurally underwater. The dashboard reads this from `cfg("strategy.delta_critical_threshold")`; tunable per Settings tab without a code deploy.

#### Why this matters

A short call that started at delta 0.20 and drifted to 0.40 is a near-ATM short with full gamma exposure. The position's risk profile has fundamentally changed since entry. Treating delta drift as drift, rather than as a fresh decision, is a known failure mode.

#### Interaction with existing rules

- **Time-based roll rule:** if 14–21 DTE approaches and delta is >0.30, prioritise rolling that position.
- **Never roll on strong-underlying days:** if delta is >0.35 AND today is a strong-up day, wait one session for the underlying to consolidate, then roll.
- **Never roll losers into earnings:** if delta is >0.35 AND earnings is within 10 days, close instead of roll.

#### Tool support

Dashboard surfaces this rule with red cell accents on positions where short call |delta| > 0.35 (per Build Spec §5.5.3). Visual flag triggers a manual review. The decision to roll, close, or wait remains a human judgment per §15.1.

---

## 6. Exit Rules

### Put Credit Spreads

- Close at 50% profit.
- Close at 200% loss.
- Close 7 days before expiration if ITM.

### Jade Lizard

- Close the entire position at 50% of total credit received.
- If short put tested: close put leg at 200% of put credit.
- If call spread tested: close call spread at 200% of call spread credit.
- Never hold to expiration. Close by 7 DTE at the latest.

### LEAPS Profit-Taking

Trim 20–30% when ANY trigger fires:
- LEAP premium returns +100% from entry cost.
- Position shows +$22K unrealized gain (USD-normalised in v3.6 from the historical €20K target).
- Stock runs past all short-call coverage.

### LEAPS Stop-Loss / Thesis Break

Close or materially reduce LEAPS position when AT LEAST TWO of the following are true:
- Weekly close below 200-day moving average.
- LEAP mark-to-market value drops >50% from its peak.
- Fundamental thesis break.

One signal alone is not sufficient. Two or more = act. Dashboard implements as a 3-signal aggregator with an additional 1b "DP floor proximity" warning that doesn't count toward firing.

---

## 7. Risk Management

### Position Sizing (revised v3.6 to USD)

- Max new position size: **$15K–$22K** typical (was €15–20K).
- Max concurrent put credit spreads: 5.
- Max total put-side notional at risk: **$25K–$30K** (~30% of Net Liquidity).
- Dry powder reserve: **~$5K–$6K** uncommitted for opportunities.

### Concentration

- **Conviction-weighted:** Higher-conviction names may hold higher concentration. No fixed hard cap across the board.
- **Concentration is managed via hedging, not forced trimming.**
- Current MSFT allocation (>60% of book) is accepted as a deliberate high-conviction position, offset by SPY hedge.
- **Monitoring:** Flag if any non-MSFT single name exceeds 20% of book.

#### High-concentration entry override

When a single name is already >50% of book, post-earnings entry rules tighten but do not close entirely:
- **Tighter gap threshold:** Require gap down 5–8% (PRIME ENTRY zone).
- **Thesis health confirmed:** Earnings reaction must be reaction-driven, NOT thesis-driven.
- **Reduced size:** 1 contract maximum, never 2+.
- **Override conditions evaluated at moment of decision,** not any moment during the day.

#### Concentration trimming on profit

When the high-concentration name gaps UP >5% post-earnings, the LEAPS profit-take rule takes priority over any add consideration.

### Pacing (Cooling-Off Target)

- **Soft target:** Maximum 2 new positions per week.
- **Exceptions** (not counted): Rolls, hedges, post-earnings playbook triggers.
- **Enforcement:** Flag when exceeded, do not force block.

### Market Regime Filters

- VIX >25: pause new entries.
- Single name sells off >5% in a session: skip that name's new entries that day.
- Single name gaps >10% post-earnings: pass LEAP entry unless thesis explicitly confirms.

### Margin Discipline (revised v3.6 to USD)

- Maintain Available Funds **>$17K** minimum (~20% of Net Liquidity).
- Maintain Excess Liquidity **>$25K** cushion.
- Current readings checked daily.

**Currency note:** v3.4 / v3.5 expressed these floors in EUR. The dashboard now stores and compares in USD (matching IBKR's reporting currency), with EUR equivalents shown alongside as informational. The numerical thresholds — $17K and $25K — are unchanged from the EUR values; v3.6 simply formalises that the comparison is USD-to-USD. If in the future the FX rate moves materially and these floors should track EUR purchasing-power, the thresholds are configurable via Settings → Strategy (`available_funds_min_usd`, `excess_liq_min_usd`).

### Prohibited Actions

- Never hold uncovered LEAPS.
- Never sell naked puts (credit spreads only) — EXCEPTION: Jade Lizard short put per §2.E.
- Never use SPY shares for hedging (options only).
- Never sell puts on names in clear downtrend.
- Never enter LEAP or put-spread positions on names with active DOJ/SEC investigations.

---

## 8. Workflow

### Before Every New Trade

1. Pull live option chain from broker — IBKR live (CP Gateway snapshot) or screenshot fallback.
2. Pull Clean Decision Chart from TradingView (see §9).
3. Verify earnings date on the ticker.
4. Select strikes using real bid/ask/delta data and chart structure.
5. Confirm the structure matches the intended strategy.
6. Verify limit price direction and magnitude relative to bid/mid/ask.
7. Submit as limit order, work patiently.

### Daily Routine

- **Morning:** check book, identify any triggered conditions.
- Place orders after 10:00 AM ET.
- Monitor fills; walk limits patiently.
- **End of day:** screenshot or sync book, note any issues.

### Weekly Routine

- **Sunday or Monday morning:** review Clean Decision Charts for each active LEAP position.
- Flag any 200-day MA breaks immediately — stop-loss signal inputs per §6.
- Identify any positions approaching roll windows (14–21 DTE on short calls).

---

## 9. Chart Setup & Review (TradingView Workflow)

Unchanged from v3.5. Clean Decision Chart for strategic decisions; Signal/Timing Chart retained for tactical use.

---

## 10. Post-Earnings Entry Playbook

Unchanged from v3.5. Gap × IV crush matrix:

| Gap range | Rule | Verdict |
|---|---|---|
| Gap up >5% | Missed move, IV will be low | PASS |
| +2 to +5% | Buy if IV crush > 30% | CONDITIONAL |
| Flat ±2% | Buy if IV crush > 25% | CONDITIONAL |
| −3 to −8% | PRIME ENTRY zone (assuming thesis intact) | PRIME ENTRY |
| −8 to −15% | Evaluate fundamentals before entry | EVALUATE |
| Gap down >15% | Thesis likely broken | PASS |
| IV crush <20% (any gap) | Premium not crushing — no edge | PASS (override) |

High-concentration filter, execution timing, put-credit-spread post-earnings rules unchanged.

---

## 11. Current Book Snapshot

Live state in `active_positions.json`. Refreshed via CP Gateway Web API sync (preferred) or OCR upload fallback.

---

## 12. Open Items & Pipeline

- Continue MSFT high-conviction concentration, offset by SPY hedge (§2.D).
- Maintain `earnings_blocklist.json` — auto-fetcher available via Universe tab.
- Review Settings tab thresholds quarterly (`delta_critical_threshold`, `available_funds_min_usd`, etc.) — they're tunable without code deploy.
- IBKR Account Management → Settings → API → Settings → "Read-Only API" enabled (May 5, 2026) to support CP Gateway.
- OAuth 2.0 direct migration deferred (currently using CP Gateway via voyz/ibeam).

---

## 13. Calendar Events (Next 30 Days)

Live calendar maintained in `earnings_blocklist.json` and visible in dashboard.

---

## 14. Change Log

- **v3.6 (May 5, 2026):** Two formalisations of dashboard practice. (1) §5 Critical Gamma threshold tightened from 0.40 to **0.35** based on operational learning that 0.40 surfaces the position too late; the dashboard now reads from `cfg("strategy.delta_critical_threshold")` so it's tunable in Settings. (2) §7 margin floors and §2.D hedge target normalised to **USD** (the broker's reporting currency, matching IBKR convention); EUR equivalents shown alongside for reference but not used in threshold checks. §15.6 tool stack updated — IB Gateway (TWS API) is now legacy; **CP Gateway via voyz/ibeam is the live broker integration**, with bs_yfinance as the always-available fallback. Added §12 note about Read-Only API enabled at the IBKR account level.
- **v3.5 (May 4, 2026):** §2.D SPY hedge MV tracker enforcement; §2.E Jade Lizard credit gate enforcement.
- **v3.4 (May 1, 2026):** §5 Delta Drift Monitoring (≤0.30 / 0.30–0.40 / >0.40); §15.1 Signaling vs. Blocking principle.
- **v3.3 (May 1, 2026):** §2.5 Source-of-Truth Hierarchy; §3.4 Universe as Signal, Not Law; §15 How the Framework is Enforced.
- **v3.2 (Apr 27, 2026):** §7 High-Concentration Entry Override.
- **v3.1 (Apr 24, 2026):** §5 DTE Discipline subsection.
- **v3.0 (Apr 24, 2026):** Definitive merge of v1.2 and v2.1. Added Strategy E (Jade Lizard). Added §10 Post-Earnings Entry Playbook.
- (Earlier) v1.0–v1.2 covered initial PMCC + diagonals + put credit spreads; merged into v3.0.

---

## 15. How the Framework is Enforced

### 15.1 Signaling vs. Blocking

**No tool blocks a trade. Tools warn; humans decide.**

Discipline is a human responsibility, not a software-enforced state. Every button in the dashboard is technically clickable; every script can be overridden; every alert can be dismissed.

**What tools DO:**
- Surface relevant data (IV/HV spread, dark pool floors, earnings dates, concentration percentages).
- Flag rule conflicts visually — amber for warnings, red for critical conditions.
- Pre-fill recommended actions for human review.
- Log decisions and outcomes.
- Refuse to execute actions that violate hard rules in the absence of an explicit override flag.

**What tools DO NOT do:**
- Disable trade-execution paths in IBKR.
- Block the user from clicking past a warning.
- Auto-correct the book or auto-trim concentrated positions.
- Override your judgment when judgment differs from the framework.

**Visual conventions:**
- **Green:** position or candidate is within all framework parameters.
- **Amber:** parameter approaching a threshold (e.g., delta 0.30–0.35, position 30–50% concentration, VIX above 25).
- **Red:** parameter has crossed a critical threshold (e.g., **delta >0.35**, position >50% concentration, dark pool floor broken).

### 15.2 Enforcement layers

| Layer | How rules are applied |
|---|---|
| Manual checklist | Pre-trade workflow in §8. Each step verified by the trader. |
| Code-enforced gates | Dashboard pre-trade gate (§3.3 exclusion, §4 earnings, §7 concentration, §7 VIX). `workflow_02_entry_scoring.py` rejects within 10-day blackout. Jade Lizard validator rejects if credit ≤ width. |
| Surfacing & alerts | Daily QuantData Summary, IV Crush Report, Dark Pool Alert. Profit-take alerts. Dashboard surfaces all of the above. |
| Decision logic helpers | Stop-loss aggregator (§6 multi-signal), roll evaluator (§5), post-earnings playbook (§10), Jade Lizard validator (§2.E), SPY hedge coverage (§2.D). |

### 15.3 Authority hierarchy when sources conflict

**Strategy document > Tool behavior > Memory.**

If a tool produces a recommendation that contradicts a rule in this document, the rule wins. If memory contains a rule that contradicts this document, this document wins.

### 15.4 What this means for tool development

- Tools may add safety beyond what this document requires. They may not subtract safety.
- Tools may surface information faster than manual review. They may not bypass review entirely.
- If a tool's behavior diverges from the strategy document, the tool is wrong and gets corrected.

### 15.5 Review cadence

- **Strategy document:** review quarterly or after significant outcome events.
- **Tool stack:** review monthly. Tools should evolve faster than strategy.
- **Memory:** review weekly.

### 15.6 Tool stack inventory (May 2026, post-Web-API migration)

For reference. Descriptive, not prescriptive.

- **QuantData scripts:** `workflow_01` through `workflow_08`. Pre-market scan, daily summary, position monitor, EOD review, IV crush, dark pool alert, whale flow, max pain.
- **State files** in `~/Fortress_Dashboard/quant/`: `active_positions.json`, `earnings_blocklist.json`, `ticker_universe.json`, `alerts.json`, `journal.json`, `chart_annotations.json`, `ibkr_uploads.json`, **`fortress_config.json`** (schema-driven settings, new in v3.6).
- **Dashboard:** 9-tab web interface — Briefing, Positions, Manage, New Trade, Playbook, Uploads, Universe, Journal, **Settings** (new). Schema-driven settings UI lets you tune `delta_critical_threshold`, USD floors, etc. without code deploy.
- **Greeks backend:** auto-resolved per `cfg("technical.greeks_backend")` — `web_api` (CP Gateway + OPRA, preferred), `bs_yfinance` (Black-Scholes from yfinance, fallback), `tws_ibkr` (legacy TWS gateway, diagnostics-only), `auto` (default; picks best available).
- **CP Gateway:** `voyz/ibeam` Docker container at `https://localhost:5000`. Daily IBKR Mobile push approval to refresh session. **Replaces** the legacy `gnzsnz/ib-gateway` (TWS API), which is stopped.
- **TradingView:** charting and alert delivery.
- **IBKR:** position state, trade execution, option chain queries. Read-Only API enabled at the account level (May 5, 2026).

— End of document —
