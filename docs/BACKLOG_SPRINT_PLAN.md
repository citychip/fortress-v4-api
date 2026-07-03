# Fortress — Backlog Sprint Plan
**Created 2026-06-19 · Source: HANDOFF optimization backlog (06-18 review) + Catalyst Gate §6 follow-ups + Journal Feedback §6 follow-ups.**
Parapet UI sprints are at 13; these are **system/backend sprints** numbered 15→17 (Sprint 14 = the already-shipped catalyst-gate work).

---

## ✅ Sprint 0 — Unblock (DONE 2026-06-19)
Four high-value items touch routes that lived **outside the OneDrive repo mount** (`pretrade_check`, `regime`, `strategy_metrics`, `pacing`). Now pulled in, drift-tracked, and deployable.

- [x] **Pulled the out-of-mount route/service files into OneDrive** via `sprint0_pull_routes.sh` (discovers owners by grep, copies, compile-checks, writes `sprint0_manifest.txt`). Curated the broad grep down to the 7 real owners; dropped `ibkr_web/__init__.py` (its "pacing" = httpx rate-limit, false positive).
- [x] **Registered in `sync_check.sh` `MAP`** (drift-tracked) and **`deploy_data_sources.sh` `ROUTE_FILES`** block (self-contained backup → copy → compile-check → rollback; doesn't touch the chain.py/options_analytics logic).
- **7 files mirrored** (OneDrive ↔ repo):
  | File | Repo path | Backs item |
  |---|---|---|
  | `options.py` | `app/routes/options.py` | 15.1 strategy_metrics (`/options/strategy_metrics`) |
  | `manage.py` | `app/routes/manage.py` | 16.1 pretrade (`/manage/pretrade_all`) |
  | `market_intelligence.py` | `app/routes/market_intelligence.py` | 15.3 regime synthesis (`_synthesize_regime`) |
  | `briefing.py` | `app/routes/briefing.py` | 16.5 pacing (`compute_pacing`) |
  | `config_store.py` | `app/services/config_store.py` | 15.3/16.5 defaults (VIX thresholds, pacing cap) |
  | `state.py` | `app/services/state.py` | 15.3 macro-regime parse |
  | `settings.py` | `app/routes/settings.py` | 16.5/Catalyst #80 settings schema |
- **Remaining (user, in WSL):** (1) gitignore `*.pre-sprint0-bak` in `~/fortress-v4-api` (same policy as `*.pre-ibkr-bak`); (2) run `bash sync_check.sh` to confirm all 7 read "✓ in sync"; (3) commit the newly-tracked files at session wrap. **Unblocks 15.1 · 15.3 · 16.1 · 16.5.**

---

## Sprint 15 — "Trust the pre-trade read" (data-source truth)
**Goal:** every number that gates a trade is live, not placeholder. Highest leverage — these are the numbers most likely to cause a bad entry.

| # | Item | File | Effort | Dep |
|---|---|---|---|---|
| 15.1 | ✅ **DONE + VERIFIED LIVE (2026-06-19)** — `strategy_metrics` on real vol. IV/IVR now from `get_iv_rank` (IBKR-first), DTE from `state.days_to_earnings`; added `vol_source`. Root cause was a double bug: import from `app.routes.market` (wrong module → throws) AND intel never emitted `current_iv`/`iv_rank`/`days_to_earnings`, so every call fell to IV30/IVR50/DTE999. Regime left at neutral fallback → 15.3. **Deployed + verified:** AAPL `vol_source=bs_inversion`, ivr 66.8 == iv-rank 66.8, iv 26.2 ≈ current_iv 26.21, DTE 41 (real). | `options.py` | M | Sprint 0 ✅ |
| 15.2 | ✅ **DONE + VERIFIED LIVE (2026-06-20)** — `check_liquidity` ATM-clustering fix. Attaches a BS delta to every strike, grades the ~0.20Δ short legs via `_spread_grade`, bases `liquidity_grade` on the OTM tradeable zone (\|Δ\|≤0.35) so tight ATM strikes can't inflate it. New fields: `short_leg{put,call}`, `tradeable_spread_pct`/`tradeable_status`, `grade_basis`, per-strike `delta`. Band 15%→20%, IBKR strikes 24→32. Graceful fallback when IV/delta unavailable. **Verified:** AAPL grade D (`otm_tradeable`); short call Δ0.18 $320 = 15.1% **wide** (old `atm_spread_pct` masked it at 8.9%). | `options_analytics.py` | M | — |
| 15.3 | ✅ **DONE (2026-06-21, needs deploy) — `get_vix_term` wired into the regime read.** `_synthesize_regime` now takes the `get_vix_term()` payload and adds a VIX-term signal: contango +1 (calm, premium-selling favored), flat 0, backwardation **−2** (term inversion / stress) so it can flip an otherwise neutral/mildly-bullish read bearish on its own; regime payload now carries a `vix_term` field. `strategy_metrics` no longer hardcodes neutral — it reads the synthesized `overall` (now incl. VIX term) via `get_market_intelligence` (correct module `app.routes.market_intelligence`) and **normalizes** granular labels ("Strongly/Mildly Bullish/Bearish") → canonical bullish/bearish/neutral so `regime_score` matches; also sets `gex_regime` from `gamma_regime` and exposes `regime_source`/`vix_term_state`. Config thresholds added (`vix_term_contango_ratio` 0.95 / `vix_term_backwardation_ratio` 1.00). **Verified** standalone (backwardation +3→+1, contango +1, flat 0, error→None; all 9 label cases map). ⚠ **Needs deploy** (`deploy_data_sources.sh`); no MCP change (proxies flow through). Finding: `scenario_estimate` still imports the wrong module (`app.routes.market`) → left for 16.x. | `market_intelligence.py` + `options.py` + `config_store.py` | S | Sprint 0 ✅ |
| 15.4 | ✅ **DONE + VERIFIED LIVE (2026-06-20)** — ex-div assignment-risk gate. Claude-curated store (`get_ex_div`/`set_ex_div_events`, same pattern as macro_events) cross-references the **live short-call legs**: ITM+ex-div≤expiry = `high`, near-ITM = `watch`; deep-OTM/non-dividend never flag. Backend routes + MCP tools + NaN smoke-test. **Verified:** 4 synthetic cases + live (seeded MSFT ex-div 08-20 → correctly NO risk, as 490/510C are deep OTM). Parapet chip = follow-up. | `options_analytics.py` + MCP | S | — |

**Acceptance:** `strategy_metrics` output reprices within tolerance of a manual `get_iv_rank` + chain check on 2 tickers · `check_liquidity` returns a sane grade for an OTM strike, not just ATM · regime payload carries a `vix_term` field that flips the read on a backwardation day · a name with an ex-div inside a short-call expiry shows the risk chip.

---

## Sprint 16 — "Consolidate + close the feedback loop"
**Goal:** one pre-trade gate that sees everything; the trade-outcomes loop actually accrues data.
**Status: ✅ DEPLOYED + verified live 2026-06-21 (backend + MCP v4.10.0 + Parapet UI). Keystone pivoted from the /trades feed to POSITION-DIFF (see note). Remaining: commit at wrap; position-diff pacing goes live once ≥2 daily snapshots exist (auto via briefing).**

> **Keystone design note (2026-06-21):** The planned IBKR executions reader (`/iserver/account/trades`) proved unusable — the CP Gateway feed is **session-scoped** and returned `[]` for a window with known June 18/20 fills (verified live). Pivoted to a **position-diff detector**: a daily snapshot of the IBKR-synced leg book (`state.get_active_positions`, which the sync updates with manual fills too), diffed per ticker on net SHORT-leg count. Rolls net to zero, SPY hedge excluded. Daily granularity, driven by the existing scheduled briefing. The `/trades` reader is retained as inspection/enrichment only (`/api/ibkr/fills`).

| # | Item | File | Effort | Dep |
|---|---|---|---|---|
| 16.1 | ✅ **DONE + DEPLOYED (incl. Parapet caution UI)** — consolidated **advisory layer** in `pre_trade_check` + `pretrade_all`: `macro_defer` (get_macro_events.defer_advisory), `vix_term` (amber on backwardation), `ex_div` (ticker-filtered assignment_risks). Kept **separate from the 5 hard gates** — never changes PROCEED/BLOCKED, only raises `caution`/`caution_flags`. Each source soft-fails to `unknown`. Batch endpoint fetches market-wide advisories once (`_market_advisories`) + per-ticker ex-div. Verified standalone. **Parapet UI shipped:** market-wide amber banner (macro_defer/vix_term) on Candidates+Triage + per-row `⚠ EX-DIV` chip in the Candidates gate cell. | `manage.py` + `fortress-parapet` | M | Sprint 0, 15.3, 15.4 |
| 16.2 | ✅ **DONE + DEPLOYED** — entry-condition capture (+ first-snapshot guard so the existing book isn't back-filled with today's values): on a position-diff OPEN of a short option leg, snapshot IVR/current-IV/DTE/short-delta (BS) into `entry_conditions.json` keyed by opra. `log_trade_outcome` auto-reads it at CLOSE (oldest-open per ticker, consume-on-use) to populate `*_at_entry` when not supplied — caller values always win. Verified standalone. | `options_analytics.py` + MCP | M | keystone |
| 16.3 | ✅ **DONE** — schema already had `ivr_at_entry`/`dte_at_entry`/`short_delta_at_entry`/`days_held`/`exit_reason` in `_OUTCOME_FIELDS`; the gap was *population* (16.2). `journal_analytics.py` bucketing now has a feed. | `trade_outcomes.json` + analytics | S | 16.2 |
| 16.4 | ⏳ **Ready (user action — needs live writes-enabled MCP)** — going forward 16.2 auto-accrues. For immediate buckets, optionally re-log the 2 known closes with *estimated* entry conditions (commands in HANDOFF). | manual + MCP | S | 16.3 |
| 16.5 | ✅ **DONE + DEPLOYED** (goes live once ≥2 daily snapshots exist) — `compute_pacing` reconciles against the position-diff (`weekly_position_opens`): prefers it when ≥2 snapshots exist (authoritative — catches manual fills), else falls back to journal-only (no regression). Returns `source`/`journal_used`/`position_diff_used`. `get_briefing` triggers an idempotent **daily snapshot** so history accrues with no extra scheduler. Verified standalone. | `briefing.py` + `options_analytics.py` | M | keystone |
| 16.6 | ✅ **DONE + DEPLOYED** (verified: regime `signals` → `['Macro','VIXTerm']`) — `_synthesize_regime` now appends a `{"source":"Macro",...}` entry to `signals[]` alongside the score adjustment, so the array sums to `score`. Verified standalone. | `market_intelligence.py` | S | - |

**Acceptance:** a freshly filled order auto-creates a trade-outcomes record with entry IVR/DTE/delta populated · `journal_analytics.py` prints expectancy by IVR/DTE/delta bucket on ≥1 seeded bucket · pacing reflects a manually-entered IBKR fill · `pretrade_check` shows the consolidated macro/vix/exdiv sub-flags.

---

## Sprint 17 — Automation + polish (lower urgency)

| # | Item | Effort | Notes |
|---|---|---|---|
| 17.1 | ✅ **DONE (2026-06-21)** — two weekly scheduled tasks created: **`weekly-macro-calendar-refresh`** (Sun 18:00 local; pulls FRED/FMP calendar → `set_macro_events`) + **`weekly-journal-analytics`** (Sat 10:00 local; expectancy/win-rate by IVR/DTE/delta bucket via `get_trade_outcomes`). | S | Scheduler tasks, no deploy. journal report now has a feed thanks to 16.2 auto-capture. |
| 17.2 | ✅ **DONE (2026-06-21)** — **`defer-advisory-premarket-check`** (weekday 13:30 local) reads `get_macro_events`, alerts 🔴 when `defer_advisory` true / 🟢 when clear. **Scheduled task, NOT a conditional alert** — defer is date-based and conditional alerts false-fire on intraday wicks. | S | Catalyst §6 #5 |
| 17.3 | ✅ **DONE (2026-06-22, needs deploy)** — new `catalyst` config section (`defer_days`, `news_spike_cooldown_days`) in `config_store`; SCHEMA + KNOWN_SECTIONS + Parapet SECTION_META ('Catalyst Gate' panel) entries → editable in System > Settings > Config. `get_macro_events` (backend route + MCP) now reads `cfg("catalyst.defer_days")` when no explicit override (None-default); explicit param still overrides. **Bonus fix:** the Config-tab save was fully broken (frontend `updateSettings` sent `PATCH` + flat body vs backend `PUT` + `{values:…}`) — fixed `api.ts` to `PUT`+wrapped, so ALL config sections are now editable. | S | Catalyst §6 #1 |
| 17.4 | ✅ **DONE (2026-06-22, needs deploy)** — per-ticker news-spike cooldown indicator. Backend `GET /api/market/news/{ticker}` + `GET /api/market/news` (all) + `POST` setter — Claude-curated store (`data/ticker_news.json`, same pattern as macro_events/ex_div since the backend has no FMP creds) computing `days_since` + `cooldown_active` from `cfg("catalyst.news_spike_cooldown_days")`. MCP: `get_ticker_news`/`get_all_ticker_news`/`set_ticker_news` (v4.11.0). Parapet `📰 {n}d` chip on Candidates (gate cell) + Triage (roll-table ticker), amber when in cooldown. Core logic unit-tested (6 cases). "Indicator, not a reader" as specced. QuantData→FMP sourcing is Claude-side via MCP into the store (consistent with §4 curated pattern). | M | Catalyst §6 #3; operationalizes the §4 cooldown |
| 17.5 | ✅ **DONE (2026-06-22, verification)** — confirmed ZERO Massive/Polygon import across all backend `.py` (only the unrelated "massive DP floor" descriptive string). No paywalled Massive options dependency exists; Massive stays MCP-side GEX/skew fallback only. No code change needed. | S | Cleanup; massive stays only as a GEX/skew fallback |
| 17.6 | 🟡 **DOCUMENTED (2026-06-22) — tool gated** — LunarCrush MCP is connected (tools: `topic`/`stocks`/`keyword_posts`/etc.) but social data is **subscription-gated** (free tier returns "Subscription required"). Situational Claude-side workflow documented (consult `topic($TICKER)` galaxy_score/alt_rank/sentiment before sizing retail-driven names like MSTR); activate by upgrading the LunarCrush plan when needed. No code artifact (Claude-side only, as scoped). | M | Lowest priority; Claude-side only, retail-driven names (MSTR-type) |

---

## Sprint 18 — Bug fixes (found in live use)

| # | Item | File | Effort | Notes |
|---|---|---|---|---|
| 18.1 | ✅ **FIXED 2026-06-22 (needs deploy) — candidate scanner now IBKR-first.** Root cause: `get_atm_iv` read yfinance's raw `impliedVolatility` column (placeholder junk ~1e-5..0.03 on the delayed feed) with NO band guard → every `current_iv` ~0% → every IV-HV spread bogus-negative → all rows `POOR SPREAD`. The DATA_SOURCES claim "yfinance IV column eliminated from ALL paths since v1.1" was inaccurate — this scanner was the surviving exception (missed by v1.1 + 15.1). **Fix:** new `_backend_iv_rank()` sources IV + IVR from the backend `/api/options/iv-rank` route (iv_source: ibkr → BS-inversion → hv_proxy — same canonical path as `get_iv_rank`); the yfinance chain is now a BAND-GUARDED fallback (`_yf_atm_iv`, rejects sub-4%/over-500% as junk); `get_iv_rank` skips a ticker rather than emit junk; a `MIN_SANE_IV_PCT=4.0` floor + a loud `iv_degraded` banner (stdout + report blockquote) make the failure impossible to miss. Repro that triggered it: scanner MSFT `IVR 0/IV 0.4%` vs `get_iv_rank(MSFT)` `IVR 48.6/IV 29.5%` same session. Wired into `deploy_data_sources.sh` (compile-check + rollback) and `sync_check.sh` MAP (was untracked). Syntax + guard logic unit-tested. | `workflow_05_iv_crush_report.py` | M | DONE — verify post-deploy via `refresh_iv_data` (expect real IVR, not all-zero) |
| 18.2 | ✅ **FIXED 2026-06-22 (needs deploy) — shared IBKR-first IV module.** `workflow_01_premarket_scanner.py` had the SAME raw-IV-column bug (lines 33-36, unguarded ×100). Rather than duplicate the 18.1 fix, factored the IBKR-first helpers into **`quant/iv_source.py`** (one source of truth: `backend_iv_rank`/`prefetch_backend_iv`/`yf_atm_iv`/`get_atm_iv` + the 4–500% sane band) — BOTH scanners now import it via a `sys.path` bootstrap (`from iv_source import …`), so they can't drift apart again (that drift is exactly how 18.1/18.2 happened). workflow_05 refactored to import the shared module too (removed its inline copies). Wired `iv_source.py` + workflow_01 into `deploy_data_sources.sh` (copied before the scanners so the sibling import resolves; compile-check + rollback) and `sync_check.sh` MAP. iv_source compiles; import wiring + guard/concurrency logic unit-tested. | `quant/iv_source.py` (new) + both scanners | S | DONE |
| 18.3 | ✅ **FIXED 2026-06-22 (needs deploy) — signal parser.** `state.parse_crush_report_markdown` read `cols[7]` as signal, but the scanner emits 9 cols (Conc Risk before Signal) → every candidate signal silently rendered `-`. Now reads `cols[-1]` (last column), correct for both the 8-col (legacy) and 9-col layouts. Regression-tested on both layouts incl. a BLOCKED row. | `state.py` parser | S | DONE — verify post-deploy that candidate `signal` populates |

## Sprint 19 — Strategy enhancements (research-codified 2026-06-22)
**Source: `IMPROVEMENT_RESEARCH_2026-06-22.md` + `STRATEGY_ENHANCEMENTS_v3_10.md`. Config keys already added to `config_store.strategy.*` (advisory/informational — no live behaviour change yet).**

| # | Item | File(s) | Effort | Notes |
|---|---|---|---|---|
| 19.1 | ✅ **DONE + VERIFIED LIVE (2026-06-27, via Sprint 20.6)** — β-weighted vega shipped in the briefing. `state.compute_beta_weighted_vega` + `beta_weighted_vega`/`beta_vega_target`/`beta_vega_flag` in `get_briefing.greeks`; recovery-dashboard artifact surfaces it with a net-long-vega flag. Verified: raw −355.6 → β-vega −421.7, flag `net_short_vega`. SPY-hedge-sizing cross-check + Parapet chip remain as small follow-ups. See Sprint 20.6 row for detail. | `briefing.py`/`state.py` + artifact | M | DONE |
| 19.2 | ✅ **DONE + verified live 2026-06-23** — `get_briefing.concentration.cluster` sums `cfg("strategy.mag7_cluster")` long exposure; warns > `cluster_concentration_warn_pct`. Live: cluster **74.3%** of NLV vs 25% top single-name. Parapet chip = small follow-up. | `briefing.py` | S | — |
| 19.3 | ✅ **DONE + verified live 2026-06-23** — scanner `classify_signal` reads `cfg("strategy.vrp_good/fair_spread_pp")`; `pre_trade_check.advisories.vrp` flags amber when IV−HV < `vrp_min_entry_pp` (soft-fails to `unknown` "run refresh_iv_data" with no fresh scan). | `workflow_05` + `manage.py` | S | — |
| 19.4 | 🟡 **PARTIAL** — ✅ **19.4a** `/api/options/pmcc-breakeven` guardrail (short must clear long breakeven, else GUARANTEED-LOSS) deployed + unit-tested. 🔴 **19.4b** delta-based LEAP-roll alert (`leap_roll_delta` 0.70 / `leap_roll_dte` 120) DEFERRED — needs per-leg greeks not in the aggregated position rows. MCP wrapper for pmcc-breakeven pending next relaunch. | `options_analytics.py` (+ `manage.py`/alerts for 19.4b) | M | — |
| 19.5 | **Expected-move bands** — 1SD (16Δ) expected-move band per candidate for strike selection. | `options_analytics.py` + Parapet Candidates | M | Generalizes the earnings implied-move you already have |
| 19.6 | **Payoff / what-if slider** — interactive payoff diagram (price × IV × time) on Positions; backend `forward_pnl`/`scenario_estimate` mostly exists. | Parapet Positions | M | Surfaces existing backend |
| 19.7 | ✅ **DECISION (2026-06-23): keep 80%** — `journal_analytics.py` has only 2 closed records, both *defensive* closes (unrepresentative). Not a basis to change `profit_target_pct`. Revisit once Sprint-16 entry-capture accrues representative closes (bucketing also blocked until entries carry ivr/dte/delta_at_entry). | settings + journal | S | `profit_target_pct_recommended = 50` recorded |

**Sequencing:** 19.1 (β-vega) + 19.2 (cluster) first — both speak directly to the concentrated, short-vega book and hedge sizing. Then 19.3/19.4 (cheap, codified). 19.5/19.6 are polish. 19.7 is a data decision, not code.

## Sprint 20 — Workflow hardening & feedback-loop repair (added 2026-06-27)
**Source: 2026-06-27 tooling/workflow review. These are the gaps that break the *workflow* (not the strategy): broken feedback pipes, manual-step traps, and reads that can silently lie. Sequenced by leverage — the journal fix is top because it starves every analytics loop.**

| # | Item | File(s) | Effort | Notes |
|---|---|---|---|---|
| 20.1 | ✅ **DONE + VERIFIED LIVE (2026-06-27)** — journal 422 fixed. **Two root causes, not one:** (1) the MCP `add_journal_entry` sends a **lowercase** `action` (`observe`/`open`/`adjust`…) but `JournalEntryCreate` enforced `pattern="^(OPEN\|CLOSE\|ROLL\|TRIM\|ADD\|NOTE)$"` → every MCP prose entry 422'd; (2) the Parapet note box (`SystemPage.tsx`) POSTed `{note,entry}` — none of the required `ticker`/`action`/`description` → 422 too; and the prose fields (`reasoning`/`framework_rules`/`outcome`/`tags`) weren't in the model so even successful entries dropped them. **Fix (backend-accepts-prose):** rewrote the model tolerant — `@field_validator` normalizes `action` case-insensitively + maps aliases (`observe`/`adjust` kept, unknown→`NOTE`), defaults `action`→`NOTE` & `ticker`→`GENERAL`, a `@model_validator(before)` coalesces `description` from `note`/`entry`/`text`, and it now **accepts + persists** `reasoning`/`framework_rules`/`outcome`/`tags`; NOTE/OBSERVE/`GENERAL` entries bypass the §3.4.4 universe gate. Hardened `SystemPage.tsx` to POST an explicit schema-valid body. **Pulled `app/routes/journal.py` into OneDrive** (Sprint 0 pattern) + wired into `deploy_data_sources.sh` ROUTE_FILES & `sync_check.sh` MAP. **Verified live:** the exact lowercase-`observe` prose body that 422'd now returns 201 (id `742a3c9b`, action normalized `OBSERVE`) and reads back with `reasoning`/`framework_rules` intact. Un-skews the n=4 → unblocks 19.7. | `app/routes/journal.py` + `fortress-parapet` `SystemPage.tsx` | M | DONE |
| 20.2 | ✅ **DONE + DEPLOYED (2026-06-27)** — verification surfaced an **active bug**, not just a doc-lag. Position-diff pacing *is* wired (16.5), and `get_position_opens` correctly reconciled this week's opens to **used:5** (NVDA/AAPL/ARM 06-23 + AMZN/MU 06-26; the 06-25 roll-downs correctly netted to zero), while `get_ibkr_fills` is empty as designed (session-scoped, inspection-only). **BUT** a single `get_briefing` collapsed the snapshot store to <2 → pacing silently fell back to `journal_only` (0/5). **Root cause:** `capture_position_snapshot` (fired every briefing) did a **non-atomic write**, and `_load_position_snapshots` returned empty on *any* read error, so a concurrent/truncated read let the next capture **overwrite real history with one fresh snapshot** (reproduced live: capture returned all-24-legs-`opened`/`prior=None`). **Fix:** atomic writes (`tmp`+`os.replace`+`fsync`); guarded load that distinguishes absent-file from corrupt and sets `_load_error`; capture refuses to clobber on `_load_error` (moves the corrupt file aside once to self-heal); `compute_pacing` now exposes `position_diff_reason` so a fallback is never silent. **Verified live:** new `position_diff_reason` field present in briefing; atomic capture returns `captured:true`. ⏳ Full count re-verification (position-diff reads 5/5 again) accrues once ≥2 distinct-day snapshots exist — Mon 06-29 (pacing resets then anyway). | `options_analytics.py` + `briefing.py` | S→M | DONE |
| 20.3 | ✅ **CODE-COMPLETE 2026-06-29 (needs deploy + live-verify)** — close-confirmed alert type. Pulled the two out-of-mount files into OneDrive (Sprint 0 pattern): `app/routes/conditional_alerts.py` → `route_conditional_alerts.py`, `app/scheduler/runner.py` → `sched_runner.py`. **Route:** added `close_above`/`close_below` to the `AlertType` Literal; the intraday `/evaluate` pass now **skips** them (so spot wicks can't fire a close rule); new `_daily_close()` (yfinance settled daily bar, NOT `chain.get_spot`) + `POST /conditional-alerts/evaluate-close` evaluates close_* against the official daily close, stamping `last_close`/`last_close_date` (audit) and `triggered_close`/`triggered_close_date` on fire. **Scheduler:** new in-process `_evaluate_close_alerts()` + one daily `close_alert_eval` cron at **21:15 UTC** (post-close in BOTH EDT 17:15 ET and EST 16:15 ET — no seasonal edit), gated on `alerts.close_eval_enabled`, time from `alerts.close_eval_utc_hour/minute`; surfaced in `get_status()`. **Config:** `alerts.close_eval_enabled/utc_hour/utc_minute` added. **MCP:** `add_conditional_alert` docstring lists the new types; new `evaluate_close_alerts()` tool (POST /evaluate-close). Wired both new files into `deploy_data_sources.sh` ROUTE_FILES + `sync_check.sh` MAP. ⏳ Deploy (`deploy_data_sources.sh` compile-checks both + rollback) → MCP relaunch → verify live by converting MSFT `8bd4926b` to `close_below 375` and running `evaluate_close_alerts`. Removes the recurring manual OPEN-checklist close-confirmation step. Follow-up (small): Parapet alert-type dropdown + settings-schema UI rows for the new config keys. | `app/routes/conditional_alerts.py` + `app/scheduler/runner.py` + `config_store` + MCP | M | Directly removes a recurring manual OPEN-checklist step. |
| 20.4 | ✅ **DONE (2026-06-27)** — CANONICAL basis declared = **market_value / NetLiq** (what `state.compute_concentration` emits and `get_briefing.concentration` returns; the denominator the §7 caps + 60% cluster-warn are calibrated to). The cluster block now carries `basis: "market_value_pct_of_netliq"` so nothing recomputes it differently. **Verified both live reads already agree:** the `fortress-recovery-dashboard` artifact reads `b.concentration.cluster` straight from the briefing (renders "% of NLV") — no separate recompute, no edit needed. The old ~93% was cluster MV / total-position MV (drops cash) from the 06-26 manual recovery analysis — documented as NOT the source of truth. HANDOFF Current-State note reconciled. | `briefing.py` + docs | S | DONE |
| 20.5 | ✅ **DONE (2026-06-27)** — created the **`hedge-coverage-drift-alert`** scheduled task (weekday 09:03 local; cron `0 9 * * 1-5`). Calls `get_spy_hedge_coverage`, emits a 🔴 when `coverage_ok=false` (shows hedge $, % NLV, gap to the $20k floor + the §2.D put-spread rebuild action) / 🟢 when within the $20–30k band; soft-fails to a ⚠️ skip if the IBKR gateway is down (checks `get_ibkr_status`). Chosen as a **scheduled poll, not a conditional alert** — coverage is a slow metric, and `price_*` conditional alerts false-fire on intraday wicks (cf. 20.3). Claude-side task, no backend code. **Verified against live data:** `coverage_ok:false`, $3,018 vs $20k → fires 🔴 (gap ≈$16,982). ⚠ User: click **Run now** once to pre-approve the Fortress MCP tool so future runs don't pause on the permission prompt. | scheduled task | S | DONE |
| 20.6 | ✅ **DONE + VERIFIED LIVE (2026-06-27)** — β-weighted vega in the briefing (= 19.1). New `state.compute_beta_weighted_vega` scales each leg's dollar-vega (`qty×current_vega×mult`) by the name's SPY beta (price-beta as a documented IV-sensitivity proxy) → SPY-IV-equivalent $/vol-pt; `compute_portfolio_greeks_with_beta` adds `beta_weighted_vega`, `beta_vega_target` (`cfg("strategy.beta_vega_target")`), and `beta_vega_flag` (`net_long_vega`/`net_short_vega`/`flat`) — the last is the blind-spot catcher (a premium-selling book is normally net-short; a long flip is the unflagged risk). Flows through `get_briefing.greeks` (no MCP change). Recovery-dashboard artifact updated: real β-Vega row + a 🔴 flag on `net_long_vega` (replaced the "no β-vega stat yet" placeholder). **Verified live:** raw vega −355.6 → β-vega **−421.7** (betas>1 amplify), flag `net_short_vega`. ⚠ Parapet greeks chip = small follow-up. | `state.py` + `briefing.py` + artifact | M | DONE |

**Done this session without code (2026-06-27):** hardened the `daily-post-open-briefing` scheduled task (force `trigger_ibkr_sync` first + staleness>2h guard; refreshed stale watch items; added hedge-coverage + cluster-glide + β-vega-flag steps); built the **`fortress-recovery-dashboard`** live Cowork artifact (NLV/liq, cluster glide, β-Δ/greeks, hedge coverage, alerts, rolls, stops — refreshes from Fortress each open). Neither needed a backend change.

---

# Sprints 21–24 — Enhancement Proposal v1 (added 2026-07-02)
**Source: `Fortress_Enhancement_Proposal_v1.md` (session 2026-07-02) + `Fortress_MultiTimeframe_Procedure_v1_DRAFT.md`. Driven by live findings: the `strategy_metrics` covered-call/PMCC engine emits $0-credit far-OTM short strikes (root cause of 0.15–0.6× LEAP capital efficiency); `recommended=True` fires on 4–5 strategies at once; regime labels conflict (per-name bullish vs macro bearish vs SPY GEX negative); 25% win rate from selling premium on names below their 200-SMA; persona set to "directional/no-hedge" vs the live hedged-income book.**

### Already shipped — verify, do NOT re-plan
| Proposal item | Covered by | Status |
|---|---|---|
| Auto-capture entry IVR/DTE/delta | 16.2 / 16.3 | ✅ going forward (legacy trades uncaptured, acceptable) |
| β-weighted vega stat | 19.1 / 20.6 | ✅ live (vega-flip **alert** = new item 24.4) |
| Mag-7 cluster metric | 19.2 | ✅ live (glide-tracker UI = new item 23.6) |
| Concentration basis (MV/NLV) | 20.4 | ✅ canonical (hard-gate enforcement = new item 21.5) |
| Manage-at-50% decision | 19.7 | ⏸ kept 80%; revisit when entry-capture accrues (item 23.5) |

---

## Sprint 21 — "Monetize & gate" (strategy-metrics correctness) — HIGHEST LEVERAGE
**Goal:** the pre-trade strategy engine tells the truth and gates on trend + concentration. These are the fixes that most directly change P&L and win rate.

| # | Item | File(s) | Effort | Dep |
|---|---|---|---|---|
| 21.1 | ✅ **CODE-COMPLETE 2026-07-03 (needs deploy + live-verify)** — **21.1a** fixed the inverted call bisection in `target_strike_by_delta` (direction-aware bounds + 40→60 iters); offline harness confirms MSFT PMCC short **$780→$425**, GOOGL **$715→$395**, SPY **$1485→$770**, all non-zero credit; puts unchanged. **21.1b** added module-level `pick_short_call_delta(ivr, regime, weekly_below_200, days_to_earnings, conc_pct)` (base 0.30, clamp [0.20,0.40], IVR/trend/catalyst/concentration nudges + rationale) wired into PMCC + Diagonal short legs; concentration input via `state.compute_concentration` (soft-fail); `weekly_below_200` wired but None until 22.1. $0-credit sanity guard → `credit_ok`/`flags:["zero_credit"]`. Config keys added to `config_store.strategy.*` (`short_call_base/min/max_delta`, `delta_*_weight`, plus the 21.4/21.5 gate keys). Tests: `tests/test_sprint21_offline.py` (exit 0). | `options.py` + `config_store` | M | — |
| 21.2 | ✅ **CODE-COMPLETE 2026-07-03 (needs deploy + live-verify)** — added `annualized_yield` per strategy; rank by `(regime_score desc, annualized_yield desc)`; **exactly one** `recommended=True` that passes gates (credit_ok + earnings_safe today; trend/concentration gates attach when 22.1 lands); others carry `eligible`/`gate_reason`; new top-level `recommended_id`. Offline test confirms exactly one recommended per name. ⚠ Behavioral note: in a neutral regime the singular pick now often surfaces the Iron Condor (highest score×yield) — expected, but review against intent when live. | `options.py` | S | — |
| 21.3 | ✅ **CODE-COMPLETE 2026-07-03 (needs deploy + live-verify)** — `_synthesize_regime` now emits a single canonical `regime_gate {label, source, score, inputs[]}` (label = bullish/neutral/bearish from the score sum; inputs[] = every signal's source+label+score). `get_strategy_metrics` prefers `regime_gate.label` (sets `regime_source="regime_gate"`) and surfaces the gate object in its payload. Offline test `tests/test_sprint21_gates_offline.py` (exit 0). ⏳ **Follow-up:** wire `get_briefing.macro_regime` to read the same gate (currently a separate iv_report read) so the two can't diverge — left additive to avoid destabilizing the briefing macro path this pass. | `market_intelligence.py` + `options.py` | M | — |
| 21.4 | ✅ **CODE-COMPLETE 2026-07-03 (needs deploy + live-verify)** — trend-filter entry gate, warn-mode. Consumes 22.1's `weekly_trend_state`. In `strategy_metrics`: `trend_gate` payload field + when spot < weekly-200-SMA a bullish premium-sell gets `regime_score −2` + `trend_penalized`/`flags:["below_wk200"]` and `_passes_gates` returns `eligible=False, gate_reason="below_wk200"` (never removed). Also activates the 21.1b adaptive-delta trend nudge. In `manage._pretrade_advisories`: new `_trend_advisory` → amber below the weekly 200. Unknown history → no effect (soft-fail). Offline test extends `test_sprint21_offline.py` (21.4 section). | `options.py` + `manage.py` (+ 22.1) | M | 22.1 ✅ |
| 21.5 | ✅ **CODE-COMPLETE 2026-07-03 (needs deploy + live-verify)** — added a **warn-mode** `concentration` advisory to `manage._pretrade_advisories` (covers both `pre_trade_check` and `pretrade_all`/candidates). `_market_advisories` computes single-name % + Mag-7 cluster % once (canonical MV/NLV basis, Sprint 20.4); `_concentration_advisory` raises amber when the name is ≥ `single_name_cap_pct` (20) or a cluster member and the cluster is ≥ `cluster_cap_pct` (60). Never touches the 5 hard gates (PROCEED/BLOCKED intact) — config `concentration_gate_mode` can flip to block later. Offline test (exit 0). | `manage.py` | S–M | — |
| 21.6 | 🟡 **PARTIAL (21.6-lite) — CODE-COMPLETE 2026-07-03 (needs deploy).** Per user decision (2026-07-03): **kept persona `income_seeker`** (the change-list's `strategic_speculator` premise didn't match live). Aligned `active_strategies` to the real hedged-premium-seller book — `[PMCC, PCS, CASH_SECURED_PUT, COVERED_CALL, COLLAR, DIAGONAL, SPY_HEDGE, LEAPS]` (dropped JADE_LIZARD) in both `config_store` DEFAULTS + the `income_seeker` preset in `settings.py`. Hedge already on (`SPY_HEDGE` in set + `show_spy_hedge=True`). ⚠ **Runtime note:** DEFAULTS/preset edits only affect fresh/reset configs — if a persisted `active_strategies` override exists, apply via Settings UI or `update_settings_section`. **Not done:** schema-level 20% cap enforcement (deferred — the 21.5 warn-advisory covers the behavior). | `config_store` + `settings.py` | S | — |

**Acceptance:** `strategy_metrics` returns a covered-call/PMCC with a **non-zero credit** at its **adaptive delta** on all 6 core names, with a `delta_rationale` explaining any deviation from 0.30 · exactly one strategy per name carries `recommended=True` · regime payload exposes a single `regime_gate` + inputs · a name below its weekly 200-SMA is flagged ineligible/caution · a candidate breaching 20%/60% is blocked/warned · settings persona reads "hedged premium-seller".

### 21.1 — Adaptive short-call delta engine (design)
`pick_short_call_delta(ticker) → {target_delta, strike, credit, delta_rationale[]}`

- **Base anchor:** `strategy.short_call_base_delta` = **0.30**. Clamp final to `[short_call_delta_min 0.20, short_call_delta_max 0.40]`.
- **Signed nudges** (sum, then clamp; each logs a rationale line):
  - **IVR / VRP:** high IVR (rich premium) → nudge **lower** delta (reach target income further OTM, keep upside). Low IVR → nudge **higher**. (e.g. ±0.05 across IVR 30↔80.)
  - **Weekly trend / regime:** name in a healthy weekly uptrend (above 200-wk) → **lower** (protect upside). Broken / below weekly 200-wk (e.g. MSFT) → **higher** (more premium + more downside cushion, since the short call gains as it falls).
  - **Technical resistance anchor:** snap the strike to sit **at/above** the nearest overhead level (WMA62 / 52-wk high / GEX call wall) rather than a pure delta — cap where price is likely to stall, not mid-air.
  - **Catalyst proximity:** inside an earnings/high-impact window → **lower** delta (reduce gap risk) or defer per the catalyst gate.
  - **Concentration:** if the name is over-cap (>20%), bias **higher** — a closer short call also trims net delta (doubles as de-risk).
- **Output:** the chosen delta, the resolved strike + credit, and `delta_rationale[]` (why it moved off 0.30) so every pick is explainable in the briefing.
- **Config keys:** `short_call_base_delta`, `short_call_delta_min`, `short_call_delta_max`, and per-factor weights (`delta_ivr_weight`, `delta_trend_weight`, `delta_catalyst_weight`, `delta_concentration_weight`).

---

## Sprint 22 — "Multi-timeframe technical layer" (data + procedure + UI)
**Goal:** weekly/daily (and monthly/4h interactively) technicals are first-class inputs, with the data-source-availability rule made visible.

| # | Item | File(s) | Effort | Dep |
|---|---|---|---|---|
| 22.1 | 🟡 **CORE CODE-COMPLETE 2026-07-03 (needs deploy + MCP relaunch).** Built `options_analytics.weekly_trend_state(ticker)` — yfinance weekly-200-SMA read (`spot/sma_200w/above_200w/pct_from_sma/bars`, 6h TTL cache, soft-fail None on thin history) + route `GET /api/technical/gate` (`get_technical_gate`, SPY + open-position tickers, hold/watch/act/unknown) + MCP tool `get_technical_gate`. This is the ingest that unblocked 21.4 + the 21.1b trend nudge. ⏳ **Follow-up:** wire the per-name line into the `daily-post-open-briefing` SKILL output + add the daily-1d trend/key-level (weekly done; daily is the small remainder). Headless-safe, source-labeled. | `options_analytics.py` + MCP + `daily-post-open-briefing` task | M | — |
| 22.2 | **TradingView interactive integration** (Claude-side, documented in the Procedure): launch-with-debug command, dynamic watchlist, TN-signal read (Thesis Stop / WMA62 / Re-entry), graceful fallback to `get_chart_data`. Monthly + 4h are TV-only. | Procedure doc + Claude-side | S | — |
| 22.3 | **Data-source status banner (Parapet).** web_api vs `bs_yfinance` fallback, TradingView attached (y/n), last-sync age. Makes the availability rule visible; optionally gates write actions when on fallback (§Open). | `fortress-parapet` | M | — |
| 22.4 | **Multi-timeframe technical panel (Parapet).** Monthly/Weekly/Daily/4h with the 200-wk Thesis Stop line per name; ingest `get_chart_data` + TradingView. | `fortress-parapet` | M–L | 22.1 |
| 22.5 | **Backend interval extension (optional).** `get_chart_data` currently supports `1d`/`1wk` only; add `1mo` (and `4h` if feasible) so Monthly/intraday don't depend solely on TradingView. | `options_analytics.py`/chart route | M | — |

**Acceptance:** the automated briefing prints a weekly+daily technical line per watchlist name with an explicit source/fallback label · Parapet shows a live data-source banner · a multi-timeframe panel renders the Thesis Stop per name.

---

## Sprint 23 — "Capital efficiency & structures" (strategy optimization)
**Goal:** convert dead-weight LEAP capital into defended income; surface efficiency; diversify.

| # | Item | File(s) | Effort | Dep |
|---|---|---|---|---|
| 23.1 | **Capital-efficiency heatmap (Parapet).** Surface `get_capital_efficiency` per position (income ÷ capital-at-risk) to spotlight under-monetized LEAPs (GOOGL 0.25×, AMZN 0.15×). Data already exists. | `fortress-parapet` | S–M | — |
| 23.2 | **Collar / overlay builder.** One-click structure to sell a ~0.30Δ call + buy a protective put against a held LEAP (self-funding downside defense for the concentrated names). Backend structure + Parapet. | `options_analytics.py` + `fortress-parapet` | M | 21.1 |
| 23.3 | **Systematic LEAP call-writing playbook.** Monthly ~0.30Δ / 30–45 DTE covered calls on the LEAP cores (depends on 21.1 producing real strikes); codify in Strategy v3.10 + surface as candidates. | Strategy doc + `options.py` | S | 21.1 |
| 23.4 | **Diversify the premium sleeve.** Whitelist non-tech / index underlyings for CSP/PCS (`add_universe_ticker`) so income isn't 100% Mag-7 correlated. | `config_store`/universe | S | — |
| 23.5 | **Manage-at-50% revisit (data decision).** Re-run `journal_analytics` bucketing once ≥ representative closes accrue; compare 50% vs 80% profit-take for the defined-risk sleeve. (Supersedes the 19.7 hold.) | journal + settings | S | 16.2 accrual |
| 23.6 | **Cluster-glide tracker (Parapet).** Current cluster % vs the 60% target with the glide path (91→60). | `fortress-parapet` | S | 19.2 |
| 23.7 | **Dynamic watchlist.** Reflect "open positions + user additions" as the watchlist in the UI + universe logic. | `fortress-parapet` + universe | S | — |

**Acceptance:** efficiency heatmap ranks positions and flags <0.5× · collar builder produces a priced call+put overlay on a held LEAP · a LEAP call-writing candidate appears with a non-zero credit · cluster-glide widget shows current vs 60%.

---

## Sprint 24 — Docs & governance
**Goal:** documentation catches up to the new logic and rules.

| # | Item | File(s) | Effort | Dep |
|---|---|---|---|---|
| 24.1 | **Strategy v3.9 → v3.10.** Fold in the multi-timeframe layer, the trend-filter entry gate, the collar overlay, manage-at-50% option, and the hedged-premium-seller persona. | `docs/01_Portfolio_Strategy` + `STRATEGY_ENHANCEMENTS_v3_10.md` | M | Sprint 21 decisions |
| 24.2 | **Briefing SKILL update.** Add the Technical Gate step, explicit fallback labeling, and optimization KPIs (capital-efficiency flag, cluster-glide, hedge coverage) to the standard output. | `daily-post-open-briefing` SKILL | S | 22.1 |
| 24.3 | **Adopt the two session rules** (already in the Procedure): dynamic watchlist; data-source availability (tell first in live sessions, label fallback in scheduled). Reference from Strategy + SKILL. | Procedure + Strategy | S | ✅ in Procedure |
| 24.4 | **Vega-flip alert.** Scheduled task / alert when `beta_vega_flag` flips `net_short → net_long` (the unflagged risk the β-vega stat surfaces but doesn't alert on). | scheduled task | S | 19.1/20.6 |

---

## Sequencing rationale
- **Sprint 0 first** — without the out-of-mount files, 15.1 / 15.3 / 16.1 / 16.5 can't deploy. One small copy unblocks the two most valuable sprints.
- **Sprint 15 before 16** — `pretrade_check` consolidation (16.1) depends on VIX-term (15.3) and ex-div (15.4) existing as inputs first.
- **16.2 → 16.3 → 16.4** is a strict chain (capture → schema → backfill).
- **Sprint 17** is all independent and deferrable; pull any item forward if a quiet session allows.
- **Sprint 21 before 22/23** — 21.1 (strike-selection fix) is the keystone: it unblocks the LEAP call-writing (23.3) and collar (23.2) work, and 21.4 (trend gate) consumes the weekly SMA that 22.1 ingests. Do **21.1 → 21.2 → 21.6** first (correctness + safety), then 21.4/21.5 (gates), then the UI/structure sprints.
- **22.1 before 21.4** — the trend gate needs the weekly-SMA ingest from the Technical Gate.
- **Sprint 24 trails** its corresponding code sprints (docs after behavior).

## Open decisions
**Resolved 2026-07-02:**
- ✅ 21.1: **adaptive** short-call delta (base 0.30, band 0.20–0.40, 30–45 DTE), engine reasons from IVR/trend/resistance/catalyst/concentration and logs a rationale — see 21.1 design.
- ✅ 21.4: trend gate = **warning** (not a hard block).
- ✅ 22.3: stale/fallback data = **warn clearly**, do not gate write actions.

**Resolved 2026-07-02 (cont.):**
- ✅ 23.2: **full collar** on the concentrated LEAPs (GOOGL/AMZN) — sell an adaptive-Δ call to fund a protective put.

**Resolved 2026-07-02 (cont.):**
- ✅ 23.4: non-tech whitelist screened (Fortress IVR + TradingView weekly trend-gate) across all four sectors. **Add now:** **JPM** (financials, IVR 72, above all weekly MAs) + **JNJ** (healthcare, IVR 90, clean weekly uptrend). **Whitelisted but trend-gated** (add on a weekly-200-SMA reclaim): XOM (energy, marginal), CVX / COST / WMT (currently below their weekly 200-SMA). **Excluded:** UNH (bearish, IVR 23, earnings 14d). LLY optional (rich premium but earnings 34d + high IV). Live demonstration of the 21.4 trend gate: 4 of 8 candidates failed it despite bullish Fortress regime + high IVR.

## Effort key
S = <½ session · M = ~1 session · L = ≳2 sessions (only 22.4 is M–L). Sprints 15–20 shipped. Sprints 21–24 add ~7–9 working sessions; Sprint 21 alone (~2 sessions) captures most of the profit/reliability upside.
