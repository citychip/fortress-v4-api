# Fortress MCP — Workflow and Prompts Playbook

**Version 1.2 — May 9, 2026**

A practical companion to `06_Fortress_MCP_Proposal_v1_1.md`. Maps every phase of Strategy v3.6's daily/weekly routine to concrete Claude prompts that exercise the MCP tools.

v1.2 changes from v1.1: The MCP server (`fortress_mcp.py`) and example scripts have been moved to a dedicated repository — **[citychip/fortress-mcp](https://github.com/citychip/fortress-mcp)**. The `scripts/mcp_*.py` files previously in this repo have been removed; equivalent cleaned-up scripts are in `fortress-mcp/examples/`. See the fortress-mcp README for Claude Desktop installation and configuration.

v1.1 changes from v1.0: USD-native currency convention; CP Gateway re-auth path replaces TWS popup workflow; `get_capability` tool added for "is Greeks coverage live?" checks; delta thresholds reflect v3.6 (>0.35 critical).

**Installation:** `git clone https://github.com/citychip/fortress-mcp.git && pip install -r fortress-mcp/requirements.txt`
Then add the Claude Desktop config block from `fortress-mcp/claude_desktop_config_snippet.json` to your `claude_desktop_config.json` and restart Claude Desktop.

Use this document as:

- A copy-paste reference for the morning routine
- A set of saved-prompt templates for Claude Desktop
- A test plan for verifying the MCP works end-to-end after install

If a prompt below stops producing the expected tool calls, the MCP probably regressed. If it produces them but the response is wrong, the underlying dashboard endpoint or strategy rule is wrong — fix the dashboard, not the MCP.

---

## 1. How this works

Once the Fortress MCP is installed in Claude Desktop, every prompt below should trigger Claude to call one or more MCP tools, reason over the JSON returns, and reply in natural language. The tools wrap existing dashboard endpoints — there's no AI-generated data; every number Claude cites comes from the dashboard's deterministic logic.

**Conventions used in this doc:**

- `prompt:` → what the trader types into Claude
- `tools:` → which MCP tools Claude should call (in order if order matters)
- `response:` → the expected shape of Claude's natural-language reply
- `notes:` → caveats, follow-ups, or strategy refs

**Tool name reference** (full spec in `06_Fortress_MCP_Proposal_v1_1.md` §2):

Read tools (Tier 1):
`get_briefing`, `get_positions`, `get_candidates`, `get_calendar`, `get_universe`, `get_journal`, `get_alerts`, `get_chart_data`, `evaluate_stop_loss`, `evaluate_roll`, `evaluate_post_earnings`, `validate_jade_lizard`, `get_spy_hedge_coverage`, `pretrade_check`, `get_ibkr_status`, `get_capability`, `get_settings`, `get_quantdata_reports`

QuantData Live API tools (Tier 1, requires credentials):
`qd_get_order_flow`, `qd_get_net_drift`, `qd_get_dark_pool_levels`, `qd_get_max_pain`, `qd_get_iv_rank`, `qd_get_oi_change`

Write tools (Tier 2, opt-in):
`add_journal_entry`, `add_alert`, `update_alert` (v1.1), `delete_alert`, `update_calendar`, `add_excluded_ticker`, `add_universe_ticker` (v1.1), `update_settings_section` (v1.1), `trigger_ibkr_sync`

---

## 2. Daily routine — phase-by-phase prompts

> **CURRENT BOOK STATE (May 2026):** The portfolio is in a defensive posture. MSFT is heavily concentrated (>70% of NetLiq), SPY hedge is underbuilt, and delta bias is excessively long (+437) in a bearish macro regime. **The workflow prioritizes position management and de-risking over new entry hunting.**

### Phase 1 — Pre-Market (09:00–09:35 ET / 15:00–15:35 Amsterdam)

#### 2.1 Morning Preflight (The Triad)

> **prompt:** *"Run my morning preflight: briefing, SPY hedge coverage, today's calendar, and any positions where evaluate_stop_loss returns 'act'. Flag concentration and delta-bias violations."*
>
> **tools:** `get_briefing()` → `get_spy_hedge_coverage()` → `get_calendar()` → `evaluate_stop_loss()` (across positions)
>
> **response:** Walks through the core risk triad. 
> 1. Briefing: Account thresholds, concentration top-3 (especially MSFT), and portfolio delta vs target.
> 2. Hedge: SPY hedge coverage vs $22k–$33k target band.
> 3. Actions: Any stop-loss triggers in `ACT` state and earnings on major positions today.
>
> **notes:** Do NOT run `get_candidates` here. Entries are not decided pre-market. Looking at candidates first creates a bias to enter when the book requires de-risking. Pass criteria to move to Phase 2: no stop-loss in `act`, no earnings today on major positions, no hedge breach worse than already known.

### Phase 2 — Market Open (09:35–10:00 ET)

#### 2.2 Macro regime and flow validation (Only on entry days)

> **prompt:** *"Show me get_market_intelligence for SPY. Then for any name from get_candidates with IVR > 50 and no earnings in the next 21 days, run get_market_intelligence for those tickers. Run pretrade_check on each."*
>
> **tools:** `get_market_intelligence("SPY")` → `get_candidates()` → `get_market_intelligence(ticker)` → `pretrade_check(ticker)`
>
> **response:** Establishes macro regime first (SPY flip zone, DP floors). Then filters premium-selling candidates. For each valid candidate, pulls structural levels (GEX walls, DP floors) to anchor short strikes. Finally, runs the pre-trade gate to catch size caps and concentration limits.
>
> **notes:** The `pretrade_check` is non-negotiable. With current concentration breaches, it will automatically catch the size cap. Use GEX walls to anchor short strikes (e.g., short call spread around GEX call wall).

---

### Phase 3 — Intraday Triggers (Event-driven, not scheduled)

#### 2.3 Intraday Alerting

> **prompt:** *"Add stop-loss alerts at the act threshold for every position over 5% of NetLiq, and a delta-watch alert at 0.7 for any position with delta > 0.6."*
>
> **tools:** `add_alert()` (called iteratively)
>
> **response:** Confirms alerts have been set.
>
> **notes:** Set this up once, then react when they fire. The `evaluate_stop_loss` and `evaluate_roll` tools are decision support when they do.

#### 2.4 Regime change on concentrated positions

> **prompt:** *"Compare today's get_market_intelligence for MSFT against yesterday's get_market_intelligence for MSFT — has the dominant DP floor or GEX put wall migrated down?"*
>
> **tools:** `get_market_intelligence("MSFT")`
>
> **response:** Evaluates whether institutional support levels have dropped.
>
> **notes:** If yes, that's the day to tighten or roll the concentrated exposure, not the day to ride it out.

---

### Phase 4 — Post-Close (~16:00–16:30 ET)

#### 2.5 EOD Review

> **prompt:** *"Log today's trades to the journal with the strategy reasoning. Then evaluate any position where mark-to-market changed more than 50% today. Finally, update tomorrow's calendar from any earnings reschedules I should know about."*
>
> **tools:** `add_journal_entry()` → `evaluate_stop_loss()` / `evaluate_roll()` → `update_calendar()`
>
> **response:** Confirms journal entries. Evaluates movers. Updates calendar.
>
> **notes:** Journaling is the highest-ROI habit. Use `get_journal` in 6 weeks to find which entry templates actually worked.

---

### Phase 5 — Weekly Workflow (Sunday ~18:00 ET)

#### 2.6 Full Portfolio Audit & De-risking

> **prompt:** *"Run a full portfolio audit: briefing, all positions aggregated and non-aggregated, concentration breakdown, SPY hedge coverage, and current Greeks. Then for each position over 10% of NetLiq, run evaluate_roll and tell me three concrete options to reduce concentration: roll out, scale down, or convert to a debit spread. Show me get_market_intelligence for the underlying for context."*
>
> **tools:** `get_briefing()` → `get_positions()` → `get_spy_hedge_coverage()` → `evaluate_roll()` → `get_market_intelligence()`
>
> **response:** Comprehensive audit. Proposes specific structures to deload concentrated positions (e.g., MSFT) and specific SPY put structures to close the hedge gap.
>
> **notes:** This is where you make the decision to deload MSFT — not on a random Tuesday. Plan it on Sunday, execute on Monday, journal the reasoning.

---

### Phase 6 — Position-Event Workflows (When something fires)

#### 2.7 Pre-trade gate before any new entry

> **prompt:** *"I'm thinking AMD PMCC. Run the pre-trade gates."*
>
> **tools:** `pretrade_check("AMD", "PMCC")` → `qd_get_order_flow("AMD", min_premium=50000)`
>
> **response:** All five gates with verdict + reason: §3.3 exclusion, §4 earnings blackout, §7 concentration, §7 VIX, and the new LEAP blackout gate. If all PASS, checks recent QuantData order flow for large sweeps/blocks confirming the directional thesis (Gate 6). If flow contradicts thesis, warns the trader.
>
> **notes:** Per Strategy §15.1, a failing gate doesn't block — but Claude should make the trader explicitly acknowledge any override.

#### 2.7 Strike selection prep

> **prompt:** *"For AMD PMCC, where should I be looking for the short strike? Pull the structural levels."*
>
> **tools:** `get_chart_data("AMD", period="6mo")` → `qd_get_dark_pool_levels("AMD")`
>
> **response:** Current spot, 50-day SMA, 200-day SMA. Top 3 dark pool floors from live QuantData API. Top 3 GEX call walls (resistance) and put walls (support). Suggests strike zones per §5: 7–10% OTM for the short call, ideally aligned with a GEX call wall or first chart resistance above current price.
>
> **notes:** Reminder per §15.1: Claude can suggest, but the trader decides. Don't prescribe an exact strike — describe the band.

#### 2.8 Post-earnings playbook

> **prompt:** *"AMD opened down 6%, IV crushed 35%. Walk me through the playbook."*
>
> **tools:** `evaluate_post_earnings(ticker="AMD", gap_pct=-6.0, iv_crush_pct=35, thesis={revenue_beat: true, guidance_maintained: true, no_leadership_or_regulatory_event: true, sector_context_normal: true})` → `pretrade_check("AMD", "PMCC")` → `qd_get_dark_pool_levels("AMD")`
>
> **response:** Matrix verdict (PRIME_ENTRY for −6% with IV crush ≥ 25%), final action (PROCEED if all 4 thesis checks pass), size cap if any, overrides applied. Then runs the pre-trade gate. Then the structural levels for strike selection.
>
> **notes:** If thesis checks haven't been confirmed, prompt: "Confirm thesis health checklist first — revenue beat, guidance maintained, no leadership/regulatory event, sector context normal." Don't assume.

#### 2.9 Jade Lizard validation

> **prompt:** *"Validate this MSFT Jade Lizard: short put $400 / call spread $480-$490, put credit $5.20, call spread credit $5.85."*
>
> **tools:** `validate_jade_lizard(put_strike=400, call_short_strike=480, call_long_strike=490, put_credit=5.20, call_spread_credit=5.85)` → `pretrade_check("MSFT", "JADE_LIZARD")`
>
> **response:** Validator verdict (PASS — total credit $11.05 exceeds call spread width $10 by $1.05). Followed by the pre-trade gate (note: MSFT at 70% concentration would block per §7 unless this is a high-conviction add scenario, in which case §7 override applies). Reminds: Tier 1 only per §2.E.
>
> **notes:** If validator FAILS, Claude must refuse to recommend the trade — §2.E is a hard rule.

#### 2.10 Diagonal post-earnings

> **prompt:** *"NFLX gapped −4% post-earnings, IV crush 28%. Diagonal entry?"*
>
> **tools:** `evaluate_post_earnings("NFLX", -4, 28, thesis={...})` → `pretrade_check("NFLX", "DIAGONAL")` → `get_chart_data("NFLX", "3mo")`
>
> **response:** Matrix verdict, gates check. For diagonals specifically, references §2.B Post-Earnings Diagonal Playbook: long leg 30–90 DTE delta 0.55–0.70 ATM, short leg 14–21 DTE delta 0.25–0.30 at first resistance, target net debit ≤50% of long leg value. Suggests strike zones from chart resistance.

---

### Phase 4 — Mid-Day Monitoring (11:00–15:45 ET)

#### 2.11 Roll review

> **prompt:** *"Anything I should be rolling right now?"*
>
> **tools:** `get_positions(aggregated=true)` → for each position with `delta_state ∈ {watch, critical}`: `evaluate_roll(ticker)`
>
> **response:** Filtered list of roll candidates. For each: current short strike + delta + DTE, top recommended candidate (strike, expiry, delta, mid, net credit), and the IBKR ticket text ready to copy. If a position is at delta > 0.35 critical_gamma, prioritizes it and references §5 "Roll up-and-out within current trading week."
>
> **notes:** Per §5, never roll on strong-up days. If today is a strong-up day and Claude knows it (from the Briefing's regime), it should warn before recommending the roll.

#### 2.12 Stop-loss check on a specific position

> **prompt:** *"Run the stop-loss aggregator on UNH. Anything firing?"*
>
> **tools:** `evaluate_stop_loss("UNH")`
>
> **response:** All four signals (1, 1b, 2, 3) with status + detail. Verdict (HOLD/WATCH/ACT/ACT_IMMEDIATELY). Recommended action. If signal 2 (LEAP MTM 50% drop) returns "unknown" because peak MV wasn't provided, flags that Phase 3 IBKR sync should populate it.
>
> **notes:** If verdict is ACT or ACT_IMMEDIATELY, Claude should NOT recommend a specific exit price — that requires live chain data and chart confirmation per §6.

#### 2.13 Mid-day pulse check

> **prompt:** *"Quick pulse — anything moved into watch since the morning sync?"*
>
> **tools:** `get_briefing()` → `get_alerts()`
>
> **response:** Compares current `staleness.hours` to confirm data is fresh. Lists any HIGH or new MED actions. Lists any alerts that fired since last check. If nothing, says so explicitly — "No new actions; book is steady."

---

### Phase 5 — Pre-Close Review (15:00–16:00 ET)

#### 2.14 Pre-close decision sweep

> **prompt:** *"Pre-close sweep. What needs action before the bell?"*
>
> **tools:** `get_positions(aggregated=true)` → `get_alerts()` → `get_briefing()`
>
> **response:** Three categories:
> 1. **Profit targets:** short calls at 80%+ profit, PCS at 50%+, Jade Lizards at 50%+ — close before close.
> 2. **Loss limits:** any position past the 200% loss rule (§6) — mechanical close required.
> 3. **HIGH actions** still on the briefing list that haven't been resolved.
>
> If any category is empty, says so. If multiple in a category, ranks by urgency (delta, DTE, alert state).

---

### Phase 6 — End of Day (16:15–17:00 ET)

#### 2.15 EOD review

> **prompt:** *"Walk me through the EOD review. What did the regime do?"*
>
> **tools:** `get_quantdata_reports("eod_review", "latest")` → `get_briefing()` → `get_journal(limit=5)`
>
> **response:** Reports the next-day regime signal (🟢 BULLISH or 🔴 BEARISH) from the EOD report. Compares to the morning's regime call (drift?). Summarizes today's journal entries (any OPENs / CLOSEs / ROLLs).

#### 2.16 Journal entry for today's actions

> **prompt:** *"Log my close on the UNH Jun 5 $390 short call. Realized $187 profit on the leg, framework rules: §5 80% profit target, §5 time-based roll. Reasoning: short was at 22% of credit received, rolled into Jun 18 $400 for net credit."*
>
> **tools:** `add_journal_entry(action="ROLL", ticker="UNH", description="UNH Jun5 $390C → Jun18 $400C", reasoning="Short was at 22% of credit received, rolled up-and-out for net credit per §5.", framework_rules=["§5 80% profit target", "§5 time-based roll"], realized_pnl=187)`
>
> **response:** Confirms the entry was appended to `journal.json`, returns the assigned `id` and timestamp.
>
> **notes:** Tier 2. If writes disabled, Claude says "writes disabled — please add this manually via the Journal tab" and provides the form values verbatim.

---

## 3. Strategy-specific entry flows

Each strategy in §2 of Strategy v3.5 has a different entry workflow. These are the prompts for each.

### 3.1 PMCC entry (post-earnings, pre-planned)

> **prompt:** *"It's the morning after AMD earnings. Gap −5%, IV crush 32%, fundamentals look fine. Walk me through the PMCC entry."*
>
> **tools:** `evaluate_post_earnings("AMD", -5, 32, thesis={...})` → `pretrade_check("AMD", "PMCC")` → `get_chart_data("AMD", "6mo")` → `qd_get_dark_pool_levels("AMD")` → `get_briefing()` (for pacing budget)
>
> **response:** Matrix says PRIME_ENTRY → PROCEED. Gates clear. Chart structure: 200-SMA at $X, 50-SMA at $Y, key support/resistance. DP floor at $Z (which becomes the LEAP entry "do not break" reference). For the LEAP: 25–30% ITM target, ~640 DTE (Jan 2028). For the short call (T+1): 30–45 DTE, 7–10% OTM, delta 0.20–0.25, ideally aligned with first GEX call wall above spot. Pacing remaining: N/2.
>
> **action items for the trader:** pull live IBKR chain, confirm bid/ask spread ≤10% mid, confirm OI >100, place LEAP today, place short call T+1 per §10.

### 3.2 Put Credit Spread entry

> **prompt:** *"Looking at NVDA PCS for next month. IVR is 53. Where to set the strikes?"*
>
> **tools:** `get_candidates()` → `pretrade_check("NVDA", "PCS")` → `get_chart_data("NVDA", "3mo")` → `qd_get_dark_pool_levels("NVDA")` → `qd_get_max_pain("NVDA")`
>
> **response:** Confirms NVDA is on the IV Crush list at IVR 53 (CRUSH flag). Pre-trade gates. Per §2.C: short put delta 0.15–0.20, 30–45 DTE, $10 width for $100–300 stocks ($15–20 for >$300). Suggests short strike alignment with DP floor or chart support. Notes: §6 exit rules — close at 50% profit, 200% loss cap.

### 3.3 SPY Hedge sizing

> **prompt:** *"Need to deploy SPY hedge. Confirm I'm under-covered first."*
>
> **tools:** `get_spy_hedge_coverage()` → `get_briefing()` → `get_chart_data("SPY", "3mo")`
>
> **response:** Current hedge MV vs €20–30K target band. Coverage_ok flag. If under-covered, suggests sizing per §2.D: 60 DTE put debit spread, ~4% OTM short strike, $40 wide, 1–2 spreads. Pulls SPY chart to identify ~4% OTM strike level. Calculates how many spreads to add to land in the target band.

### 3.4 Jade Lizard prep

> **prompt:** *"Looking for a Jade Lizard candidate. Who's eligible right now?"*
>
> **tools:** `get_universe()` → `get_candidates()` → `get_calendar(window_days=14)` → `get_briefing()` (for concentration)
>
> **response:** Filters candidates to Tier 1 only per §2.E (MSFT, AVGO, NFLX, VST, GOOGL, AMZN). Excludes anything within 10 days of earnings. Excludes anything at >50% concentration without override. For each remaining: confirms IVR > 25 and consolidation (referencing chart structure if available). Reminds: max 2 concurrent Jade Lizards, total credit must exceed call spread width — use `validate_jade_lizard` once strikes are picked.

---

## 4. Position management flows

### 4.1 Daily position drift check

> **prompt:** *"Walk through every active position. Flag anything at watch or worse."*
>
> **tools:** `get_positions(aggregated=true)`
>
> **response:** One row per ticker. For each: ticker, strategy, leg count, primary short strike + expiry, current delta + delta_state, alert_state. Highlights anything ∈ {watch, approaching, breaking, broken, critical_gamma}. For each highlighted, suggests a follow-up: "run `evaluate_stop_loss('UNH')` for the multi-signal verdict" or "run `evaluate_roll('VST')` for roll candidates."

### 4.2 Position-specific deep dive

> **prompt:** *"Tell me everything about my MSFT position."*
>
> **tools:** `get_positions(aggregated=true)` (filter to MSFT) → `evaluate_stop_loss("MSFT")` → `evaluate_roll("MSFT")` → `qd_get_dark_pool_levels("MSFT")` → `get_chart_data("MSFT", "6mo")`
>
> **response:** Aggregated MSFT row (6 legs, net MV, concentration %). Per-leg breakdown if asked. Stop-loss verdict. Roll candidates. Structural levels. Notes the position is at 70% concentration — §7 high-concentration override applies for any add consideration.

### 4.3 Concentration check

> **prompt:** *"Am I over-concentrated? Anything I should trim?"*
>
> **tools:** `get_briefing()` → `get_positions(aggregated=true)`
>
> **response:** Concentration top-5 with thresholds (green <30%, amber 30–50%, red >50%). Per §7: MSFT > 50% accepted as high-conviction (offset by SPY hedge); flags any non-MSFT >20%. Calls out OST (§3.3 ignored — display only, no recommendations). If MSFT >50% AND there's been a recent gap-up >5%, references §7 "concentration trimming on profit" rule.

---

## 5. Weekly + ad-hoc prompts

### 5.1 Sunday planning

> **prompt:** *"Run my Sunday planning checklist."*
>
> **tools:** `trigger_ibkr_sync()` (if writes enabled) → `get_briefing()` → `get_calendar(window_days=21)` → `get_spy_hedge_coverage()` → `get_journal(limit=14)` → `get_candidates()`
>
> **response:** Six-section report:
> 1. **Sync status** — gateway connected, data fresh.
> 2. **Account thresholds** — AvailFunds and ExcessLiq vs €17K/€25K floors.
> 3. **Earnings cluster for the week ahead** — 21-day window, focus on the next 7.
> 4. **SPY hedge coverage** — €20–30K target check.
> 5. **Last 14 days of journal entries** — pacing usage, framework rules cited.
> 6. **IV crush watchlist** — names worth pre-planning for the week.
>
> **notes:** This is the weekly canonical prompt. Consider saving as a Claude Project shortcut.

### 5.2 Friday wrap

> **prompt:** *"Friday close — what's the week look like in review, and what's flagged for next week?"*
>
> **tools:** `get_journal(limit=10)` → `get_quantdata_reports("max_pain", "latest")` → `get_positions(aggregated=true)` → `get_calendar(window_days=14)`
>
> **response:**
> 1. **This week's trades** — OPENs, CLOSEs, ROLLs, with realized P&L if logged.
> 2. **Pacing check** — total OPENs (excluding rolls/hedges) against 2/week soft cap.
> 3. **Max Pain pinning targets** for next week's expirations.
> 4. **14-DTE roll candidates** — short calls entering the time-based roll window per §5.
> 5. **Earnings cluster** for next week.

### 5.3 "What did I learn this month?"

> **prompt:** *"Pull the last 30 days of journal. What patterns do you see?"*
>
> **tools:** `get_journal(limit=60)`
>
> **response:** Outcome metrics card values (total realized, PCS hit rate, framework violations). Then qualitative patterns — most-used framework rules, average hold time, any recurring tickers, any decisions where the verdict was overridden. Per §15.5, this informs whether the strategy doc needs review.

### 5.4 Quick book status

> **prompt:** *"Book status."*
>
> **tools:** `get_briefing()`
>
> **response:** One-paragraph summary: NetLiq (USD + EUR), concentration top-3, Greeks bias, count of HIGH actions, count of positions in watch/critical. No commentary unless asked.

### 5.5 Health check

> **prompt:** *"Is everything working? Sync, gateway, data freshness?"*
>
> **tools:** `get_ibkr_status()` → `get_briefing()`
>
> **response:** Gateway connected (or not), account ID, staleness state. If anything is wrong (gateway disconnected, data >24h stale, IBKR errors), surfaces immediately with the recovery step.

---

### 5.6 Greeks coverage health check (NEW v1.1)

> **prompt:** *"Quick health check — is the dashboard still seeing live IBKR Greeks?"*
>
> **tools:** `get_capability()`
>
> **response shape:**
>
> > Web API session: established. OPRA: subscribed. Active backend: `web_api`. Last capability check 23s ago. All four Greeks should be live on the next sync.
>
> If `web_api.session_status.established: false`: "CP Gateway needs re-authentication. Check your phone for an IBKR Mobile push notification, approve it, then re-check capability."
> If `web_api.opra_subscribed: false`: "OPRA market-data subscription is missing. Greeks will fall back to BS-from-yfinance until subscription is reactivated. Check IBKR Account Management → Subscriptions → Market Data."

## 6. Tier 2 write prompts (optional, env-var-gated)

These prompts mutate state but never execute trades. Each requires `FORTRESS_MCP_ALLOW_WRITES=1` on the MCP client.

### 6.1 Log a journal entry

> **prompt:** *"Log: opened MSFT Jan'28 $310 LEAP, debit $111.40 per contract, qty 5. Reasoning: post-earnings PRIME_ENTRY at gap −6%, IV crush 35%, thesis confirmed. Framework rules: §10 PRIME_ENTRY, §2.A LEAP delta 0.78–0.85, §4 post-earnings IV crush window."*
>
> **tools:** `add_journal_entry(action="OPEN", ticker="MSFT", description="MSFT Jan'28 $310C LEAP", reasoning="...", framework_rules=[...], economics={debit: 111.40, qty: 5})`
>
> **response:** Confirms append. Returns `id` and timestamp.

### 6.2 Set a profit-take alert

> **prompt:** *"Set an alert on the UNH Jun 18 $400 short call to fire when option price drops to $0.80 (80% profit on the $4.00 entry)."*
>
> **tools:** `add_alert(position_id="unh_jun18_400c_short", trigger_type="option_price", trigger_value=0.80, direction="below", action="close_at_80_pct")`
>
> **response:** Confirms creation. Returns alert id.

### 6.3 Update earnings calendar

> **prompt:** *"AMD just confirmed earnings for May 6, AMC. Update the calendar."*
>
> **tools:** `update_calendar(ticker="AMD", next_earnings="2026-05-06", confirmed=true)`
>
> **response:** Confirms write. Re-runs the briefing to show the impact on candidate scanner cross-checks (AMD should now show in the 10-day blackout window).

### 6.4 Add an exclusion

> **prompt:** *"Add LMND to the excluded list — regulatory risk pending state insurance review."*
>
> **tools:** `add_excluded_ticker(ticker="LMND", reason="regulatory")`
>
> **response:** Confirms write. Notes that any held LMND positions remain visible but the candidate scanner and pre-trade gate will block new entries.

---

## 7. Compound workflows

These are multi-step prompts that exercise several tools and require Claude to reason across the results. They're the highest-value uses of the MCP — anything where the dashboard has the data but Claude has to weave it together.

### 7.1 "Should I take this trade?"

> **prompt:** *"AMD post-earnings: gap −4.2%, IV crush 31%, fundamentals look fine. PMCC entry — go or no-go?"*
>
> **tools (in order):**
> 1. `evaluate_post_earnings("AMD", -4.2, 31, thesis={revenue_beat: true, ...})`
> 2. `pretrade_check("AMD", "PMCC")`
> 3. `get_briefing()` (for pacing remaining + concentration + VIX)
> 4. `get_chart_data("AMD", "6mo")`
> 5. `get_dp_floors_and_gex("AMD")`
> 6. `get_candidates()` (find AMD's IVR/IV-HV row for confirmation)
>
> **response shape:** A decision walk-through:
>
> > **Verdict: PROCEED with PRIME_ENTRY band.**
> >
> > Matrix says PRIME_ENTRY (gap −4.2% in the −3..−8% band, IV crush 31% > 25% floor). All 4 thesis checks confirmed. Pre-trade gates all clear: AMD not excluded, no earnings blackout (we're past it), concentration ok, VIX state normal.
> >
> > Pacing remaining: 1 of 2 this week.
> >
> > Strike zones from chart + structural levels:
> > - LEAP long: ~$315–325 (25–30% ITM, delta 0.78–0.85). DP floor at $213.84 sits below — clear runway.
> > - Short call (T+1): $415–420 zone (7–10% OTM, delta 0.20–0.25). First GEX call wall is at $215 — note that's underneath, so resistance is structural support not above the short. Use chart resistance instead.
> >
> > Per §10 execution timing: place LEAP after 10:00 ET in the 10:00–11:00 ET window. Sell short call cover T+1.
> >
> > **Open:** confirm thesis health checklist live, pull live IBKR chain for exact strike + bid/ask spread.

### 7.2 "Roll review across the book"

> **prompt:** *"Walk through every position and tell me what to roll, in order of urgency."*
>
> **tools:**
> 1. `get_positions(aggregated=true)` → filter to PMCC/DIAGONAL with `delta_state ∈ {watch, critical}` OR primary short DTE ≤ 21
> 2. For each candidate: `evaluate_roll(ticker)`
> 3. For each that's also in critical: `evaluate_stop_loss(ticker)`
>
> **response shape:** Ordered list, most urgent first:
>
> > 1. **UNH — critical_gamma, delta 0.46, 14 DTE** (highest urgency per §5 "Roll up-and-out within current trading week")
> >    - Recommended candidate: $400 strike Jun 5 (delta 0.24, mid $4.00, +$117 net credit per contract)
> >    - Ticket text [paste]
> > 2. **MSFT $480 Dec 18 short — watch, delta 0.36, 28 DTE**
> >    - Recommended candidate: ...
> > 3. ... etc.
>
> Concludes with: "VST has earnings in 3 days — per §5 'never roll losers into earnings', if delta drifts above 0.35 before then, close instead of roll."

### 7.3 "Pre-mortem on this idea"

> **prompt:** *"I'm thinking of selling a Jade Lizard on AMZN, $215 short put / $250-$260 call spread. Total credit $11. Sanity check?"*
>
> **tools:**
> 1. `validate_jade_lizard(put_strike=215, call_short_strike=250, call_long_strike=260, put_credit=4.50, call_spread_credit=6.50)` (assume reasonable split — Claude should ask if unclear)
> 2. `pretrade_check("AMZN", "JADE_LIZARD")`
> 3. `get_chart_data("AMZN", "6mo")` → confirm $215 short put is at or below 50-day MA
> 4. `get_calendar(window_days=14)` → confirm no AMZN earnings within 10 days
> 5. `get_briefing()` → check current Jade Lizard count (max 2 concurrent per §2.E)
>
> **response shape:**
>
> > **PASS on the credit-vs-width gate** — total $11 > spread width $10 by $1.
> >
> > Pre-trade gates all clear (AMZN is Tier 1 per §2.E). 50-day MA is at ~$210, so the $215 short put is just above it — per §2.E "must represent a level where you would genuinely add to the position", that's borderline. Consider $210 or $205 instead.
> >
> > Earnings calendar: no AMZN earnings within 10 days (next is Jul X).
> >
> > Currently 0 Jade Lizards on the book; cap is 2 per §2.E.
> >
> > Per §6 exit rules: close the entire position at 50% of total credit ($5.50 buy-back). If short put is tested, close put leg at 200% of put credit. If call spread is tested, close call spread at 200% of call spread credit.

### 7.4 "Generate next week's earnings prep doc"

> **prompt:** *"Build me a pre-earnings prep checklist for next week's tickers. Anything in our universe with earnings in the next 7 days."*
>
> **tools:**
> 1. `get_calendar(window_days=10)`
> 2. `get_universe()` → filter calendar entries to tier1/tier2 only
> 3. For each: `get_chart_data(ticker, "6mo")` to identify pre-earnings S/R zones
> 4. `get_briefing()` for current concentration to flag any high-conc names entering earnings
>
> **response shape:** Markdown table per ticker with: earnings date+time (AMC/BMO), confirmed flag, current price, 50-SMA, 200-SMA, key resistance, key support, current concentration in book, pre-plan strategy choice (PMCC vs Diagonal vs PCS).

---

## 8. Anti-patterns — don't use the MCP for these

Some things look like they should go through the MCP but shouldn't. Per §15.4 of the strategy: tools may add safety, never subtract.

### 8.1 Don't ask Claude to pick exact strikes

> **bad:** *"Pick my strike for the AMD short call."*
>
> **why:** Strike selection requires the live IBKR option chain (per §2.5 source-of-truth hierarchy — IBKR is authoritative for live chain data). The MCP doesn't expose live chain bid/ask, only yfinance approximations cached for 5 minutes. Claude should suggest strike *zones* but the exact strike is a live-data decision.

### 8.2 Don't ask Claude to "set the stop"

> **bad:** *"Put a stop on UNH at $355."*
>
> **why:** Stops on options positions go through TradingView alerts or IBKR conditional orders, not the dashboard's `alerts.json`. The dashboard's alerts file is a profit-take/stop *log* for human review, not an execution layer.

### 8.3 Don't override the strategy through the MCP

> **bad:** *"Run the post-earnings playbook on AMD ignoring the IV crush floor."*
>
> **why:** The IV crush <20% override is a strategy rule, not a tool config. Per §15.4: "If a tool's behavior diverges from the strategy document, the tool is wrong and gets corrected." If the rule should change, change Strategy v3.5; don't bypass it via tool params.

### 8.4 Don't use `trigger_ibkr_sync` as a poor-man's polling

> **bad:** *"Every minute, sync IBKR and tell me if anything changed."*
>
> **why:** The dashboard already does 60-second polling on `/api/briefing`. The IBKR sync is ~30–60s and disconnects/reconnects the gateway each time — running it constantly will hammer the broker and trip rate limits. Use `get_briefing()` for fast pulse checks.

### 8.5 Don't ask Claude to evaluate trades on excluded tickers

> **bad:** *"Run the post-earnings playbook on COIN."*
>
> **why:** COIN is on §3.3 hard exclusion. The pre-trade gate will FAIL it. Even if `evaluate_post_earnings` returns a verdict, the trade is blocked. Claude should refuse to walk through scenarios for excluded names — it normalizes evaluation of names the strategy says are off-limits.

---

## 9. Saved-prompt suggestions

These are the prompts most worth saving as Claude Desktop "Quick Action" prompts or Claude Project starter prompts. They're high-frequency and have a stable shape:

| Slot | Prompt | Purpose |
|---|---|---|
| Morning | *"Sync and brief me. What's HIGH today?"* | §2.1 + §2.2 combined |
| Pre-trade | *"Pre-trade gate on {TICKER} for {STRATEGY}. Then suggest strike zones."* | §2.6 + §2.7 |
| Post-earnings | *"Post-earnings playbook: {TICKER} gap {X}%, IV crush {Y}%. Thesis confirmed."* | §2.8 |
| Roll review | *"Roll review across the book, ordered by urgency."* | §7.2 |
| Sunday | *"Run my Sunday planning checklist."* | §5.1 |
| Friday | *"Friday wrap and pre-stage next week."* | §5.2 |
| Pulse | *"Quick book status."* | §5.4 |
| Health | *"MCP and gateway health check."* | §5.5 |

---

## 10. Failure modes to expect

How Claude should handle common error conditions:

| Condition | Symptom | What Claude should do |
|---|---|---|
| Gateway disconnected | `get_ibkr_status` returns `connected: false` | Flag immediately. Suggest `docker compose restart ib-gateway` or wait 90s. Don't fall back to silently stale data. |
| Stale data (>24h) | `briefing.staleness.state == "stale"` | Front-load every response with "data is N hours old — sync recommended." Refuse compound workflows that depend on fresh state until synced. |
| BS fallback unavailable for a ticker | `current_delta_source == "unavailable"` | Note the affected positions; explain that delta-drift visual indicators won't fire for them. Suggest manual delta lookup in IBKR. |
| Chain provider rate-limited | yfinance returns no chain | Fall back to `get_dp_floors_and_gex` which uses the QuantData report. Note that strike-band suggestions from §2.7 are unavailable. |
| Tier 2 disabled | Write tool returns "writes disabled" | Don't fail silently. Output the would-be payload as form values the trader can paste into the dashboard manually. |
| Excluded ticker | Pre-trade gate FAIL with `reason: ignored_entirely` or `regulatory` | Refuse to walk through entry scenarios. Reference §3.3 explicitly. |

---

## 11. Maintenance

When the strategy changes, this doc updates in this order:

1. **Strategy v3.x** (currently v3.6) — the source of truth changes first.
2. **Build Spec v1.x** (currently v1.8) — the dashboard's implementation catches up.
3. **Workflow v2.x** (currently v2.8) — operational procedures update.
4. **MCP Proposal** — new tools added if needed.
5. **This do