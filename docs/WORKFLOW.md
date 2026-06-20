# Fortress — Daily Workflow
**v2.7 · Updated 2026-06-16 (catalyst gate + `get_vix_term` VIX term-structure input; ex-div assignment check; `journal_analytics.py` feedback loop; GEX/skew/liquidity NaN-500 fix + deploy smoke-test; IBKR-first verified; gateway-down + alert gotchas — see ⚠ below)**

> ⚠ **2026-06-10 — QuantData `iv_rank` is broken upstream** (ticker argument ignored; SPX/MSFT/NVDA return identical payloads). IV rank comes from the **fortress MCP `get_iv_rank(ticker)`**. All `qd_get_iv_rank` references below and in 07_MCP_Workflow are superseded.
>
> ⚠ **2026-06-10 evening — backend is now IBKR-first** (Data Sources Optimization P1-P4, deployed + verified): spot (incl. conditional-alert evaluation), liquidity bid/ask, IV rank, and vol skew pull real-time data from IBKR CP Gateway, silent yfinance/BS-inversion fallback. Check the `source`/`iv_source` field in payloads: `ibkr` = live; `bs_inversion`/`yfinance_bs` = delayed-but-sane fallback (gateway down or 0DTE). Cross-check against `massive` chain IV if a number looks off.

---

## MCP Tooling Stack

| Tool | Source | Use for |
|---|---|---|
| `fortress-dashboard` | Plugin: fortress | Briefing, positions, P&L, orders, candidates, rolls, stop-losses, market intel, **IV rank (`get_iv_rank`)**, GEX, vol skew, liquidity |
| `quantdata` | AppData config (WSL stdio) | Order flow, dark pool levels, max pain, OI, net flow — **NOT iv_rank / volatility_skew / exposure_by_strike (broken)** |
| `fmp` | Plugin: fmp (HTTP, free tier) | Company profile, 52-week range, dividend check — candidate sanity check |
| `fred` | Plugin: fred (WSL stdio) | Macro regime: yield curve, Fed funds rate, CPI releases, upcoming economic dates |
| `massive` | Plugin: massive (WSL stdio) | Options chain backup; greeks, IV, OI from OPRA; 15-min delayed — independent IV cross-check |

**Rule:** Start every portfolio question with `fortress-dashboard`. Use `quantdata` for flow/dark-pool/max-pain only. Use `fmp` for new ticker sanity check. Use `fred` for macro regime context. Use `massive` for an independent chain/IV check.

**FMP free tier covers:** company profile, price, beta, 52w range, market cap, sector, last dividend, volume vs average volume.  
**FMP free tier does NOT cover:** earnings calendar, earnings history, economic calendar, analyst ratings (these require Starter at $19/mo — not worth it since Fortress covers earnings via yfinance).

**FRED key series:** T10Y2Y (yield spread), FEDFUNDS (rate environment), CPIAUCSL (inflation), DGS10 (10yr treasury), VIXCLS (vol backup).

**Massive key endpoint:** `/v3/snapshot/options/{ticker}` — full chain with greeks. Use when `qd_get_exposure_by_strike` or `qd_get_volatility_skew` return empty.

---

## Quick Reference (merged from 03_Quick_Start cheatsheet, 2026-06-15)

### System URLs & Access
| Service | URL / Command | Notes |
|---|---|---|
| Fortress V4 Dashboard | `http://localhost` | nginx → React |
| Dashboard health | `GET http://localhost:8081/api/health` | liveness |
| IBKR status | `GET http://localhost:8081/api/ibkr/status` | connection + account |
| FastAPI docs | `http://localhost:8081/docs` | auto API docs |
| IBKR CP Gateway | `https://localhost:5000` | iBeam headless |
| QuantData | `https://v3.quantdata.us` | credential refresh |
| Parapet | `http://localhost:4000` | active UI |

### Key Thresholds (current)
| Metric | Floor / Target | Action if breached |
|---|---|---|
| Available Funds | > $17K | pause new entries |
| Excess Liq | > $25K | pause new entries |
| β-weighted Δ | ~320 target | hedge/trim if far over; add if well under |
| MSFT concentration | < 50% NLV | **achieved (41.9%)** — no new MSFT legs |
| SPY hedge | $20K–$30K notional | buy puts to close gap |
| IV Rank (entry) | ≥ 25 (≥ 50 prime) | min for premium selling |
| DTE short leg | 30–45 entry / ≤ 21 roll | entry window / roll trigger |
| Δ short leg | 0.25–0.30 (PMCC), 0.15–0.20 (PCS) | roll if > 0.40 |
| Profit target / stop | close at 50% gain / 200% of credit | manage |

### QuantData credential refresh (when Market Intel / flow shows no data)
Auto: daily 06:00 ET via APScheduler (`qd_refresh_session.py`). Manual:
1. Dashboard → Settings → QuantData Auto-Login, or `cd ~/fortress-v4-api && venv/bin/python3 quant/qd_refresh_session.py`
2. `sudo cp ~/.quantdata-mcp/config.json /root/.quantdata-mcp/config.json`
3. `sudo systemctl restart fortress-dashboard-v4`, then relaunch Claude Desktop to pick up the new token.

---

## How the Tools Work Together (Trade Decision Logic)

Every trade goes through six stages. Each stage is cross-confirmed by at least two data sources before moving forward.

**Stage 1 — Macro regime + catalyst gate (FRED + Fortress)**
Before looking at candidates, check whether the environment supports entering at all. FRED provides the yield curve (T10Y2Y), rate direction (FEDFUNDS), and inflation trend (CPIAUCSL). Fortress provides the regime signal (bearish/neutral/bullish based on VIX + SPY drift) and SPY hedge coverage. In a bearish regime with rising VIX, pacing gets more conservative and strike selection shifts further OTM.

**Catalyst gate (§4 binary-event timing):** `get_macro_events()` [fortress] surfaces upcoming FOMC/CPI/PPI/NFP/PCE with `days_until` and a `defer_advisory` flag. If a high-impact event is inside the defer window (default 2d), **hold new premium-selling entries until it clears** — selling vol right before a binary print means shorting premium that can gap either way. Advisory only (§15.1). Keep the calendar current by curating FRED/FMP dates into `set_macro_events()`; it feeds the Parapet Briefing event-horizon row + amber defer banner. (Full design: `CATALYST_GATE_PROPOSAL.md`.)

**Vol regime (VIX term structure):** `get_vix_term()` [fortress] compares spot VIX to VIX3M — contango (VIX < VIX3M) favors premium selling; backwardation (VIX > VIX3M) flags stress, so tighten size or defer new short premium. Read it alongside the regime score, not instead of it.

**Stage 2 — Candidate identification (Fortress)**
Fortress scans the universe for tickers with IVR > 25, no earnings gate violation (7-day buffer), and delta headroom. IV rank comes from `get_iv_rank()` (fortress MCP — backend yfinance, BS-inverted; the old QuantData dual-confirm is retired since `qd_get_iv_rank` is broken upstream). For an independent check when a number looks off, pull chain IV via `massive`. QuantData order flow remains a second filter: if unusual put buying or heavy call selling is showing on a ticker, skip it regardless of IVR.

**Stage 3 — New ticker sanity check (FMP)**
For any ticker not already in the universe, FMP pulls a quick profile: price relative to 52-week range (near a top?), beta (portfolio delta impact), dividend date (ex-div risk for covered calls), sector (concentration check). Catches candidates that look good on IV but are structurally wrong.

**Stage 4 — Strike selection (Fortress + QuantData → Massive as backup)**
Fortress provides DP floors (dark pool support) and GEX walls (gamma exposure — where market makers hedge heaviest). QuantData backs this with exposure-by-strike data. The short call strike anchors to the GEX call wall, targeting Δ 0.25–0.30 — the wall acts as a natural ceiling. If QuantData's exposure-by-strike is broken during market hours (known bug), use Massive `/v3/snapshot/options/{ticker}` for an independent greeks check.

**Stage 5 — Pre-trade check + order staging (Fortress)**
`pretrade_check()` validates: earnings gate clear, pacing < 5/week, MSFT concentration below threshold, regime not full bearish. `stage_order()` builds the combo order with all required leg fields. `preview_order()` confirms IBKR margin impact. Nothing is sent to IBKR without an explicit approve step in Parapet.

**Stage 6 — Position management (Fortress + QuantData + Massive)**
Daily: Fortress flags roll triggers (short call Δ > 0.40 or DTE ≤ 21) and stop-loss ACT signals (underlying below 200-SMA floor). QuantData provides real-time GEX and dark pool levels to determine roll direction (up vs. out). If QuantData is down, Massive provides an independent snapshot for greeks verification before any roll decision.

**Why this matters:** The dual-confirm rule (two independent IV sources before entry) and GEX + DP floor anchoring (two independent strike references) are the two guardrails that prevent the most common PMCC failure modes — entering when IV is insufficient and getting assigned at the wrong strike.

---

## Morning Startup (5 min)

**1. Check iBeam (headless — authenticates automatically)**
- Open Parapet → System → Settings → Connections
- If IBKR ● green → authenticated, proceed
- If IBKR ● red → click **⟳ Reconnect** → wait ~35s → auto-syncs on success
- Verify: **IBKR ● green** in sidebar + Overview Positions tab loaded

**2. Morning preflight via Claude**
```
Run my morning preflight: briefing, SPY hedge, today's calendar, stop-loss signals
```
Checks: Net Liq · MSFT concentration · portfolio delta · SPY hedge coverage · pacing

**3. Refresh IV + max pain (always)**
```
run_script("max_pain") then refresh_iv_data()
```
Takes ~15s. Required before looking at candidates.

**4. Candidates scan (entry days only)**
Open Parapet → Candidates page. Shows IVR, gate status, spread.  
Or via Claude: `get_candidates()` — filters can_trade=True, sorts by IVR desc.

---

## Entry Workflow

**Step 0 — Candidate sanity check (new tickers only)**
For any ticker not already in the universe, pull a quick profile via FMP:
```
Company profile for [TICKER]   # fmp MCP → profile-symbol endpoint
```
Check: 52w range (where is price relative to range?), beta (affects portfolio delta), last dividend (ex-div risk for covered calls), sector, average vs current volume.

**Step 1 — Macro context + catalyst gate**
```
SPY market intel, net drift, dark pool levels
get_macro_events()          # FOMC/CPI/PPI/NFP/PCE — defer_advisory? hold if high-impact ≤2d (§4)
```

**Step 2 — Per-candidate confirmation**
For each READY candidate (IVR > 25):
```
IV rank + intel for [TICKER]
get_iv_rank("[TICKER]")             # fortress MCP — canonical IVR source
get_market_intelligence("[TICKER]") # fortress MCP
```
IVR must be ≥ 25 (`source: hv_proxy` is acceptable; it tightens automatically as snapshots accumulate). If the number looks implausible, cross-check chain IV via massive before entering.

**Step 3 — Strike selection**
```
GEX walls and DP floor for [TICKER]
get_dp_floors_and_gex("[TICKER]")
```
Strike anchor: GEX call wall → Δ 0.25–0.30 → chart confirmation

**Step 4 — Stage order**
```
Stage PMCC short call for [TICKER]: sell [strike]C [expiry], limit [price], qty [n]
```
Required leg fields: ticker, sec_type, right, strike, expiry, action, ratio  
limit_price must be POSITIVE for combo orders.

**Step 5 — Approve**
Parapet → Orders → Approve (or via Claude: `approve_order(id)`)

---

## Roll Workflow

**When to roll:** Short call Δ > 0.40 OR DTE ≤ 21

**Step 1 — Identify**
```
Check roll candidates: get_roll_all()
```

**Step 2 — Evaluate**
```
Evaluate roll for [TICKER]: evaluate_roll("[ticker]", "[current_short]", "[expiry]")
```

**Step 3 — Stage**
```
Stage roll for [TICKER]: buy [current_strike]C [current_expiry], sell [new_strike]C [new_expiry], limit [price]
```

---

## Stop-Loss Workflow

**Trigger:** `delta_state = "critical"` OR stop-loss ACT signal

**Step 1:**
```
evaluate_stop_loss("[TICKER]")
```

**Step 2 — If verdict is ACT:**
```
Stage close for [TICKER] [leg_description]
```

---

## Ex-Dividend Assignment Check (short calls / covered calls)

Early assignment risk on a short call spikes when it is **ITM near an ex-dividend date** — the counterparty exercises to capture the dividend. Before each ex-div for a dividend-paying holding:

```
Pull the ex-div calendar (FMP dividends-calendar), then for any ITM / near-ITM
short call expiring after the ex-div date, flag early-assignment risk.
```

Verified 2026-06-16: FMP `dividends-calendar` works on the current tier (only `economics` is paywalled). Rule of thumb: **only ITM calls carry real dividend-capture risk** — deep-OTM short calls (e.g. the current MSFT 490/510) are safe regardless of ex-div. Non-dividend names (AMZN, GOOGL, NVDA, META) are never at ex-div risk. No action needed when no held name has an ex-div before its short-call expiry (the case on 2026-06-16).

**Automated since 2026-06-20 (Sprint 15.4):** this check is now codified as a Claude-curated gate (same pattern as the catalyst gate). Curate the upcoming ex-div dates from FMP for the held dividend-paying names, then push them in: `set_ex_div_events([{ticker, ex_date, amount?}, ...])` (write). `get_ex_div()` then cross-references the **live short-call legs** and returns `assignment_risks[]` (severity `high`=ITM / `watch`=near-ITM) with `has_assignment_risk` — deep-OTM and non-dividend names never flag. Run `set_ex_div_events` ~weekly (or when a new dividend-payer short call is opened); `get_ex_div` is cheap to call in the daily briefing.

## Key Claude Commands

```
# Portfolio health
get_briefing()
get_positions()
get_pnl()

# Market
get_market_intelligence("SPY")
get_candidates()
get_iv_rank("TICKER")       # fortress MCP — NOT qd_get_iv_rank (broken upstream)
get_macro_events()          # catalyst gate — FOMC/CPI/PPI/NFP defer advisory (§4)
set_macro_events([...])     # curate calendar from FRED/FMP (write; needs ALLOW_WRITES=1)
get_vix_term()              # VIX vs VIX3M — contango = sell-vol favored; backwardation = caution
get_contract_price("TICKER", strike, "YYYY-MM-DD", "C"|"P")  # live bid/ask/last for ONE specific strike (any OTM) — for ticket pricing (IBKR-first, yfinance fallback)

# Feedback loop
log_trade_outcome(...)         # at each close: ticker, strategy, realized_pnl, exit_reason, ivr/dte/short-delta at entry (write)
get_trade_outcomes()           # structured closed-trade records + summary
python3 journal_analytics.py   # weekly: expectancy/win-rate by strategy + IVR/DTE/delta buckets (reads data/trade_outcomes.json)

# Orders
stage_order(...)           # requires FORTRESS_MCP_ALLOW_WRITES=1
approve_order("id")
get_pending_orders()

# Maintenance
run_script("max_pain")
run_script("iv_crush")
refresh_iv_data()
trigger_ibkr_sync()

# FMP (new tickers / candidate sanity check)
# Say: "Company profile for [TICKER]" — Claude will use fmp plugin
# Gives: price, beta, 52w range, sector, dividend, volume context
```

---

## Common Issues

| Problem | Fix |
|---|---|
| Positions not loading | iBeam disconnected → Parapet System → Reconnect button |
| "<!doctype" JSON errors | Same — iBeam disconnected → click Reconnect |
| Stale data (staleness.state = "stale") | `trigger_ibkr_sync()` |
| **Book looks "fresh" but won't change / `synced_at` frozen** | Gateway is down — backend silently fell back to `bs_yfinance` and serves a FROZEN snapshot while `staleness` still reads "fresh". Check `get_ibkr_status` → `active_backend`. If `web_api` shows 401/`gateway_unreachable`, a sync retry won't help — restart iBeam (`docker restart cp-gateway` / Parapet Reconnect, wait ~40s), then re-pull |
| **Conditional price alert fired but rule was "close below X"** | `price_above`/`price_below` alerts evaluate on **live intraday spot, not daily close** — they false-fire on intraday wicks (MSFT 385 fired Jun 11 on a $384 wick though it never closed <385). Confirm the actual close before acting |
| **Pacing shows headroom after manual fills** | Pacing counter only increments on Fortress-staged orders; manual IBKR fills are NOT counted. Track manual entries yourself |
| Orders page not updating | Auto-polls every 15s — wait, or manual refresh |
| QuantData IV skew / exposure_by_strike broken | Known issue, GitHub issue pending |
| Backend down | `sudo systemctl restart fortress-dashboard-v4` |
| 502 Bad Gateway | `sudo systemctl restart fortress-dashboard-v4 && sudo nginx -s reload` |
| IV Rank / Market Intel blank | QuantData session expired → run QuantData credential refresh (see Quick Reference) |
| MCP changes not showing | Fully quit + relaunch Claude Desktop |
| stage_order rejected | Check limit_price positive + all leg fields present |
| Order stuck in "submitted" | Use force-decline: `DELETE /api/orders/pending/{id}/force` |
| Stale order queue at EOD | `POST /api/orders/expire-stale` to bulk-clear DAY orders |
| FMP returns "ACCESS DENIED" | Endpoint requires paid tier — free tier covers profile only |
| Fortress plugin disconnecting | Transient — Claude auto-reconnects, retry in a few seconds |
