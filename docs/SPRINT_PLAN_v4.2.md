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

| Sprint | Focus | Priority | Status |
|---|---|---|---|
| **v8.9** | QuantData per-ticker fix | P1 | ❌ Won't fix — architectural limitation (see FORTRESS_V4_MASTER_DOC.md §6) |
| **v8.10** | IBKR upload retry | P2 | ✅ Done (2026-05-30) |
| **v8.11** | Ticker universe path fix | P1 | ⏳ Pending |
| **v8.12** | Regime label formatting | P2 | ⏳ Pending |
| **v8.13** | Market Intel cache + Refresh All button | P2 | ✅ Done (2026-05-30) |
| **v8.14** | Market Intel portfolio/universe split | P2 | ✅ Done (2026-05-30) |
| **v8.15** | QuantData auto-refresh | P2 | ⏳ Pending |
| **v8.16** | IV crush + premarket schedule | P2 | ⏳ Pending |
| **v8.17** | IBKR OAuth follow-through | P1 | ⏳ When ready |

**Total estimated effort: ~8h active work**

---

*Sprint plan maintained at `docs/SPRINT_PLAN_v4.2.md`. Update as sprints complete.*

---

## Session Fixes — v8.25 (2026-05-30)

| ID | Task | File | Status |
|---|---|---|---|
| FIX-01 | Null-guard on account metrics (Net Liq / Excess Liq / Available Funds show `—` when IBKR offline) | `DashboardPage.tsx` | ✅ Done |
| FIX-02 | IBKR status route switched from `/api/ibkr/status` (buggy) to `/api/ibkr/capability` | `useApi.ts` | ✅ Done |
| FIX-03 | Duplicate `stroke` attribute on `<Line>` in StrategySandbox removed | `StrategySandbox.tsx` | ✅ Done |
| FIX-04 | Backend logging audit — `app/` routes already use `logger.*`; CLI scripts use `print` intentionally | — | ✅ Confirmed clean |

---

## Trade Flow Redesign — v8.26–v8.32

Full spec: `docs/TRADE_FLOW_REDESIGN.md`

### v8.26 — Phase 1: Deep-link wiring (P1, ~3h)
| ID | Task | File | Est. |
|---|---|---|---|
| TF-01 | Add Roll / Close / Add buttons to Portfolio position groups | `PortfolioPage.tsx` | 1h |
| TF-02 | Parse `?ticker`, `?mode`, `?leg` URL params in Trade tab | `TradePage.tsx` | 30m |
| TF-03 | Ticker dropdown: active positions (urgency-ordered, with context) + undeployed universe below divider | `TradePage.tsx` | 45m |
| TF-04 | Mode selector: New Entry / Add / Roll / Close — auto-set from URL param | `TradePage.tsx` | 30m |
| TF-05 | State reset `useEffect` on ticker/mode change — flush leg, preview, proposals, sandbox | `TradePage.tsx` | 15m |

**AC:** Clicking Roll on any position lands in Trade with ticker, mode, and leg pre-set. Zero re-selection.

### v8.27 — Phase 2: Collapsible position groups (P2, ~2h)
| ID | Task | Est. |
|---|---|---|
| TF-10 | Group Portfolio positions by ticker + strategy; collapsible cards | 1.5h |
| TF-11 | Header: net delta, concentration %, strike range, expiry, alert dot | 30m |

### v8.28 — Phase 3: Move Sandbox to Trade (P1, ~2h)
| ID | Task | Est. |
|---|---|---|
| TF-20 | Extract StrategySandbox from AnalysisPage; mount in Trade tab | 1h |
| TF-21 | Connect sandbox to selected ticker + mode on arrival | 1h |

### v8.29 — Phase 4: Action Queue in Briefing (P1, ~3h)
| ID | Task | Est. |
|---|---|---|
| TF-30 | Backend: `GET /api/action-queue` — aggregates roll_all + stop_loss_all + candidates | 1h |
| TF-31 | Backend: `GET /api/action-queue/summary` — cached integer count (60s TTL) | 30m |
| TF-32 | Frontend: Action Queue panel in Briefing Overview; each row "→ Trade" deep-link | 1h |
| TF-33 | Sidebar badge: polls `/api/action-queue/summary` only | 30m |

### v8.30 — Phase 5: Roll alternatives engine (P1, ~4h)
| ID | Task | Est. |
|---|---|---|
| TF-40 | Backend: fetch IBKR options chain for ticker + expiry range | 1h |
| TF-41 | Expiry nearest-match function (round to highest-OI monthly/weekly cycle) | 30m |
| TF-42 | Score candidates: net credit, OTM buffer, delta, DTE extension → return top 3 | 1.5h |
| TF-43 | Frontend: proposals panel (Conservative / Balanced / Aggressive) | 1h |

### v8.31 — Phase 6: Strategy selector (P2, ~3h)
| ID | Task | Est. |
|---|---|---|
| TF-50 | Live strategy comparison: PMCC / PCS / diagonal — credit, margin, PoP, IVR suitability | 2h |
| TF-51 | Add mode: show existing position as context; sandbox models combined result | 1h |

### v8.32 — Phase 7: Conditional alerts system (P2, ~4h)
| ID | Task | Est. |
|---|---|---|
| TF-60 | Alert types: price ≥/≤, P&L %, DTE ≤, delta ≥, conditional entry | 1h |
| TF-61 | "Set Alert" button on any recommendation in Briefing / Action Queue | 1h |
| TF-62 | Portfolio: alerts sub-section per position group | 1h |
| TF-63 | Trade: post-order alert suggestion step | 1h |

---

## v8.26 — Phase 1: Deep-link wiring (COMPLETED 2026-05-30)

| ID | Task | Status |
|---|---|---|
| TF-01 | Roll / Close / Add buttons on Portfolio position groups | ✅ Roll + Build buttons wired |
| TF-02 | Parse `?ticker`, `?mode`, `?leg` URL params in Trade tab | ✅ Done via `useSearch()` in TradePage |
| TF-03 | Ticker dropdown: active positions (urgency-ordered) + undeployed universe below divider | ✅ positionContextMap in TickerSelector |
| TF-04 | Mode selector: New Entry / Add / Roll / Close — auto-set from URL param | ✅ Done |
| TF-05 | State reset `useEffect` on ticker/mode change | ✅ Done with `isFirstRender` ref guard |

**Commit:** `5b483e0` on `fortress-v4-frontend`

**Notes:**
- Found and fixed a second `/trade-builder` link (Build button on ticker group header) during testing
- `positionContextMap` destructuring bug caught and fixed during QA
- `/trade-builder` route kept as legacy fallback; primary route is now `/trade?ticker&mode&leg`
