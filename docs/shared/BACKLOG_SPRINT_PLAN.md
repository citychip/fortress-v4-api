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

**Visuals catalogue (build order after 28.2):** ① sector treemap/donut · ② ✅ staged-uncap tracker (SHIPPED 07-10: 4-gate readiness per LEAP) · ③ leaf-overlap matrix · ④ ✅ delta/β-vega gauges (SHIPPED 07-10) · ⑤ ✅ β-DD bars 30/40 (SHIPPED 07-10) · ⑥ hedge-coverage band (B-2 25–33%) · ⑦ vol-skew curve + VIX-term sparkline · ⑧ equity curve (`get_pnl_history`) · ⑨ expectancy tiles by IVR/DTE/delta · ⑩ household-concentration glide vs 35% · ⑪ ✅ position-and-catalyst timeline (SHIPPED 07-09: DTE bars + macro markers) · ⑫ two-leaf architecture SVG header. All recharts/div-based, read-only.

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
| O-10 | **v4.0 household layer — Phase 2 (read-only view)** — `get_household_overview` + `get_household_concentration` (aggregate over `get_briefing` + an eToro `household_state.json` snapshot) + Parapet **Household** page panels 1–2. Promotes `Combined_Portfolio.xlsx` to a live view. Later phases: staged-uncap + tail-hedge trackers, scheduled diversification screen, Chrome eToro ingest. Full design in the proposal. | M | read-only; engine untouched |

## Standing conventions
- New backend script in OneDrive → add to `sync_check.sh` MAP + `deploy_data_sources.sh`; new Parapet file → `deploy_parapet.sh` FILES.
- Fully-shipped sprint tables move to `archive/BACKLOG_COMPLETED.md` (one-line pointer stays here).
- Effort key: S = <½ session · M = ~1 session · L = ≳2 sessions.
