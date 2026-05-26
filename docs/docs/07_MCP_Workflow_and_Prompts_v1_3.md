# Fortress MCP — Workflow and Prompts Playbook

**Version 1.3 — May 18, 2026**

A practical companion to the MCP server. Maps every phase of Strategy v3.7's daily/weekly routine to concrete Claude prompts that exercise the MCP tools.

**v1.3 changes from v1.2:** Updated for Strategy v3.7 and Sprint v7.x dashboard changes. QuantData API calls now use widget-UUID REST endpoints — the deprecated `tool/OPTIONS_*` tool IDs have been removed from `chart.py` and are no longer valid. Credential refresh workflow updated to reference the Settings → QuantData Credentials UI (no SSH required). `get_market_intelligence` response now includes sort/regime score fields. Maintenance section updated with correct document version chain.

**v1.2 changes from v1.1:** The MCP server (`fortress_mcp.py`) and example scripts have been moved to a dedicated repository — **[citychip/fortress-mcp](https://github.com/citychip/fortress-mcp)**. The `scripts/mcp_*.py` files previously in this repo have been removed; equivalent cleaned-up scripts are in `fortress-mcp/examples/`. See the fortress-mcp README for Claude Desktop installation and configuration.

**v1.1 changes from v1.0:** USD-native currency convention; CP Gateway re-auth path replaces TWS popup workflow; `get_capability` tool added for "is Greeks coverage live?" checks; delta thresholds reflect v3.6 (>0.35 critical).

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

**Tool name reference:**

Read tools (Tier 1):
`get_briefing`, `get_positions`, `get_candidates`, `get_calendar`, `get_universe`, `get_journal`, `get_alerts`, `get_chart_data`, `evaluate_stop_loss`, `evaluate_roll`, `evaluate_post_earnings`, `validate_jade_lizard`, `get_spy_hedge_coverage`, `pretrade_check`, `get_ibkr_status`, `get_capability`, `get_settings`, `get_quantdata_reports`, `get_market_intelligence`

QuantData Live API tools (Tier 1, requires valid credentials):
`qd_get_order_flow`, `qd_get_net_drift`, `qd_get_dark_pool_levels`, `qd_get_max_pain`, `qd_get_iv_rank`, `qd_get_oi_change`

Write tools (Tier 2, opt-in):
`add_journal_entry`, `add_alert`, `update_alert`, `delete_alert`, `update_calendar`, `add_excluded_ticker`, `add_universe_ticker`, `update_settings_section`, `trigger_ibkr_sync`

> **QuantData credential note:** If QuantData tools return 401/403 or empty data, the session has expired. Refresh credentials at **Dashboard → Settings → QuantData Credentials** (no SSH required). See `operations/04_Incident_Recovery_Playbook.md` §5 for the step-by-step procedure.

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
> **response:** Establishes macro regime first (SPY flip zone, DP floors, regime score). Then filters premium-selling candidates. For each valid candidate, pulls structural levels (GEX walls, DP floors) to anchor short strikes. Finally, runs the pre-trade gate to catch size caps and concentration limits.
>
> **notes:** The `pretrade_check` is non-negotiable. With current concentration breaches, it will automatically catch the size cap. Use GEX walls to anchor short strikes (e.g., short call spread around GEX call wall). The `get_market_intelligence` response now includes a `regime_score` field (-4 to +4) and `sort_key` — use these to prioritise which tickers to analyse first.

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

### Phase 4 — Post-Close (~16:00–16:30 ET)

#### 2.5 EOD Review

> **prompt:** *"Log today's trades to the journal with the strategy reasoning. Then evaluate any position where mark-to-market changed more than 50% today. Finally, update tomorrow's calendar from any earnings reschedules I should know about."*
>
> **tools:** `add_journal_entry()` → `evaluate_stop_loss()` / `evaluate_roll()` → `update_calendar()`
>
> **response:** Confirms journal entries. Evaluates movers. Updates calendar.
>
> **notes:** Journaling is the highest-ROI habit. Use `get_journal` in 6 weeks to find which entry templates actually worked.

### Phase 5 — Weekly Workflow (Sunday ~18:00 ET)

#### 2.6 Full Portfolio Audit & De-risking

> **prompt:** *"Run a full portfolio audit: briefing, all positions aggregated and non-aggregated, concentration breakdown, SPY hedge coverage, and current Greeks. Then for each position over 10% of NetLiq, run evaluate_roll and tell me three concrete options to reduce concentration: roll out, scale down, or convert to a debit spread. Show me get_market_intelligence for the underlying for context."*
>
> **tools:** `get_briefing()` → `get_positions()` → `get_spy_hedge_coverage()` → `evaluate_roll()` → `get_market_intelligence()`
>
> **response:** Comprehensive audit. Proposes specific structures to deload concentrated positions (e.g., MSFT) and specific SPY put structures to close the hedge gap.
>
> **notes:** This is where you make the decision to deload MSFT — not on a random Tuesday. Plan it on Sunday, execute on Monday, journal the reasoning.

### Phase 6 — Position-Event Workflows (When something fires)

#### 2.7 Pre-trade gate before any new entry

> **prompt:** *"I'm thinking AMD PMCC. Run the pre-trade gates."*
>
> **tools:** `pretrade_check("AMD", "PMCC")` → `qd_get_order_flow("AMD", min_premium=50000)`
>
> **response:** All five gates with verdict + reason: §3.3 exclusion, §4 earnings blackout, §7 concentration, §7 VIX, and the LEAP blackout gate. If all PASS, checks recent QuantData order flow for large sweeps/blocks confirming the directional thesis (Gate 6). If flow contradicts thesis, warns the trader.
>
> **notes:** Per Strategy §15.1, a failing gate doesn't block — but Claude should make the trader explicitly acknowledge any override.

#### 2.8 Strike selection prep

> **prompt:** *"For AMD PMCC, where should I be looking for the short strike? Pull the structural levels."*
>
> **tools:** `get_chart_data("AMD", period="6mo")` → `qd_get_dark_pool_levels("AMD")`
>
> **response:** Current spot, 50-day SMA, 200-day SMA. Top 3 dark pool floors from live QuantData API. Top 3 GEX call walls (resistance) and put walls (support). Suggests strike zones per §5: 7–10% OTM for the short call, ideally aligned with a GEX call wall or first chart resistance above current price.
>
> **notes:** Reminder per §15.1: Claude can suggest, but the trader decides. Don't prescribe an exact strike — describe the band.

#### 2.9 Post-earnings playbook

> **prompt:** *"AMD opened down 6%, IV crushed 35%. Walk me through the playbook."*
>
> **tools:** `evaluate_post_earnings(ticker="AMD", gap_pct=-6.0, iv_crush_pct=35, thesis={revenue_beat: true, guidance_maintained: true, no_leadership_or_regulatory_event: true, sector_context_normal: true})` → `pretrade_check("AMD", "PMCC")` → `qd_get_dark_pool_levels("AMD")`
>
> **response:** Matrix verdict (PRIME_ENTRY for −6% with IV crush ≥ 25%), final action (PROCEED if all 4 thesis checks pass), size cap if any, overrides applied. Then runs the pre-trade gate. Then the structural levels for strike selection.
>
> **notes:** If thesis checks haven't been confirmed, prompt: "Confirm thesis health checklist first — revenue beat, guidance maintained, no leadership/regulatory event, sector context normal." Don't assume.

#### 2.10 Jade Lizard validation

> **prompt:** *"Validate this MSFT Jade Lizard: short put $400 / call spread $480-$490, put credit $5.20, call spread credit $5.85."*
>
> **tools:** `validate_jade_lizard(put_strike=400, call_short_strike=480, call_long_strike=490, put_credit=5.20, call_spread_credit=5.85)` → `pretrade_check("MSFT", "JADE_LIZARD")`
>
> **response:** Validator verdict (PASS — total credit $11.05 exceeds call spread width $10 by $1.05). Followed by the pre-trade gate. Reminds: Tier 1 only per §2.E.

---

## 3. Failure modes to expect

How Claude should handle common error conditions:

| Condition | Symptom | What Claude should do |
|---|---|---|
| QuantData credentials expired | `qd_get_*` returns 401/403 or empty data | Flag immediately. Direct trader to **Settings → QuantData Credentials** to refresh. See `operations/04_Incident_Recovery_Playbook.md` §5. |
| Gateway disconnected | `get_ibkr_status` returns `connected: false` | Flag immediately. Suggest `docker compose restart ib-gateway` or wait 90s. Don't fall back to silently stale data. |
| Stale data (>24h) | `briefing.staleness.state == "stale"` | Front-load every response with "data is N hours old — sync recommended." Refuse compound workflows that depend on fresh state until synced. |
| BS fallback unavailable for a ticker | `current_delta_source == "unavailable"` | Note the affected positions; explain that delta-drift visual indicators won't fire for them. Suggest manual delta lookup in IBKR. |
| Chain provider rate-limited | yfinance returns no chain | Fall back to `get_dp_floors_and_gex` which uses the QuantData report. Note that strike-band suggestions from §2.7 are unavailable. |
| Tier 2 disabled | Write tool returns "writes disabled" | Don't fail silently. Output the would-be payload as form values the trader can paste into the dashboard manually. |
| Excluded ticker | Pre-trade gate FAIL with `reason: ignored_entirely` or `regulatory` | Refuse to walk through entry scenarios. Reference §3.3 explicitly. |

---

## 4. Anti-patterns — don't use the MCP for these

### 4.1 Don't ask Claude to pick exact strikes

> **bad:** *"Pick my strike for the AMD short call."*
>
> **why:** Strike selection requires the live IBKR option chain. The MCP doesn't expose live chain bid/ask, only yfinance approximations cached for 5 minutes. Claude should suggest strike *zones* but the exact strike is a live-data decision.

### 4.2 Don't ask Claude to "set the stop"

> **bad:** *"Put a stop on UNH at $355."*
>
> **why:** Stops on options positions go through TradingView alerts or IBKR conditional orders, not the dashboard's `alerts.json`. The dashboard's alerts file is a profit-take/stop *log* for human review, not an execution layer.

### 4.3 Don't override the strategy through the MCP

> **bad:** *"Run the post-earnings playbook on AMD ignoring the IV crush floor."*
>
> **why:** The IV crush <20% override is a strategy rule, not a tool config. Per §15.4: "If a tool's behavior diverges from the strategy document, the tool is wrong and gets corrected." If the rule should change, change Strategy v3.7; don't bypass it via tool params.

### 4.4 Don't use `trigger_ibkr_sync` as a poor-man's polling

> **bad:** *"Every minute, sync IBKR and tell me if anything changed."*
>
> **why:** The dashboard already does 60-second polling on `/api/briefing`. The IBKR sync is ~30–60s and disconnects/reconnects the gateway each time — running it constantly will hammer the broker and trip rate limits. Use `get_briefing()` for fast pulse checks.

### 4.5 Don't use deprecated QuantData tool IDs

> **bad:** *"Call `tool/OPTIONS_GEX_WALLS_TABLE` directly."*
>
> **why:** These deprecated tool IDs were removed in Sprint v7.1 after causing 400 errors and account revocation. All QuantData calls now use widget-UUID REST endpoints. The MCP tools (`qd_get_dark_pool_levels`, `qd_get_order_flow`, etc.) handle this correctly — don't bypass them.

---

## 5. Saved-prompt suggestions

| Slot | Prompt | Purpose |
|---|---|---|
| Morning | *"Sync and brief me. What's HIGH today?"* | §2.1 + §2.2 combined |
| Pre-trade | *"Pre-trade gate on {TICKER} for {STRATEGY}. Then suggest strike zones."* | §2.7 + §2.8 |
| Post-earnings | *"Post-earnings playbook: {TICKER} gap {X}%, IV crush {Y}%. Thesis confirmed."* | §2.9 |
| Market Intel | *"What's the regime on {TICKER}? Show me the GEX walls and DP floors."* | `get_market_intelligence` |
| Roll review | *"Roll review across the book, ordered by urgency."* | §2.11 |
| Sunday | *"Run my Sunday planning checklist."* | §2.6 |
| Pulse | *"Quick book status."* | `get_briefing` |
| Health | *"MCP and gateway health check."* | `get_capability` + `get_ibkr_status` |
| QD Health | *"Check QuantData connectivity — are credentials valid?"* | `qd_get_iv_rank("SPY")` |

---

## 6. Maintenance

When the strategy changes, this doc updates in this order:

1. **Strategy v3.x** (currently v3.7) — the source of truth changes first.
2. **Build Spec v2.x** (currently v2.0) — the dashboard's implementation catches up.
3. **Workflow v2.x** (currently v2.9) — operational procedures update.
4. **MCP Proposal** — new tools added if needed.
5. **This document** — prompt library and failure modes update.

---

## Document History

| Version | Date | Changes |
|---|---|---|
| 1.3 | 2026-05-18 | Updated for Strategy v3.7 and Sprint v7.x. QuantData credential refresh via Settings UI. Deprecated `tool/OPTIONS_*` anti-pattern added. `get_market_intelligence` regime_score field noted. |
| 1.2 | 2026-05-09 | MCP server moved to `citychip/fortress-mcp` repo. |
| 1.1 | 2026-05-05 | USD-native currency. CP Gateway re-auth. `get_capability` tool. |
| 1.0 | 2026-05-03 | Initial release. |
