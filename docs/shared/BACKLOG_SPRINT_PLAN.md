# Fortress — Backlog Sprint Plan
**Created 2026-06-19 · Trimmed 2026-07-08. This file tracks the ACTIVE backlog only.**

> **Completed Sprints 0–26 (all shipped + verified) → `archive/BACKLOG_COMPLETED.md`.**
> Latest shipped: **Sprint 26** (collar · profit-targets scan · Health Manager — deployed+verified 07-08) and **Sprint 27** below.

---

## ✅ Sprint 27 — v3.11 backend wiring (SHIPPED + LIVE-VERIFIED 2026-07-08, single session)
The entire v3.11 backend backlog plus the session's own finds. Commits: fortress-v4-api `041a884`, fortress-mcp `cbe2814` (v4.12.0), fortress-parapet `29be18c`.

| # | Item | Where | Status |
|---|---|---|---|
| 27.1 | **Matched-vertical exemption (doctrine v2)** — `state.short_call_vertical_exempt()` (greedy same-expiry qty allocation; strictly-lower long strike; PMCC calendar shorts never match). Suppresses briefing critical_gamma; `roll_all`/`stop_loss_all` rows carry `vertical_exempt: true` + summary counts. Live: MSFT Jan'28 450C + AMZN Jan'28 280C exempt; GOOGL/AAPL real flags untouched. | `state.py` + `manage.py` | ✅ verified |
| 27.2 | **Earnings-null fix** — canonical `state.earnings_state_from_days()`: `None` → **"unverified"** (advisory `earnings_unverified` caution, never "clear"/blocking). Wired into the 3 in-mount derivations. ⚠ Remaining: same one-liner in the pulled `route_candidates.py` (next code session). | `state.py` + `manage.py` | ✅ (route wire-up open) |
| 27.3 | **`get_profit_targets` fail-safe** — legs with missing expiry/strike/right are SKIPPED (was: DTE defaulted 0 → every short leg false-flagged pre-sync). | `manage.py` | ✅ verified |
| 27.4 | **MCP v4.12.0** — `_json_or_ok()` on all HTTP helpers (204/empty-body tolerant; `delete_conditional_alert` fix). Same fix in Parapet `req()`. | `fortress_mcp_v452.py` + `api.ts` | ✅ verified |
| 27.5 | **Weekly-close alert types** — `weekly_close_above/below`: ride the EOD pass, fire ONLY when the settled bar is a Friday (holiday-short weeks skip). Intraday pass skips all close-types via `CLOSE_ALERT_TYPES`. | `route_conditional_alerts.py` + `sched_runner.py` + MCP docs | ✅ (create the MSFT 383 alert) |
| 27.6 | **Dynamic pacing (v3.11)** — briefing `compute_pacing(vix=…)`: VIX<18→2/wk · 18–25→3 · >25→5; `strategy.entries_per_week_max` stays the CEILING; payload carries `pacing_mode`/`vix_band`/`static_max`. Config `strategy.dynamic_pacing_enabled`. | `briefing.py` + `config_store.py` | ✅ verified (band vix<18 live) |
| 27.7 | **Per-ticker β-DD briefing block** — `compute_beta_dd()`: Σ(qty×Δ×mult×spot)/NLV per ticker; soft-gate 30% → `frozen[]`, hard backstop 40%; SPY/OST `gate_eligible: false`. Config `strategy.beta_dd_*`. Live: AAPL 34.1% frozen (matches hand calc). | `briefing.py` + `config_store.py` | ✅ verified |
| 27.8 | **Parapet** — self-contained ConditionalAlertsCard (type dropdown incl. weekly types, urgency, armed/TRIGGERED, last-close stamp, delete) on the Alerts tab; `alerts.close_eval_*` settings rows; **MONETIZE = under-written only** (requires membership in `covered_call_candidates`). | `AlertsSection.tsx` + `api.ts` + `settings.py` + `EfficiencyPage.tsx` | ✅ built (visual check open) |

---

## 🔨 Sprint 28 — v4 Household dashboard (IN PROGRESS, started 2026-07-09 Cowork)
Option-1 coexistence: ONE Parapet app, an `Engine v3` | `Household v4` mode toggle in the sidebar (persisted in localStorage); v3 pages untouched. Frontend-only, read-only, engine/MCP not modified.

| # | Item | Where | Status |
|---|---|---|---|
| 28.1 | **Mode switcher** — `lib/useMode.ts` (v3\|v4, localStorage + `fortress-mode` CustomEvent for cross-component sync); Sidebar renders a toggle + swaps its NAV list per mode; `App.tsx` gains the `/household` route. v3 nav unchanged. | `Sidebar.tsx` · `App.tsx` · `lib/useMode.ts` | ✅ shipped 07-09 |
| 28.2 | **Household page** — `pages/HouseholdPage.tsx`: metric cards (household NLV, leaf split, AI/tech/chips vs 35%, semis) + single-name-vs-15%-cap bars + sector-vs-25%-cap bars (div-bar pattern reused from `ClusterGlide`). Seeded from `lib/household.ts` (Combined_Portfolio.xlsx values) until the live route lands. | `pages/HouseholdPage.tsx` · `lib/household.ts` | ✅ shipped 07-09 |
| 28.3 | **Data wiring (Phase 2 dep)** — swap the seed for `get_household_overview` / `get_household_concentration` (O-10) via a `/api/household/*` route; `household.ts.getHousehold()` already returns a Promise so the page won't change. | backend routes + `lib/household.ts` | ✅ shipped 07-09 (client-side: live getBriefing + eToro snapshot) |

**Visuals catalogue (build order after 28.2):** ① sector treemap/donut · ② ✅ staged-uncap tracker (SHIPPED 07-10: 4-gate readiness per LEAP) · ③ ✅ leaf-overlap matrix (SHIPPED 07-10) · ④ ✅ delta/β-vega gauges (SHIPPED 07-10) · ⑤ ✅ β-DD bars 30/40 (SHIPPED 07-10) · ⑥ ✅ hedge-coverage band (SHIPPED 07-11; backend B-2 fields + Risk-page band) · ⑦ ✅ vol-skew + term structure (SHIPPED 07-11) · ⑧ ✅ equity curve (SHIPPED 07-11; empty until EOD snapshots accrue) · ⑨ ✅ expectancy tiles (SHIPPED 07-11) · ⑩ ✅ concentration glide (SHIPPED 07-11; Mag-7 cluster vs 60%) · ⑪ ✅ position-and-catalyst timeline (SHIPPED 07-09: DTE bars + macro markers) · ⑫ ✅ two-leaf header (SHIPPED 07-10, div-based). All recharts/div-based, read-only.

**28.8 - v4 Analytics page (SHIPPED 07-11):** new `/analytics` v4 nav tab hosting equity curve (⑧), concentration glide (⑩, recharts), expectancy tiles (⑨, /api/trade-outcomes), and vol-skew + term structure (⑦, SPY). New `AnalyticsPage` + 4 components; `getTradeOutcomes` added to api.ts. All read-only. **All 12 catalogue visuals shipped.** ⑥ unblocked via `_compute_b2_hedge` on the spy_hedge_coverage route (Sprint 28.9).

**28.6 - v4 pages split (SHIPPED 07-10):** the single Household page split into a v4 nav - `Household` (leaf header + concentration + sectors), `Risk` (greeks + β-DD + uncap tracker), `Timeline` (DTE ladder). New `RiskPage`/`TimelinePage`; Sidebar `NAV_V4` expanded; routes `/risk` `/timeline` added.

## Open items (small)
| # | Item | Effort | Note |
|---|---|---|---|
| O-1 | ✅ **DONE + VERIFIED LIVE 2026-07-08** — `route_candidates.py` wired (`state.earnings_state_from_days` + `earnings_note`), deployed, and confirmed: null-earnings rows (TROW/COST/WMT) return `earnings_state: "unverified"` + warning note, never "clear". | S | closed |
| O-2 | **Create MSFT `weekly_close_below 383`** conditional alert (v3.11 weekly rule) — retire the manual Friday check. | S | write-tool one-liner |
| O-3 | **Hedge/roll journal tagging** — pacing excludes entries whose `framework_rules` mention roll/hedge; the 07-06/07 SPY tranches were untagged → pacing over-counts (2/2 at VIX<18). Tag at journal time, or add a ticker/description heuristic. | S | data hygiene + optional code |
| O-4 | **Profit-take 50 vs 80 decision** — `profit_target_pct` is user-set 80; research default 50 (`profit_target_pct_recommended`). One click in Settings → Strategy if adopting. | S | operator decision |
| O-5 | ✅ **DONE 2026-07-08** — deleted the 5 stale unmapped OneDrive duplicates (`route_settings/briefing/journal/options_analytics/pnl.py`); repo cruft removed + gitignored (`main`, `*.corrupt`, commit `0286d9d`); ancient repo-only docs purged via docs rsync. Bonus: MCP instructions string bumped v4.5.1/v3.9.0 → v4.12.0/v3.11 (applies at next MCP relaunch — copy `fortress_mcp_v452.py` to the Windows path first). | S | closed |
| O-6 | **Parapet visual check** — Alerts tab ConditionalAlertsCard + Settings close-eval rows after next build. | S | 27.8 follow-up |
| O-7 | **Briefing-SKILL wiring** (old 22.1/24.2 remainder) — add Technical-Gate + β-DD/`frozen` + dynamic-pacing band to the `daily-post-open-briefing` scheduled-task prompt. | S | no code |
| O-8 | **OAuth Stage 2** — IBKR-side consumer-key activation (SHARMILAH). Nothing to build locally; portal/ticket only. | ext | the only external blocker |
| O-9 | ✅ **DONE 2026-07-09 (Cowork)** — docs reorg into `v3/`+`v4/`+`shared/`+`archive/`; README rewritten (foldered index, both v4 docs registered, v3.11 reframed as Leaf-B ENGINE); review-loop snapshots + `REVISED_RECOVERY` archived; `deploy_data_sources.sh` docs-copy made recursive (rsync). Remaining: run the repo `git mv` set + deploy + commit (commands handed over); optional root cleanup of `Combined_Portfolio_Strategy_v4.md` stub + `Fortress_Forward_Prognosis` docx + sprint0 files; optional non-breaking code-comment path bumps (`fortress_mcp_v452.py:68`, `config_store.py:63`, `options_analytics.py:2317`). | S | mostly closed |
| O-11 | **Parapet v3/v4 mode switcher** → now **Sprint 28** (in progress 07-09). Toggle in the Sidebar (not Layout — that's where the nav lives), household page seeded until O-10 lands live data. | M | see Sprint 28 |
| O-10 | ✅ **SHIPPED 2026-07-12 (Cowork)** — v4.0 household layer Phase 2 (read-only view). `app/routes/household.py` (`/api/household[/overview|/concentration]`) nets Leaf B live (`get_active_positions`+`compute_concentration`+fx) over the Leaf A eToro snapshot `quant/household_state.json`; MCP tools `get_household_overview`/`get_household_concentration`. Mirrors `lib/household.ts` server-side; route hardened w/ `_EMERGENCY_SEED`. **Verified live via curl+MCP (`source: live`, €85,288, 71/29, AAPL 14.2%).** Registered in `app/main.py`; deploy seeds store to `$FORTRESS_DATA_DIR` (quant/). Commits fortress-v4-api `a5c1bab`→`b0b777c`, fortress-mcp `21d98f6`. **Later phases still open:** Phase 3 staged-uncap + tail-hedge trackers, Phase 4 scheduled diversification screen + Chrome eToro auto-ingest. ⚠ Gated: adopting v4.0 as the standing overlay is a user decision (HANDOFF Priority #8) — only the read-only view shipped. | M | read-only; engine untouched |

| O-13 | ✅ **SHIPPED 2026-07-14 (Cowork)** — v4.0 **Phase 3** read-only tools (backend/MCP behind Sprint 28's client-side UncapTracker). In `app/routes/household.py`: `/api/household/uncap_stages` (per-LEAP stage 0–3 derived live from short-call:long-LEAP coverage + 4 §3.1 gates + verdict) and `/api/household/tail_hedge` (§5: 0.75%-NLV/qtr budget, far-OTM ≥15% SPY crash puts, roll DTE; replaces B-2 widget for Leaf B). MCP tools `get_uncap_stages`/`get_tail_hedge`. Lazy imports avoid route circulars; null-gate graceful degrade. Verified live (`source: live`): regime bearish→de-stage; MSFT S1, rest S0; tail_put_count 0 (B-2 spreads, not tail puts — correctly flagged). Commits fortress-v4-api `b303d4b`, fortress-mcp `8ebf496`. **Phase 4 still open:** scheduled diversification screen + Chrome eToro auto-ingest (refresh `household_state.json` automatically). | M | read-only; engine untouched |
| O-12 | **Manus IB_MCP + OpenAPI v3 integration proposal (reviewed 07-11).** VERDICT: good ideas, wrong blueprint — the doc is written against a Node/Express `/home/ubuntu/Fortress_Dashboard` stack + `ib_gateway.service:5055`; our backend is **Python/FastAPI** (`fortress-v4-api`, :8081) with **cp-gateway (Docker/iBeam)**. ADOPT (as read-only FastAPI routes, translated to our stack): (a) **pre-trade what-if margin gate** `/iserver/.../orders/whatif` (v3.11 §G) — highest value; (b) **live option greeks snapshot** 7308/7310/7311/7087 to firm up β-DD (the hedge-band caveat); (c) **`/pa/transactions` → auto-expectancy** to feed the n≥30 loop vs manual `trade_outcomes.json`. RECONCILE not rebuild: fold tickle+Slack into the EXISTING `gateway_watchdog.sh`/`fortress-gateway-watchdog.service` (don't add a parallel service). REJECT as-written: all Express/Node routes + paths. Keep: what-if read-only, execution stays manual in TWS. | M | design doc reviewed; not adopted |

## Standing conventions
- New backend script in OneDrive → add to `sync_check.sh` MAP + `deploy_data_sources.sh`; new Parapet file → `deploy_parapet.sh` FILES.
- Fully-shipped sprint tables move to `archive/BACKLOG_COMPLETED.md` (one-line pointer stays here).
- Effort key: S = <½ session · M = ~1 session · L = ≳2 sessions.
