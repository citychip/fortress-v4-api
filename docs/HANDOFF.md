# Fortress — Session Handoff & Start-Here Guide
**Last updated: 2026-07-16 · Read this top-to-bottom to start any session. This is the lean START-HERE — current state, open priorities, and protocols only. Per-session narrative lives in `SESSION_LOG.md`; per-item backlog in `BACKLOG_SPRINT_PLAN.md`; deep detail via the Documentation Index. Run the OPEN checklist now; run the CLOSE protocol (bottom) at wrap.**

> **2026-07-08: Sprint 26 DEPLOYED+VERIFIED and Sprint 27 (v3.11 backend wiring) SHIPPED same day.** Sprint 26 live: collar fields on `get_covered_call_candidates`, `get_profit_targets` (manage-at-%/21-DTE), `get_risk_limits` Health Manager + Recovery-page banner/cards (empty cards hide by design). **Sprint 27 (all live-verified):** ① **matched-vertical exemption** — MSFT/AMZN Jan'28 verticals no longer false-flag roll/stop/gamma (`vertical_exempt: true`, briefing actions clean; NO more manual ignoring), ② scanner **earnings-null → "unverified"** (never renders clear; candidates route wire-up = next code session, `route_candidates.py` pulled), ③ `get_profit_targets` fail-safe (missing leg metadata → skip, kills the pre-sync DTE-0 false-flags), ④ MCP **v4.12.0** empty-body-tolerant helpers (delete-alert fix), ⑤ **weekly_close_above/below** alert types (fire on the FRIDAY bar only — the v3.11 weekly-close rules are now automatable), ⑥ **dynamic pacing** in the briefing (VIX<18→2/wk · 18–25→3 · >25→5, static cap = ceiling; `pacing_mode`/`vix_band` exposed), ⑦ **per-ticker β-DD block in the briefing** (`beta_dd.frozen` — the 30% soft-gate is machine-enforced; live: AAPL 34.1% FROZEN), ⑧ Parapet conditional-alerts card w/ type dropdown + `alerts.close_eval_*` settings rows; MONETIZE flag now = genuinely under-written only. Only external blocker: **OAuth Stage 2 = IBKR-side**.

> **2026-07-09 (Cowork strategy session): v4.0 TWO-LEAF HOUSEHOLD OVERLAY DRAFTED — PROPOSAL, NOT ADOPTED.** An **eToro** copy account (Jeppe Kirk Bonde, €25.0k) was read in as **Leaf A** (self-hedged by the copied trader, constituents unmanaged); IBKR = **Leaf B**. New separate strategy `02_Household_Strategy_v4_0.md` **coexists with — does NOT supersede — v3.11** (v3.11 is now the "Leaf-B engine" rulebook); its §7 is the full v3.11↔v4.0 diff map. Leaf B re-mandated income→**responsible growth**: staged-uncap ladder, **tail-hedge-only** (retires B-2 for Leaf B), household caps (single-name 15% / sector 25% / AI-tech-chips 35%), widened non-tech universe. Key finding: household is **~57% big-tech/AI/chips** (semis ~15%) — the two leaves stack the same factor. Artifacts: `Combined_Portfolio.xlsx` (exposure netting + non-tech **Candidates** tab, built from Fortress gate + **TradingView scanner via CDP**), `PROPOSAL_Two_Leaf_Dashboard_and_Docs_2026-07-09.md` (household dashboard+docs, 4-phase). **NO code edited, NO files deleted, NO trades, sync_check NOT run (2 new docs unmapped).** Open decisions → Open Priorities **#8**. · **Docs reorganized 07-09** into `v3/` (engine) + `v4/` (household) + `shared/` + `archive/`; README index rewritten; the 4 review-loop snapshots + `REVISED_RECOVERY` archived; `deploy_data_sources.sh` docs-copy made recursive.

---

## ⭐ DATA-SOURCING PROCEDURE — READ FIRST, EVERY SESSION

**Goal: never trust a number without confirming its source is live. Run Step 0 before any portfolio/trade work.**

### Step 0 — Verify the data backbone (do this first, always)
1. `get_ibkr_status` → confirm **`active_backend: "web_api"`** AND `web_api.authenticated: true`.
   - If `active_backend: "bs_yfinance"` → **gateway is DOWN. Data is frozen/delayed — do NOT trade on it.** `staleness` may still falsely read "fresh". Fix: `docker restart cp-gateway` (WSL) or Parapet → Reconnect, wait ~40s, re-check. A `retry_ibkr_sync()` alone will NOT fix a 401/iBeam auth failure.
2. `get_briefing` → after any trade, re-pull and confirm **`_ibkr_sync_time` advanced**. A frozen `synced_at` = gateway down, not just stale.
3. **Ignore `get_ibkr_status.oauth`** for OAuth Stage 2 — it lies (`authenticated:true` while the real handshake 401s). Only `test_ibkr_oauth.py` tests Stage 2.
4. **Gateway vs IBKR Desktop = ONE session per username (learned 07-06).** Logging into IBKR Desktop/TWS to place orders kicks the gateway (web_api 401) — expected, not a fault. Trade sessions follow **`WORKFLOW.md` §Trade Session Procedure**: Phase 1 ANALYZE with gateway up → exact-orders deliverable → Phase 2 EXECUTE in TWS (gateway down, TWS quotes authoritative, don't restart mid-session) → Phase 3 log out, restart gateway, re-sync, VERIFY + journal.

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
- **β-Δ partial-greeks trap (bit again 07-08):** the first sync can leave the SPY hedge legs with `delta_contribution: 0.0` for minutes → β-Δ falsely read **+386** instead of −116 and β-vega sign-flipped. **Never trust β-Δ until `get_portfolio_beta` shows SPY ≠ 0.0**; if 0, force another `trigger_ibkr_sync`, wait ~40s, re-pull.
- **Matched-vertical flags are auto-exempt since 07-08** — `roll_all`/`stop_loss_all` rows carry `vertical_exempt: true` and the briefing no longer emits gamma actions for them. If a vertical DOES flag, the coverage detection broke — investigate, don't ignore.
- **Scanner `days_to_earnings: null` now renders `earnings_state: "unverified"`** (advisory caution, never "clear"). In-mount routes fixed 07-08; the `/api/candidates` route itself ships next code session (`route_candidates.py` pulled) — until then still verify per name on the candidates board.
- **Pacing hedge-tagging:** `compute_pacing` excludes entries whose journal `framework_rules` mention "roll"/"hedge" — the 07-06/07-07 SPY hedge tranches were journaled WITHOUT the tag, so they wrongly count (2/2 used at VIX<18). **Tag hedge/roll journals with the matching framework rule** or pacing over-counts.
- **`strategy_metrics` vol is now REAL (fixed 2026-06-20, Sprint 15.1):** IV/IVR come from `get_iv_rank`, DTE from `state.days_to_earnings`; payload carries `vol_source` (`ibkr`/`bs_inversion`/`hv_proxy` = real; `placeholder` = fallback). Credit/POP/IVR are trustworthy now. ⚠ **Regime is still the `neutral` placeholder** until Sprint 15.3 wires the real regime read — so don't lean on `strategy_metrics` regime_score yet.
- **Conditional price alerts (`price_above`/`price_below`) fire on intraday spot, not daily close.** A "close below X" rule needs manual close confirmation — they false-fire on wicks.
- **Pacing now catches manual IBKR fills** (Sprint 16.5 position-diff) — it diffs the IBKR-synced book, not just Fortress-staged orders. ⚠ **Sprint 20.2 fix (2026-06-27):** the per-briefing snapshot capture had a **non-atomic write** that, on a concurrent/truncated read, let the next capture **clobber the snapshot history** → position-diff silently collapsed and the briefing fell back to `journal_only` (0/5). Fixed with atomic writes + a non-destructive guarded load; the briefing now exposes `pacing.position_diff_reason` so a fallback is never silent again. If pacing reads `source: journal_only`, check `position_diff_reason` (`need ≥2 snapshots to diff` = normal early-week/after-reset; anything else = investigate). Needs ≥2 distinct-day snapshots to diff.
- **Spread pricing:** always work the limit at the **mid**, never the ask/bid the ticket pre-fills. Verify the expiry doesn't span an earnings date (`get_earnings_history`) unless that's intended.
- **MCP server "disconnected" mid-session** is transient — reload the tool via ToolSearch and retry; the data is fine.

---

## 🔺 Session OPEN Checklist (run these first)
1. `get_ibkr_status` — confirm `web_api` authenticated (Step 0 above).
2. **`trigger_ibkr_sync` FIRST, then `get_briefing`** — and check `staleness.hours`. **If > ~2h, re-sync again before trusting any positions/roll/stop read** (the 06-26 trap: first briefing was 18.8h stale and silently showed the wrong book). **Also `get_portfolio_beta`: SPY `delta_contribution` must be ≠ 0.0 or β-Δ is garbage** (07-08 trap: +386 vs true −116 — re-sync fixes it). Then read NLV, concentration, β-weighted delta vs target, **pacing (now dynamic — check `vix_band`)**, regime, **`beta_dd.frozen`** (per-ticker 30% soft-gate list, live in the briefing since 07-08). Portfolio **β-vega** is a briefing stat: `greeks.beta_weighted_vega` + `beta_vega_flag` (`net_long_vega` = the blind-spot flip on a premium-selling book). Watch the flag.
3. `get_conditional_alerts` — any triggered? (Sprint 20.3 added `close_below`/`close_above` types evaluated by the EOD pass against the daily close — use those for close rules. Legacy `price_*` rules still fire on intraday wicks, so confirm those on the actual daily close until converted.)
4. If managing/entering: `get_roll_all`, `get_stop_loss_all`, `get_candidates`. Recovery KPIs: `get_spy_hedge_coverage` (vs $20k floor) + `concentration.cluster` (vs 60%).
5. Macro context if entering: FRED for FOMC/CPI dates; `get_market_intelligence("SPY")`.

> **Automation:** the **`daily-post-open-briefing`** scheduled task (weekday 15:45 CEST / 09:45 ET) now runs this checklist automatically — force-sync first + staleness guard + hedge/cluster/β-vega steps. The **`hedge-coverage-drift-alert`** task (weekday 09:03 CEST, Sprint 20.5) is a dedicated under-hedge watchdog (🔴 when `coverage_ok=false`). The **`fortress-recovery-dashboard`** Cowork artifact renders the same live read on demand (re-open/Reload to refresh).

---

## Current State (live read 2026-07-16 ~13:40 UTC, post NVDA-roll — staleness 0.0h/fresh, web_api. ⚠ Backend restarts / fresh syncs trigger the PARTIAL-GREEKS trap: short-leg deltas read 0.0 and β-DD false-freezes at 2–3× — re-sync + re-pull until short legs populate; verify SPY `delta_contribution` ≠ 0 AND a name's short leg is counted before trusting β-DD. ⚠ Always re-sync if staleness >~2h. ⚠ Partial-greeks trap: verify SPY `delta_contribution` ≠ 0 before trusting β-Δ. ⚠ Gateway 401s during order placement are EXPECTED — see WORKFLOW.md §Trade Session Procedure.)

**⭐ v3.11 IN FORCE — canonical Leaf-B ENGINE rules: `v3/01_Portfolio_Strategy_v3_11.md` (consolidated single spec:** two-bucket, hybrid XSP income, β-DD caps, B-2 hedge formula, roll doctrine v2, weekly-close de-risk, dynamic pacing, compliance-score measurement — the old v3.9 spec + v3.10 addendum are archived). Review package (STRATEGY_v3_11_UPDATE + AI_REVIEW_BRIEF + REVIEW_REQUEST + LEAP_SALVAGE_MSFT_CROSSCHECK) **ARCHIVED 07-09 → `archive/`** (the reviewed rules now live in the v3.11 engine spec; retained as the review record). **v4.0 household overlay sits above the engine: `v4/02_Household_Strategy_v4_0.md`.**

**⭐ v4.0 HOUSEHOLD OVERLAY — PROPOSED 07-09 (Cowork, no code):** `02_Household_Strategy_v4_0.md` sits ABOVE v3.11 as the household (Leaf A eToro + Leaf B IBKR) strategy; re-mandates Leaf B income→growth (staged uncap, tail-hedge-only, caps 15/25/35, non-tech universe). Coexists with v3.11 (the engine rulebook) — nothing engine-side changed. Decisions pending: see Priority #8. Live household read (07-09): ~€85.4k, IBKR 71% / eToro 29%, ~57% big-tech/AI/chips. **DASHBOARD BUILT 07-11 (Sprint 28):** Parapet v4 mode — Household/Risk/Timeline/Analytics pages + all 12 catalogue visuals; the only backend change was read-only B-2 fields on `/manage/spy_hedge_coverage` (`_compute_b2_hedge`: engine $74.2k vs hedge max-payout $81.5k = OVER the 25–33% band). v3 engine untouched.

| Metric | Value |
|---|---|
| Net Liq | **$65,662** (≈€57,318) — 07-16 ~13:40 UTC, web_api. Down ~$5.2k from 07-15's $70.9k = a **€5,500 (~$6.3k) cash WITHDRAWAL to checking (holiday), NOT a loss** — ex-withdrawal the book actually rose ~$1.1k. |
| Available / Excess Liq | **$43,832 / $45,511** (far above the $17k/$25k floors) |
| β-weighted Δ | **−97.7** (clean read; SPY contribution −252 ≠0 → trustworthy). NVDA roll (07-16) added ~+NVDA long delta. Net modestly net-short, appropriate for the bearish regime; core SPY hedge retained. β-vega net_long (protective; the known blind-spot flag). |
| VIX / Regime | **16.2 / normal**, macro **bearish**; VIX term contango. XSP book gate CLOSED (needs IVR≥25 + VRP≥3.5pp + contango). |
| Pacing | Briefing DYNAMIC: **band vix<18 → max 2/wk, reads 0/2 used** (source now `position_diff`). NVDA roll (07-16) was a management roll, not an income open. True income entries this week: 0. |
| **β-DD (briefing `beta_dd`, clean read)** | All under the 30% soft-gate: MSFT ~22 · AAPL ~26 · GOOGL ~22 · AMZN ~21 · NVDA ~28. SPY/OST gate-exempt. ⚠ On a fresh sync the block false-freezes GOOGL/AAPL/MSFT at 56/50/38 (partial-greeks) — re-sync clears it. |

**Concentration:** ⚠ **cluster (Mag-7) 61.3% — marginally over the 60% target** (was 55.7 on 07-15; crept up on mark drift + the withdrawal shrinking NLV, not new risk). MV top-5: AAPL 13.8, GOOGL 13.2, AMZN 13.0, SPY 12.2, MSFT 11.1 — no single name dominant. Not a trade trigger; watch it.

**Management signals (07-16 13:40, web_api, clean read):** All clean, no required trades. **NVDA Aug21 220C→240C rolled 07-16** (de-gamma, cleared the ACT) → roll/stop now NONE/SAFE. Only flag is GOOGL Jan'27 420C at Δ~0.39 = soft WATCH (optional up-and-out, not required; healthy name, earnings-clear). 3 matched verticals (AAPL/MSFT/AMZN) `vertical_exempt`. Briefing `actions: []`. **Hedge: core 8× Sep 745/700 + 1× Sep 745/650 + 5× Aug 710/665; `coverage_ok:false` is the RETIRED MV floor, ignore it. B-2 re-run scheduled for Aug 21 expiry.** MSFT de-risk codified via `e0669078` weekly_close_below 383 + `baa3bc98` ≥395 trim.

**Open book (18 legs, web_api-verified 07-16 post-NVDA-roll):** MSFT **Jan'28 310/450 vertical** + 465C residual · AAPL **Jan'28 240/420 vertical** · GOOGL LEAP 310C×1 / short **Jan'27 420C** · AMZN LEAPs 200C×2 / short Jan'28 280C+300C (verticals) · NVDA LEAP 170C / short **Aug21 240C** (rolled up from 220C 07-16, Δ0.14, pre-earnings) · SPY hedge **8× Sep 745/700** + 5× Aug 710/665 + 1× Sep 745/650 · OST (ignored). **Cash ~$26.4k USD + €0.4k EUR** — the €5.5k that was earmarked for VWCE seed 1 was **withdrawn to checking for the holiday 07-16**, so the seed is now UNFUNDED/deferred (would re-fund fresh from USD→EUR).

**Trade-outcomes store (n=9):** 07-08 logged: AMD Jul31 450/430 PCS close (−$16.83, de-gamma pre-CPI). 07-07: GOOGL trim (−$84) + MSFT 340C-unit salvage exit (−$1,979). ⚠ ARM/MU/V + June V/AMD closes = **permanent data gap** (journaled `e7e737c8`) — store stats are biased; per v3.11 §I use compliance scoring + base rates until n≥30.

**Universe/strategy (07-07):** **tier2 rotation sleeve added (14): RMD PYPL HCA CBRE GILD MSI RJF MA CVX XOM PG WMT COST TROW** (OptionsPlay 07-06 rotation thesis + TV watchlist). Preference rule: candidates tying on IVR/VRP → take the non-Mag-7 name until cluster ≤60%. `trader_profile` fixed live to income_seeker + real strategy list (closes the 21.6 runtime gap). NB **Jul 14 = CPI + JPM/BAC/C/WFC/GS/MS earnings same session** — bank IV doubly elevated; JPM post-crush entry is setup #1.

**⭐ TWO-BUCKET AMENDMENT ADOPTED 07-07 (`STRATEGY_AMENDMENT_TWO_BUCKET_2026-07-07.md`, → fold into strategy doc as v3.11):** Bucket A = **VWCE core, 20% of NLV (~$14k)** — seed 1 (~$5.5k USD→EUR→VWCE, Euronext, manual) goes on the NEXT trade-session order list; seed 2 post-CPI. Bucket B income book = **HYBRID: XSP base spreads (in universe macro) + ≤2-name post-earnings sleeve; pre-earnings single-name premium selling DISCONTINUED.** Open: B-2 hedge-floor formula at fold-in. Journaled `f17d6bc6`.

---

## Open Priorities / Action Items
**Recovery framing (now `archive/REVISED_RECOVERY_STRATEGY_2026-06-26.md`, archived 07-09 — superseded by the v4.0 growth mandate): the −$21.3k drawdown was 100% long mega-cap tech LEAPs + dead OST. v4.0's household caps + diversification now carry the de-concentration goal; the v3 engine income book stays green.**

1. **VWCE seed 1 — DEFERRED (unfunded).** The ~€5.5k that was earmarked for the seed was **withdrawn to checking for the holiday (07-16)** — EUR cash is now €0.4k. Re-funding is fresh from USD→EUR whenever the seed is revisited (Bucket A target 20% NLV); not an active item.
2. ✅ **DONE 07-12 — MSFT `weekly_close_below 383` alert created (`e0669078`)**, retires the manual Friday check. `baa3bc98` (≥395 trim) kept.
3. **New income entries: post-earnings only, XSP-first.** **Jul 14 = CPI + six big banks same session** — JPM post-crush entry (Jul 15+) is setup #1, JNJ second. XSP gates: index IVR ≥25 + VRP ≥3.5pp + contango (term currently FLAT → closed). Pacing is now dynamic in the briefing (band vix<18 → 2/wk; over-counted by untagged hedge journals — see Hard rules).
4. ✅ **DONE 07-15 — AAPL de-concentrated.** Closed 1 unit of the Jan'28 290/420 vertical (sold 290C long, bought back one 420C short) → clean 1×1 240/420 vertical. Verified live: AAPL β-DD **43.1% → 20.5%** (unfrozen, under both gates), concentration **20.3% → 12.6%** (under the 15% household cap), cluster **63.7% → 55.7%** (under 60%). Journal `4efb60a6`. (Historical: AAPL short first converted to the Jan'28 vertical 07-09, GOOGL 390C→Jan'27 420C — journals `42b73d54`/`74f8ec8a`.)
5. ✅ **DONE 07-15 — off-doctrine SPY tranche unwound.** Closed 4 of the 12 Sep 745/700 spreads (~7.95 credit) → 8× 745/700 + 1× 745/650 + 5× Aug 710/665 core retained. β-Δ restored **−185 → −124.5** (SPY contrib −255). `coverage_ok:false` is the RETIRED MV floor — ignore. Journal `72e52b5c` (hedge-tagged). Do NOT add more hedge; original B-2 re-run still scheduled for Aug 21 expiry. **JPM post-earnings entry SKIPPED 07-15** — failed §4 quality filter (liquidity grade D, 8–22% wide) + IV already crushed (IV/HV 0.83); pacing 0/2 so no cost to waiting.
6. ✅ **Candidates-route earnings-null fix DONE 07-08** (`route_candidates.py` wired + mapped) — **needs one `deploy_data_sources.sh` run**, then verify `get_candidates` shows "unverified". Stale duplicates deleted (route_settings/briefing/journal/options_analytics/pnl). Still open: profit-take 50-vs-80 decision (one click in Settings) · hedge-journal tagging · Parapet visual check of the conditional-alerts card · repo cruft (`main`, `.corrupt`).
7. **CPI Jul 14, PPI Jul 15, FOMC Jul 29, PCE Jul 30, NFP Aug 7.** OAuth Stage 2 still IBKR-side. **Manus is writing proposal v6** (has the corrections list: no-margin-debt fix + hedge-decay footnote).
   - ✅ **DONE 07-15: gateway watchdog PAUSE switch — deployed + smoke-tested live** (`gateway_watchdog.sh` skips probe/restart while `/home/ubuntu/.fortress-watchdog-pause` exists; log confirmed PAUSED→resumed). Trade-session ritual = `touch` the flag before IBKR Desktop, `rm` after (WORKFLOW §Trade Session Procedure Phase 2/3; SYSTEM.md §Gateway watchdog).
   - ⏳ **#1 data-trust flag — REDEPLOY PENDING (07-16).** First deploy 500'd the briefing: the OneDrive→WSL sync served an inconsistent `briefing.py` (compiled, but NameError at runtime — the compile-check can't catch that). **Reverted live via `git checkout app/routes/briefing.py` + restart; briefing is back on the pre-flag version.** The OneDrive `briefing.py` + `fortress_mcp_v452.py` edits are correct (verified). **To re-apply: FIRST `python3 -m py_compile /mnt/c/.../briefing.py` ON THE WSL MOUNT and confirm `grep -c data_trustworthy` = 7 (guards the sync-lag), THEN `bash deploy_data_sources.sh` + MCP relaunch** → verify `get_briefing.data_trustworthy` live. (`briefing.py`: top-level `data_trustworthy`/`data_trust_reason`; MCP: `_trade_safety`/`_with_safety` banner on `stage_order`/`preview_order`/`pretrade_check`/`get_pretrade_all`.) **LESSON: always py_compile on the WSL mount immediately before deploying OneDrive edits — the sync boundary is flaky and the deploy compile-check can't catch a NameError.**
   - ✅ **#2 Flex fills — DELIVERED (07-15).** Standalone `flex_fills.py` (stdlib, WSL) captures manual IBKR-Desktop fills the gateway `/trades` feed misses; ran end-to-end (reached IBKR, clean error on the placeholder token). Needs a one-time IBKR Flex Query + token (SYSTEM.md §Flex fills), then `python3 flex_fills.py`. · ✅ **#3 HANDOFF session-block trim DONE.** · Both new files (`flex_fills.py`, `gateway_watchdog.sh`) are NOT in `sync_check.sh` MAP — add them if they should be drift-tracked/repo-deployed.

8. **v4.0 two-leaf overlay — ✅ DASHBOARD SHIPPED (Sprint 28, 07-11: Parapet v4 + 12 visuals + read-only B-2 route). ADOPTION DECISIONS still open.** Review `docs/02_Household_Strategy_v4_0.md` (separate strategy; §7 = v3.11 diff map) + `docs/PROPOSAL_Two_Leaf_Dashboard_and_Docs_2026-07-09.md` (4-phase household layer) + `Combined_Portfolio.xlsx` (exposure + non-tech Candidates tab). Decide: **(a)** adopt v4.0 as a coexisting overlay? · **(b)** ✅ Phase-1 doc wiring DONE 07-09 — README index rewritten with the v3/v4/shared folders + both v4 docs registered; docs auto-drift-track (no `sync_check` MAP edit needed); `deploy_data_sources.sh` docs-copy made recursive · **(c)** ✅ obsolete-candidate docs archived: `REVISED_RECOVERY_STRATEGY_2026-06-26.md` (07-09) + `Fortress_Forward_Prognosis_2026-07-02.docx` (07-15); the 4 review-loop snapshots stay retained as the review record · **(d)** ✅ **Phase 2 (07-12, O-10) + Phase 3 (07-14, O-13) SHIPPED** — Phase 2: `/api/household[/overview|/concentration]`. Phase 3: `/api/household/uncap_stages` (per-LEAP stage 0–3 from live coverage + 4 §3.1 gates + verdict) + `/api/household/tail_hedge` (§5 far-OTM crash-put monitor, 0.75%-NLV/qtr budget). MCP tools `get_household_overview`/`_concentration`/`get_uncap_stages`/`get_tail_hedge`, all live (`source: live`). eToro snapshot in `quant/household_state.json`; engine untouched. **Phase 4 (scheduled diversification screen + Chrome eToro auto-ingest) still open. Adopting v4.0 as the standing overlay (a) remains the open decision** — shipping the read-only views does not commit to it. Note: household single-name 15% cap — **AAPL now 12.6%, UNDER the line after the 07-15 trim** (was over); the de-concentration served both v3.11 (β-DD) and v4.0 (household cap).

## Optimization backlog → **`BACKLOG_SPRINT_PLAN.md`** (full per-item plan + status)
- **Sprints 0–27 ALL SHIPPED** (0–24 archived in `archive/BACKLOG_COMPLETED.md`; 25/26/27 detail in the backlog file). Latest: **Sprint 26** (collar, profit-targets scan, Health Manager — deployed+verified 07-08) and **Sprint 27 "v3.11 wiring"** (vertical exemption, earnings-null, weekly-close alerts, dynamic pacing, β-DD block, MCP v4.12.0 — shipped+verified 07-08).
- **Open (small):** candidates-route earnings-null wire-up (`route_candidates.py` pulled) · hedge/roll journal tagging (pacing over-count) · profit-take 50-vs-80 decision · delete `route_settings.py` · Parapet visual check of the conditional-alerts card. **External:** OAuth Stage 2 (IBKR-side).

## Active Conditional Alerts
| ID | Ticker | Trigger | Status | Note |
|---|---|---|---|---|
| `baa3bc98` | MSFT | close_above 395 | Armed | **Trim-into-strength** — take the LEAP-trim tranche into a $395+ bounce rather than selling the low. |
| `e0669078` | MSFT | weekly_close_below 383 | Armed (07-12) | v3.11 weekly rule (Fri close <383 → cut the 310/450 vertical 50% Monday); fires on the Friday bar only. Supersedes the deleted daily 382/375 rules. Last Fri close 385.1 (07-10) — not triggered. |
| ~~`f9be085a`~~ | MSFT | close_below 382 | **DELETED 07-08** | Daily-close rule superseded by the ONE weekly rule. |
| ~~`de612a78`~~ | MSFT | close_below 375 | **DELETED 07-08** | Same — superseded by the weekly rule. |

---

## System Status (live 2026-06-15)
- Backend `fortress-dashboard-v4`: WSL, port 8081 (`sudo systemctl status fortress-dashboard-v4`)
- IBKR CP Gateway `cp-gateway`: Docker, iBeam headless, **web_api AUTHENTICATED** (account U7453366, OPRA live)
- **OAuth Stage 2: ❌ pending IBKR** (Priority 7) — don't trust `get_ibkr_status.oauth`
- MCP server live at `C:\Users\cityc.000\fortress_mcp\fortress_mcp.py` (dev copy: `fortress_mcp_v452.py`; repo: `~/fortress-mcp`). Write tools need `FORTRESS_MCP_ALLOW_WRITES=1`.
  - **Token now FILE-DRIVEN (2026-06-20):** `_resolve_api_token()` prefers `~/.fortress_api_token` over the env var. The plugin runs the MCP as a **Windows** process, so it reads **`C:\Users\cityc.000\.fortress_api_token`** (a Windows-side copy of the WSL secret). This immunizes against the stale token a per-session plugin `.mcp.json` was injecting (the 401 trap — the **6th** rotation place; runbook updated in `SYSTEM.md`). On rotation, write BOTH token files (WSL + Windows); the `.mcp.json`/desktop-config steps are no longer required. The live Windows MCP copy is drift-tracked in `sync_check.sh`.
  - **MCP now v4.12.0** (2026-07-08: empty-body-tolerant HTTP helpers — `delete_conditional_alert` no longer errors on success; 07-08 also verified Sprint 26 tools `get_profit_targets`/`get_risk_limits`/collar fields live). Earlier: Sprint 16 tools `get_ibkr_fills`, `get_position_opens`, `capture_position_snapshot`, `get_entry_conditions`; `get_ex_div`/`set_ex_div_events`; `check_liquidity` `short_leg`/`tradeable_spread_pct`.
- Parapet **v2.7 / Sprint 13** at `http://localhost:4000` (top-bar data-source badge live since 2026-06-19)
- QuantData JWT: `~/.quantdata-mcp/config.json` (refresh procedure in `WORKFLOW.md`)
- **TradingView MCP (NEW 2026-06-26):** `tradingview` server added to `claude_desktop_config.json` (`command: node`, `C:\Users\cityc.000\tradingview-mcp\src\server.js`). Reads the live TradingView Desktop chart via CDP. Use the **"Clean"** layout (TN Alerts v17 / Clean Decision Chart v3.2 / LuxAlgo S-R); `data_get_study_values` gives price/50-200SMA/WMA/LuxAlgo S-R/signals. Caveats: re-read once after a symbol switch (first read = TN only); `quote_get` ignores its symbol arg and returns the *chart* symbol; LuxAlgo pivots stale on trending names (use SMAs). Replaces the need for chart screenshots.

## OneDrive ↔ GitHub Sync (run `sync_check.sh` at every session wrap)
The OneDrive `2606Fortress` folder is the **dev/edit copy**; deploys copy files **into** the WSL repos (`~/fortress-v4-api`, `~/fortress-mcp`, …), which are what push to GitHub. A file edited in OneDrive but never re-deployed/committed leaves GitHub stale **while `git status` still looks clean** — this is how drift hides.
- **Detect drift:** `bash /mnt/c/Users/cityc.000/OneDrive/_Stocks26/2606Fortress/sync_check.sh` — content-diffs every mapped OneDrive→repo file and prints per-repo git status. Run it before ending any session. (Canonical repo copy: `~/fortress-v4-api/scripts/sync_check.sh`; it now self-checks via its own MAP entry.)
- **Parapet auto-tracked (2026-06-19):** `sync_check.sh` now derives the Parapet file list straight from `deploy_parapet.sh`'s `FILES=()` array — every frontend file the deploy copies is drift-checked automatically. To track a NEW Parapet file, add it to `deploy_parapet.sh`'s `FILES` and you're done (no second list).
- **Convention:** any NEW *backend* script created in OneDrive must be added to the `MAP` in `sync_check.sh` **and** (if backend-related) to `deploy_data_sources.sh`'s copy block, so it can never silently miss GitHub.
- **Runtime-state policy:** `iv_history.json`, `pending_orders.json`, `position_snapshots.json`, `entry_conditions.json` (last two NEW, Sprint 16), and `*.pre-ibkr-bak`/`*.pre-sprint0-bak` are transient — gitignore them. `conditional_alerts.json`, `macro_events.json`, `trade_outcomes.json` are config/data — commit them (the last re-appears as a diff as trades close; commit at session wrap).

## Documentation Index
**→ The master doc map is `README.md`** — every doc, its purpose, and its LIVING/SNAPSHOT status, kept current there (single source; this table was retired 2026-07-04 to avoid a second index that drifts). **Docs foldered 2026-07-09** (root / `v3/` engine / `v4/` household / `shared/` / `archive/`; README has the full map + the bare-name reference convention). Quick pointers: v3 engine spec = `v3/01_Portfolio_Strategy_v3_11.md`; v4 household overlay = `v4/02_Household_Strategy_v4_0.md`; daily workflow = `v3/WORKFLOW.md`; data source-of-truth = `shared/DATA_SOURCES.md`; system/deploy = `shared/SYSTEM.md`; dashboard = `shared/PARAPET.md`; backlog = `shared/BACKLOG_SPRINT_PLAN.md`; history = `SESSION_LOG.md` (root) + `archive/`. Live book state = `get_briefing` + the Current State table above (the old `PORTFOLIO.md` is archived).

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
**2026-07-16 (Thu — Cowork management + finish the optimizations).** **NVDA de-gamma roll** (Aug21 220C→240C, same expiry): the 220C short hit delta 0.43 (stop-loss ACT); rolled UP not out to stay pre-earnings (NVDA reports 08-26, Aug21 expires before it). Verified live: short Δ0.14, roll/stop now NONE/SAFE, book β-Δ −97.7. Journal `6e4a3b8f`. **Cash mystery solved:** the €5.5k EUR drop was a **withdrawal to checking for the holiday**, not a VWCE buy or a loss — so the ~$5k NLV dip is the withdrawal (ex-withdrawal the book rose ~$1.1k); VWCE seed now DEFERRED/unfunded. **Optimizations:** #3 HANDOFF session-block trimmed (06-29/06-30 preserved to archive); #2 `flex_fills.py` delivered (ran end-to-end); #1 data-trust flag **code-complete but its first deploy 500'd the briefing (OneDrive→WSL sync served an inconsistent file — compiles, NameError at runtime) → reverted via `git checkout briefing.py` + restart; REDEPLOY PENDING with a py_compile-on-WSL-mount gate** (Priority #7). Watchdog pause switch (07-15) deployed + smoke-tested. ⏳ Carryover: re-apply #1 flag (compile-gate first) · `sync_check.sh` + commit the docs/journal · VWCE deferred.

_Older session entries live in `SESSION_LOG.md` (most-recent-first) and, pre-2026-07-03, in `archive/SESSION_LOG_archive_thru_2026-07-03.md`. Keep only the single most-recent session here — the CLOSE protocol appends to `SESSION_LOG.md`, not this block._
