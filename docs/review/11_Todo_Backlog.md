# Fortress Dashboard — Todo Backlog

**Last updated: 2026-05-05**

This is the single source of truth for all open build items, known issues, and deferred work. Items are grouped by category and prioritised within each group. Completed items are moved to the "Done" section at the bottom.

---

## Priority Legend

| Symbol | Meaning |
|---|---|
| 🔴 | Blocking — affects live trading decisions or data integrity |
| 🟠 | High — significant operational impact; fix within 1 sprint |
| 🟡 | Medium — improves reliability or workflow; fix within 1 month |
| 🟢 | Low — nice-to-have; backlog |

---

## 1. Security & Infrastructure

| # | Priority | Item | Notes |
|---|---|---|---|
| S-02 | 🟡 | **Decommission legacy IB Gateway container** | `gnzsnz/ib-gateway` container is stopped but still present. Remove once CP Gateway soak window passes (week of 2026-05-19). |
| S-03 | 🟠 | **UFW lockdown on port 8080** | Restrict to home IP only: `sudo ufw allow from [HOME_IP] to any port 8080`. Currently open to all. |
| S-04 | 🟡 | **Tailscale or VPN for multi-device access** | Enables dashboard access from phone/tablet without public exposure. See VPS Guide §5.2. |
| S-05 | 🟡 | **HTTPS reverse proxy (Caddy or nginx)** | TLS termination + HTTP basic auth or OAuth in front of uvicorn. Out of scope until Bearer token is deployed. |

---

## 2. Dashboard — Known Bugs

| # | Priority | Item | Notes |
|---|---|---|---|
| B-01 | ✅ | **Theta and vega now live** | Resolved 2026-05-05. All four Greeks (delta/gamma/theta/vega) populate via Web API + OPRA. |
| B-02 | 🟡 | **qty=0 legs persist in sync list** | IBKR sync writes zero-quantity legs that were closed but not yet purged. Add a post-sync filter: `positions = [p for p in positions if p.get("qty", 0) != 0]`. |
| B-03 | 🟡 | **Confirm SPY hedge FX conversion uses live rate** | Field `spy_hedge_coverage.target_min/max` is now in USD ($22K–$33K) per Strategy v3.6 §2.D. Confirm FX conversion in `ibkr_sync_web/greeks.py` is using the live rate from `fx.py` and not a hardcoded EUR value. (`ibkr_sync.py` is archived — legacy TWS path.) |
| B-05 | 🟢 | **Position notes disabled for IBKR-synced positions** | Notes editing is disabled to avoid clobbering on next sync. Consider a merge strategy: preserve notes field across syncs unless explicitly overwritten. |

---

## 3. Dashboard — New Features (Tier 1.5 API Surface)

These four endpoints are required to support the new Tier 1.5 MCP tools approved in Strategy v3.6.

| # | Priority | Item | Endpoint | Notes |
|---|---|---|---|---|
| F-01 | 🟠 | **Portfolio Beta-Weighting endpoint** | `GET /api/manage/portfolio_beta` | Computes beta-weighted delta for the entire book relative to SPY. Beta values sourced from yfinance. Returns: `{beta_weighted_delta, spy_equivalent_shares, hedge_gap, positions: [{ticker, beta, raw_delta, beta_weighted_delta}]}`. See MCP Proposal §2 Tier 1.5. |
| F-02 | 🟠 | **Sector Exposure endpoint** | `GET /api/manage/sector_exposure` | Aggregates net MV by GICS sector. Sector classification sourced from yfinance `info.sector`. Returns: `{sectors: [{sector, net_mv, pct_of_netliq, tickers}], dominant_sector, dominant_pct, flag_threshold: 80}`. |
| F-03 | 🟠 | **Capital Efficiency endpoint** | `GET /api/manage/capital_efficiency` | Returns BP utilisation, per-position ROC (annualised premium / margin used), and idle capital. Returns: `{buying_power_used_pct, idle_capital_usd, positions: [{ticker, margin_used, premium_collected_30d, roc_annualised}]}`. |
| F-04 | 🟠 | **Earnings Volatility endpoint** | `GET /api/manage/earnings_volatility/{ticker}` | Compares current implied move (ATM straddle / spot) against last 4 earnings actual moves. Returns: `{ticker, implied_move_pct, historical_moves: [...], avg_historical_move_pct, implied_vs_historical_ratio, recommendation}`. Data from yfinance + QuantData. |

---

## 4. MCP Server — Build Items

| # | Priority | Item | Notes |
|---|---|---|---|
| M-06 | 🟢 | **SSE transport wrapper** | For mobile/phone access via Claude in a browser tab. Deferred until Tier 1 is stable. |

---

## 5. Operational Runbooks (Documentation Gaps)

| # | Priority | Item | Notes |
|---|---|---|---|
| O-01 | 🟠 | **VPS down during market hours — fallback procedure** | Document manual fallback: use IBKR directly, note which decisions require dashboard data vs can be made without. Add to `operations/04_Incident_Recovery_Playbook.md`. |
| O-02 | 🟠 | **QuantData API 401 token refresh runbook** | Document: where the token is stored, how to refresh it, how to verify the fix, how to re-run the failed script. Add to `operations/04_Incident_Recovery_Playbook.md`. |
| O-03 | 🟡 | **Gateway crash recovery procedure** | Steps to restart the CP Gateway (voyz/ibeam) container, re-authenticate IBKR Mobile push, re-run IBKR sync, confirm Greeks are populated. |
| O-04 | 🟡 | **Automated alert: notify when gateway disconnects** | Currently silent failure. Add a health-check cron or systemd watchdog that sends a notification (email or webhook) when `GET /api/ibkr/status` returns `connected: false` for >5 minutes. |

---

## 6. Strategy & Workflow Enhancements

| # | Priority | Item | Notes |
|---|---|---|---|
| W-01 | 🟡 | **Scale-out workflow prompts** | Add prompts for partial position exits (trim 20–30% per §6 LEAPS Profit-Taking) to `07_MCP_Workflow_and_Prompts_v1_1.md`. |
| W-02 | 🟡 | **Review far-dated short call exceptions** | MSFT Dec'26 $480, MSFT Sep'18 $520, VST Sep'26 $200 are flagged as rule exceptions in Strategy §5. Evaluate whether to roll to compliant DTE or formally document as permanent exceptions. |
| W-03 | 🟡 | **Automated earnings calendar refresh** | Schedule `POST /api/calendar/fetch-earnings` to run weekly (e.g., Sunday 08:00 ET) via the orchestrator, rather than requiring manual trigger from the Universe tab. |
| W-04 | 🟡 | **Non-tech sector expansion** | UNH PCS added (May 2026). Remaining: evaluate LLY, MS, GS, JPM, XOM, OXY for PMCC or PCS entries to reduce sector correlation per Strategy §3.2 and §7. |
| W-05 | 🟢 | **Pacing budget visualisation** | Add a weekly pacing chart to the Briefing tab showing entries per week over the last 8 weeks vs the 2/week soft cap. |

---

## 7. Review & Governance

| # | Priority | Item | Notes |
|---|---|---|---|
| R-01 | 🟡 | **First quarterly strategy review** | Use `review/10_Strategy_Review_Template.md`. Schedule for end of Q2 2026 (June 30). |
| R-02 | 🟡 | **Journal outcome metrics expansion** | Current metrics: total realized P&L, PCS hit rate, framework violations. Add: average hold time per strategy, roll success rate (net credit achieved), post-earnings playbook accuracy. |
| R-03 | 🟢 | **Backtesting framework** | The dashboard is explicitly not a backtesting platform (Build Spec §1.2). If backtesting is desired, evaluate a separate tool (e.g., QuantConnect, Backtrader). Not in scope for current build. |

---

## Done

| D-22 | Workflow Test Suite 24/24 PASS | All procedures in 03_Trading_Workflow_v2_8.md tested against live system | 2026-05-08 |
| D-23 |  endpoint | 4-gate pre-trade gate: hard exclusion, earnings blackout, concentration, VIX state | 2026-05-08 |
| D-25 | IB Gateway fully decommissioned | Docker removed, TWS code stubs cleaned,  backend removed from all routes/settings/state | 2026-05-09 |
| D-24 | Workflow automation scripts | daily_workflow.py, stop_loss_scan.py, roll_scan.py, pre_trade_gate.py, eod_report.py | 2026-05-08 |
 (Completed Items)

| # | Item | Completed |
|---|---|---|
| D-01 | Phase 1 — read-only dashboard (briefing, positions, candidates, calendar) | 2026-04-xx |
| D-02 | Phase 2 — write CRUD (alerts, journal, calendar) | 2026-04-xx |
| D-03 | Phase 3 — IBKR Gateway direct sync | 2026-04-xx |
| D-04 | Phase 3 — TradingView Lightweight Charts widget (Manage tab) | 2026-04-xx |
| D-05 | Phase 3 — Earnings auto-fetcher | 2026-04-xx |
| D-06 | Phase 4 — Stop-loss aggregator | 2026-05-04 |
| D-07 | Phase 4 — Roll candidate evaluator | 2026-05-04 |
| D-08 | Phase 4 — Post-earnings playbook | 2026-05-04 |
| D-09 | Phase 4 — Jade Lizard credit gate | 2026-05-04 |
| D-10 | Phase 4 — SPY hedge MV tracker | 2026-05-04 |
| D-11 | Phase 4 — Pre-trade gate checker | 2026-05-04 |
| D-12 | Phase 4 — Portfolio Greeks aggregation | 2026-05-04 |
| D-13 | BS-from-yfinance delta fallback | 2026-05-04 |
| D-14 | EUR/USD FX conversion layer | 2026-05-04 |
| D-15 | Hard-exclusion gate (§3.3) | 2026-05-04 |
| D-16 | Per-leg IBKR records + aggregator | 2026-05-04 |
| D-17 | Strategy v3.6 — stop-loss 4-level scale, SPY hedge USD target, Tier 1.5 tools | 2026-05-05 |
| D-18 | Documentation package v2 consolidation (12 files, grouped structure) | 2026-05-05 |
| D-19 | Bearer token middleware + Settings tab + Central Config Store | 2026-05-05 |
| M-01 | Bearer token middleware on `/api/*` | 2026-05-05 |
| M-02 | Build Tier 1 MCP server (19 read tools + 9 write tools) | 2026-05-05 |
| M-03 | Write claude_desktop_config.json snippet + install README | 2026-05-05 |
| M-04 | Settings tab conflicts resolved (DOM panel, dead widget, schema fix) | 2026-05-05 |
| M-05 | Tier 2 write tools built (env-gated, FORTRESS_MCP_ALLOW_WRITES=1) | 2026-05-05 |
| D-20 | Editable Universe tab (add/remove/move/exclude tickers inline) | 2026-05-05 |
