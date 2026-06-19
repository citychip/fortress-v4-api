# Fortress — Session Handoff
**2026-06-15 | For: Next Cowork session**

---

## ⭐ DATA-SOURCING PROCEDURE — READ FIRST, EVERY SESSION

**Goal: never trust a number without confirming its source is live. Run Step 0 before any portfolio/trade work.**

### Step 0 — Verify the data backbone (do this first, always)
1. `get_ibkr_status` → confirm **`active_backend: "web_api"`** AND `web_api.authenticated: true`.
   - If `active_backend: "bs_yfinance"` → **gateway is DOWN. Data is frozen/delayed — do NOT trade on it.** `staleness` may still falsely read "fresh". Fix: `docker restart cp-gateway` (WSL) or Parapet → Reconnect, wait ~40s, re-check. A `retry_ibkr_sync()` alone will NOT fix a 401/iBeam auth failure.
2. `get_briefing` → after any trade, re-pull and confirm **`_ibkr_sync_time` advanced**. A frozen `synced_at` = gateway down, not just stale.
3. **Ignore `get_ibkr_status.oauth`** for OAuth Stage 2 — it lies (`authenticated:true` while the real handshake 401s). Only `test_ibkr_oauth.py` tests Stage 2.

### Canonical source per data type (use ONLY these)
| Need | Use | Never use |
|---|---|---|
| NLV, account, positions, greeks, Δ/Θ/vega, concentration | fortress `get_briefing` / `get_positions` (IBKR web_api) | — |
| **IV rank / ATM IV** | fortress **`get_iv_rank(ticker)`** | ❌ `qd_get_iv_rank` (ticker arg ignored, all identical) |
| GEX walls, vol skew | fortress `get_gex` / `get_vol_skew` (can 500 on some tickers → fall back to massive) | ❌ qd `volatility_skew`/`exposure_by_strike` (empty in RTH) |
| Liquidity / option bid-ask | fortress `check_liquidity` (IBKR-first) | — |
| Order flow, dark pool, max pain, OI, net flow | **quantdata** only | — |
| Live contract price / chain for spread-building | quantdata `qd_get_contract_price` or massive snapshot — **read bid/ask, not just `last`** | — |
| POP / greeks for a hypothetical spread | fortress `options_greeks` (BS) | — |
| Earnings dates | fortress `get_earnings_history` (yfinance) | ❌ FMP free tier (no earnings) |
| Macro: rates, CPI, FOMC, yield curve | FRED | — |
| Company profile, 52w, beta, dividend | FMP | — |

### Hard rules (learned from real errors)
- **`strategy_metrics` runs on PLACEHOLDER vol** (IV 30 / IVR 50 / regime neutral / DTE 999). Use it for strategy *ranking* only — its credit/POP/IVR are NOT real. Always reprice with `get_iv_rank` + a live chain.
- **Conditional price alerts (`price_above`/`price_below`) fire on intraday spot, not daily close.** A "close below X" rule needs manual close confirmation — they false-fire on wicks.
- **Pacing counter misses manual IBKR fills** — it only counts Fortress-staged orders. Track manual entries yourself.
- **Spread pricing:** always work the limit at the **mid**, never the ask/bid the ticket pre-fills. Verify the expiry doesn't span an earnings date (`get_earnings_history`) unless that's intended.
- **MCP server "disconnected" mid-session** is transient — reload the tool via ToolSearch and retry; the data is fine.

> Full reliability ledger + routes: `docs/DATA_SOURCES.md` (v1.2). Daily workflow: `docs/WORKFLOW.md` (v2.4).

---

## Update — Jun 10 night session (Data Sources Optimization implemented — DEPLOYED)

Implemented `DATA_SOURCES_OPTIMIZATION_PROPOSAL.md` Phases 1-4. **Deployed Jun 10 ~19:00 UTC, verified live:**
- liquidity `source: ibkr` (grade A, 0.4% ATM spread on live quotes) ✓
- iv-rank/skew initially fell back. Root cause chain: (1) `ibkr_web/snapshot.py`'s `_has_data` backoff returns as soon as ANY field populates — bid/ask arrive before computed IV; (2) field 7633 alone is unreliable (the roll engine's permanent 0.30-IV fallback was the tell). Fixed in `ibkr_marketdata.py` v2: requests BOTH 7633 + 7283, robust `%`/decimal/percent parsing, polls up to ~3s until an IV field populates. **Final verified state (3rd deploy, ~19:30 UTC):** iv-rank `iv_source: ibkr` ✓ · skew `source: ibkr` confirmed for SPY 2026-07-17 (ATM 19.1, skew_25d +3.6) AND MSFT 0DTE (ATM 75.2 — expiry-day vol, sane) ✓. The deploy script's SPY-default skew check can still show `yfinance_bs` when SPY's 0DTE daily doesn't yield IV — correct fallback, not a bug.
- **All four phases live.** Reliability ledger in `docs/DATA_SOURCES.md` v1.1 now accurate. Sprint 14 "BS-inversion for GEX/skew" backlog item: superseded/done.
- Next MCP version bump: drop the "GEX/vol skew degraded on Yahoo delayed-feed days" caveat from server instructions (no longer true).
- GEX `yfinance_bs` (by design — hybrid).

**Deploy (one command from WSL):**
```
bash /mnt/c/Users/cityc.000/OneDrive/_Stocks26/2606Fortress/deploy_data_sources.sh
```
Backs up, copies, patches `chain.py` in place, py_compiles (auto-rollback on failure), restarts backend, curls all 4 routes printing their `source` fields. Fallback test: `docker stop cp-gateway` → re-curl → expect yfinance sources → `docker start cp-gateway`.

**What was built (all in this folder):**
- `ibkr_marketdata.py` (NEW → `app/services/`): `ibkr_spot()` (field 31, 45s cache), `ibkr_quotes()` (n strikes nearest spot, both rights, fields 84/86/7633, 60s cache), `ibkr_atm_iv()` (median per side). Built on existing `ibkr_chain.py` helpers (conid resolution + `_snapshot_contracts`). Everything returns None on failure → silent yfinance fallback.
- `options_analytics.py` (v2, edited in place): liquidity uses IBKR bid/ask when ≥4 live quotes (`source: "ibkr"`); iv-rank tries IBKR 7633 first (`iv_source: "ibkr"|"bs_inversion"`); vol-skew per-strike IV from IBKR (`source: "ibkr"|"yfinance_bs"`), fallback + term structure BS-invert from lastPrice (raw Yahoo IV column eliminated everywhere); GEX hybrid — yfinance strikes/OI, IV via `_row_iv` sanity-banded (0.04–5.0) or inversion, lazy IBKR ATM as last resort. All routes: spot is IBKR-first.
- `chain.py` patch (inside `deploy_data_sources.sh`): `get_spot()` → IBKR-first, original yfinance body preserved as `_yf_get_spot()`. **This makes conditional alert triggers (MSFT 385/412) evaluate on live prices instead of 15-min-delayed + 300s-cached.**

**Verify next session:** `source`/`iv_source` fields during RTH; `iv_history.json` keeps populating; skew no longer needs the Sprint 14 BS-inversion fix (superseded). MCP server instructions still mention the "degraded on Yahoo delayed-feed days" caveat — drop it in the next MCP version bump after verifying.

**Note:** sandbox py_compile of the edited `options_analytics.py` was blocked by OneDrive sync lag; `ibkr_marketdata.py` compiles clean, all edit regions visually verified, and the deploy script compile-gates with auto-rollback before restart.

---

## Update — Jun 10 late session (alerts root-caused + fixed)

**The alert bug was deeper than the v4.5.0 fix.** Backend has TWO alert APIs (verified via openapi.json + repo source):
- `/api/alerts` = notification feed only: `{ticker, message (req), severity info|warn|critical, source, position_id}`. No condition/threshold. v4.5.0's `add_alert` fix still 422'd (missing `message`). `update_alert` accepts `{severity, message, snoozed}` — old fields were silently ignored.
- `/api/conditional-alerts` = real trigger engine (`conditional_alerts.py`, Phase 7 v8.44): `{ticker, alert_type price_above|price_below|pnl_pct|dte_lte|delta_gte|conditional_entry, threshold, message (req, ≤300), urgency critical|watch|profit|entry, position_id, action_mode}`. Auto-evaluated by scheduler `alert_eval` job (~every 5 min RTH). PATCH re-arms on threshold change; `snoozed` pauses.

**Done:**
- `fortress_mcp_v451.py` built (73 tools, compiles clean): corrected `add_alert`/`update_alert` + new `get/add/update/delete_conditional_alert` + `evaluate_conditional_alerts`. **Install pending:** copy to `C:\Users\cityc.000\fortress_mcp\fortress_mcp.py` + restart Claude Desktop.
- **MSFT triggers now LIVE as conditional alerts** (created via API): `8bd4926b` price_below 385 (critical, tranche-1 sell) · `f4d83a20` price_above 412 (watch, sell into strength). Priority-0 verify item resolved.

**New backlog (Sprint 14):** Parapet System > Alerts form posts `{ticker, condition, threshold}` to `/api/alerts` → always 422 (wants `{ticker, message, severity}`). That's why manual alert entry failed Jun 10 evening. Also: Parapet has no UI for `/api/conditional-alerts` at all — consider a Conditional Alerts card on Triage (backend already returns them + `/api/action-queue/summary` badge endpoint exists).

---

## Update — Jun 10 evening session

**Decisions made (hold the user to these):**
- **MSFT staged exit agreed, deferred through FOMC (Jun 16–17) with hard triggers:**
  - Tranche 1 = SELL 1× Jan28 310C + BUY back Aug21 465C short (keeps 1:1 coverage, locks ~+$925 on the short).
  - Trigger A: MSFT daily close **< $385** (GEX put support) → sell immediately, no debate.
  - Trigger B: MSFT bounce **> $412** (into 412–418 GEX call walls) → sell into strength.
  - Either way tranche 1 executes by ~Jun 19. Tranche 2 on the same triggers after FOMC.
  - Rationale: ACT signal live ($401 vs $444 floor), bearish regime, IV ~35% (sell extrinsic rich), Box 3 = no tax friction. 12m model: discipline costs ~$5–8k bull-case, saves ~$8.5k bear-case, +$4–5k/yr income in all scenarios.
- **MSFT additional LEAP buy: REJECTED** (pretrade BLOCKED on concentration 92.8% vs 50%; user agreed to drop).
- **AAPL Jan28 290C: position EXISTS in book** (1×, Δ0.66, filled ~Jun 10). Duplicate pending order `a0275a29` **force-declined Jun 10 ~21:40** (it sat in backend `pending`, never submitted to IBKR, so DAY expiry wouldn't have cleared it). Queue is clean. Post-PPI question is only whether to ADD the deeper 250C — do not re-enter the 290C.

**State changes since handoff was written:**
- NLV $74,506 (Jun 10 18:30 UTC). VIX 21.12, regime bearish. β-wtd Δ 412.6 vs 320 target.
- **OAuth Stage 2 — NOT connected (corrected 2026-06-15).** The Jun 10 "connected" note was based on the backend `get_ibkr_status.oauth` field, which is MISLEADING (reports `authenticated:true` without testing the Stage-2 handshake). `test_ibkr_oauth.py` run Jun 15 still returns 401 "Invalid signature" at `ssodh/init` — Stage 1 (LST) works, Stage 2 pending IBKR activation. Priority 7 remains OPEN. Live data is unaffected (runs on CP Gateway/iBeam web_api, not OAuth).
- V back to **SAFE** ($324.50, above floor). ACT signals now only MSFT + META.
- NVDA Δ 0.171 — no roll needed.

**Bug found + fixed (install pending):**
- `add_alert` MCP tool body `{position_id, trigger_type, trigger_value, direction, action}` does NOT match backend POST /api/alerts `{ticker, condition, threshold}` → always 422. Fixed in `fortress_mcp_v450.py` (this folder). `update_alert` likely has the same mismatch (`trigger_value` etc.) — check next session.
- Alerts for the MSFT triggers (385 / 412) could NOT be set via MCP this session — user instructed to add them via Parapet → System → Alerts. **Verify they exist next session** (`get_alerts`).

---

## Documentation (start here)

| Doc | What's in it |
|---|---|
| `docs/SYSTEM.md` | Architecture, services, deploy commands, GitHub repos, IBKR auth |
| `docs/PORTFOLIO.md` | Current positions, pending actions, strategy rules, universe, LEAP watch list |
| `docs/WORKFLOW.md` | Daily startup, entry/roll/stop workflows, key Claude commands |
| `docs/PARAPET.md` | Component map, API layer, sprint log, design principles |

---

## Immediate Priorities (next session)

**Priority 0 — iBeam auth (do first, every session)**
iBeam is headless — it authenticates automatically. Check Parapet → System → Settings → Connections.
- If IBKR ● green → you're done
- If IBKR ● red → click **Reconnect** button (new, Jun 8) → wait ~35s → auto-syncs on success

**Priority 1 — AAPL LEAP entry window**
WWDC was June 8. No sell-the-news dip to $300–305 materialised today. Default entry: **June 12 — after PPI print**.
Target: Jan28 250C, Δ ~0.87, ~$86/contract. Run pretrade check first.
⚠️ Two binary events this week: CPI (May) Wednesday Jun 10 at 8:30am AND PPI (May) Thursday Jun 12 (both High impact). Do NOT enter before PPI — SPY Jun12 vol skew shows 17.15% ATM IV with skew_10d +6.19 (steep tail puts), meaning real IV crush risk post-prints. Entering before PPI means buying inflated premium that could crush 10-15% even if AAPL moves your way. Wait until after both prints, then enter.
AAPL confirmed as only Tech name in bullish leadership (OptionsPlay). Last week's momentum plays: Jun05 $310C +50%, Jun12 $315C +10.29% — empirical validation.

**Priority 2 — MSFT Jun18 BPS expires Jun 18**
Short Jun18 380P/370P ×1 — near worthless, Δ ~-0.04. Let expire. No action.

**Priority 3 — AMD Jun26 PCS expires Jun 26**
Jun26 380P/375P ×1 — far OTM, Δ ~-0.067. Let expire. No action.

**Priority 4 — NVDA roll still open**
Aug21 250C Δ 0.211 — safe. The Jun2 roll order `2572e40c` to Sep19 265C is likely expired. Re-stage only if delta rises above 0.35.

**Priority 5 — Stop-loss ACT signals (monitor, no mechanical trigger)**
MSFT ($410 vs SMA floor $445), META ($588 vs SMA floor $648), V ($320 vs SMA floor $322). All short strikes well OTM — no required action. V is borderline ($1.35 below floor). Monitor.

**Priority 6 — MSFT de-risking (can accelerate — Dutch Box 3)**
93% NLV. No new PMCC entries. Original goal: below 50% by Dec 2026.
Dutch Box 3 tax law applies: NO capital gains tax on realized gains. Tax is calculated on total portfolio value at January 1 (peildatum) each year as a deemed return (~6.17% × 36% = ~2.2% annually). Selling a MSFT LEAP and reinvesting creates zero additional tax friction vs. holding. The Dec 2026 target can be accelerated — pace should be driven by market conditions and entry opportunities in rotation sectors, not tax concerns. Confirm specifics with a belastingadviseur re Box 3 vs Box 1 classification of options activity.

**Priority 7 — OAuth Stage 2 (STILL OPEN)**
Re-tested June 15 via `test_ibkr_oauth.py` — still 401 "Invalid signature" at `iserver/auth/ssodh/init`. Stage 1 (LST) works, Stage 2 (brokerage session) pending IBKR activation of consumer key SHARMILAH. Retry after the next weekend maintenance window (reminder scheduled for Mon Jun 22).
⚠ Do NOT trust `get_ibkr_status.oauth` — it reports `authenticated:true` while the real handshake 401s. The script is the only reliable Stage-2 test.
Note: live data is unaffected — it runs on CP Gateway/iBeam (`web_api`), which is authenticated. OAuth is a redundant path not currently in use.

---

## What Happened This Session (Jun 10 — Parapet Sprint 12)

Sprint 12 — 5 fixes to Parapet, deployed and verified live, pushed as commit `f900231`:

- **#73 QuantData IV Rank table** — documented the upstream `iv_rank` bug (identical values per ticker when `expiration_date` is passed) as a "Known issue" callout in `MarketPage.tsx`. Not fixable from Parapet — needs an upstream quantdata-mcp fix.
- **#74 Exposure tab β-wtd delta target** — fixed units mismatch in `PositionsPage.tsx`: target was 0.35 (a per-position option-delta number), should be **320** (portfolio β-weighted delta, matching System > Strategy "β-wtd target"). Now shows e.g. "658.20 ... target 320 β-Δ · +338.2 off".
- **#75 Vol Skew chart x-axis** — `AnalyticsCharts.tsx` switched to `type="number"` XAxis with `domain={['dataMin','dataMax']}` + `tickCount={8}` and `connectNulls` on Lines. Was rendering one-tick-per-point and crushing the chart; now spans the real strike range (e.g. AVGO $150–$720) with readable ticks.
- **#76 Journal/Scripts timestamps** — new `fmtDateTime()` helper in `api.ts` (`YYYY-MM-DD HH:MM:SS`, locale-independent), wired into System > Journal and System > Scripts "Last run".
- **#77 Market tab merge** — folded the separate "QuantData" tab into "Analytics" as a "Universe Signals (QuantData)" section below the per-ticker GEX/Skew/Ladder view. Market is now 3 tabs: Analytics, Earnings Calendar, Universe.
- Also added `src/components/system/ScriptsSection.tsx` to `deploy_parapet.sh`'s FILES array (was missing, so Scripts changes weren't being synced to WSL on deploy).

Docs updated: `PARAPET_SPRINT.md` (new "Sprint 12 (complete)" section), `docs/PARAPET.md` (bumped to v2.4, Market tab table + Component Map + Sprint Log updated to reflect 3-tab Market page).

Investigated a suspected `\api\...` backslash path bug in `api.ts` carried over from a prior session — **false alarm**, paths in `api.ts` (lines ~218-225, ~336-340) use correct forward slashes. No change needed.

Remaining backlog: two upstream quantdata-mcp issues (`iv_rank` identical values per ticker; `exposure_by_strike`/`volatility_skew` returning empty during market hours) — both already surfaced in-app via "Known issues" callouts, not actionable from Parapet.

---

## What Happened This Session (Jun 8 — third context)

### Parapet v2.0 — 6 new features implemented

All implemented in a single session pass. Files changed:

**`fortress-parapet/src/lib/api.ts`** — 6 new exports:
- `getTimeOfDay()` → `GET /api/run/time_of_day`
- `getRollAll()` → `GET /api/manage/roll_all`
- `getStopLossAll()` → `GET /api/manage/stop_loss_all`
- `getPretradeAll()` → `GET /api/manage/pretrade_all`
- `getGex(ticker)` → `GET /api/options/gex/{ticker}`
- `getVolSkew(ticker)` → `GET /api/options/vol-skew/{ticker}`

**`fortress-parapet/src/components/Layout.tsx`** — Market status chip in header
- Fetches `getTimeOfDay()` on mount; shows `● Open` (green) / `○ Pre` (amber) / `○ Closed` (muted)
- Chip appears in every page header between timestamp and action slot

**`fortress-parapet/src/pages/CandidatesPage.tsx`** — 2 new columns
- **Pretrade**: PROCEED (green) / BLOCKED (red) — from `getPretradeAll()`, loaded in background after candidates fetch
- **Eff%**: capital efficiency for positions that exist (from `getCapitalEff()`, `by_position` array); `—` for new candidates with no existing position. Green ≥15%, yellow ≥8%, red <8%.

**`fortress-parapet/src/pages/PortfolioPage.tsx`** — Triage tab + P&L history
- New **Triage** tab (second position in tab bar): calls `getRollAll()` + `getStopLossAll()` in parallel on mount. Shows summary chips + sortable tables for both roll urgency and stop-loss verdict. Stop-loss table sorted ACT → WATCH → SAFE.
- **P&L → History** section added to bottom of P&L tab: fetches `getPnlHistory()`. Empty state shows graceful message; when data exists shows cumulative P&L SVG line chart (green above zero, red below).

**`fortress-parapet/src/pages/MarketPage.tsx`** — Options Analytics tab
- New **Options Analytics** tab (second in tab bar, before Earnings Calendar)
- Ticker selector chips from universe; auto-loads on tab entry
- **GEX chart**: horizontal bar chart per strike coloured green (positive GEX) / red (negative GEX). KV chips for Net GEX, Call Wall, Put Wall, Flip Level. Spot strike highlighted.
- **Vol Skew chart**: SVG line chart with call IV (green), put IV (red), mid IV (blue) by strike. KV chips for ATM IV, skew slope, spot.

⚠️ **ACTION REQUIRED: Rebuild and redeploy Parapet** (`npm run build` in `fortress-parapet/`).

---

## What Happened This Session (Jun 8 — evening, continued, second context)

### Backend deploy — all endpoints confirmed live

**All three yfinance routes now deployed and confirmed working on VPS** (`root@76.13.138.194`):

| Endpoint | Status | Sample |
|---|---|---|
| `GET /api/options/gex/SPY` | ✓ live | spot=739.22, call_wall=739, put_wall=740, flip=739 |
| `GET /api/options/vol-skew/SPY` | ✓ live | atm_iv=0.77%, skew_25d=0.34, skew_10d=0.41 |
| `GET /api/options/liquidity/SPY` | ✓ live | grade=B, atm_spread=0.4%, advisory=False |
| `GET /api/options/strategy_metrics?ticker=SPY` | ✓ live | regime=neutral, ivr=50.0, rec=PCS |

VPS token: `07f03fb6e664859ac5e8113eaf1102ac43a3cb785c5` (env var in systemd unit, NOT the file at `.fortress_api_token`)

**Root cause of context-switch confusion:** VPS `options_analytics.py` had been corrupted (duplicate liquidity stub, missing GEX/skew routes, no module header). Fixed by SCP-ing the clean workspace version to VPS, confirming registration in `app/main.py` lines 138-139.

### MCP v4.4.0 — 2 new tools written

File: `fortress_mcp_v430.py` in workspace (despite filename, now contains v4.4.0 with 67 tools)

**⚠️ ACTION REQUIRED: Copy to active location manually:**
```
From: C:\Users\cityc.000\OneDrive\_Stocks26\2606Fortress\fortress_mcp_v430.py
To:   C:\Users\cityc.000\fortress_mcp\fortress_mcp.py
Then: Restart Claude Desktop
```

New tools added (above Entry point block):
- `get_strategy_metrics(ticker, mode="new", target_dte=45)` → `GET /api/options/strategy_metrics`
- `check_liquidity(ticker, expiry=None, moneyness_range=0.15)` → `GET /api/options/liquidity/{ticker}`

### Parapet — "Rec" strategy column added to Candidates tab

Files modified:
- `fortress-parapet/src/lib/api.ts` — added `StrategyMetrics` interface + `getStrategyMetrics()` function
- `fortress-parapet/src/pages/CandidatesPage.tsx` — added `StrategyBadge` component; parallel fetch of strategy metrics for all `can_trade` rows after candidates load; "Rec" column in table

⚠️ **ACTION REQUIRED: Rebuild and redeploy Parapet** (if running local dev server it updates automatically; otherwise `npm run build`).

### Strategy document — v3.9.0

File: `01_Portfolio_Strategy_v3_9.md` (source of truth updated in-place at `01_Portfolio_Strategy_v3_8.md`, copy saved as v3.9)

Key additions: §2.F–H (CSP, IC, CC strategies); §2.5 strategy selection framework (regime gate → yield comparison); §4 two-tier bid-ask threshold (5% advisory, 10% hard block); workflow step 3 updated; tool stack updated to v4.4.0; QuantData qd_get_volatility_skew and qd_get_exposure_by_strike marked broken.

---

## What Happened This Session (Jun 10 — Sprint 11)

### Parapet v2.3 — Sprint 11 (earnings vol calendar, NLV delta, auto-refresh, bundle split)

**1 new file, 3 files updated:**

| Change | File | Detail |
|---|---|---|
| Earnings volatility calendar | `MarketPage.tsx` | Earnings Calendar table gains "Expected Move" and "IV Crush Risk" columns. Background fetch of `getEarningsVolatility(ticker)` per calendar ticker; `crushRisk()` flags PRIME CRUSH (≥5pp implied−avg, red) / ELEVATED (≥2pp, yellow) / NORMAL (green). |
| Briefing NLV Δ vs yesterday | `BriefingPage.tsx` | New `nlv_history` localStorage map (date → net liq, 30-day rolling). Stat bar gains "NLV Δ (1d)" showing `$Δ (±%Δ)` vs the most recent prior-day snapshot, green/red by sign. |
| Triage auto-refresh | `TriagePage.tsx` | Replaced 5-min poll with 60s poll, paused when tab hidden (`document.visibilityState`), plus immediate refresh on tab refocus. New `⟳ Auto 60s` / `⏸ Paused` toggle in page header, persisted via `triage_auto_refresh` localStorage key. |
| Lazy-load Recharts | `MarketPage.tsx`, `components/AnalyticsCharts.tsx` (new) | `GexChart`, `VolSkewChart`, `VolSkewSvg` extracted into a new file and loaded via `React.lazy()` + `Suspense`. Recharts (~688KB) no longer ships in MarketPage's main chunk — only loaded when the Analytics GEX/Skew view renders. |
| Deploy script | `deploy_parapet.sh` | Now also syncs `src/components/AnalyticsCharts.tsx` |

**Parapet state:** v2.3 · Sprint 11 complete · pending deploy (run `deploy_parapet.sh` from WSL)

---

## What Happened This Session (Jun 9 — Sprint 10)

### Parapet v2.2 — Sprint 10 (Recharts, Exposure tab, PoP calc)

**3 files upgraded, 1 new dependency (Recharts v3):**

| Change | File | Detail |
|---|---|---|
| Recharts v3 added | `package.json` | `"recharts": "^3.0.0"` — replaces 770 modules (was 864 on v2) |
| Vol skew charts → Recharts | `MarketPage.tsx` | `VolSkewChart` + `VolSkewSvg` replaced with `LineChart`/`ResponsiveContainer`. Interactive tooltips, spot price `ReferenceLine`, clean axis ticks. Removed SVG coordinate math (~80 lines → ~40). |
| Exposure tab rebuilt | `PositionsPage.tsx` | New `ExposureTab` component. Summary row: β-weighted delta vs 0.35 target + visual progress bar + stacked sector mix bar. Sector breakdown: visual horizontal bars per sector (8 OKLCH colors). Delta contribution: bar chart per ticker, green/red by direction. |
| Black-Scholes PoP | `CandidatesPage.tsx` | `normCDF` + `calcPoP` + `calc1SD` pure-JS functions added. Stage Trade form now shows vol context strip: expected 1-SD move (±$ and ±%) + ATM PoP %, updates live as DTE changes. |
| Deploy script | `deploy_parapet.sh` | Now syncs `package.json` and runs `npm install` before build |

**Parapet state:** v2.2 · Sprint 10 complete · deployed Jun 9 · Recharts v3.x

---

## What Happened This Session (Jun 9 — morning)

### Parapet v2.1 — Sprint 9 (6 features) + IV rank caching

**Sprint 9 features — all shipped:**

| # | Feature | Files |
|---|---|---|
| #53 | Horizontal scroll on Triage active-alerts table | TriagePage.tsx |
| #54 | In-page tab keyboard shortcuts (1–N keys) | MarketPage.tsx, PositionsPage.tsx, SystemPage.tsx |
| #55 | P&L summary strip on Briefing (total/unrealized/realized + winner/loser) | BriefingPage.tsx |
| #56 | QuantData live IV rank signal board (auto-loads, sort toggle) | MarketPage.tsx |
| #57 | Roll P&L column in Triage roll table (via `evaluateRoll()` background fetch) | TriagePage.tsx, api.ts |
| #58 | Stage trade inline mini-form on Candidates expandable row | CandidatesPage.tsx, api.ts |

**IV rank localStorage caching (bonus fix):**
- `saveCachedIvr(ticker, data)` saves to `ivr_cache:TICKER` whenever live `iv_rank` is non-null
- `loadCachedIvr(ticker)` reads cache as fallback when live is null (outside market hours)
- Table merges live + cached: cached rows render at 75% opacity with a small `M/DD HH:MM` timestamp
- Sort uses cached IVR when live is null — table remains useful after hours
- File: `MarketPage.tsx` (`IvRankSection` component)

**IV units bug also fixed this session:**
- Backend returns IV as percentage values (e.g., `39.05` = 39.05%), not decimals
- Removed spurious `* 100` multiplier in `MarketPage.tsx` and `ConnectionsSection.tsx`

**Parapet state:** v2.1 · deployed at `http://localhost:4000`

---

## What Happened This Session (Jun 9 — earlier)

### MCP + Parapet — backlog items completed

**MCP: `force_decline_order` + `expire_stale_orders` added (fortress_mcp.py v4.2.1)**
Two new write tools exposed via MCP — previously REST-only:
- `force_decline_order(order_id)` → `DELETE /api/orders/pending/{id}/force`
- `expire_stale_orders()` → `POST /api/orders/expire-stale`
Both use existing `_delete`/`_post` helpers and `_writes_check()`. Confirmed live in Claude.

**Parapet v1.9.1: SPY Hedge Coverage + DP Floors wired up**
Bug: `api.ts` had wrong URL paths for both endpoints. Fixed:
- `getSpyHedge`: `/api/spy-hedge-coverage` → `/api/manage/spy_hedge_coverage`
- `getDpFloorsGex`: `/api/dp-floors-and-gex/{ticker}` → `/api/chart/{ticker}/levels`
UI code was already built — two-line fix. Both cards confirmed rendering live data in Overview → Market tab. Committed as Parapet v1.9.1.

---

## What Happened This Session (Jun 8 — evening, continued)

### Research analysis — two weekly reports reviewed

**OptionsPlay Weekly (Jun 8):**
- Regime: Neutral (0/+5, down from +5). Entire AI/semi/mega-cap complex in Early Breakdown.
- AAPL: only Tech name in confirmed bullish leadership. Green light for LEAP entry.
- NVDA: explicitly Early Breakdown. Fortress SAFE signal (above SMA $188) diverges — monitor.
- V: ACT signal (barely below SMA) but financials are #1 bullish sector — probable false alarm.
- Top sector rotation: financials, healthcare, industrials (XLF entered confirmed bullish first time this cycle).
- Top ideas to watch: ELV, GE, PNC, CSX, MAR, SPG.

**Trading Analyst Weekly (Jun 8):**
- Corroborates OptionsPlay: Nasdaq -4.68%, VIX closed Friday at 21.50 (highest since March).
- Fear & Greed Index: 42 (fear). Market breadth negative NYSE and Nasdaq.
- Adds: PPI (May) Thursday Jun 12 is also High-impact — two back-to-back inflation prints.
- AAPL empirical validation: Jun05 $310C +50%, Jun12 $315C +10.29% both won last week.
- FOMC Jun 16-17: Kevin Warsh's first meeting. Expected hold, but higher-for-longer confirmed.
- Pre-market Jun 9 snapshot: S&P -2.64%, Nasdaq -4.18%, VIX 19.0 (down from 21.51 — orderly selloff, not panic).

### Universe additions — 5 new tickers added to tier1

Added via `add_universe_ticker` based on OptionsPlay rotation thesis:

| Ticker | Sector | Rationale |
|---|---|---|
| ELV | Healthcare | Confirmed bullish, OptionsPlay top idea |
| GE | Industrials | Early Breakout, aerospace/defense |
| PNC | Financials | Early Breakout, XLF bullish leadership |
| CSX | Industrials | Early Breakout, transports |
| MAR | Consumer/Travel | OptionsPlay top idea, resilient travel demand |

Universe now 22 tickers in tier1 (up from 17).

### Dutch tax law — de-risking calculus revised

Portfolio is taxed under Dutch Box 3 (Sparen en Beleggen). Key implication: **there is no capital gains tax event when selling MSFT LEAPs**. Tax is assessed annually on January 1 (peildatum) on total net asset value at a deemed return rate (~6.17% on investments × 36% tax = ~2.2% of portfolio value per year). Selling and reinvesting creates no additional tax friction vs. holding concentrated MSFT. The US-style "don't sell, defer the gain" logic does not apply under Dutch law. De-risking pace can be driven purely by market conditions and entry opportunities. Confirm Box 3 vs Box 1 classification with a belastingadviseur given frequency of options activity.

### Portfolio scenario model built

3/6/9/12-month NLV forecasts across bear/base/bull scenarios:

| Scenario | 3m | 6m | 9m | 12m | MSFT assumption |
|---|---|---|---|---|---|
| Bull | $100k | $116k | $130k | $145k | $410 → $525 |
| Base | $88k | $100k | $110k | $122k | $410 → $470 |
| Bear | $72k | $71k | $75k | $83k | $410 → $390 |

Key insight: theta ($68/day = $24,480/year) provides a positive return floor in all scenarios. Bear case ends positive over 12 months purely on theta accumulation. MSFT delta (~$400 P&L per $1 move) is the dominant variable.

---

## What Happened This Session (Jun 8 — evening)

### MCP tooling stack completed — all 5 confirmed live

Built and installed plugins for FRED and Massive, bringing the full tooling stack online.

**Root cause found (config file):** The `claude_desktop_config.json` in the Fortress folder is a reference copy only. Claude Desktop reads its real config from `C:\Users\cityc.000\AppData\Roaming\Claude\claude_desktop_config.json`, which only contains fortress-dashboard and quantdata. FMP, FRED, and Massive connect exclusively via the plugin system — no config file changes needed for those.

**Plugin fixes applied:**
- Both fred.plugin and massive.plugin rebuilt (v1.1.0) with corrected WSL invocation: `wsl -e /usr/bin/env KEY=value binary` — this embeds the API key directly in the command, bypassing the WSL env var passthrough issue that was preventing the servers from starting.
- fred.plugin additionally uses `/usr/bin/node` explicitly (the JS binary can't be exec'd directly without node in PATH).
- mcp_massive installed in WSL from GitHub: `uv tool install "mcp_massive @ git+https://github.com/massive-com/mcp_massive@v0.10.0"` — not on PyPI, must use git source.

**MCP stack — confirmed live:**

| Tool | Source | Status |
|---|---|---|
| fortress-dashboard | AppData config (Python stdio) + Plugin | ✅ |
| quantdata | AppData config (WSL stdio) | ✅ |
| fmp | Plugin (HTTP URL) | ✅ |
| fred | Plugin (WSL stdio via node) | ✅ — T10Y2Y +0.38% tested |
| massive | Plugin (WSL stdio) | ✅ — SPY $737.55 tested |

**API keys in use (treat as compromised — were shared in chat, regenerate when convenient):**
- FMP: `IlAAFEDrsofoV5epZgLeDknQcYQAMYBB`
- FRED: `cf61f7f52e710e816190e2ec317569d3`
- Massive: `GOrg0WHt1_XYppuHn2kpBpFBt0WVBZXh`

**WORKFLOW.md updated to v2.0** (earlier session): added MCP Tooling Stack table, FMP pre-entry step, FRED and Massive use cases, common issues rows.

---

## What Happened This Session (Jun 8 — day)

### OAuth test — still pending
Ran `test_ibkr_oauth.py`. Stage 1 (LST) works, Stage 2 still "Invalid signature". IBKR hasn't activated the consumer key yet.

### Portfolio check (live IBKR data)
NLV $78,125 (down ~$5.6k from Jun 4 — MSFT at $410, below 200-SMA). All positions safe, no roll triggers. 3 stop-loss ACT signals: MSFT, META, V (all below 200-SMA, no mechanical trigger). Full details in PORTFOLIO.md.

### Stale order queue cleared
3 Jun 4 roll orders (2× MSFT, 1× GOOGL) were stuck in `submitted` status. Force-declined via new `/api/orders/pending/{id}/force` endpoint. Queue is now clean.

### Parapet v1.9 shipped — commit `eb01391` + Jun 8 additions

**Reconnect button (new):**
- `InfraSection.tsx` — Reconnect button appears when IBKR is disconnected
- Calls `POST /api/ibkr/reconnect` → restarts cp-gateway → polls status every 3s (up to 60s) → auto-syncs on success
- Hidden when already connected

**Order lifecycle fixes (backend):**
- `DELETE /api/orders/pending/{id}/force` — force-cancel any order regardless of status
- `POST /api/orders/expire-stale` — bulk-expire all stale DAY `submitted` orders (call at EOD)
- Fixed `place_order()` in `ibkr_web/orders.py` — now loops through multiple IBKR confirmation rounds instead of getting stuck after one

### iBeam clarification
cp-gateway uses iBeam headless (Selenium-based auto-login). Auth mode `web_api`. OAuth (ibind) is a separate pending activation. The Reconnect button restarts cp-gateway and works correctly for iBeam.

---

## Account Snapshot (2026-06-08 ~16:00 UTC)

| | |
|---|---|
| Net Liq | **$78,125** |
| Available | $24,771 |
| Excess Liq | $29,626 |
| Portfolio Δ | +558 raw / +381.7 beta-weighted |
| Θ/day | +$68.0 |
| Vega | 517.1 |
| VIX | 18.34 |
| Regime | **Bearish** |
| Pacing | 0/5 this week |

### Unrealized P&L by ticker
| Ticker | P&L |
|---|---|
| MSFT | ~+$72,590 |
| AMZN | ~+$7,773 |
| GOOGL | ~+$9,937 |
| NVDA | ~+$6,825 |
| AMD | ~-$28 |
| V | ~-$315 |
| META | ~-$412 |
| OST | ~+$75 |

---

## Open Items / Sprint 11

- AAPL LEAP — entry after CPI (Jun 10) + PPI (Jun 12) — do NOT enter before both prints clear
- NVDA roll re-stage — when delta > 0.35
- MSFT de-risking plan — ongoing (no capital gains tax under Dutch Box 3, pace by market conditions)
- MSFT unhedged LEAPs — add covered call legs when conditions allow
- OAuth Stage 2 — still pending IBKR activation
- Unusual Whales trial — $50/week, evaluate if needed (GEX covered by yfinance, IV rank covered by QuantData)
- **Sprint 11** — complete (see above); Sprint 12 backlog TBD

---

## MCP v4.5.0 — ACTION REQUIRED (built 2026-06-10, not yet installed)

`fortress_mcp_v450.py` (in this folder) = the live `fortress_mcp.py` (v4.4.0, 67 tools) + `get_iv_rank(ticker)` tool + corrected server instructions (IV rank from fortress, NOT quantdata — `qd_get_iv_rank` is broken upstream: ticker arg ignored, all tickers identical).

```
Copy: C:\Users\cityc.000\OneDrive\_Stocks26\2606Fortress\fortress_mcp_v450.py
To:   C:\Users\cityc.000\fortress_mcp\fortress_mcp.py
Then: restart Claude Desktop
```

Also new: `snapshot_iv.sh` — daily IV sweep over the universe (cron 16:05 CET Mon-Fri suggested) so the IV Rank board converges from hv_proxy to true IV rank in ~60 trading days. Docs updated: `docs/DATA_SOURCES.md` (new), `docs/WORKFLOW.md` v2.2, `07_MCP_Workflow_and_Prompts` v1.9 banner.

**Sprint 14 backlog:** (1) BS-inversion for GEX + vol-skew backend routes (still read Yahoo's junk IV column); (2) #90 server-side NLV history endpoint + Briefing sparkline; (3) FMP economic calendar → `intel.events` for the Briefing event horizon.

---

## Parapet State

- **Current version:** v2.5 · Sprint 13 complete (restructure per `PARAPET_V25_ANALYSIS.md`, #78–#93) · **pending deploy** — run `deploy_parapet.sh` from WSL
- Sprint 13 highlights: orders → Triage read-only (approvals via Claude/MCP, needs `FORTRESS_MCP_ALLOW_WRITES=1`); dead pages deleted; settings-driven thresholds; Positions = Overview/P&L/Exposure/Risk/Legs; Market = signal board → drill-down; per-page ErrorBoundary; tiered Briefing polling. Verified: tsc + vite build clean.
- Deferred: #90 server-side NLV history (needs backend snapshot endpoint)
- **Repo:** `citychip/fortress-parapet` (branch: `master`)
- **Live at:** `http://localhost:4000`

---

## System Status (2026-06-08)

- Backend `fortress-dashboard-v4`: running on WSL, port 8081
- IBKR CP Gateway `cp-gateway`: Docker, iBeam headless, authenticated
- OAuth Stage 1: working · Stage 2: pending IBKR activation
- QuantData: JWT configured at `~/.quantdata-mcp/config.json`
- MCP server: `C:\Users\cityc.000\fortress_mcp\fortress_mcp.py` (Windows)
- MCP write tools require `FORTRESS_MCP_ALLOW_WRITES=1` in Claude Desktop config

### Key commands
```bash
# Backend status
sudo systemctl status fortress-dashboard-v4
journalctl -u fortress-dashboard-v4 -n 50 --no-pager

# Restart backend
sudo systemctl restart fortress-dashboard-v4

# IBKR gateway
docker restart cp-gateway

# Parapet deploy
rsync -a "/mnt/c/Users/cityc.000/OneDrive/_Stocks26/2606Fortress/fortress-parapet/src/" \
      ~/fortress-parapet/src/ && bash ~/fortress-parapet/scripts/deploy.sh

# Parapet commit
cd ~/fortress-parapet
git add -A
git commit -m "feat: Parapet vX.X — description"
git push origin master

# Force-decline a stuck order  (TOKEN=$(cat ~/.fortress_api_token))
curl -s -X DELETE "http://localhost:8081/api/orders/pending/{ID}/force" \
  -H "Authorization: Bearer $TOKEN"

# Expire all stale DAY orders (run at EOD)
curl -s -X POST "http://localhost:8081/api/orders/expire-stale" \
  -H "Authorization: Bearer $TOKEN"
```

### GitHub PAT
Stored in WSL `~/.git-credentials` — do not paste in docs.
