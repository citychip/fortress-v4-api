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

## Standing conventions
- New backend script in OneDrive → add to `sync_check.sh` MAP + `deploy_data_sources.sh`; new Parapet file → `deploy_parapet.sh` FILES.
- Fully-shipped sprint tables move to `archive/BACKLOG_COMPLETED.md` (one-line pointer stays here).
- Effort key: S = <½ session · M = ~1 session · L = ≳2 sessions.
