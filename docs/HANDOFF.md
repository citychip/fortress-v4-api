# Fortress — Session Handoff & Start-Here Guide
**Last updated: 2026-06-30 · Read this top-to-bottom to start any session. This is the lean START-HERE — current state, open priorities, and protocols only. Per-session narrative lives in `SESSION_LOG.md`; per-item backlog in `BACKLOG_SPRINT_PLAN.md`; deep detail via the Documentation Index. Run the OPEN checklist now; run the CLOSE protocol (bottom) at wrap.**

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
| **Chart trend / SMAs / LuxAlgo S-R / TN signals** | **`tradingview` MCP** (`data_get_study_values` on the **"Clean"** layout) — see §sourcing note below | screenshots (now redundant) |

### Hard rules (learned from real errors)
- **`strategy_metrics` vol is now REAL (fixed 2026-06-20, Sprint 15.1):** IV/IVR come from `get_iv_rank`, DTE from `state.days_to_earnings`; payload carries `vol_source` (`ibkr`/`bs_inversion`/`hv_proxy` = real; `placeholder` = fallback). Credit/POP/IVR are trustworthy now. ⚠ **Regime is still the `neutral` placeholder** until Sprint 15.3 wires the real regime read — so don't lean on `strategy_metrics` regime_score yet.
- **Conditional price alerts (`price_above`/`price_below`) fire on intraday spot, not daily close.** A "close below X" rule needs manual close confirmation — they false-fire on wicks.
- **Pacing now catches manual IBKR fills** (Sprint 16.5 position-diff) — it diffs the IBKR-synced book, not just Fortress-staged orders. ⚠ **Sprint 20.2 fix (2026-06-27):** the per-briefing snapshot capture had a **non-atomic write** that, on a concurrent/truncated read, let the next capture **clobber the snapshot history** → position-diff silently collapsed and the briefing fell back to `journal_only` (0/5). Fixed with atomic writes + a non-destructive guarded load; the briefing now exposes `pacing.position_diff_reason` so a fallback is never silent again. If pacing reads `source: journal_only`, check `position_diff_reason` (`need ≥2 snapshots to diff` = normal early-week/after-reset; anything else = investigate). Needs ≥2 distinct-day snapshots to diff.
- **Spread pricing:** always work the limit at the **mid**, never the ask/bid the ticket pre-fills. Verify the expiry doesn't span an earnings date (`get_earnings_history`) unless that's intended.
- **MCP server "disconnected" mid-session** is transient — reload the tool via ToolSearch and retry; the data is fine.

---

## 🔺 Session OPEN Checklist (run these first)
1. `get_ibkr_status` — confirm `web_api` authenticated (Step 0 above).
2. **`trigger_ibkr_sync` FIRST, then `get_briefing`** — and check `staleness.hours`. **If > ~2h, re-sync again before trusting any positions/roll/stop read** (the 06-26 trap: first briefing was 18.8h stale and silently showed the wrong book). Then read NLV, concentration, β-weighted delta vs target, pacing, regime. Portfolio **β-vega** is now a briefing stat (Sprint 20.6/19.1): `greeks.beta_weighted_vega` + `beta_vega_flag` (`net_long_vega` = the blind-spot flip on a premium-selling book). Watch the flag.
3. `get_conditional_alerts` — any triggered? (Sprint 20.3 added `close_below`/`close_above` types evaluated by the EOD pass against the daily close — use those for close rules. Legacy `price_*` rules still fire on intraday wicks, so confirm those on the actual daily close until converted.)
4. If managing/entering: `get_roll_all`, `get_stop_loss_all`, `get_candidates`. Recovery KPIs: `get_spy_hedge_coverage` (vs $20k floor) + `concentration.cluster` (vs 60%).
5. Macro context if entering: FRED for FOMC/CPI dates; `get_market_intelligence("SPY")`.

> **Automation:** the **`daily-post-open-briefing`** scheduled task (weekday 15:45 CEST / 09:45 ET) now runs this checklist automatically — force-sync first + staleness guard + hedge/cluster/β-vega steps. The **`hedge-coverage-drift-alert`** task (weekday 09:03 CEST, Sprint 20.5) is a dedicated under-hedge watchdog (🔴 when `coverage_ok=false`). The **`fortress-recovery-dashboard`** Cowork artifact renders the same live read on demand (re-open/Reload to refresh).

---

## Current State (live read 2026-06-26 ~20:38 UTC, post `trigger_ibkr_sync` — staleness 0.0h/fresh; re-pull `get_briefing` next session. ⚠ Always re-sync if staleness >~2h — the OPEN checklist now forces it.)

| Metric | Value |
|---|---|
| Net Liq | **$64,813** (≈€56,893) |
| Available / Excess Liq | **$26,066 / $29,414** (above floors $17k/$25k — cushion intact) |
| β-weighted Δ | **210** (raw Δ +385, Θ **+7.3**, vega **+1,050**). ⚠ Note vs 06-26 16:15: theta collapsed (+113→+7.3) and vega **flipped long** (−374→+1,050) — consistent with the MSFT roll-down adding long-vega/long-gamma on the short leg. ✅ **β-vega now auto-flagged (Sprint 20.6):** `greeks.beta_weighted_vega` + `beta_vega_flag` — today β-vega **−421.7** (`net_short_vega`, normal); a `net_long_vega` flip now shows in the briefing + recovery dashboard. |
| VIX / Regime | **18.4 / normal**, portfolio macro **bearish**. |
| Pacing | **5/5 used** this week (`position_diff`) — 0 remaining, resets Monday 06-29. NFP defer-gate arms ~06-30. |

**Concentration (briefing, NLV basis):** GOOGL **25.1%**, MSFT **23.0%**, AMZN **19.6%**, AAPL 16.2%, NVDA 7.3% · **cluster (Mag-7) 91.2% ⚠⚠** (warn 60%). (NB: ✅ **20.4 resolved 2026-06-27** — CANONICAL basis = **market_value / NetLiq** (what `get_briefing.concentration` emits; the denominator §7 caps + the 60% warn use). The cluster block now carries `basis: "market_value_pct_of_netliq"`. The old ~93% figure was cluster MV / total-position MV — a different denominator (drops cash), **not** the source of truth; cite the briefing `cluster.pct`.)

**Management signals (06-26 20:38):** **MSFT** is unanimous across all three systems — alert `8bd4926b` TRIGGERED + roll **URGENT** (short Sep18 375C Δ **0.536**) + stop **ACT_IMMEDIATELY** (below 200-SMA $446); spot $372. AMD Jun26 380C = DTE-0 lapse (full credit ~+$131, no action). **WATCH:** ARM Aug21 320C (Δ 0.374), MU Jul31 1100C (Δ 0.409). AMZN/NVDA/AAPL/GOOGL short legs all SAFE. **SPY hedge $3,035 vs $20–30k floor — still UNDER-HEDGED.**

**Open book (detail via `get_positions`):** MSFT LEAPs 310C+340C / short **375C×2** (rolled DOWN from 390C **06-26**, +$1,200 cr) + 465C-long · AAPL LEAPs 240C+290C / short 305C×2 · GOOGL LEAP 310C / short 375C · AMZN LEAP 200C / short Aug21 250C (PMCC) · NVDA LEAP 170C / short Aug21 220C / Jul17 180/175 PCS · ARM Aug21 320/310 PCS ×4 · MU Jul31 1100/1075 PCS ×1 · V Jul31 305/290 PCS (**Jul17 300/295 ×4 CLOSED 06-26 ~+$272, 87%**) · AMD Jul31 450/430 PCS + **Jun26 380/375 (expires today 6/26, deep OTM → full credit ~+$131)** · **SPY hedge: 5× Aug21 710/665 put spreads — net only ~$2.9k vs $20–30k §2.D floor ⚠ UNDER-HEDGED** · OST stock (44 sh, ~$75, −98% dead — CLOSE).

**Trade-outcomes store (n=4):** ✅ logged 06-26 — SPY 705P (+$1,724) and META (−$235). **Still to log:** today's V Jul17 close (+$272), MSFT roll, and AMD lapse (after close). **✅ FIXED 2026-06-27 (Sprint 20.1): dashboard journal `/api/journal` 422** — prose entries now record (action case-normalized + prose fields `reasoning`/`framework_rules`/`outcome`/`tags` accepted & persisted; verified live, id `742a3c9b`). Narrative journaling restored alongside the numeric `log_trade_outcome` store.

---

## Open Priorities / Action Items
**NEW: see `REVISED_RECOVERY_STRATEGY_2026-06-26.md` — the recovery plan (diagnosis + 5 pillars + Monday sequence). The −$21.3k drawdown is 100% long mega-cap tech LEAPs + dead OST; the income engine is green. Recover via the engine, not by doubling down on beta.**

1. **Close OST** — 44 sh, ~$75, −98% dead line. Sell as a LIMIT (~$1.60–1.70, illiquid). Free it. (Pending as of 06-26 wrap.)
2. **MSFT de-risk = the trim target** (alert `8bd4926b` still **TRIGGERED**). TV levels: MSFT ~$373 (bounced today), below BOTH 50SMA (411) & 200SMA (448) = only structurally broken name → trim a Jan'28 LEAP (or roll down-and-in) **into the 405–411 bounce zone**, not at 373. **GOOGL weakened** (~337, re-entry SHORT, now below its 50SMA 369) — no longer the safe anchor; trim into **367–369**, support 314. AMZN/NVDA/AAPL = keep (healthy), short calls correctly above resistance.
3. **SPY hedge re-fund** — only ~$2.9k vs $20–30k §2.D floor → **UNDER-HEDGED**. Rebuild toward floor as a put spread **Monday, ahead of NFP Jul 2**. (Want SPY/QQQ chart first.)
4. **New non-tech income (Monday, pacing resets):** TV levels pulled — **MAR = top pick** (PCS short ~**345** below LuxAlgo support, earnings ~38d clear); **VST** small second (short ~150, below 200SMA so size tiny); **LLY** if sizing allows (short ~1100, big notional, 1 lot). **HOLD ELV & GE** — earnings ~19d (§4c). Exact strikes need Monday's live chain (short ~0.20–0.25Δ below support). Full level tables in `REVISED_RECOVERY_STRATEGY_2026-06-26.md` §4.
5. **Log outcomes:** V Jul17 close (+$272), MSFT roll, AMD lapse (after close). ~~Fix dashboard journal 422.~~ ✅ **journal 422 FIXED 2026-06-27 (Sprint 20.1)** — prose entries record again; consider re-logging the qualitative narrative for the recent trades now that it works.
6. **Cluster glide:** 93% → ≤60% over ~6–8 wks on bounces. Keep AMZN/NVDA/AAPL (healthy uptrend pullbacks) + write calls into resistance (AMZN 250 ✓, NVDA 212 / 220C ✓, AAPL 305/310 ✓). NVDA add-back zone = 174–176 support.
7. **MU Jul31 1100/1075 PCS** — TP ~50% or if MU breaks **$1,150 DP floor**. Max profit $927 / loss $1,573 / BE $1,091.
8. **NFP Thu Jul 2**, CPI Jul 14, FOMC Jul 29. **OAuth Stage 2** still pending. **Sprint 19** next builds: 19.1 β-vega (top), 19.4b LEAP-roll, 19.5 expected-move, 19.6 payoff. See `BACKLOG_SPRINT_PLAN.md` + `STRATEGY_ENHANCEMENTS_v3_10.md`.

## Optimization backlog → **`BACKLOG_SPRINT_PLAN.md`** (full per-item plan + status)
- **Done (deployed + verified live + pushed):** Sprints **0, 15, 16, 17, 18** — out-of-mount mirroring; real-vol `strategy_metrics`; OTM liquidity grading; ex-div + VIX-term + catalyst gates; advisory layer; position-diff pacing + entry-condition capture; catalyst settings UI + news-spike cooldown (MCP **v4.11.0**); **IBKR-first candidate/premarket scanners via shared `iv_source.py`** (Sprint 18) + signal-parser fix.
- **Open:** **Sprint 19 — strategy enhancements** (β-vega, cluster concentration, VRP-gate wiring, PMCC guardrails, expected-move, payoff slider). Config keys codified in `config_store.strategy.*`; builds pending. Rules of record in `STRATEGY_ENHANCEMENTS_v3_10.md`.
- **NEW: Sprint 20 — workflow hardening & feedback-loop repair** (added 2026-06-27, from the tooling review): **20.1 ✅ DONE+VERIFIED 2026-06-27 — journal 422 fixed** (action case-normalized + prose fields accepted/persisted; backend `journal.py` pulled into mount + wired into deploy/sync), 20.2 ✅ **DONE+DEPLOYED 2026-06-27 — pacing manual-fill capture** (found+fixed an active bug: per-briefing snapshot capture's non-atomic write collapsed the position-diff store → silent 0/5 fallback; now atomic-write + guarded load + `position_diff_reason` surfaced; full count re-verify Mon 06-29), 20.3 close-confirmed alert type (kills the wick false-fire / manual-close step), 20.4 ✅ **DONE 2026-06-27 — single cluster-% basis** (canonical = market_value/NetLiq; `cluster.basis` label added; recovery dashboard already cites the briefing), 20.5 ✅ **DONE 2026-06-27 — `hedge-coverage-drift-alert` scheduled task** (weekday 09:03 local; 🔴 when `get_spy_hedge_coverage.coverage_ok=false` w/ §2.D action, 🟢 in-band; gateway-down soft-skip), 20.6 ✅ **DONE+VERIFIED 2026-06-27 — β-vega in the briefing** (= 19.1; `greeks.beta_weighted_vega` −421.7 + `beta_vega_flag` net_short/net_long; recovery dashboard shows it; raw −355.6 → β-vega −421.7 live). **20.3 ✅ CODE-COMPLETE 2026-06-29 (needs deploy+verify) — close-confirmed `close_below`/`close_above` alert type** (pulled `conditional_alerts.py`+`scheduler/runner.py` into mount; EOD pass vs the daily close at 21:15 UTC, intraday spot skips close-types; config `alerts.close_eval_*`; MCP `evaluate_close_alerts`; wired into deploy/sync). **Sprint 20 now fully addressed — 20.3 pending the deploy/commit pass.** **Done without code 2026-06-27:** hardened the `daily-post-open-briefing` task (force-sync + staleness guard + hedge/cluster/β-vega) and built the `fortress-recovery-dashboard` live artifact.

## Active Conditional Alerts
| ID | Ticker | Trigger | Status | Note |
|---|---|---|---|---|
| `8bd4926b` | MSFT | price_below 375 | **TRIGGERED** | MSFT ~$369 (below 375, under 200-SMA). Tranches taken: 420→390C (06-25), 390→375C (06-26, +$1,200 cr). Still ~24.7% — **next tranche = trim a Jan'28 LEAP into a $395–410 bounce** (don't sell 369). ⚠ **Post-20.3 deploy: delete + recreate as `close_below 375`** (alert_type isn't PATCH-updatable) so it's EOD-confirmed and stops false-firing on wicks. |
| ~~`320fc5ae`~~ | META | dte_lte 8 | **DELETED 06-26** | Jul31 PCS closed; alert removed. |
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
- **TradingView MCP (NEW 2026-06-26):** `tradingview` server added to `claude_desktop_config.json` (`command: node`, `C:\Users\cityc.000\tradingview-mcp\src\server.js`). Reads the live TradingView Desktop chart via CDP. Use the **"Clean"** layout (TN Alerts v17 / Clean Decision Chart v3.2 / LuxAlgo S-R); `data_get_study_values` gives price/50-200SMA/WMA/LuxAlgo S-R/signals. Caveats: re-read once after a symbol switch (first read = TN only); `quote_get` ignores its symbol arg and returns the *chart* symbol; LuxAlgo pivots stale on trending names (use SMAs). Replaces the need for chart screenshots.

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
**2026-06-30 (Mon — management session, new pacing week)** — Fresh sync (web_api authed, OPRA live): NLV **$67.0k**, excess liq $32.2k / avail $28.5k (above floors), VIX 17.7 bearish, pacing **0/5**, cluster **91.6%** (GOOGL 26.3 / MSFT 21.2 / AMZN 20.5). ⚠ Risk drift: **β-Δ jumped to ~337** (from 220) and **theta to +216** (MSFT same-strike out-roll loaded short-call premium) — book running long-delta into a bearish tape; **β-vega still net_long** (flagged). Open-position unrealized **−$18.5k**, still ~all long tech LEAPs (MSFT −4.1k, GOOGL −3.0k, NVDA −2.7k, AMZN −1.9k, AAPL −1.7k); income side green (AMD/ARM +) and **MU recovered above 1100** (spot 1139, PCS healing), ARM safe. **Trades (all filled + journaled):** MSFT short 375C×2 rolled Sep18→Oct16 same-strike **+$4.19 cr** (harvest; kept tight cap on the broken name — spot $370 < 200SMA $445; LEAP trim still waits for a **395–410 bounce**, alert `8bd4926b` live); SPY hedge **+1 Sep18 700/650** debit $5.18 (duration top-up through CPI/FOMC); AMZN short rolled Aug21 250C→Oct16 280C **$3.22 debit** (Δ0.44→0.26, healthy name, delta relief); GOOGL short rolled Sep18 375C→Oct16 375C same-strike **+$4.00 cr** (kept tight cap on the 26% line, deliberately no up-roll). ⚠ AMZN combo first-built with **legs inverted** (would've doubled the short) — caught pre-submit; rule: roll = BUY-to-close front short + SELL-to-open back leg. **MAR Jul31 350/340 PCS abandoned** — credit evaporated into illiquid puts (live combo mid ~breakeven). **OST: ignore from now (user directive).** Realized −$535 = cost of closing the two front shorts. **No code changes.** Carryover: trim MSFT on a bounce; watch β-Δ / β-vega drift.

**2026-06-29 (Sprint 20.3 — close-confirmed conditional alerts, code-complete)** — Built the last open Sprint 20 item. Pulled the two out-of-mount files into OneDrive (Sprint 0 pattern): `app/routes/conditional_alerts.py` → `route_conditional_alerts.py`, `app/scheduler/runner.py` → `sched_runner.py`. Added `close_above`/`close_below` alert types: the intraday `/evaluate` pass now **skips** close-types (no more wick false-fires), and a new `POST /conditional-alerts/evaluate-close` evaluates them against the official daily close via `_daily_close()` (yfinance settled bar, not `chain.get_spot`), stamping `last_close`/`triggered_close` for audit. Scheduler gained an in-process `_evaluate_close_alerts()` + one daily `close_alert_eval` cron at **21:15 UTC** (post-close in EDT *and* EST — no seasonal edit), gated/tuned by new `alerts.close_eval_enabled/utc_hour/utc_minute` config. MCP: new `evaluate_close_alerts()` tool + updated `add_conditional_alert` docs. Wired both files into `deploy_data_sources.sh` ROUTE_FILES + `sync_check.sh` MAP; backlog 20.3 + Active-Alerts row updated. ⏳ **NOT yet deployed** — this session's sandbox can't reach WSL; user runs `deploy_data_sources.sh` (compiles both + rollback) → MCP relaunch → verify by converting MSFT `8bd4926b` to `close_below 375` + `evaluate_close_alerts` → `sync_check.sh` all-green → commit `fortress-v4-api` + `fortress-mcp`. Follow-up (small): Parapet alert-type dropdown + settings-schema rows for the new config keys.

**2026-06-27 (cont. — Sprint 20 execution: 5 of 6 shipped)** — Worked Sprint 20 end-to-end with deploy/verify/commit each: **20.1** journal 422 fixed (prose-tolerant schema; `app/routes/journal.py` pulled into mount); **20.2** pacing — found+fixed an *active* bug (per-briefing snapshot capture's non-atomic write was collapsing the position-diff store → silent 0/5; now atomic write + guarded load + `position_diff_reason`); **20.4** cluster-% canonical basis = market_value/NetLiq (`cluster.basis` label; both live reads agree); **20.5** `hedge-coverage-drift-alert` scheduled task (weekday 09:03; 🔴 on `coverage_ok=false`); **20.6 = 19.1** β-weighted vega in the briefing (`greeks.beta_weighted_vega` −421.7 + `beta_vega_flag`; recovery dashboard surfaces it). Commits: fortress-v4-api `f4eda5f`/`703fbd6`/`17376b6`/`2392060`/`31927e4`, fortress-parapet `5ca72d4`. All verified live, sync_check all-green. **Only 20.3 (close-confirmed alert type) remains** — deferred: its eval logic is out-of-mount (needs the conditional-alerts route + scheduler `alert_eval` pulled in, like journal.py) and it needs a new EOD close-evaluation pass. ⚠ Carryover to commit when convenient: `data/trade_outcomes.json`, `quant/conditional_alerts.json`. ⚠ Click **Run now** once on `hedge-coverage-drift-alert` to pre-approve its tool.

**2026-06-27** — Session-OPEN + tooling/workflow review (no trades, no backend code). Ran the OPEN checklist with a forced `trigger_ibkr_sync` first (staleness 0.0h after): NLV **$64,813**, liq $26.1k/$29.4k above floors, β-Δ **210** (raw 385, Θ +7.3, **vega +1,050 — flipped long** vs −374 earlier), VIX 18.4/bearish, pacing 5/5, cluster **91.2%**. Signals unanimous on **MSFT** (alert TRIGGERED + roll URGENT Δ0.54 + stop ACT_IMMEDIATELY; spot $372) — plan-consistent move is the short-leg gamma roll, LEAP trim waits for a 395–410 bounce. SPY hedge still **$3.0k vs $20k floor**. **Reviewed the full toolkit**, then shipped the two no-code improvements: (1) **hardened `daily-post-open-briefing`** scheduled task — force-sync first + staleness>2h guard (closes the 06-26 18.8h-stale trap), refreshed stale watch items (META/AMD removed), added hedge-coverage + cluster-glide + β-vega-flag steps; (2) built **`fortress-recovery-dashboard`** live Cowork artifact (NLV/liq, cluster glide, β-Δ/greeks, hedge coverage, alerts, rolls, stops — refreshes from Fortress each open). Everything needing code → **new Sprint 20** in `BACKLOG_SPRINT_PLAN.md` (20.1 journal-422 fix [top], 20.2 pacing manual-fill, 20.3 close-confirmed alerts, 20.4 single cluster basis, 20.5 hedge-drift alert, 20.6 β-vega). Updated OPEN checklist + Current State here. Full detail → `SESSION_LOG.md`.

**2026-06-26** — Management + strategy session (NLV ~$65k, bearish/VIX ~19). **First `get_briefing` was 18.8h STALE** (showed pre-06-25 book); `trigger_ibkr_sync` fixed it — always re-sync if staleness >2h. **Trades:** closed **V Jul17 300/295 ×4** (~+$272, 87%); **rolled MSFT 390→375C ×2** (+$1,200 cr, 2nd de-risk tranche down); **AMD Jun26 380/375** left to lapse (~+$131). **Housekeeping:** logged SPY (+$1,724) & META (−$235) to outcomes store (n=4); deleted moot META alert 320fc5ae. **Built `REVISED_RECOVERY_STRATEGY_2026-06-26.md`** — loss attribution (100% long-tech LEAPs + dead OST; engine green), 5-pillar recovery (de-concentrate 93%→60%, PMCC the dead LEAP capital, diversify income OUT of tech, re-fund the under-sized SPY hedge $2.9k→$20k, no averaging-down). **Reviewed tech LEAP charts** → trim priority flipped: **MSFT** is the broken name to cut (into 395–410 bounce), **GOOGL** strongest (hold/trim into strength), AMZN/NVDA/AAPL = keep + write calls into resistance. **Pending Monday:** close OST, re-fund hedge ahead of NFP Jul 2, one non-tech PCS (pacing resets). Need SPY/QQQ + ELV/GE/MAR/LLY/VST charts. **No code changes.** ⚠ journal 422 still unfixed. Full detail → `SESSION_LOG.md`.

