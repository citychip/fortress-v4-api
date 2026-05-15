# Todo Backlog

**Last updated: 2026-05-15**

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
| S-03 | 🟠 | **UFW lockdown on port 8080** | Restrict to home IP only: `sudo ufw allow from [HOME_IP] to any port 8080`. Currently open to all. |
| S-04 | 🟡 | **Tailscale or VPN for multi-device access** | Enables dashboard access from phone/tablet without public exposure. See VPS Guide §5.2. |
| S-05 | 🟡 | **HTTPS reverse proxy (Caddy or nginx)** | TLS termination + HTTP basic auth or OAuth in front of uvicorn. |

---

## 2. Dashboard — Known Bugs

| # | Priority | Item | Notes |
|---|---|---|---|
| B-02 | 🟡 | **qty=0 legs persist in sync list** | IBKR sync writes zero-quantity legs that were closed but not yet purged. Add a post-sync filter: `positions = [p for p in positions if p.get("qty", 0) != 0]`. |
| B-05 | 🟢 | **Position notes disabled for IBKR-synced positions** | Notes editing is disabled to avoid clobbering on next sync. Consider a merge strategy: preserve notes field across syncs unless explicitly overwritten. |

---

## 3. Dashboard — New Features (Tier 1.5 API Surface)

These four endpoints are required to support the new Tier 1.5 MCP tools approved in Strategy v3.6.

| # | Priority | Item | Endpoint | Notes |
|---|---|---|---|---|
| F-01 | 🟠 | **Portfolio Beta-Weighting endpoint** | `GET /api/manage/portfolio_beta` | Computes beta-weighted delta for the entire book relative to SPY. Beta values sourced from yfinance. Returns: `{beta_weighted_delta, spy_equivalent_shares, hedge_gap, positions: [{ticker, beta, raw_delta, beta_weighted_delta}]}`. |
| F-02 | 🟠 | **Sector Exposure endpoint** | `GET /api/manage/sector_exposure` | Aggregates net MV by GICS sector. Returns: `{sectors: [{sector, net_mv, pct_of_netliq, tickers}], dominant_sector, dominant_pct, flag_threshold: 80}`. |
| F-03 | 🟠 | **Capital Efficiency endpoint** | `GET /api/manage/capital_efficiency` | Returns BP utilisation, per-position ROC (annualised premium / margin used), and idle capital. |
| F-04 | 🟠 | **Earnings Volatility endpoint** | `GET /api/manage/earnings_volatility/{ticker}` | Compares current implied move (ATM straddle / spot) against last 4 earnings actual moves. Data from yfinance + QuantData. |

---

## 4. MCP Server — Build Items

| # | Priority | Item | Notes |
|---|---|---|---|
| M-02 | 🟠 | **Add Tier 1.5 tools to MCP server** | `get_portfolio_beta_risk`, `get_sector_exposure`, `get_capital_efficiency`, `get_earnings_volatility_data`. Requires F-01 through F-04 to be built first. |
| M-05 | 🟡 | **Build Tier 2 write tools** | `add_alert`, `delete_alert`, `update_calendar`, `add_excluded_ticker`, `trigger_ibkr_sync`. Env-var-gated (`FORTRESS_MCP_ALLOW_WRITES=1`). |
| M-06 | 🟢 | **SSE transport wrapper** | For mobile/phone access via Claude in a browser tab. Deferred until Tier 1 is stable. |

---

## 5. Operational Runbooks (Documentation Gaps)

| # | Priority | Item | Notes |
|---|---|---|---|
| O-01 | 🟠 | **VPS down during market hours — fallback procedure** | Document manual fallback: use IBKR directly, note which decisions require dashboard data vs can be made without. Add to `operations/04_Incident_Recovery_Playbook.md`. |
| O-02 | 🟠 | **QuantData API 401 token refresh runbook** | Document: where the token is stored, how to refresh it, how to verify the fix, how to re-run the failed script. Add to `operations/04_Incident_Recovery_Playbook.md`. |
| O-03 | 🟡 | **Gateway crash recovery procedure** | Steps to restart the IB Gateway container, verify health, re-run IBKR sync, confirm Greeks are populated. |
| O-04 | 🟡 | **Automated alert: notify owner when gateway disconnects** | Currently silent failure. Add a health-check cron or systemd watchdog that sends a notification when `/api/ibkr/status` returns `connected: false` for >5 minutes. |

---

## 6. v2 Dashboard — Open Features

| # | Priority | Item | Notes |
|---|---|---|---|
| V-01 | 🟠 | **Historical earnings overlay on Analysis chart** | Backend only stores `next_earnings`. Add `GET /api/calendar/{ticker}/history` using `yfinance.Ticker.earnings_dates` to return past earnings dates for multi-marker chart overlay. |
| V-02 | 🟠 | **Live option chain viewer on Analysis page** | IBKR Web API supports full chain access (expirations, strikes, conids, live Greeks/IV snapshot). Build a chain table on Analysis for strike selection before entry. |
| V-03 | 🟡 | **Keyboard shortcuts** | `useEffect` in `App.tsx` mapping keys `1`–`8` to sidebar nav tabs and `R` to refresh. One-hour change with significant daily-use value. |
| V-04 | 🟡 | **Roll candidate link to P&L** | Clicking a roll candidate row navigates to `/pnl` with the ticker pre-filtered (mirrors the Analysis deep-link already built for post-earnings rows). |
| V-05 | 🟡 | **Auto-run Connection Health checks on Settings mount** | Currently both IBKR and QuantData tests require a manual click. Auto-fire both on Settings page open for instant status on every visit. |
| V-06 | 🟡 | **Positions page Greeks column** | Add a collapsible Greeks row under each ticker card on the Positions page showing per-leg delta, gamma, theta, vega inline. |
| V-07 | 🟡 | **IV surface heatmap on Analysis** | 2D heatmap (strike × expiry, IV% as colour intensity) using live IBKR chain data. Visualises skew and term structure at a glance. |
| V-08 | 🟡 | **Scheduled morning briefing email** | Wire the existing email generation code in DashboardPage to a scheduled heartbeat job that fires at 08:30 ET and sends the trade report via Gmail/Outlook MCP. |
| V-09 | 🟢 | **Ticker command palette (Cmd+K)** | Keyboard-accessible command palette that lets the user type a ticker and jump directly to the Analysis tab. |
| V-10 | 🟢 | **Earnings → Outlook Calendar sync** | Button on the Earnings tab that creates Outlook Calendar events for all upcoming earnings dates using the `outlook_calendar_create_events` MCP tool. |
| V-11 | 🟢 | **Pre-trade strike suggester using live chain** | Wire the Candidates page strike suggestion panel to live IBKR chain data instead of estimated values. |

---

## 7. Strategy & Workflow Enhancements

| # | Priority | Item | Notes |
|---|---|---|---|
| W-01 | 🟡 | **Scale-out workflow prompts** | Add prompts for partial position exits (trim 20–30% per §6 LEAPS Profit-Taking) to `mcp/09_MCP_Workflow_and_Prompts_v2.md`. |
| W-02 | 🟡 | **Review far-dated short call exceptions** | MSFT Dec'26 $480, MSFT Sep'18 $520, VST Sep'26 $200 are flagged as rule exceptions in Strategy §5. Evaluate whether to roll to compliant DTE or formally document as permanent exceptions. |
| W-03 | 🟡 | **Automated earnings calendar refresh** | Schedule `POST /api/calendar/fetch-earnings` to run weekly (e.g., Sunday 08:00 ET) via the orchestrator, rather than requiring manual trigger from the Universe tab. |
| W-04 | 🟢 | **Non-tech sector expansion** | Evaluate UNH, LLY, MS, GS, JPM, XOM, OXY for PMCC or PCS entries to reduce sector correlation per Strategy §3.2 and §7. |
| W-05 | 🟢 | **Pacing budget visualisation** | Add a weekly pacing chart to the Briefing tab showing entries per week over the last 8 weeks vs the 2/week soft cap. |

---

## 8. Review & Governance

| # | Priority | Item | Notes |
|---|---|---|---|
| R-01 | 🟡 | **First quarterly strategy review** | Use `review/10_Strategy_Review_Template.md`. Schedule for end of Q2 2026 (June 30). |
| R-02 | 🟡 | **Journal outcome metrics expansion** | Current metrics: total realized P&L, PCS hit rate, framework violations. Add: average hold time per strategy, roll success rate (net credit achieved), post-earnings playbook accuracy. |
| R-03 | 🟢 | **Backtesting framework** | The dashboard is explicitly not a backtesting platform (Build Spec §1.2). If backtesting is desired, evaluate a separate tool (e.g., QuantConnect, Backtrader). Not in scope for current build. |

---

## Done (Completed Items)

| # | Item | Completed |
|---|---|---|
| D-01 | Phase 1 — read-only dashboard (briefing, positions, candidates, calendar) | 2026-04-xx |
| D-02 | Phase 2 — write CRUD (alerts, journal, calendar) | 2026-04-xx |
| D-03 | Phase 3 — IBKR Gateway direct sync | 2026-04-xx |
| D-04 | Phase 3 — TradingView Lightweight Charts widget | 2026-04-xx |
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
| D-18 | Documentation package v2 consolidation | 2026-05-05 |
| D-19 | Bearer token middleware implementation (S-01) | 2026-05-05 |
| D-20 | Editable Universe tab — add/remove/move/exclude tickers from UI | 2026-05-05 |
| D-21 | Mode 4 — Trader Personas & Expanded Strategy Catalogue (24 strategies, 5 personas) | 2026-05-09 |
| D-22 | Mode 5 — Public GitHub release, codebase sanitisation, install.sh, CI/CD | 2026-05-09 |
| D-23 | IBKR Web API migration — CP Gateway (voyz/ibeam), per-leg live Greeks via OPRA | 2026-05-09 |
| D-24 | Settings tab v2 — Security section, Backup & Restore, Strategy tab readability | 2026-05-09 |
| D-25 | fix: fetchEarningsDates() bare fetch() missing Authorization header (v3.6 patch) | 2026-05-15 |
| D-26 | fix: SPY hedge classifier broadened to count untagged SPY puts | 2026-05-15 |
| D-27 | feat: Post-earnings candidates section in Trade Report (v2 dashboard) | 2026-05-15 |
| D-28 | feat: Roll candidates DTE countdown ring (v2 dashboard) | 2026-05-15 |
| D-29 | feat: Greeks Summary panel on Analysis page (v2 dashboard) | 2026-05-15 |
| D-30 | feat: Earnings date overlay on Analysis price chart (v2 dashboard) | 2026-05-15 |
| D-31 | feat: Deep-link navigation from Dashboard roll/post-earnings rows to Analysis (v2 dashboard) | 2026-05-15 |
| D-32 | feat: Settings sync indicator (SyncBadge) in Settings page header (v2 dashboard) | 2026-05-15 |
| D-33 | feat: Connection Health panel in Settings — IBKR and QuantData ping tests (v2 dashboard) | 2026-05-15 |
| D-34 | fix: Null-safety hardening on all .toFixed() calls on nullable fields (v2 dashboard) | 2026-05-15 |
| D-35 | feat: New MCP scripts — mcp_briefing, mcp_full_analysis, mcp_gex2, mcp_position_analysis2 | 2026-05-15 |
| D-36 | S-02 resolved — IBKR Read-Only API enabled; theta/vega now live via OPRA | 2026-05-15 |
| D-37 | M-01 resolved — Tier 1 MCP server built and deployed (fortress_mcp) | 2026-05-09 |
| D-38 | M-03 resolved — claude_desktop_config.json snippet and install README written | 2026-05-09 |
| D-39 | M-04 resolved — End-to-end Tier 1 MCP tools tested in Claude Desktop | 2026-05-09 |
