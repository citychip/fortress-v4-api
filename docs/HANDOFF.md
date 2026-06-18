# Fortress — Session Handoff & Start-Here Guide
**Last updated: 2026-06-16 · Read this top-to-bottom to start any Cowork session. Everything needed to be operational is here; deep detail is pointed to in the Documentation Index.**

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
| GEX walls, vol skew | fortress `get_gex` / `get_vol_skew` (NaN-500 fixed 2026-06-16; massive only if a route still errors or gateway down) | ❌ qd `volatility_skew`/`exposure_by_strike` (empty in RTH) |
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

---

## Session Startup Checklist (run these first)
1. `get_ibkr_status` — confirm `web_api` authenticated (Step 0 above).
2. `get_briefing` — NLV, concentration, β-weighted delta vs target, pacing, regime.
3. `get_conditional_alerts` — any triggered? (note the known false-fire on intraday wicks).
4. If managing/entering: `get_roll_all`, `get_stop_loss_all`, `get_candidates`.
5. Macro context if entering: FRED for FOMC/CPI dates; `get_market_intelligence("SPY")`.

---

## Current State (snapshot 2026-06-15 ~16:00 UTC — re-pull `get_briefing` to confirm live)

| Metric | Value |
|---|---|
| Net Liq | ~$74,404 (€64,099) |
| Available / Excess Liq | ~$36,020 / ~$39,446 (both above floors $17k/$25k) |
| β-weighted Δ | **308** (target ~320 — slightly light) · raw +524 |
| Θ / day | +$53 · Vega ~528 |
| VIX / Regime | 16.3 / **bearish** |
| Pacing | 0/5 logged ⚠ (manual fills not counted — 4 trades done 6/15) |

**Concentration:** MSFT **41.9%** (below 50% cap — warning cleared), AAPL 19.0%, GOOGL 14.1%, AMZN 10.5%, NVDA 9.4%. Others ≤1%.

**Open book (summary — full detail in `PORTFOLIO.md` / `get_positions`):** MSFT (LEAPs 310C×1+340C×2, short 490C×2/510C×3/465C-long, Jun18 BPS expiring) · AAPL LEAPs 290C+240C · GOOGL/AMZN/NVDA PMCCs · META Jul31 545/525 PCS · AMD Jun26 + Jul31 450/430 PCS · V Jul17 300/295 PCS · OST stock (ignore).

---

## Open Priorities / Action Items
1. **META Jul31 545/525 PCS — CLOSE before Jul 29 earnings** (expires Jul 31, holds through the print). Conditional alert `320fc5ae` fires at DTE≤8 (~Jul 23). Take profit at 50% or close.
2. **MSFT alerts cleanup (pending):** alert `8bd4926b` (price_below 385) is stuck `triggered` from a Jun 11 intraday wick (MSFT never *closed* <385) — re-arm / make close-based. The `>$412` sell-into-strength alert is **missing** — recreate if continuing the staged exit.
3. **MSFT Jun18 380/370 BPS** — worthless, let expire Thu Jun 18.
4. **AMD Jun26 380/375 PCS** — far OTM, let expire Jun 26.
5. **MSFT de-risking** — primary target (<50% NLV) **achieved (41.9%)**. Tranche 2 (sell another 310C + cover) optional, on <$385 close / >$412 triggers, post-FOMC. No tax friction (Dutch Box 3).
6. **NVDA roll** — only if short Δ > 0.35 (currently 0.21).
7. **OAuth Stage 2** — still pending IBKR (Priority 7). Reminder scheduled Mon Jun 22. Re-test with `test_ibkr_oauth.py` (NOT `get_ibkr_status.oauth`). Live data unaffected (runs on web_api).

## Active Conditional Alerts
| ID | Ticker | Trigger | Status | Note |
|---|---|---|---|---|
| `320fc5ae` | META | dte_lte 8 | armed | Close Jul31 PCS before Jul 29 earnings (~Jul 23) |
| `8bd4926b` | MSFT | price_below 385 | **triggered** ⚠ | Fired on Jun 11 intraday wick; re-arm close-based |
| (missing) | MSFT | price_above 412 | — | Recreate if continuing staged exit |

---

## System Status (live 2026-06-15)
- Backend `fortress-dashboard-v4`: WSL, port 8081 (`sudo systemctl status fortress-dashboard-v4`)
- IBKR CP Gateway `cp-gateway`: Docker, iBeam headless, **web_api AUTHENTICATED** (account U7453366, OPRA live)
- **OAuth Stage 2: ❌ pending IBKR** (Priority 7) — don't trust `get_ibkr_status.oauth`
- MCP server **v4.5.1** live at `C:\Users\cityc.000\fortress_mcp\fortress_mcp.py` (dev copy: `fortress_mcp_v452.py`). Write tools need `FORTRESS_MCP_ALLOW_WRITES=1`.
- Parapet **v2.5 / Sprint 13** at `http://localhost:4000`
- QuantData JWT: `~/.quantdata-mcp/config.json` (refresh procedure in `WORKFLOW.md`)

## Documentation Index (where detail lives)
| Doc | What's in it |
|---|---|
| `PORTFOLIO.md` (v4.1) | **Live positions, account, pending actions, stop-loss watch, strategy quick-ref, universe** — start here for state |
| `01_Portfolio_Strategy_v3_9.md` | Full strategy spec: governance, active strategies, entry/exit/risk rules, post-earnings playbook |
| `WORKFLOW.md` (v2.5) | Daily workflow, startup, entry/roll/stop, system URLs, thresholds, QuantData refresh, common issues |
| `07_MCP_Workflow_and_Prompts_v1_9.md` | MCP prompt playbook — exact phrasings per phase |
| `DATA_SOURCES.md` (v1.2) | Reliability ledger + source-of-truth per data attribute |
| `SYSTEM.md` | Architecture, services, IBKR auth, deploy commands, repos, key paths |
| `PARAPET.md` | Frontend reference / component map / API layer |
| `PARAPET_SPRINT.md` | Parapet sprint history (Sprints 1–13) |
| `CATALYST_GATE_PROPOSAL.md` | Macro-event/news catalyst gate — backend→MCP→Parapet design, deploy + seed steps, follow-ups |
| `JOURNAL_FEEDBACK_LOOP.md` | Trade-outcomes store + `journal_analytics.py` — expectancy/win-rate by IVR/DTE/delta; capture at each close |
| `archive/` | Superseded proposals + `HANDOFF_full_2026-06-15.md` (full prior dated session log) |

## Key Commands (token in `SYSTEM.md` / WSL `~/.git-credentials`)
```bash
sudo systemctl restart fortress-dashboard-v4          # restart backend
journalctl -u fortress-dashboard-v4 -n 50 --no-pager  # logs
docker restart cp-gateway                             # restart IBKR gateway / iBeam
bash deploy_data_sources.sh                           # deploy IBKR-first data layer
bash deploy_parapet.sh                                # deploy Parapet
# Force-decline a stuck order / expire stale DAY orders:
curl -s -X DELETE "http://localhost:8081/api/orders/pending/{ID}/force" -H "Authorization: Bearer $TOKEN"
curl -s -X POST   "http://localhost:8081/api/orders/expire-stale"       -H "Authorization: Bearer $TOKEN"
```

## Recent Session Log
Full dated history (Jun 8–10 deploys, sprints, decisions) is archived in **`archive/HANDOFF_full_2026-06-15.md`**.
- **2026-06-16:** Fixed the GEX/skew/liquidity NaN-in-JSON 500 bug in `options_analytics.py` (`get_gex`/`get_vol_skew`/`check_liquidity` — NaN `openInterest`/`bid`/`ask` from yfinance slipped past `<=0` guards via the `float(x or 0)` trap and crashed Starlette's `allow_nan=False` serializer). Added a `_f()` NaN/Inf-safe coercion + `math.isfinite` skip-guard; deployed via `deploy_data_sources.sh`; get_gex verified live on V and AAPL. Reviewed OptionsPlay DailyPlay (HOOD/RDDT/RCL) — all declined vs framework (HOOD excluded; PCS/bullish structures fail the bearish regime gate; near-ATM deltas vs the 0.15–0.20 PCS spec). Scanned Tier-1 financials/consumer (V/PNC/MAR) for a compliant CSP/IC — all grade-D liquidity, passed. Updated `DATA_SOURCES.md` v1.3. Built the **catalyst gate** (Strategy §4 binary-event timing → codified): backend `get_macro_events`/`set_macro_events` routes in `options_analytics.py` (Claude-curated store, `defer_advisory` when high-impact FOMC/CPI/PPI/NFP/PCE ≤2d, advisory only), MCP tools (v4.6.0), Parapet event-horizon feed + amber defer banner. Implements the old Sprint 14 `intel.events` item. ⚠ **Needs deploy** (data-sources + parapet + MCP relaunch) then **seed** via `set_macro_events()` from FRED/FMP. Full design: `CATALYST_GATE_PROPOSAL.md`. **Deployed + seeded same day** (FOMC Jun17/PCE Jun25/NFP Jul2/CPI Jul14/PPI Jul15/FOMC Jul29; defer_advisory firing on FOMC). Then a profitability/reliability batch: **`get_vix_term`** VIX-vs-VIX3M term-structure regime input (backend route + MCP, v4.7.0); **`journal_analytics.py`** expectancy/win-rate feedback loop (repo root — journal currently near-empty + lacks ivr/dte/delta-at-entry, so a schema enrichment is recommended to unlock bucketing); **NaN route smoke-test** (`tests/test_options_routes_nan.py`) wired into `deploy_data_sources.sh` with rollback; verified **FMP `dividends-calendar`** works on-tier and documented the ex-div assignment-risk check (no current risk — book's short calls are deep-OTM / non-dividend names). MCP now v4.7.0 — **needs another deploy + relaunch** for `get_vix_term`. (Resolved: deployed + relaunched; v4.7.0 live, `get_vix_term` verified — VIX 15.9/VIX3M 19.3 = contango, premium-selling favorable; deploy NaN smoke-test hardened to actually exercise the routes after 3 env fixes.) Then built the **trade-outcomes feedback loop**: backend `GET/POST /api/trade-outcomes` (structured closed-trade sidecar capturing ivr/dte/short-delta at entry), MCP `log_trade_outcome`/`get_trade_outcomes` (**v4.8.0**), `journal_analytics.py` repointed to the store (expectancy by IVR/DTE/delta buckets). Sidecar chosen because the backend journal route is outside the repo mount + the MCP `add_journal_entry` is schema-drifted from the stored entry (noted finding). ⚠ **Needs deploy + relaunch** for v4.8.0. Design: `JOURNAL_FEEDBACK_LOOP.md`. (Deployed + relaunched; v4.8.0 live, trade-outcomes store working.)
- **2026-06-18 (post-FOMC):** Tech sold off (MSFT 394→375). **Closed the MSFT Jun18 380/370 BPS** (it went ITM through the 380 short strike) — realized −$241.49, logged as the first **trade-outcomes** record. **Added a SPY hedge** (3× Aug21 705P @ $7.196, ~−67 delta) to close the §2.D gap (hedge was $0). META Jul31 PCS on watch (delta −0.33, earnings inside expiry — close by ~Jul 23). Built **`get_contract_price`** (backend `GET /api/options/contract-price/{ticker}` in options_analytics.py + `ibkr_contract_quote` helper in ibkr_marketdata.py + MCP **v4.9.0**) — IBKR-first real-time bid/ask/last/IV for ANY single strike (fixes check_liquidity's near-spot-only limitation), yfinance fallback; added to the NaN smoke-test. Verified `qd_get_contract_price` works across SPY/MSFT/AMD/META/AAPL (last-traded OHLCV) as a Claude-side cross-check. ⚠ **Needs deploy + relaunch** for the route + v4.9.0.
- **2026-06-15:** Rotated MSFT (sold 1× Jan28 310C) → bought AAPL Jan28 240C; MSFT concentration 59% → 42%. Added AMD Jul31 450/430 + META Jul31 545/525 put credit spreads. Set META earnings-close alert. Confirmed OAuth Stage 2 still pending (corrected an earlier false "connected" reading). Codified the ⭐ data-sourcing procedure. Consolidated/cleaned docs (deleted dupes + superseded MCP versions, archived completed proposals, merged the cheatsheet into WORKFLOW, moved all reference docs under `docs/`).
