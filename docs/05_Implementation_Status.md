# Fortress Dashboard — Implementation Status

**Snapshot:** 2026-05-31 | **Strategy:** v3.7.2 | **Dashboard:** Fortress V4 (WSL) | **Frontend:** v8.51

---

## Live Components

| Component | Status | Version | Notes |
|---|---|---|---|
| **FastAPI backend** | ✅ Live | v1.2.0 | `fortress-dashboard-v4.service` on port 8081 (WSL) |
| **React frontend** | ✅ Live | v8.51 | Served by nginx at localhost:80. Source: `~/fortress-v4-frontend/` |
| **MCP server** | ✅ Live | v1.2 | `C:\Users\cityc.000\fortress_mcp\fortress_mcp.py`. Connected to Claude Desktop. |
| Bearer token auth | ✅ Live | — | All `/api/*` endpoints require `Authorization: Bearer <token>` |
| CP Gateway (voyz/ibeam) | ✅ Live | latest | Docker container `cp-gateway`. Daily browser login. |
| IBKR Greeks | ✅ Live | Web API | Δ/Γ/Θ/V live when OPRA subscribed. BS fallback when closed. |
| IBKR Web API auto-sync | ✅ Live | — | Background task, 60s polling. Manual trigger via MCP `trigger_ibkr_sync` |
| Market Intelligence | ✅ Live | — | `/api/market-intelligence` — GEX, DP floors, Net Drift, regime score |
| Conditional Alerts | ✅ Live | Phase 7 | Evaluate every 5min (market hours), 30min off-hours. Manual via Scripts tab. |
| Action Queue | ✅ Live | Phase 4 | `/api/action-queue/summary` — 60s cache. Sidebar badge. |
| Roll Alternatives | ✅ Live | Phase 5 | IBKR live chain + yfinance fallback. 3 proposals (Conservative/Balanced/Aggressive) |
| Strategy Selector | ✅ Live | Phase 6 | BS pricing at Δ0.20, regime fit score 0–5, Recommended badge |
| Sub-clustering | ✅ Live | post-50 | 7 strategy types: PMCC, PCS, BCS, CCS, IC, STR/STD, CC. Structural detection. |
| QuantData integration | ✅ Live | — | JWT auth. Auto-refreshes at 06:00 ET. 401 errors use report file fallback. |
| APScheduler | ✅ Live | v8.3 | 8 auto workflows. In-process alert evaluation. |
| MySQL data layer | ✅ Live | v8.7 | Positions + greeks written on every IBKR sync. MySQL-first read. |

---

## Navigation (current)

| Tab | Path | Contents |
|---|---|---|
| Briefing | `/` | Overview (Priority Orders + badge) · Market Intel · Earnings |
| Portfolio | `/portfolio` | Positions · P&L · Journal |
| Trade | `/trade` | Landing (positions + candidates) · Trade Builder (7 steps) · Orders |
| Analysis | `/analysis` | Chart · Vol Analytics |
| System | `/config` | Strategy · Settings · Scripts · Monitor |

---

## Strategy Tab — Zone Architecture (v8.51)

| Zone | Content |
|---|---|
| Zone 1 | Trader Profile: persona cards + custom persona editor, risk/objective dropdowns, active strategies checklist, live narrative |
| Zone 2 | Ticker Universe: Tier 1/2, Macro/Index, Excluded (tiered, managed via VPS ticker_universe.json) |
| Zone 3 | Strategy Rules: 4 groups — Entry Filters, Risk Limits, Position Sizing, Credit Minimums. Number inputs only. |
| Zone 4 | Volatility Regime Playbook: IV×GEX matrix, regime-based strategy recommendations |
| Right col | Exploratory Sandbox: payoff curve, Capital Efficiency table, Export to Trade Builder |

---

## Key Components

| Component | File | Notes |
|---|---|---|
| Strategy Rules | `components/settings/StrategySection.tsx` | Single source of truth for all strategy parameters. No slider version. |
| Persona Editor | `components/PersonaEditorPanel.tsx` | Fork/edit/apply custom personas. Override tracking with ↺ reset. Diff dialog. |
| Strategy Sandbox | `components/StrategySandbox.tsx` | Used in Trade tab (workflow) AND StrategyPage right col (exploratory). Different use cases — both kept. |
| Config Context | `contexts/ConfigContext.tsx` | Includes `CustomPersona` type, `customPersonas[]`, `activeCustomPersonaId`, CRUD methods |
| App shell | `App.tsx` | Sidebar pin/unpin (click logo), regime tint on status bar |

---

## Known Issues

| ID | Severity | Description | Status |
|---|---|---|---|
| K-01 | Low | CP Gateway session expires every ~24h. ibeam re-authenticates; requires IBKR Mobile push approval. | Acceptable — daily login. |
| K-02 | Low | QuantData JWT expires periodically. | Mitigated — Settings → QuantData Auto-Login re-writes JWT. |
| K-03 | Low | IBKR ibind OAuth 2.0 pending activation by IBKR. | Monitoring IBKR developer portal. |

---

## Pending / Backlog

| ID | Priority | Item |
|---|---|---|
| S11-01 | Low | Keyboard shortcuts (B/P/T/A/C/Esc) |
| S11-02 | Medium | Move PersonaEditorPanel → Settings tab |
| P-04 | Medium | Scenario planning — model hypothetical positions, impact on Greeks/concentration/delta |
| P-01 | High | QuantData OAuth 2.0 — eliminate manual credential refresh |
| P-05 | Low | Vol analytics — IV term structure, skew chart |
| P-06 | Low | Trade journal export (CSV/PDF) |

---

## Version History

| Date | Version | Summary |
|---|---|---|
| 2026-05-31 | v8.51 | Sprint 10: custom persona editor, Strategy tab restructured (4 zones), Settings = Connections+System only, Config→System rename, sidebar pin/unpin, regime chip tint, Strategy Rules unified (no sliders) |
| 2026-05-31 | v8.50 | Sprint 9: earnings banner, position sizing, journal prompt, mark actioned, config→Trade Builder wiring, floor-anchored strikes, Briefing redesign |
| 2026-05-31 | post-50 | Sprint 8: 5-tab nav, lazy loading, Portfolio P&L chips, Analysis panels, sub-clustering, page splits |
| 2026-05-30 | v4.3 | Market Intel cache, retry_ibkr_sync MCP tool |
| 2026-05-29 | v4.2 | QD proxy, workflow yfinance IVR fallback |
| 2026-05-28 | v4.0 | ibind OAuth, dual-token auth, CP Gateway allowlist |
