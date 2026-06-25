# Fortress — Session Handoff & Start-Here Guide
**Last updated: 2026-06-24 · Read this top-to-bottom to start any session. This is the lean START-HERE — current state, open priorities, and protocols only. Per-session narrative lives in `SESSION_LOG.md`; per-item backlog in `BACKLOG_SPRINT_PLAN.md`; deep detail via the Documentation Index. Run the OPEN checklist now; run the CLOSE protocol (bottom) at wrap.**

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

## Current State (live read 2026-06-24 ~14:51 UTC — RTH; re-pull `get_briefing` next session)

| Metric | Value |
|---|---|
| Net Liq | ~$69,600 (≈€61,000) |
| Available / Excess Liq | ~$31.2k / ~$34.2k (above floors $17k/$25k) |
| β-weighted Δ | still **OVERSTATED** when greeks under-hydrate (hedge + short legs read 0.0) — trust the post-open re-pull / the daily-briefing sanity-check, not the headline. (β-vega build = Sprint 19.1.) |
| VIX / Regime | 18.7 / **Strongly Bullish +4** — SPY $738.5 reclaimed the flip zone (positive gamma); VIX-term **contango**. (Whipsawed from bearish/negative-gamma at the 06-24 open; tech bounced hard — AMZN +5%, GOOGL +13%.) |
| Realized P&L | +$1,724 (closed 3× SPY 705P in the hedge swap, 06-24). |
| Pacing | 3/5 (`source: position_diff`; 2 entries left this week) |

**Concentration:** MSFT **25.1%**, AAPL 18.2%, GOOGL 11.8%, AMZN 10.4%, NVDA 8.7% · **cluster (Mag-7) 74.2% ⚠** (`concentration.cluster`, warn >60%) — the real exposure. `msft_warning: false`.

**Open book (detail via `get_positions`):** MSFT LEAPs 310C+340C / short **420C×2** + 490C×2 / 465C-long · AAPL LEAPs 240C+290C / short 325C×2 · GOOGL LEAP 310C / short 395C · AMZN LEAP 200C (**naked — no short call; $9.7k at 0% income, write a call**) · NVDA LEAP 170C / short 250C / Jul17 180/175 PCS · ARM **Jul24 345/340 PCS ×4 (largest)** · V Jul17 300/295 + Jul31 305/290 PCS · META Jul31 545/525 PCS · AMD Jun26 380/375 (expires Fri) + Jul31 450/430 PCS · **SPY hedge: 5× Aug21 710/665 put spreads** ($22.5k max payout, ~−80 SPY-Δ — swapped from 3× 705P on 06-24) · OST stock (ignore).

**Trade-outcomes store:** 2 records (MSFT BPS −$241, MSFT de-risk −$1,385) — ⚠ the 06-24 705P close (+$1,724) is **not yet logged**. Run `python3 journal_analytics.py`.

---

## Open Priorities / Action Items
1. **PCE tomorrow (Jun 25)** — catalyst defer gate ACTIVE; hold new premium-selling entries until the print clears.
2. **MSFT <$375 close watch** — alert `8bd4926b` triggered 06-22 intraday; confirm on the **daily close** (not wick). If it closes <$375 → next de-risk tranche toward 20%. (One-time reminder set for 06-24 16:05 ET.)
3. **AMD Jun26 380/375 PCS** — expires **Fri Jun 26** for +~$131; let lapse, then `log_trade_outcome`. (Reminder set Fri.)
4. **Post-PCE OPTIMIZATION queue (from `get_capital_efficiency` 06-24):** (a) **AMZN** Jan'28 200C is a **naked LEAP, $9.7k at 0% income — write a call** (→ PMCC); (b) **roll under-OTM cluster short calls down** (NVDA 250C is 24% OTM ~$0; MSFT 490C×2; AAPL 325C/GOOGL 395C) — lifts income **and** trims the 74% cluster's upside delta; (c) **harvest 50%-profit PCS** (V/NVDA/AMD/META) — *not* blocked by the defer gate, do anytime.
5. **SPY hedge** — swapped to **5× Aug21 710/665 put spreads** ($22.5k payout). Maintain. ⚠ greeks-under-hydration still inflates β-delta (β-vega = Sprint 19.1).
6. **OAuth Stage 2** — still pending IBKR; re-test via `test_ibkr_oauth.py` (NOT `get_ibkr_status.oauth`). (Reminder set Mon Jun 29.)
7. **Sprint 19** — 19.2/19.3 live, 19.4a (pmcc-breakeven) live. **Next build: 19.1 β-vega** (top); then 19.4b LEAP-roll, 19.5 expected-move, 19.6 payoff, Parapet cluster chip. See `BACKLOG_SPRINT_PLAN.md` + `STRATEGY_ENHANCEMENTS_v3_10.md`.

## Optimization backlog → **`BACKLOG_SPRINT_PLAN.md`** (full per-item plan + status)
- **Done (deployed + verified live + pushed):** Sprints **0, 15, 16, 17, 18** — out-of-mount mirroring; real-vol `strategy_metrics`; OTM liquidity grading; ex-div + VIX-term + catalyst gates; advisory layer; position-diff pacing + entry-condition capture; catalyst settings UI + news-spike cooldown (MCP **v4.11.0**); **IBKR-first candidate/premarket scanners via shared `iv_source.py`** (Sprint 18) + signal-parser fix.
- **Open:** **Sprint 19 — strategy enhancements** (β-vega, cluster concentration, VRP-gate wiring, PMCC guardrails, expected-move, payoff slider). Config keys codified in `config_store.strategy.*`; builds pending. Rules of record in `STRATEGY_ENHANCEMENTS_v3_10.md`.

## Active Conditional Alerts
| ID | Ticker | Trigger | Status | Note |
|---|---|---|---|---|
| `320fc5ae` | META | dte_lte 8 | armed | Close Jul31 PCS before Jul 29 earnings (~Jul 23) |
| `8bd4926b` | MSFT | price_below 375 | **TRIGGERED** (06-22 intraday) | MSFT ~$374. ⚠ Confirm on the **daily close** before acting (fires on intraday spot). <$375 close → next de-risk tranche toward 20%. |
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
**2026-06-24** — Live trading session. Executed the **SPY hedge swap** (closed 3× 705P +$1,724, opened 5× Aug21 710/665 spreads, $22.5k payout). Regime whipsawed bearish→**Strongly Bullish +4** (tech bounced; SPY reclaimed flip zone). Declined OptionsPlay DASH/ARM (off-spec delta + concentration). Verified Sprint 19.2/19.3 live; surfaced the **optimization queue** (AMZN naked LEAP @ 0% income; roll under-OTM cluster calls; harvest 50% PCS). Set 3 reminders. **No code changes.** Next build = **19.1 β-vega**. Prior session (06-23): Sprint 19.2/19.3/19.4a shipped + verified + pushed. Full detail → `SESSION_LOG.md`.

