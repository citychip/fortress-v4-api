# Fortress — Session Log
**Chronological session history, most recent first. `HANDOFF.md` keeps only the latest 1–2; older detail lives in `archive/SESSION_LOG_archive_thru_2026-07-03.md`, and pre-2026-06-15 in `archive/HANDOFF_full_2026-06-15.md`.**

## Entry template — keep entries SHORT (3–6 lines, not an essay)
> **YYYY-MM-DD (focus):** what shipped (1–2 lines) · deploy/commit refs (hashes) · verified (1 line) · ⚠ open follow-ups (1 line) · trades (P&L or "none").

---

- **2026-07-05 (Sprint 26 — risk-manager hardening from the Manus AI v5.0 proposal; code-complete, needs deploy/relaunch/build):**
  - **26.2 full collar** — `covered_call_candidates` extended with a DTE-matched protective put (`_collar_protective_put`, BS put-by-delta ~0.25Δ) + `collar_net`; Recovery table gains Buy-put / Collar-net columns.
  - **26.3 manage-at-50% + 21-DTE** — `GET /api/manage/profit_targets` + MCP `get_profit_targets` (short-leg scan: ≥50% capture via avg_cost vs mark, or ≤21 DTE) + Recovery "Manage now" card.
  - **26.1 Health Manager** — `GET /api/manage/risk_limits` + MCP `get_risk_limits` (USD-cash −15k floor, excess-liq 25k floor, stale-data, breach flags, fail-safe) + config keys + **`margin-debt-alert`** scheduled task (weekday 09:03) + Recovery Health-Manager banner. ⏳ deferred: Discord/Slack webhook, scheduler/latency monitors.
  - ⚠ Needs: `deploy_data_sources.sh` + `deploy_parapet.sh` + sync `fortress_mcp_v452.py` → Windows path + relaunch. Then verify `get_covered_call_candidates` shows collar fields, `get_profit_targets`, `get_risk_limits`. · Trades: none.

- **2026-07-05 (Sprint 25 close-out — all remaining items + follow-ons; deployed + verified):**
  - **25.13** JPM/JNJ/MU/CSX Candidates fix — 3rd layer (`state.parse_crush_report_markdown` `int("-")` crash) deployed; board back to 25 rows (commit `7261951`).
  - **25.1 gateway watchdog** BUILT + INSTALLED + VALIDATED — `gateway_watchdog.sh` + systemd unit. First probe (curl `/v1/api/tickle`) false-negatived a healthy gateway (IBKR Akamai bounces raw `/v1/api/*` with "Bad Request"); corrected to read iBeam's own log state (`docker logs | grep "running and authenticated"`) + an UNKNOWN state that never restarts. Live-confirmed iBeam auto-re-auths on restart (`IBEAM_ACCOUNT/PASSWORD` set). Commits `e33e56c`.
  - **25.9/23.3** covered-call recommender — `GET /api/manage/covered_call_candidates` + MCP `get_covered_call_candidates` (reuses tested `strategy_metrics` PMCC leg). Live: AMZN 270C Δ0.28 $533, GOOGL 395C Δ0.28 $787 (Δ reconciles: base 0.30 − 0.05 IVR + 0.03 conc). **+ Recovery-page panel** (follow-on).
  - **25.6 follow-on** cluster-glide **history line** — `cluster_history.json` store (`POST/GET /api/manage/cluster_history`, upsert-by-date) + MCP `get_cluster_history` + recharts line on Recovery vs ≤60% target.
  - **25.8c** candlestick drill-down on TechnicalPage (`MtfCandleChart.tsx`, recharts floating-bar; 200w + GEX walls + DP floor overlays). Parapet `tsc && vite build` clean.
  - **Cleanups:** stale/negative earnings-days → blank (`state.days_to_earnings`, also fixed a latent options.py:738 gap-risk bug); HANDOFF alert-table refreshed to the MSFT close-confirmed ladder.
  - Commits `ffa57d3` + `e33e56c` (`fortress-v4-api`). ⚠ Follow-ups: relaunch MCP (new `get_covered_call_candidates` + `get_cluster_history`); hit **Sync** on System page (session live again); OAuth Stage 2 still IBKR-side. · Trades: none.

- **2026-07-03/04 (multi-sprint session — Sprints 21, 22, 25 + docs reorg; all deployed + live-verified):**
  - **Sprint 21 "Monetize & gate":** inverted call-bisection bug fixed (MSFT PMCC short $780→$425 with real credit); adaptive short-call delta (21.1b); singular `recommended` + `annualized_yield` (21.2); canonical `regime_gate` (21.3); concentration warn-gate (21.5); weekly-200 "Thesis Stop" trend gate (21.4); persona/strategies align (21.6-lite).
  - **Sprint 22 "Multi-timeframe":** `weekly/daily/monthly_trend_state` + `get_technical_gate` (22.1/22.4a); backend `1mo`/`4h` chart intervals (22.5); data-source sync-age badge (22.3); MTF procedure v1.1 (22.2); Parapet **Technical panel** (22.4b).
  - **Sprint 25 "Reliability / visibility / de-concentration":** chart cache + gate parallelization (25.2/25.3); **Recovery page** = cluster-glide gauge + capital-efficiency heatmap (25.6/25.7); MSFT close-below Thesis-Stop alert ladder (25.10); JPM/JNJ income diversification + LEAP call-writing playbook §8 (25.9); MTF disposition polish (25.8); briefing `regime_gate` (25.4); `refresh_iv_data` async (25.5); `leap_roll_all` route+tool (25.11); `vega-flip-alert` scheduled task (25.12). **Only 25.1 (gateway reliability) remains.**
  - **Docs:** consolidation started — `README.md` master index; OneDrive root cleared; stale/shipped archived; this log reformatted + split.
  - Commits across `fortress-v4-api` / `-parapet` / `-mcp`; every deploy green (compile + rollback) and live-verified. ⚠ Follow-ups: relaunch the writes-enabled MCP (new `get_leap_roll_all` + async `refresh_iv_data`); Run-now `vega-flip-alert` once to pre-approve its tool. · Trades: none.

---

Older entries (2026-06-19 → 2026-07-03) → **`archive/SESSION_LOG_archive_thru_2026-07-03.md`**.
