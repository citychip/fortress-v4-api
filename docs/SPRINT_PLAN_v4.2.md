# Fortress Dashboard — Sprint Plan
**From:** v4.2 (2026-05-29) | **Next sprint:** v8.9

Based on gap analysis of VPS vs WSL, phase backlog, implementation status, and today's work.

---

## Priority Framework

- **P0 — Blocking:** Breaks daily trading workflow
- **P1 — High:** Significant data quality or risk management gap
- **P2 — Medium:** Useful but has a working workaround
- **P3 — Low:** Nice to have

---

## Sprint v8.9 — QuantData Per-Ticker Fix ⭐ (P1, ~2h)

The most impactful open issue. All `qd_*` MCP tools and workflow_02/06/07 return SPY data for every ticker.

**Root cause:** QuantData tool instances are saved per-ticker. Fetching per-ticker data requires `PUT /api/tool` (update tool filter) before the GET. The server proxy skips this step.

**Items:**

| ID | Task | File | Est. |
|---|---|---|---|
| QD-01a | Add `_qd_update_tool()` to `app/routes/qd.py` — mirrors `update_tool()` in workflow scripts | `app/routes/qd.py` | 30m |
| QD-01b | Call `_qd_update_tool()` before each `_qd_get()` in the proxy | `app/routes/qd.py` | 15m |
| QD-01c | Test: `qd_get_iv_rank("MSFT")` returns MSFT data (not SPY) | MCP + curl | 15m |
| QD-02a | workflow_02 (entry_scoring): verify GEX/OI/dark pool/flow return per-ticker data once QD-01 is fixed | `quant/workflow_02_entry_scoring.py` | 30m |
| QD-02b | workflow_06 (dark_pool_alert): same verification | `quant/workflow_06_dark_pool_alert.py` | 15m |
| QD-02c | workflow_07 (whale_flow): same verification | `quant/workflow_07_whale_flow_report.py` | 15m |

**AC:** `qd_get_iv_rank("MSFT")` via MCP returns MSFT IV rank ≠ SPY IV rank. workflow_06 alerts on real per-position dark pool data.

---

## Sprint v8.10 — IBKR Upload Retry (P2, ~45m)

Known issue K-03 from VPS backlog. If an IBKR snapshot upload fails mid-transfer, it must be re-uploaded manually.

| ID | Task | File | Est. |
|---|---|---|---|
| K-03 | Add `POST /api/ibkr/upload/retry` endpoint — re-runs last failed upload | `app/routes/ibkr.py` | 30m |
| K-03b | Add `retry_ibkr_upload` MCP tool (Tier 2) to `fortress_mcp.py` | `fortress_mcp.py` | 15m |

**AC:** `POST /api/ibkr/upload/retry` re-runs the upload without requiring a new file; MCP tool visible via `list_tools`.

---

## Sprint v8.11 — Ticker Universe Path Fix (P1, ~30m)

Scripts expect `~/ticker_universe.json` but the file lives in `~/fortress-v4-api/quant/ticker_universe.json`. Workflow scripts fall back to a hardcoded 11-ticker list instead of the live 19-ticker universe.

| ID | Task | File | Est. |
|---|---|---|---|
| DATA-01a | Create symlink: `ln -s ~/fortress-v4-api/quant/ticker_universe.json ~/ticker_universe.json` | WSL shell | 5m |
| DATA-01b | Same for earnings_blocklist.json | WSL shell | 5m |
| DATA-01c | Same for active_positions.json | WSL shell | 5m |
| DATA-01d | Update workflow scripts to use `pathlib.Path(__file__).parent` consistently instead of `Path.home()` for data files | `quant/workflow_*.py` | 15m |

**AC:** Running `workflow_01` uses all 19 tickers from `ticker_universe.json`, not the 11-ticker fallback.

---

## Sprint v8.12 — Regime Label Formatting (P2, ~30m)

Regime labels show as `SNAKE_CASE` in dashboard and MCP responses. Should be human-readable.

| ID | Task | File | Est. |
|---|---|---|---|
| UI-01 | Replace `BEARISH`, `NEUTRAL`, `BULLISH` with `Bearish`, `Neutral`, `Bullish` in regime synthesis | `app/routes/market_intelligence.py` | 15m |
| UI-02 | Ensure `vix_state` (`normal`, `elevated`, `extreme`) is already lowercase — confirm | `app/routes/briefing.py` | 10m |
| UI-03 | MCP `get_briefing()` response regime field — verify consistent casing | `fortress_mcp.py` | 5m |

**AC:** `get_briefing()` returns `"regime": "bearish"` (lowercase); no SNAKE_CASE in any MCP response.

---

## Sprint v8.13 — Forward P&L Panel Wire-Up (P2, ~1.5h)

The `/api/options/forward-pnl` endpoint exists but isn't wired to the Positions UI.

| ID | Task | File | Est. |
|---|---|---|---|
| UI-10 | Wire `ForwardPnLPanel` component to `/api/options/forward-pnl` in PositionsPage | `fortress-v4-frontend` | 1h |
| UI-11 | Add `get_forward_pnl` to MCP Tier 1 tools if not already present | `fortress_mcp.py` | 30m |

**AC:** Positions page shows forward P&L projection; MCP `get_forward_pnl()` returns data.

---

## Sprint v8.14 — QuantData Auto-Refresh (P2, ~2h)

Currently, QuantData sessions expire and require manual re-login via Settings. Automate this.

| ID | Task | File | Est. |
|---|---|---|---|
| QD-10 | Check if `qd_refresh_session.py` in quant/ works and what it does | `quant/qd_refresh_session.py` | 15m |
| QD-11 | Add APScheduler job to run session refresh daily at 06:00 ET | `app/scheduler/runner.py` | 30m |
| QD-12 | Add `POST /api/settings/quantdata_login_refresh` endpoint if missing | `app/routes/settings.py` | 30m |
| QD-13 | After refresh, copy config to `/root/.quantdata-mcp/config.json` automatically | scheduler job | 15m |
| QD-14 | Dashboard notification when QD session expires (amber banner) | `fortress-v4-frontend` | 30m |

**AC:** QuantData session refreshes automatically; no manual intervention needed unless credentials change.

---

## Sprint v8.15 — IV Crush Schedule Automation (P2, ~30m)

IV crush report runs manually. Should run daily pre-market.

| ID | Task | File | Est. |
|---|---|---|---|
| AUTO-01 | Add `iv_crush` to APScheduler pre-market group (08:30 ET Mon–Fri) | `app/scheduler/runner.py` | 15m |
| AUTO-02 | Add `premarket` scan to APScheduler pre-market group (08:45 ET Mon–Fri) | `app/scheduler/runner.py` | 10m |
| AUTO-03 | Verify `max_pain` is already scheduled or add it (15:00 ET) | `app/scheduler/runner.py` | 5m |

**AC:** Candidates data is refreshed automatically each morning before market open without manual trigger.

---

## Sprint v8.16 — IBKR OAuth Activation Follow-Through (P1, when ready)

ibind OAuth 1.0a is built and configured. Blocked on IBKR activating the consumer key at their weekend server restart. When activated:

| ID | Task | File | Est. |
|---|---|---|---|
| IBKR-01 | Toggle `ibkr_use_ibind_oauth = true` in Settings → Security | Dashboard | 5m |
| IBKR-02 | Verify `get_ibkr_status()` shows `authenticated: true` without daily login | MCP | 10m |
| IBKR-03 | Monitor for 48h — confirm auto-reconnect works | Ops | — |
| IBKR-04 | Update ops docs: remove "daily login required" note | `docs/FORTRESS_V4_MASTER_DOC.md` | 10m |

**AC:** IBKR connection maintained headlessly; no daily browser login needed.

---

## Deferred / Later

These are valid but low-urgency given current operational state:

| Item | Reason deferred |
|---|---|
| MySQL migration (P4-01 through P4-09) | JSON files work correctly; migration adds complexity with no immediate operational gain |
| Redis/SSE stream (P4-02, P4-26) | Polling works; SSE would improve responsiveness but not critical |
| Docker Compose (P6-01) | WSL systemd setup is working fine |
| GitHub Actions CI/CD for frontend | Manual build + deploy works |
| DTE exception registry CRUD (P4-23) | Config-editable manually; no UI needed urgently |

---

## Sprint Order Summary

| Sprint | Focus | Priority | Est. |
|---|---|---|---|
| **v8.9** | QuantData per-ticker fix | P1 | ~2h |
| **v8.10** | IBKR upload retry | P2 | ~45m |
| **v8.11** | Ticker universe path fix | P1 | ~30m |
| **v8.12** | Regime label formatting | P2 | ~30m |
| **v8.13** | Forward P&L panel | P2 | ~1.5h |
| **v8.14** | QuantData auto-refresh | P2 | ~2h |
| **v8.15** | IV crush + premarket schedule | P2 | ~30m |
| **v8.16** | IBKR OAuth follow-through | P1 | ~30m (when ready) |

**Total estimated effort: ~8h active work**

---

*Sprint plan maintained at `docs/SPRINT_PLAN_v4.2.md`. Update as sprints complete.*
