# Fortress — Session Handoff & Start-Here Guide
**Last updated: 2026-06-22 · Read this top-to-bottom to start any session. This is the lean START-HERE — current state, open priorities, and protocols only. Per-session narrative lives in `SESSION_LOG.md`; per-item backlog in `BACKLOG_SPRINT_PLAN.md`; deep detail via the Documentation Index. Run the OPEN checklist now; run the CLOSE protocol (bottom) at wrap.**

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
| Liquidity / option bid-ask | fortress `check_liquidity` (IBKR-first; since 2026-06-20 grades the **OTM short-leg zone** \|Δ\|≤0.35, not the ATM cluster — read `short_leg`/`tradeable_spread_pct`, not just `atm_spread_pct`) | — |
| Order flow, dark pool, max pain, OI, net flow | **quantdata** only | — |
| Live contract price / chain for spread-building | quantdata `qd_get_contract_price` or massive snapshot — **read bid/ask, not just `last`** | — |
| POP / greeks for a hypothetical spread | fortress `options_greeks` (BS) | — |
| Earnings dates | fortress `get_earnings_history` (yfinance) | ❌ FMP free tier (no earnings) |
| Macro: rates, CPI, FOMC, yield curve | FRED | — |
| Company profile, 52w, beta, dividend | FMP | — |

### Hard rules (learned from real errors)
- **`strategy_metrics` vol is now REAL (fixed 2026-06-20, Sprint 15.1):** IV/IVR come from `get_iv_rank`, DTE from `state.days_to_earnings`; payload carries `vol_source` (`ibkr`/`bs_inversion`/`hv_proxy` = real; `placeholder` = fallback). Credit/POP/IVR are trustworthy now. ⚠ **Regime is still the `neutral` placeholder** until Sprint 15.3 wires the real regime read — so don't lean on `strategy_metrics` regime_score yet.
- **Conditional price alerts (`price_above`/`price_below`) fire on intraday spot, not daily close.** A "close below X" rule needs manual close confirmation — they false-fire on wicks.
- **Pacing counter misses manual IBKR fills** — it only counts Fortress-staged orders. Track manual entries yourself.
- **Spread pricing:** always work the limit at the **mid**, never the ask/bid the ticket pre-fills. Verify the expiry doesn't span an earnings date (`get_earnings_history`) unless that's intended.
- **MCP server "disconnected" mid-session** is transient — reload the tool via ToolSearch and retry; the data is fine.

---

## 🔺 Session OPEN Checklist (run these first)
1. `get_ibkr_status` — confirm `web_api` authenticated (Step 0 above).
2. `get_briefing` — NLV, concentration, β-weighted delta vs target, pacing, regime.
3. `get_conditional_alerts` — any triggered? (note the known false-fire on intraday wicks).
4. If managing/entering: `get_roll_all`, `get_stop_loss_all`, `get_candidates`.
5. Macro context if entering: FRED for FOMC/CPI dates; `get_market_intelligence("SPY")`.

---

## Current State (live read 2026-06-22 ~14:00 UTC — RTH; re-pull `get_briefing` next session)

| Metric | Value |
|---|---|
| Net Liq | ~$70,547 (€61,680) |
| Available / Excess Liq | ~$35,416 / ~$38,282 (both above floors $17k/$25k) |
| β-weighted Δ | headline ~**420** but **OVERSTATED** — greeks under-hydrate the SPY hedge + short legs (`delta_contribution 0.0`); true net ≈ **~355** vs target ~320. Trust the post-open re-pull, not the headline. |
| VIX / Regime | 16.69 / **bearish** (VIX term contango — premium-selling favoured) |
| Realized P&L | No trades 06-22 (dev/docs session). |
| Pacing | 0/5 (`source: position_diff`; manual fills tracked separately) |

**Concentration:** MSFT **26.7%**, AAPL 19.9%, GOOGL 14.5%, AMZN 10.7%, NVDA 9.8%, SPY-hedge 2.8%. Others ≤1% (`msft_warning: false`).

**Open book (full detail in `PORTFOLIO.md` / `get_positions`):** MSFT (LEAPs 310C×1 + **340C×1** [sold 1 today], short 490C×2 / **510C×2** [bought back 1 today] / 465C-long) · AAPL LEAPs 290C+240C · GOOGL/AMZN/NVDA PMCCs · META Jul31 545/525 PCS · AMD Jun26 + Jul31 450/430 PCS · V Jul17 300/295 + Jul31 305/290 PCS · **SPY Aug21 705P ×3 (hedge, NEW)** · OST stock (ignore).

**Trade-outcomes store (NEW feedback loop):** 2 records — MSFT BPS −$241 (`closed_pre_assignment`) and MSFT de-risk −$1,385 (`concentration_trim`). Run `python3 journal_analytics.py` (reads `data/trade_outcomes.json`).

---

## Open Priorities / Action Items
1. **META Jul31 545/525 PCS — CLOSE before Jul 29 earnings** (expires Jul 31, holds through the print). Alert `320fc5ae` fires DTE≤8 (~Jul 23); daily post-open briefing also flags it. Take profit at 50% or close.
2. **AMD Jun26 380/375 PCS** — far OTM (AMD ~$555), let expire **Fri Jun 26** for +~$131, then `log_trade_outcome`.
3. **MSFT de-risking** — ~26.5–26.8%; trim toward the 20% standard opportunistically on strength, no new MSFT LEAP legs. Below 200-SMA. Alert `8bd4926b` fires on a **<$375 daily close** → next tranche (confirm on close, not wick). No tax friction (Dutch Box 3).
4. **SPY hedge** — 3× Aug21 705P on; maintain while bearish. ⚠ Known gap: the β-delta calc currently omits the hedge's (and short legs') delta when greeks under-hydrate — see the §6 note in `STRATEGY_ENHANCEMENTS_v3_10.md` (β-vega build) and the post-open delta sanity-check in `daily-post-open-briefing`.
5. **OAuth Stage 2** — still pending IBKR; re-test with `test_ibkr_oauth.py` (NOT `get_ibkr_status.oauth`). Live data unaffected (web_api).
6. **Sprint 19 (strategy enhancements)** — config codified; builds pending (β-vega, cluster concentration, VRP-gate wiring, PMCC guardrails). See `BACKLOG_SPRINT_PLAN.md` + `STRATEGY_ENHANCEMENTS_v3_10.md`.

## Optimization backlog → **`BACKLOG_SPRINT_PLAN.md`** (full per-item plan + status)
- **Done (deployed + verified live + pushed):** Sprints **0, 15, 16, 17, 18** — out-of-mount mirroring; real-vol `strategy_metrics`; OTM liquidity grading; ex-div + VIX-term + catalyst gates; advisory layer; position-diff pacing + entry-condition capture; catalyst settings UI + news-spike cooldown (MCP **v4.11.0**); **IBKR-first candidate/premarket scanners via shared `iv_source.py`** (Sprint 18) + signal-parser fix.
- **Open:** **Sprint 19 — strategy enhancements** (β-vega, cluster concentration, VRP-gate wiring, PMCC guardrails, expected-move, payoff slider). Config keys codified in `config_store.strategy.*`; builds pending. Rules of record in `STRATEGY_ENHANCEMENTS_v3_10.md`.

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
- MCP server live at `C:\Users\cityc.000\fortress_mcp\fortress_mcp.py` (dev copy: `fortress_mcp_v452.py`; repo: `~/fortress-mcp`). Write tools need `FORTRESS_MCP_ALLOW_WRITES=1`.
  - **Token now FILE-DRIVEN (2026-06-20):** `_resolve_api_token()` prefers `~/.fortress_api_token` over the env var. The plugin runs the MCP as a **Windows** process, so it reads **`C:\Users\cityc.000\.fortress_api_token`** (a Windows-side copy of the WSL secret). This immunizes against the stale token a per-session plugin `.mcp.json` was injecting (the 401 trap — the **6th** rotation place; runbook updated in `SYSTEM.md`). On rotation, write BOTH token files (WSL + Windows); the `.mcp.json`/desktop-config steps are no longer required. The live Windows MCP copy is drift-tracked in `sync_check.sh`.
  - **MCP now v4.10.0** (2026-06-21). Sprint 16 tools: `get_ibkr_fills` (inspection), `get_position_opens` (position-diff pacing source), `capture_position_snapshot`, `get_entry_conditions`. (Earlier: `get_ex_div`/`set_ex_div_events`; `check_liquidity` returns `short_leg`/`tradeable_spread_pct`/`grade_basis`.)
- Parapet **v2.7 / Sprint 13** at `http://localhost:4000` (top-bar data-source badge live since 2026-06-19)
- QuantData JWT: `~/.quantdata-mcp/config.json` (refresh procedure in `WORKFLOW.md`)

## OneDrive ↔ GitHub Sync (run `sync_check.sh` at every session wrap)
The OneDrive `2606Fortress` folder is the **dev/edit copy**; deploys copy files **into** the WSL repos (`~/fortress-v4-api`, `~/fortress-mcp`, …), which are what push to GitHub. A file edited in OneDrive but never re-deployed/committed leaves GitHub stale **while `git status` still looks clean** — this is how drift hides.
- **Detect drift:** `bash /mnt/c/Users/cityc.000/OneDrive/_Stocks26/2606Fortress/sync_check.sh` — content-diffs every mapped OneDrive→repo file and prints per-repo git status. Run it before ending any session. (Canonical repo copy: `~/fortress-v4-api/scripts/sync_check.sh`; it now self-checks via its own MAP entry.)
- **Parapet auto-tracked (2026-06-19):** `sync_check.sh` now derives the Parapet file list straight from `deploy_parapet.sh`'s `FILES=()` array — every frontend file the deploy copies is drift-checked automatically. To track a NEW Parapet file, add it to `deploy_parapet.sh`'s `FILES` and you're done (no second list).
- **Convention:** any NEW *backend* script created in OneDrive must be added to the `MAP` in `sync_check.sh` **and** (if backend-related) to `deploy_data_sources.sh`'s copy block, so it can never silently miss GitHub.
- **Runtime-state policy:** `iv_history.json`, `pending_orders.json`, `position_snapshots.json`, `entry_conditions.json` (last two NEW, Sprint 16), and `*.pre-ibkr-bak`/`*.pre-sprint0-bak` are transient — gitignore them. `conditional_alerts.json`, `macro_events.json`, `trade_outcomes.json` are config/data — commit them (the last re-appears as a diff as trades close; commit at session wrap).

## Documentation Index (where detail lives)
| Doc | What's in it |
|---|---|
| `PORTFOLIO.md` (v4.1) | **Live positions, account, pending actions, stop-loss watch, strategy quick-ref** — start here for state |
| `01_Portfolio_Strategy_v3_9.md` | Full strategy spec: governance, strategies, entry/exit/risk rules, post-earnings playbook |
| `STRATEGY_ENHANCEMENTS_v3_10.md` | **Research-codified rules + parameters (2026-06-22):** VRP gate, 50% profit-take, PMCC guardrails, β-vega, cluster concentration — status per rule |
| `IMPROVEMENT_RESEARCH_2026-06-22.md` | External best-practice scan + sources behind the v3.10 enhancements |
| `BACKLOG_SPRINT_PLAN.md` | Sprint backlog — 0/15/16/17/18 done; **19 = strategy enhancements** |
| `SESSION_LOG.md` | **Dated session history** (verbose narrative + entry template) — HANDOFF keeps only the latest |
| `WORKFLOW.md` (v2.5) | Daily workflow, entry/roll/stop, URLs, thresholds, QuantData refresh, common issues |
| `07_MCP_Workflow_and_Prompts_v1_9.md` | MCP prompt playbook — exact phrasings per phase |
| `DATA_SOURCES.md` (v1.5) | Reliability ledger + source-of-truth per data attribute |
| `SYSTEM.md` | Architecture, services, IBKR auth, deploy commands, repos, key paths |
| `PARAPET.md` / `PARAPET_SPRINT.md` | Frontend reference / component map / sprint history |
| `JOURNAL_FEEDBACK_LOOP.md` | Trade-outcomes store + `journal_analytics.py` — expectancy/win-rate by IVR/DTE/delta |
| `archive/` | Superseded/shipped proposals (incl. `CATALYST_GATE_PROPOSAL.md`) + `HANDOFF_full_2026-06-15.md` |

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

---

## 🔻 Session CLOSE Protocol (run at every wrap — keeps the handoff lean)
1. **Deploy + verify** anything changed: `bash deploy_data_sources.sh` (compile-check + NaN smoke-test + rollback) → MCP relaunch if MCP changed → `bash deploy_parapet.sh` if frontend changed → verify the change **live** via MCP before committing.
2. **`bash sync_check.sh`** — must read all-green. Any `DIFFERS`/`MISSING` → copy OneDrive→repo first.
3. **Commit + push** each touched repo (`fortress-v4-api` / `-mcp` / `-parapet`). gitignore runtime/backups (`*.pre-*-bak`, `position_snapshots.json`, `entry_conditions.json`, `__pycache__`); **commit** curated data (`conditional_alerts.json`, `macro_events.json`, `ticker_news.json`, `trade_outcomes.json`).
4. **Update this file's top:** `Current State` table (date + NLV/Δ/regime/concentration), `Open Priorities`, `Active Conditional Alerts` — only if they changed.
5. **Append ONE short entry to `SESSION_LOG.md`** using the template there (3–6 lines, not an essay). Do NOT grow the session log inside HANDOFF.
6. Bump the **Last updated** date in the header.

## Latest session
**2026-06-22** — Sprint 17 shipped (catalyst settings, news-spike cooldown, MCP **v4.11.0**) + Sprint 18 (candidate/premarket scanners → IBKR-first via shared `iv_source.py`, IV sanity guards, signal-parser fix) — all deployed, verified live, pushed (`fortress-v4-api 4a76eb6`). **Sprint 19 strategy enhancements codified** (config keys + `STRATEGY_ENHANCEMENTS_v3_10.md` + `IMPROVEMENT_RESEARCH_2026-06-22.md`); builds pending. Docs reorganized (session log split out; this START-HERE slimmed). Full detail → `SESSION_LOG.md`.

