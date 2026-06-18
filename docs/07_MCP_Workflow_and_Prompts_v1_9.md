# Fortress MCP — Workflow and Prompts Playbook

**Version 1.9 — 2026-06-10**

A practical companion to the MCP server. Maps every phase of Strategy v3.7's daily/weekly routine to concrete Claude prompts that exercise the MCP tools.

**v1.9 changes from v1.8 (⚠ supersedes all `qd_get_iv_rank` references below):** QuantData's `iv_rank` is broken upstream — the ticker argument is ignored (all tickers return identical values; verified SPX/MSFT/NVDA, 2026-06-10). Use the fortress MCP **`get_iv_rank(ticker)`** instead (new in v4.5.0; backend yfinance, Black-Scholes-inverted from lastPrice, `hv_proxy` ranking until 60 daily snapshots accumulate, then true IV rank). The "dual IV rank confirmation" pattern (v1.7) is retired — one canonical source; cross-check via `massive` chain IV when a value looks implausible. `qd_get_volatility_skew` / `qd_get_exposure_by_strike` remain broken during market hours — prefer fortress `get_vol_skew()` / `get_gex()`. QuantData stays valid for: order flow, dark pool levels, max pain, OI, net flow. See `docs/DATA_SOURCES.md` and `docs/WORKFLOW.md` v2.2.

**v1.8 changes from v1.7:** Added §2.11 Trade Staging workflow — Claude-native leg-builder pattern. Claude constructs legs from plain English, stages via `stage_order`, shows a confirmation summary, and waits for explicit approval before calling `approve_order`. Parapet Orders page serves as visual log. Also updated §5 saved-prompt table with Stage prompt.

**v1.7 changes from v1.6:** Updated for Strategy v3.8.0. Phase 2 per-ticker deep dive adds dual IV rank confirmation and vol skew gate. §2.7 pre-trade adds vol skew check. §2.8 strike selection updated — live GEX by strike as primary anchor (pending market-hours confirmation). MSFT de-risking noted in weekly routine. Advisory framing explicit throughout.

**v1.6 changes from v1.5:** Standalone `quantdata-mcp` server registered in Claude Desktop alongside `fortress-dashboard`. All 6 legacy `qd_*` proxy tools removed from `fortress_mcp.py` (v4.2.0). QuantData tools now called directly via the `quantdata` MCP (26 widget tools available). **Tested status (2026-06-01):** `qd_get_iv_rank(ticker)` confirmed working per-ticker. `qd_get_dark_pool_levels` and `qd_get_order_flow` remain SPX widget-locked — still market-level signals only. `qd_get_volatility_skew` and `qd_get_exposure_by_strike` return no data outside market hours — untested; retest tomorrow during market hours.

**v1.5 changes from v1.4:** Two-layer Phase 2 (SPY qd_* + per-ticker yfinance). Data source table clarifying which tools are accurate per-ticker.

**v1.3 changes from v1.2:** Updated for Strategy v3.7 and Sprint v7.x dashboard changes. QuantData API calls now use widget-UUID REST endpoints — the deprecated `tool/OPTIONS_*` tool IDs have been removed from `chart.py` and are no longer valid. Credential refresh workflow updated to reference the Settings → QuantData Credentials UI (no SSH required). `get_market_intelligence` response now includes sort/regime score fields. Maintenance section updated with correct document version chain.

**v1.2 changes from v1.1:** The MCP server (`fortress_mcp.py`) and example scripts have been moved to a dedicated repository — **[citychip/fortress-mcp](https://github.com/citychip/fortress-mcp)**. The `scripts/mcp_*.py` files previously in this repo have been removed; equivalent cleaned-up scripts are in `fortress-mcp/examples/`. See the fortress-mcp README for Claude Desktop installation and configuration.

**v1.1 changes from v1.0:** USD-native currency convention; CP Gateway re-auth path replaces TWS popup workflow; `get_capability` tool added for "is Greeks coverage live?" checks; delta thresholds reflect v3.6 (>0.35 critical).

**Installation:**
```bash
# Fortress MCP
git clone https://github.com/citychip/fortress-mcp.git && pip install -r fortress-mcp/requirements.txt
# QuantData MCP
pip3 install quantdata-mcp --break-system-packages
```
Add both config blocks to `claude_desktop_config.json` (see `fortress-mcp/claude_desktop_config_snippet.json`) and restart Claude Desktop.

Use this document as:

- A copy-paste reference for the morning routine
- A set of saved-prompt templates for Claude Desktop
- A test plan for verifying the MCP works end-to-end after install

If a prompt below stops producing the expected tool calls, the MCP probably regressed. If it produces them but the response is wrong, the underlying dashboard endpoint or strategy rule is wrong — fix the dashboard, not the MCP.

---

## 1. How this works

Once the Fortress MCP and QuantData MCP are installed in Claude Desktop, every prompt below should trigger Claude to call one or more MCP tools, reason over the JSON returns, and reply in natural language. The tools wrap existing dashboard endpoints and the QuantData API — there's no AI-generated data; every number Claude cites comes from deterministic sources.

**Conventions used in this doc:**

- `prompt:` → what the trader types into Claude
- `tools:` → which MCP tools Claude should call (in order if order matters)
- `response:` → the expected shape of Claude's natural-language reply
- `notes:` → caveats, follow-ups, or strategy refs
- `[fortress]` / `[quantdata]` → which MCP server provides the tool

**Tool reference:**

**Fortress MCP — Tier 1 (read-only, yfinance/IBKR-based):**
`get_briefing`, `get_positions`, `get_candidates`, `get_calendar`, `get_universe`, `get_journal`, `get_alerts`, `get_chart_data`, `get_dp_floors_and_gex`, `get_market_intelligence`, `get_vol_analytics`, `get_earnings_volatility`, `get_earnings_history`, `evaluate_stop_loss`, `evaluate_roll`, `evaluate_post_earnings`, `validate_jade_lizard`, `get_spy_hedge_coverage`, `pretrade_check`, `get_ibkr_status`, `get_capability`, `get_settings`, `get_settings_narrative`, `get_quantdata_reports`, `get_position_limits`, `get_forward_pnl`, `get_pnl`, `get_pnl_history`, `get_portfolio_beta`, `get_sector_exposure`, `get_capital_efficiency`, `get_pcs_exposure`, `get_trade_report`, `get_order_flow_chart`, `get_pretrade_all`, `get_stop_loss_all`, `get_roll_all`, `get_hydrated_assets`, `get_ibkr_preview`, `list_scripts`, `get_time_of_day`, `get_journal_suggestion`, `get_pending_orders`, `options_greeks`, `get_version`

**Fortress MCP — Tier 2 (write, requires `FORTRESS_MCP_ALLOW_WRITES=1`):**
`add_journal_entry`, `add_alert`, `update_alert`, `delete_alert`, `update_calendar`, `add_excluded_ticker`, `add_universe_ticker`, `update_settings_section`, `trigger_ibkr_sync`, `retry_ibkr_sync`, `run_script`, `stage_order`, `approve_order`, `decline_order`, `preview_order`, `refresh_iv_data`

**QuantData MCP — 50 tools (full per-ticker support, live data):**
`qd_get_market_snapshot`, `qd_get_net_drift`, `qd_get_dark_pool_levels`, `qd_get_exposure_by_strike`, `qd_get_exposure_by_expiration`, `qd_get_order_flow`, `qd_get_unconsolidated_flow`, `qd_get_heat_map`, `qd_get_interval_map`, `qd_get_gainers_losers`, `qd_get_volatility_skew`, `qd_get_term_structure`, `qd_get_volatility_drift`, `qd_get_oi_change`, `qd_get_oi_by_expiration`, `qd_get_oi_by_strike`, `qd_get_oi_over_time`, `qd_get_max_pain`, `qd_get_max_pain_over_time`, `qd_get_iv_rank`, `qd_get_contract_price`, `qd_get_contract_statistics`, `qd_get_equity_prints`, `qd_get_stock_price_time`, `qd_get_net_flow`, `qd_get_trade_side_stats`, `qd_get_news_articles`, plus page and filter management tools.

> **Data source guidance (tested status 2026-06-01):**
> - `qd_get_iv_rank(ticker)` [quantdata] ✓ confirmed per-ticker — use as live cross-check on yfinance IV from `get_candidates()`
> - `qd_get_dark_pool_levels` [quantdata] ✗ widget locked to SPX — market-level only, same as before
> - `qd_get_order_flow` [quantdata] ✗ widget locked to SPX — market-level only, same as before
> - `qd_get_volatility_skew`, `qd_get_exposure_by_strike` [quantdata] ⏱ return empty outside market hours — retest during market hours
> - `get_dp_floors_and_gex(ticker)` [fortress] — still best source for per-ticker GEX walls (daily report, ~12h old, stable intraday)
> - `get_candidates()` / `refresh_iv_data()` [fortress] — fastest for full-universe IV crush ranking (yfinance batch)

> **QuantData credential note:** If QuantData tools return 401/403 or empty data, the session has expired. Refresh at **Dashboard → Settings → QuantData Auto-Login**, then copy `~/.quantdata-mcp/config.json` and restart Claude Desktop. See `operations/04_Incident_Recovery_Playbook.md` §5.

---

## 2. Daily routine — phase-by-phase prompts

> **CURRENT BOOK STATE (June 2026):** MSFT concentration at 99% (no new entries). Portfolio beta-weighted delta at 593 — well above 320 target. MSFT short call delta at 0.396, approaching 0.40 roll threshold. Regime: Bearish. Top IV candidates: META, V, AAPL, AMZN (all PRIME CRUSH). **The workflow prioritizes monitoring MSFT roll trigger and selective new entries in non-concentrated names.**

### Phase 1 — Pre-Market (09:00–09:35 ET / 15:00–15:35 Amsterdam)

#### 2.1 Morning Preflight (The Full Sweep)

> **prompt:** *"Run my morning preflight: briefing, fresh IV scan, max pain sweep, stop-loss sweep, roll sweep, portfolio beta, SPY hedge coverage, and today's earnings calendar."*
>
> **tools:** `get_briefing()` [fortress] → `refresh_iv_data()` [fortress] → `run_script("max_pain")` [fortress] → `get_stop_loss_all()` [fortress] → `get_roll_all()` [fortress] → `get_portfolio_beta()` [fortress] → `get_spy_hedge_coverage()` [fortress] → `get_calendar(14)` [fortress] → `get_pnl()` [fortress]
>
> **response:**
> 1. **Briefing:** Net Liq, delta vs 320 target, pacing (0/5), MSFT concentration, staleness check.
> 2. **IV scan:** Full universe ranked by IVR + IV/HV spread — PRIME CRUSH / GOOD SPREAD signals.
> 3. **Max pain:** Per-ticker max pain strike + pinning direction. Current: MSFT -8.1% (pulling down), GOOGL +1.4% (pulling up). Use to anchor strike selection.
> 4. **Stop/roll:** Any overnight triggers + positions approaching DTE threshold.
> 5. **Beta/hedge:** Portfolio β-delta vs 320 target. SPY hedge vs $20k–$30k band.
> 6. **Calendar:** Earnings blackout check for next 14 days.
>
> **notes:** `refresh_iv_data()` and `run_script("max_pain")` run in ~15s and ~5s respectively. Do NOT look at candidates until stop-loss and roll sweeps are clean. Pass criteria to move to Phase 2: no ACT-state stop-loss, no unaddressed rolls, hedge within band.

### Phase 2 — Market Open (09:35–10:00 ET)

#### 2.2 Macro regime and flow validation (Only on entry days)

> **prompt:** *"Show me SPY market intelligence, net drift, dark pool levels, and order flow. Then for candidates with IVR > 50 and earnings > 21 days, pull per-ticker market intel, GEX walls, vol analytics, IV rank, and earnings volatility."*
>
> **tools (SPY/market-level):**
> `get_market_intelligence("SPY")` [fortress] → `qd_get_net_drift("SPY")` [quantdata] → `qd_get_dark_pool_levels("SPY")` [quantdata] → `qd_get_order_flow("SPY", min_premium=100000)` [quantdata]
>
> **tools (per-ticker):**
> `get_candidates()` [fortress] → for each valid candidate: `qd_get_iv_rank(ticker)` [quantdata] → `qd_get_volatility_skew(ticker)` [quantdata] → `get_market_intelligence(ticker)` [fortress] → `get_dp_floors_and_gex(ticker)` [fortress] → `get_earnings_volatility(ticker)` [fortress]
>
> **response:** Two-layer picture: (1) SPY macro context — regime score, GEX flip zone, institutional flow bias, dark pool floors. (2) Per-candidate structural levels — GEX walls (daily report), IV skew shape, earnings risk ratio, live QuantData IV rank as cross-check on yfinance.
>
> **notes:** `qd_get_dark_pool_levels` and `qd_get_order_flow` are currently SPX widget-locked — pass `"SPY"` or `"SPX"` only. `qd_get_iv_rank(ticker)` is confirmed working per-ticker. `qd_get_volatility_skew(ticker)` and `qd_get_exposure_by_strike(ticker)` are pending market-hours test — add to this workflow once confirmed. The `get_market_intelligence` response includes a `regime_score` field (-4 to +4) and `sort_key` — use these to prioritise which tickers to analyse first.

### Phase 3 — Intraday Triggers (Event-driven, not scheduled)

#### 2.3 Intraday Alerting

> **prompt:** *"Add stop-loss alerts at the act threshold for every position over 5% of NetLiq, and a delta-watch alert at 0.7 for any position with delta > 0.6."*
>
> **tools:** `add_alert()` [fortress] (called iteratively)
>
> **response:** Confirms alerts have been set.
>
> **notes:** Set this up once, then react when they fire. The `evaluate_stop_loss` and `evaluate_roll` tools are decision support when they do.

#### 2.4 Regime change on concentrated positions

> **prompt:** *"Compare today's get_market_intelligence for MSFT against yesterday's get_market_intelligence for MSFT — has the dominant DP floor or GEX put wall migrated down?"*
>
> **tools:** `get_market_intelligence("MSFT")` [fortress]
>
> **response:** Evaluates whether institutional support levels have dropped.
>
> **notes:** If yes, that's the day to tighten or roll the concentrated exposure, not the day to ride it out.

### Phase 4 — Post-Close (~16:00–16:30 ET)

#### 2.5 EOD Review

> **prompt:** *"Log today's trades to the journal with the strategy reasoning. Then evaluate any position where mark-to-market changed more than 50% today. Finally, update tomorrow's calendar from any earnings reschedules I should know about."*
>
> **tools:** `add_journal_entry()` [fortress] → `evaluate_stop_loss()` / `evaluate_roll()` [fortress] → `update_calendar()` [fortress]
>
> **response:** Confirms journal entries. Evaluates movers. Updates calendar.
>
> **notes:** Journaling is the highest-ROI habit. Use `get_journal` in 6 weeks to find which entry templates actually worked.

### Phase 5 — Weekly Workflow (Sunday ~18:00 ET)

#### 2.6 Full Portfolio Audit & De-risking

> **prompt:** *"Run a full portfolio audit: briefing, all positions aggregated and non-aggregated, concentration breakdown, SPY hedge coverage, and current Greeks. Then for each position over 10% of NetLiq, run evaluate_roll and tell me three concrete options to reduce concentration: roll out, scale down, or convert to a debit spread. Show me get_market_intelligence for the underlying for context."*
>
> **tools:** `get_briefing()` [fortress] → `get_positions()` [fortress] → `get_spy_hedge_coverage()` [fortress] → `evaluate_roll()` [fortress] → `get_market_intelligence()` [fortress]
>
> **response:** Comprehensive audit. Proposes specific structures to deload concentrated positions (e.g., MSFT) and specific SPY put structures to close the hedge gap.
>
> **notes:** This is where you make the decision to deload MSFT — not on a random Tuesday. Plan it on Sunday, execute on Monday, journal the reasoning.

### Phase 6 — Position-Event Workflows (When something fires)

#### 2.7 Pre-trade gate before any new entry

> **prompt:** *"I'm thinking AMD PMCC. Run the pre-trade gates."*
>
> **tools:** `pretrade_check("AMD", "PMCC")` [fortress] → `qd_get_iv_rank("AMD")` [quantdata] → `qd_get_volatility_skew("AMD")` [quantdata] → `qd_get_order_flow("SPY", min_premium=50000)` [quantdata]
>
> **response:** All five gates with verdict + reason: §3.3 exclusion, §4 earnings blackout, §7 concentration, §7 VIX, and the LEAP blackout gate. Then: (1) dual IV rank confirmation — yfinance IVR from candidates vs live QuantData IVR; flag if divergence > 15pp. (2) vol skew check — steep put skew flags elevated downside risk; document if proceeding. (3) SPY order flow for broad market context.
>
> **notes:** Per Strategy §15.1, all gates are advisory — a failing gate doesn't block but requires explicit acknowledgement and journal entry.

#### 2.8 Strike selection prep

> **prompt:** *"For AMD PMCC, where should I be looking for the short strike? Pull the structural levels."*
>
> **tools:** `get_chart_data("AMD", period="6mo")` [fortress] → `qd_get_exposure_by_strike("AMD")` [quantdata] → `qd_get_dark_pool_levels("SPY")` [quantdata]
>
> **response:** Current spot, 50-day SMA, 200-day SMA. Live GEX call/put walls by strike from QuantData (primary anchor per §5 — ⏱ pending market-hours confirmation). SPY dark pool for broad structural context. Suggests short strike zone: just below the nearest GEX call wall above current price, confirmed by delta 0.25–0.30 check.
>
> **notes:** `qd_get_exposure_by_strike` returns empty outside market hours — fall back to `get_dp_floors_and_gex("AMD")` [fortress] (daily report). `qd_get_dark_pool_levels` is SPX-level only. Reminder per §15.1: Claude suggests zones, trader decides exact strike.

#### 2.9 Post-earnings playbook

> **prompt:** *"AMD opened down 6%, IV crushed 35%. Walk me through the playbook."*
>
> **tools:** `evaluate_post_earnings(ticker="AMD", gap_pct=-6.0, iv_crush_pct=35, thesis={revenue_beat: true, guidance_maintained: true, no_leadership_or_regulatory_event: true, sector_context_normal: true})` [fortress] → `pretrade_check("AMD", "PMCC")` [fortress] → `qd_get_dark_pool_levels("AMD")` [quantdata]
>
> **response:** Matrix verdict (PRIME_ENTRY for −6% with IV crush ≥ 25%), final action (PROCEED if all 4 thesis checks pass), size cap if any, overrides applied. Then runs the pre-trade gate. Then the structural levels for strike selection.
>
> **notes:** If thesis checks haven't been confirmed, prompt: "Confirm thesis health checklist first — revenue beat, guidance maintained, no leadership/regulatory event, sector context normal." Don't assume.

#### 2.10 Jade Lizard validation

> **prompt:** *"Validate this MSFT Jade Lizard: short put $400 / call spread $480-$490, put credit $5.20, call spread credit $5.85."*
>
> **tools:** `validate_jade_lizard(put_strike=400, call_short_strike=480, call_long_strike=490, put_credit=5.20, call_spread_credit=5.85)` [fortress] → `pretrade_check("MSFT", "JADE_LIZARD")` [fortress]
>
> **response:** Validator verdict (PASS — total credit $11.05 exceeds call spread width $10 by $1.05). Followed by the pre-trade gate. Reminds: Tier 1 only per §2.E.

#### 2.11 Trade Staging — Claude-native leg-builder

This is the primary trade execution workflow. Claude constructs the order, stages it, shows a confirmation summary, and **waits for explicit approval** before submitting to IBKR. The Parapet Orders page (`localhost:4000/orders`) serves as a visual log of all staged and completed orders.

**Pattern: plain-English → stage → confirm → approve/decline**

> **prompt:** *"Stage a roll for NVDA: buy back the C230 Jul17, sell a C250 Aug21. Debit limit $1.20."*
>
> **Claude constructs:**
> ```
> stage_order(
>     ticker="NVDA",
>     strategy="PMCC",
>     legs=[
>         {"ticker":"NVDA","sec_type":"OPT","right":"C","strike":230,"expiry":"20260717","action":"BUY","ratio":1},
>         {"ticker":"NVDA","sec_type":"OPT","right":"C","strike":250,"expiry":"20260821","action":"SELL","ratio":1}
>     ],
>     quantity=1,
>     order_type="LMT",
>     limit_price=1.20,
>     notes="Delta roll: C230 Jul → C250 Aug. Delta 0.425→0.308.",
>     max_loss=-130.0
> )
> ```
>
> **Claude shows confirmation summary:**
> ```
> ⚠ NVDA PMCC ROLL
> BUY  C230 Jul17
> SELL C250 Aug21
> Limit: $1.20 debit | Max loss: -$130
> Notes: Delta roll — C230→C250, delta 0.425→0.308
>
> Approve or decline?
> ```
>
> **tools:** `stage_order()` [fortress] → (on "approve") `preview_order()` [fortress] → `approve_order()` [fortress]
>
> **response on approve:** IBKR order ID confirmed. Claude logs the trade rationale to the journal.
>
> **response on decline:** Order declined. Nothing submitted to IBKR.
>
> **notes:** FORTRESS_MCP_ALLOW_WRITES=1 must be set in Claude Desktop config for write tools to work. Claude should always show the summary and wait — never auto-approve. The `preview_order` (IBKR whatif) is called before `approve_order` to verify margin impact. Staged orders appear in Parapet → Orders immediately after `stage_order`.

**Supported plain-English formats:**

| What you say | What Claude stages |
|---|---|
| *"Roll NVDA C230 Jul to C250 Aug, debit limit 1.20"* | 2-leg LMT roll |
| *"Stage a GOOGL PMCC: sell C430 Aug21 at 0.28 delta, limit $4.50"* | 1-leg SELL OPT LMT |
| *"Sell to close the AMD Jun26 put spread at $0.15 credit"* | 2-leg close |
| *"Stage a META IC: sell 550P / buy 535P / sell 695C / buy 710C Jul17, credit limit $4.00"* | 4-leg IC LMT |

**Required leg fields** (Claude must include all of these — none are optional):
`ticker`, `sec_type` ("OPT"), `right` ("C" or "P"), `strike` (float), `expiry` ("YYYYMMDD"), `action` ("BUY" or "SELL"), `ratio` (int, usually 1)

**Pre-staging checklist** (Claude runs these before staging any new entry):
1. `pretrade_check(ticker, strategy)` — gates clear?
2. `qd_get_iv_rank(ticker)` — IVR > 25 dual-confirmed?
3. Check pacing (from `get_briefing`) — entries remaining this week?
4. Check concentration — MSFT locked out until <50% NLQ

---

## 3. Failure modes to expect

How Claude should handle common error conditions:

| Condition | Symptom | What Claude should do |
|---|---|---|
| QuantData credentials expired | `qd_get_*` returns 401/403 or empty data | Flag immediately. Direct trader to **Settings → QuantData Credentials** to refresh, then copy `~/.quantdata-mcp/config.json` and restart Claude Desktop. See `operations/04_Incident_Recovery_Playbook.md` §5. |
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
> **why:** These deprecated tool IDs were removed in Sprint v7.1 after causing 400 errors and account revocation. All QuantData calls now go through the standalone `quantdata-mcp` server — use the `qd_*` tools it provides. Don't bypass them.

---

## 5. Saved-prompt suggestions

| Slot | Prompt | Purpose |
|---|---|---|
| Morning | *"Sync and brief me. What's HIGH today?"* | §2.1 + §2.2 combined |
| Pre-trade | *"Pre-trade gate on {TICKER} for {STRATEGY}. Then suggest strike zones."* | §2.7 + §2.8 |
| Post-earnings | *"Post-earnings playbook: {TICKER} gap {X}%, IV crush {Y}%. Thesis confirmed."* | §2.9 |
| Market Intel | *"What's the regime on {TICKER}? Show me the GEX walls and DP floors."* | `get_market_intelligence` + `qd_get_exposure_by_strike` |
| Stage trade | *"Stage a [STRATEGY] for [TICKER]: [plain-English legs]. [Limit price]."* | §2.11 |
| Roll review | *"Roll review across the book, ordered by urgency."* | §2.6 |
| Sunday | *"Run my Sunday planning checklist."* | §2.6 |
| Pulse | *"Quick book status."* | `get_briefing` |
| Health | *"MCP and gateway health check."* | `get_capability` + `get_ibkr_status` |
| QD Health | *"Check QuantData connectivity."* | `qd_get_iv_rank("SPY")` [quantdata] |

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
| 1.7 | 2026-06-01 | Updated for Strategy v3.8.0. Dual IV rank gate in Phase 2 and §2.7. Vol skew gate added to §2.7. §2.8 updated for live GEX by strike (pending market-hours test). Advisory framing throughout. |
| 1.6 | 2026-06-01 | Standalone quantdata-mcp registered. Legacy qd_* proxy tools removed from fortress_mcp.py (v4.2.0). qd_get_iv_rank confirmed per-ticker. Dark pool and order flow remain SPX widget-locked. |
| 1.5 | 2026-06-01 | Two-layer Phase 2. Data source clarification. qd_* SPY-only caveat documented. |
| 1.3 | 2026-05-18 | Updated for Strategy v3.7 and Sprint v7.x. QuantData credential refresh via Settings UI. Deprecated `tool/OPTIONS_*` anti-pattern added. `get_market_intelligence` regime_score field noted. |
| 1.2 | 2026-05-09 | MCP server moved to `citychip/fortress-mcp` repo. |
| 1.1 | 2026-05-05 | USD-native currency. CP Gateway re-auth. `get_capability` tool. |
| 1.0 | 2026-05-03 | Initial release. |

---

## 7. Full MCP Order Workflow (Sprint 11+)

The complete end-to-end trading workflow is now available via MCP. Requires `FORTRESS_MCP_ALLOW_WRITES=1`.

#### 7.1 Refresh IV data before scanning

> **prompt:** *"Refresh the IV data and show me today's top candidates."*
>
> **tools:** `refresh_iv_data()` [fortress] → `get_candidates()` [fortress]
>
> **response:** Fresh IV scan results ranked by IVR and IV/HV spread, with PRIME CRUSH / GOOD SPREAD / BLOCKED signals.
>
> **notes:** Use this when IVR values look stale or show 0 intraday. Takes ~15 seconds.

#### 7.2 Stage an order for approval

> **prompt:** *"Stage a CSP on GOOGL, sell the 340 put expiring Jul 17 2026, 1 contract at $2.50 limit."*
>
> **tools:** `pretrade_check("GOOGL", "CSP")` [fortress] → `stage_order(ticker, strategy, legs, ...)` [fortress]
>
> **response:** Order staged with an order_id. Provides next steps for preview and approval.
>
> **example call:**
> ```python
> stage_order(
>     ticker="GOOGL",
>     strategy="CSP",
>     legs=[{"ticker":"GOOGL","sec_type":"OPT","right":"P",
>            "strike":340.0,"expiry":"20260717","action":"SELL","ratio":1}],
>     quantity=1,
>     order_type="LMT",
>     limit_price=2.50,
>     notes="IVR 71, spread +7.9pp, pretrade passed",
>     pop=0.79,
>     max_profit=250.0,
>     max_loss=-33750.0
> )
> ```
>
> **notes:** Returns `order_id`. Order appears in Build Center (Trade → Orders tab) for human review.

#### 7.3 Preview and approve

> **prompt:** *"Preview order {order_id} and if margin looks acceptable, approve it."*
>
> **tools:** `preview_order(order_id)` [fortress] → `approve_order(order_id)` [fortress]
>
> **response:** IBKR whatif result (equity impact, margin, commission), then submission confirmation with IBKR order ID.
>
> **notes:** `preview_order` is a whatif — it does NOT submit. `approve_order` resolves conids and submits to IBKR. Always preview before approve.

#### 7.4 Complete workflow prompt

> **prompt:** *"Run my pre-trade workflow for GOOGL: check market intel, IV rank, run pretrade gate, then if everything passes stage a CSP at the 0.20 delta put for the next 45 DTE expiry."*
>
> **tools:** `get_market_intelligence("GOOGL")` [fortress] → `qd_get_iv_rank("GOOGL")` [quantdata] → `pretrade_check("GOOGL","CSP")` [fortress] → `options_greeks(...)` [fortress] → `stage_order(...)` [fortress]
>
> **notes:** Claude will calculate the approximate 0.20 delta strike using options_greeks and construct the leg automatically.
