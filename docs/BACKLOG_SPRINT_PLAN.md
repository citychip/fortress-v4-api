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
| 15.3 | **Wire `get_vix_term` into the regime read** — VIX-vs-VIX3M contango/backwardation as a regime input (data already exists, not consumed) | regime route (out-of-mount) | S | Sprint 0 |
| 15.4 | ✅ **DONE + VERIFIED LIVE (2026-06-20)** — ex-div assignment-risk gate. Claude-curated store (`get_ex_div`/`set_ex_div_events`, same pattern as macro_events) cross-references the **live short-call legs**: ITM+ex-div≤expiry = `high`, near-ITM = `watch`; deep-OTM/non-dividend never flag. Backend routes + MCP tools + NaN smoke-test. **Verified:** 4 synthetic cases + live (seeded MSFT ex-div 08-20 → correctly NO risk, as 490/510C are deep OTM). Parapet chip = follow-up. | `options_analytics.py` + MCP | S | — |

**Acceptance:** `strategy_metrics` output reprices within tolerance of a manual `get_iv_rank` + chain check on 2 tickers · `check_liquidity` returns a sane grade for an OTM strike, not just ATM · regime payload carries a `vix_term` field that flips the read on a backwardation day · a name with an ex-div inside a short-call expiry shows the risk chip.

---

## Sprint 16 — "Consolidate + close the feedback loop"
**Goal:** one pre-trade gate that sees everything; the trade-outcomes loop actually accrues data.

| # | Item | File | Effort | Dep |
|---|---|---|---|---|
| 16.1 | **Consolidate macro-defer + VIX-term + ex-div into `pretrade_check`** — single gate badge with amber sub-flags, surfaced on Candidates/Triage | pretrade route (out-of-mount) | M | Sprint 0, 15.3, 15.4 |
| 16.2 | **Auto-capture entry conditions at open** — snapshot IVR/DTE/short-delta when an order fills, write to the trade-outcomes sidecar | MCP + `options_analytics.py` | M | — |
| 16.3 | **Journal schema enrichment** — add `ivr_at_entry`/`dte_at_entry`/`short_delta_at_entry`/`days_held`/`exit_reason`; unlocks bucketing in `journal_analytics.py` | `trade_outcomes.json` + analytics | S | 16.2 |
| 16.4 | **Seed history** — backfill recent closes via `log_trade_outcome` so the report has data now, not just going forward | manual + MCP | S | 16.3 |
| 16.5 | **Pacing counter counts manual IBKR fills** — reconcile fills against staged orders so the counter stops under-reporting | pacing route (out-of-mount) | M | Sprint 0 |

**Acceptance:** a freshly filled order auto-creates a trade-outcomes record with entry IVR/DTE/delta populated · `journal_analytics.py` prints expectancy by IVR/DTE/delta bucket on ≥1 seeded bucket · pacing reflects a manually-entered IBKR fill · `pretrade_check` shows the consolidated macro/vix/exdiv sub-flags.

---

## Sprint 17 — Automation + polish (lower urgency)

| # | Item | Effort | Notes |
|---|---|---|---|
| 17.1 | **Weekly scheduled tasks** — macro-calendar refresh (FRED/FMP → `set_macro_events`) + `journal_analytics.py` run | S | Use the scheduler; complements the daily post-open briefing already running |
| 17.2 | **Alert when `defer_advisory` flips true** — scheduled pre-event note / conditional alert | S | Catalyst §6 #5 |
| 17.3 | **Catalyst settings promotion (#80)** — `defer_days` + `news_spike_cooldown_days` → `settings.json`, surface in System > Settings | S | Catalyst §6 #1 |
| 17.4 | **Per-ticker news scan** — `/api/market/news/{ticker}` (QuantData → FMP fallback) + "days since last material headline" chip on Candidates/Triage (indicator, not a reader) | M | Catalyst §6 #3; operationalizes the §4 cooldown |
| 17.5 | **Retire paywalled Massive options path** | S | Cleanup; massive stays only as a GEX/skew fallback |
| 17.6 | **Social sentiment (LunarCrush, situational)** | M | Lowest priority; Claude-side only, retail-driven names (MSTR-type) |

---

## Sequencing rationale
- **Sprint 0 first** — without the out-of-mount files, 15.1 / 15.3 / 16.1 / 16.5 can't deploy. One small copy unblocks the two most valuable sprints.
- **Sprint 15 before 16** — `pretrade_check` consolidation (16.1) depends on VIX-term (15.3) and ex-div (15.4) existing as inputs first.
- **16.2 → 16.3 → 16.4** is a strict chain (capture → schema → backfill).
- **Sprint 17** is all independent and deferrable; pull any item forward if a quiet session allows.

## Effort key
S = <½ session · M = ~1 session · (none are L). Total: ~6–8 working sessions across the three sprints.
