# Fortress — Session Handoff & Start-Here Guide
**Last updated: 2026-06-19 · Read this top-to-bottom to start any Cowork session. Everything needed to be operational is here; deep detail is pointed to in the Documentation Index.**

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

## Current State (live read 2026-06-19 ~09:05 UTC — Juneteenth, markets closed; re-pull `get_briefing` next session)

| Metric | Value |
|---|---|
| Net Liq | ~$71,074 (€61,998) |
| Available / Excess Liq | ~$35,545 / ~$38,643 (both above floors $17k/$25k) |
| β-weighted Δ | **213.7** (target ~320 — conservative after de-risk + SPY hedge) |
| VIX / Regime | 16.8 / **bearish** |
| Realized P&L | No trades 06-19 (holiday). Prior session (06-18): **−$1,626** (MSFT BPS close −$241 + de-risk −$1,385) |
| Pacing | 0/5 logged ⚠ (manual fills not counted — track manually) |

**Concentration:** MSFT **26.6%** (de-risked from 41.9% over the week), AAPL 19.9%, GOOGL 14.5%, AMZN 10.7%, NVDA 9.8%, SPY-hedge 2.8%. Others ≤1%.

**Open book (full detail in `PORTFOLIO.md` / `get_positions`):** MSFT (LEAPs 310C×1 + **340C×1** [sold 1 today], short 490C×2 / **510C×2** [bought back 1 today] / 465C-long) · AAPL LEAPs 290C+240C · GOOGL/AMZN/NVDA PMCCs · META Jul31 545/525 PCS · AMD Jun26 + Jul31 450/430 PCS · V Jul17 300/295 + Jul31 305/290 PCS · **SPY Aug21 705P ×3 (hedge, NEW)** · OST stock (ignore).

**Trade-outcomes store (NEW feedback loop):** 2 records — MSFT BPS −$241 (`closed_pre_assignment`) and MSFT de-risk −$1,385 (`concentration_trim`). Run `python3 journal_analytics.py` (reads `data/trade_outcomes.json`).

---

## Open Priorities / Action Items
1. ✅ **DONE — `get_contract_price` hardening shipped (2026-06-18, commit `8bee85b`):** IV re-poll on `ibkr_contract_quote` + `spread_pct`/§4 `status` on `get_contract_price` (via `_spread_grade`) so it doubles as an OTM liquidity check. Deployed (smoke-test green) and pushed to fortress-v4-api. No action.
2. **META Jul31 545/525 PCS — CLOSE before Jul 29 earnings** (expires Jul 31, holds through the print). Conditional alert `320fc5ae` fires at DTE≤8 (~Jul 23). The daily post-open briefing task also flags it. Take profit at 50% or close.
3. **AMD Jun26 380/375 PCS** — far OTM (AMD ~$535), let expire Jun 26 for +~$131, then log via `log_trade_outcome`.
4. **MSFT de-risking** — trimmed to **26.5%** today (sold 1× Jan28 340C + bought back 1× Dec18 510C). Continue toward the 20% standard opportunistically on strength; no new MSFT LEAP legs. Still below 200-SMA. No tax friction (Dutch Box 3).
5. **SPY hedge** — 3× Aug21 705P on (§2.D gap closed). Maintain while regime is bearish.
6. ✅ **DONE (2026-06-19) — MSFT alert re-armed:** `8bd4926b` cleared from its stuck Jun-11 `triggered` state; threshold moved **385→375** (GEX put-support shelf, spot $379), message updated to a generic "next de-risk tranche toward 20%". Goes live Monday's open. (The old `>$412` staged-exit alert remains un-recreated — only needed if resuming a staged upside exit.)
7. **OAuth Stage 2** — still pending IBKR. Re-test with `test_ibkr_oauth.py` (NOT `get_ibkr_status.oauth`). Live data unaffected (web_api).

## Optimization backlog (from 2026-06-18 review)
✅ **DONE 2026-06-19 — gateway-down integrity guard + Parapet source badges** (`/api/data-integrity` + SourceBadge; see session log + `DATA_SOURCES.md` v1.4 / `PARAPET.md` v2.7).
Remaining — Data-source: fix `check_liquidity` ATM-clustering (partly addressed via `get_contract_price` spread grade); `strategy_metrics` on real vol (still placeholder); surface ex-div from FMP dividends-calendar; retire paywalled Massive options path. Workflow: consolidate macro-defer + VIX-term + ex-div into `pretrade_check`; wire `get_vix_term` into the regime read; auto-capture entry conditions (IVR/DTE/delta) at open for the trade-outcomes loop; fix pacing counter to count manual fills; add weekly scheduled tasks (macro-calendar refresh, journal_analytics run). NB: `pretrade_check`/regime/`strategy_metrics`/pacing live in backend routes outside the repo mount — need the file or a patch.

## Active Conditional Alerts
| ID | Ticker | Trigger | Status | Note |
|---|---|---|---|---|
| `320fc5ae` | META | dte_lte 8 | armed | Close Jul31 PCS before Jul 29 earnings (~Jul 23) |
| `8bd4926b` | MSFT | price_below 375 | armed | Re-armed 06-19 (was 385/stuck-triggered). Close < $375 → next de-risk tranche toward 20%. Confirm on daily close (fires on intraday spot). |
| (missing) | MSFT | price_above 412 | — | Recreate only if resuming a staged upside exit |

---

## System Status (live 2026-06-15)
- Backend `fortress-dashboard-v4`: WSL, port 8081 (`sudo systemctl status fortress-dashboard-v4`)
- IBKR CP Gateway `cp-gateway`: Docker, iBeam headless, **web_api AUTHENTICATED** (account U7453366, OPRA live)
- **OAuth Stage 2: ❌ pending IBKR** (Priority 7) — don't trust `get_ibkr_status.oauth`
- MCP server **v4.5.1** live at `C:\Users\cityc.000\fortress_mcp\fortress_mcp.py` (dev copy: `fortress_mcp_v452.py`). Write tools need `FORTRESS_MCP_ALLOW_WRITES=1`.
- Parapet **v2.7 / Sprint 13** at `http://localhost:4000` (top-bar data-source badge live since 2026-06-19)
- QuantData JWT: `~/.quantdata-mcp/config.json` (refresh procedure in `WORKFLOW.md`)

## OneDrive ↔ GitHub Sync (run `sync_check.sh` at every session wrap)
The OneDrive `2606Fortress` folder is the **dev/edit copy**; deploys copy files **into** the WSL repos (`~/fortress-v4-api`, `~/fortress-mcp`, …), which are what push to GitHub. A file edited in OneDrive but never re-deployed/committed leaves GitHub stale **while `git status` still looks clean** — this is how drift hides.
- **Detect drift:** `bash /mnt/c/Users/cityc.000/OneDrive/_Stocks26/2606Fortress/sync_check.sh` — content-diffs every mapped OneDrive→repo file and prints per-repo git status. Run it before ending any session. (Canonical repo copy: `~/fortress-v4-api/scripts/sync_check.sh`; it now self-checks via its own MAP entry.)
- **Parapet auto-tracked (2026-06-19):** `sync_check.sh` now derives the Parapet file list straight from `deploy_parapet.sh`'s `FILES=()` array — every frontend file the deploy copies is drift-checked automatically. To track a NEW Parapet file, add it to `deploy_parapet.sh`'s `FILES` and you're done (no second list).
- **Convention:** any NEW *backend* script created in OneDrive must be added to the `MAP` in `sync_check.sh` **and** (if backend-related) to `deploy_data_sources.sh`'s copy block, so it can never silently miss GitHub.
- **Runtime-state policy:** `iv_history.json`, `pending_orders.json`, and `*.pre-ibkr-bak` are transient — gitignore them. `conditional_alerts.json`, `macro_events.json`, `trade_outcomes.json` are config/data — commit them (the last re-appears as a diff as trades close; commit at session wrap).

## Documentation Index (where detail lives)
| Doc | What's in it |
|---|---|
| `PORTFOLIO.md` (v4.1) | **Live positions, account, pending actions, stop-loss watch, strategy quick-ref, universe** — start here for state |
| `01_Portfolio_Strategy_v3_9.md` | Full strategy spec: governance, active strategies, entry/exit/risk rules, post-earnings playbook |
| `WORKFLOW.md` (v2.5) | Daily workflow, startup, entry/roll/stop, system URLs, thresholds, QuantData refresh, common issues |
| `07_MCP_Workflow_and_Prompts_v1_9.md` | MCP prompt playbook — exact phrasings per phase |
| `DATA_SOURCES.md` (v1.4) | Reliability ledger + source-of-truth per data attribute (incl. `/api/data-integrity` gateway guard) |
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
bash sync_check.sh                                    # OneDrive↔GitHub drift guard — run at session wrap
# Force-decline a stuck order / expire stale DAY orders:
curl -s -X DELETE "http://localhost:8081/api/orders/pending/{ID}/force" -H "Authorization: Bearer $TOKEN"
curl -s -X POST   "http://localhost:8081/api/orders/expire-stale"       -H "Authorization: Bearer $TOKEN"
```

## Recent Session Log
Full dated history (Jun 8–10 deploys, sprints, decisions) is archived in **`archive/HANDOFF_full_2026-06-15.md`**.
- **2026-06-19 (cont. — backlog build, markets closed):** Shipped the **gateway-down integrity guard + Parapet source badge** (first item off the 06-18 optimization backlog). Backend: new `GET /api/data-integrity` in `options_analytics.py` — live IBKR snapshot probe (SPY) returning an honest `live`/`fallback`/`down` verdict that **bypasses the false-fresh `staleness` field** (the exact §Reliability trap); yfinance probe distinguishes "gateway down but degraded-usable" from "nothing responding". Frontend (`fortress-parapet`): `getDataIntegrity()` + `IntegrityData` in `api.ts` (falls back to `/api/ibkr/capability` pre-deploy); new `SourceBadge.tsx` always-visible top-of-page badge (green ● Live / amber ▲ Delayed / red ■ No data) with a `useIntegrity()` hook that also **tints the whole header bar** amber/red when degraded and shows a dashed **"↻ Restart gateway"** pill carrying the Step-0 recovery steps. Verified live post-deploy: `{"integrity":"live","source":"ibkr","spot":746.94}`; prod `tsc && vite build` green (777 modules). Then hardened the drift guard: `sync_check.sh` now **auto-tracks all Parapet `src/` files** by parsing `deploy_parapet.sh`'s `FILES=()` (no second list) + added a **self-check MAP entry** for `sync_check.sh` itself; consolidated the script to its canonical `scripts/sync_check.sh` (dropped a root-dir duplicate). Pushed: fortress-v4-api `54489de` (route) + `d5e468c` (sync_check), fortress-parapet `0456102` (badge). All four repos clean. Docs updated (HANDOFF, DATA_SOURCES v1.4, PARAPET v2.7, PARAPET_SPRINT, SYSTEM).
- **2026-06-19 (Juneteenth, markets closed):** Startup checklist run live — backend green (web_api authed, OPRA live), NLV $71,074, β-Δ 213.7, MSFT 26.6%, regime bearish/VIX 16.8. **Re-armed the stale MSFT alert `8bd4926b`**: stuck `triggered` from a Jun-11 wick → cleared; threshold **385→375** (GEX put-support shelf, spot $379), message updated to a generic "next de-risk tranche toward 20%" (old strike-specific text was stale post-trim). **GitHub sync audit:** all four repos level with origin; core code (`ibkr_marketdata`, `options_analytics`, NaN test, MCP v4.5.2) all in sync. Found **two OneDrive-only files never committed** — `journal_analytics.py` + `snapshot_iv.sh` — copied into the repo and pushed (commit `ae294f2`). Removed two 0-byte junk files from fortress-v4-frontend. Built **`sync_check.sh`** (OneDrive↔GitHub drift guard) + added the two scripts to `deploy_data_sources.sh` + documented the sync convention above. Then did the `.gitignore` runtime-state cleanup + committed `sync_check.sh` (commits `5154366`, `a35e214`). **API-token security pass:** the hardcoded backend token (`07f0…`) was exposed in tracked files + git history. Scrubbed it from `SYSTEM.md`/archive/`setup-wsl.sh` (commits `eef8b8d` api, `c8d9555` parapet), moved all scripts to read `~/.fortress_api_token`, and **rotated the token** (new `b6684e…`; old is 401-dead). The rotation touched **5 places** — backend systemd, `~/.fortress_api_token`, packaged-app `claude_desktop_config.json` (at `…\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\`, NOT a hand-editable UI — Customize→Connectors only sets tool perms), OneDrive config backup, and the **Parapet build**. Parapet fought back with a chain of traps (all → 401): stale `.env.local` overriding `.env`, systemd-quote scrape, `umask 077` → nginx 403, browser cache. All fixed + hardened in `deploy_parapet.sh`; full **token-rotation runbook with every gotcha is in `SYSTEM.md`**. Everything green: portfolio, GitHub sync, MCP connector, and Parapet all on the new token.
- **2026-06-16:** Fixed the GEX/skew/liquidity NaN-in-JSON 500 bug in `options_analytics.py` (`get_gex`/`get_vol_skew`/`check_liquidity` — NaN `openInterest`/`bid`/`ask` from yfinance slipped past `<=0` guards via the `float(x or 0)` trap and crashed Starlette's `allow_nan=False` serializer). Added a `_f()` NaN/Inf-safe coercion + `math.isfinite` skip-guard; deployed via `deploy_data_sources.sh`; get_gex verified live on V and AAPL. Reviewed OptionsPlay DailyPlay (HOOD/RDDT/RCL) — all declined vs framework (HOOD excluded; PCS/bullish structures fail the bearish regime gate; near-ATM deltas vs the 0.15–0.20 PCS spec). Scanned Tier-1 financials/consumer (V/PNC/MAR) for a compliant CSP/IC — all grade-D liquidity, passed. Updated `DATA_SOURCES.md` v1.3. Built the **catalyst gate** (Strategy §4 binary-event timing → codified): backend `get_macro_events`/`set_macro_events` routes in `options_analytics.py` (Claude-curated store, `defer_advisory` when high-impact FOMC/CPI/PPI/NFP/PCE ≤2d, advisory only), MCP tools (v4.6.0), Parapet event-horizon feed + amber defer banner. Implements the old Sprint 14 `intel.events` item. ⚠ **Needs deploy** (data-sources + parapet + MCP relaunch) then **seed** via `set_macro_events()` from FRED/FMP. Full design: `CATALYST_GATE_PROPOSAL.md`. **Deployed + seeded same day** (FOMC Jun17/PCE Jun25/NFP Jul2/CPI Jul14/PPI Jul15/FOMC Jul29; defer_advisory firing on FOMC). Then a profitability/reliability batch: **`get_vix_term`** VIX-vs-VIX3M term-structure regime input (backend route + MCP, v4.7.0); **`journal_analytics.py`** expectancy/win-rate feedback loop (repo root — journal currently near-empty + lacks ivr/dte/delta-at-entry, so a schema enrichment is recommended to unlock bucketing); **NaN route smoke-test** (`tests/test_options_routes_nan.py`) wired into `deploy_data_sources.sh` with rollback; verified **FMP `dividends-calendar`** works on-tier and documented the ex-div assignment-risk check (no current risk — book's short calls are deep-OTM / non-dividend names). MCP now v4.7.0 — **needs another deploy + relaunch** for `get_vix_term`. (Resolved: deployed + relaunched; v4.7.0 live, `get_vix_term` verified — VIX 15.9/VIX3M 19.3 = contango, premium-selling favorable; deploy NaN smoke-test hardened to actually exercise the routes after 3 env fixes.) Then built the **trade-outcomes feedback loop**: backend `GET/POST /api/trade-outcomes` (structured closed-trade sidecar capturing ivr/dte/short-delta at entry), MCP `log_trade_outcome`/`get_trade_outcomes` (**v4.8.0**), `journal_analytics.py` repointed to the store (expectancy by IVR/DTE/delta buckets). Sidecar chosen because the backend journal route is outside the repo mount + the MCP `add_journal_entry` is schema-drifted from the stored entry (noted finding). ⚠ **Needs deploy + relaunch** for v4.8.0. Design: `JOURNAL_FEEDBACK_LOOP.md`. (Deployed + relaunched; v4.8.0 live, trade-outcomes store working.)
- **2026-06-18 (post-FOMC):** Tech sold off (MSFT 394→375). **Closed the MSFT Jun18 380/370 BPS** (it went ITM through the 380 short strike) — realized −$241.49, logged as the first **trade-outcomes** record. **Added a SPY hedge** (3× Aug21 705P @ $7.196, ~−67 delta) to close the §2.D gap (hedge was $0). META Jul31 PCS on watch (delta −0.33, earnings inside expiry — close by ~Jul 23). Built **`get_contract_price`** (backend `GET /api/options/contract-price/{ticker}` in options_analytics.py + `ibkr_contract_quote` helper in ibkr_marketdata.py + MCP **v4.9.0**) — IBKR-first real-time bid/ask/last/IV for ANY single strike (fixes check_liquidity's near-spot-only limitation), yfinance fallback; added to the NaN smoke-test. Verified `qd_get_contract_price` works across SPY/MSFT/AMD/META/AAPL (last-traded OHLCV) as a Claude-side cross-check. **All shipped: deployed + MCP v4.9.0 relaunched + verified live on IBKR** (SPY 705P bid/ask 6.90/6.93, IV 19%). **MSFT de-risk executed** (340C/510C combo) → MSFT 26.5%, β-delta 212, logged. **Scheduled daily post-open briefing** created (`daily-post-open-briefing`, weekdays ~15:45 Amsterdam). **All four GitHub repos pushed** (fortress-v4-api incl. docs `0da9e11`, fortress-parapet `3de67af`, fortress-mcp `5e8e8aa`). Then shipped two follow-on optimizations (commit `8bee85b`): IV re-poll on `ibkr_contract_quote` + `spread_pct`/`status` on `get_contract_price` (OTM liquidity grade) — deployed, smoke-test green, pushed.
- **2026-06-15:** Rotated MSFT (sold 1× Jan28 310C) → bought AAPL Jan28 240C; MSFT concentration 59% → 42%. Added AMD Jul31 450/430 + META Jul31 545/525 put credit spreads. Set META earnings-close alert. Confirmed OAuth Stage 2 still pending (corrected an earlier false "connected" reading). Codified the ⭐ data-sourcing procedure. Consolidated/cleaned docs (deleted dupes + superseded MCP versions, archived completed proposals, merged the cheatsheet into WORKFLOW, moved all reference docs under `docs/`).
