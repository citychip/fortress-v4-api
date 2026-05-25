# Fortress Dashboard — Todo Backlog

**Updated:** May 18, 2026

---

## Completed (Sprint v7.x — May 2026)

| ID | Item | Resolved |
|---|---|---|
| ✅ O-01 | Candidates All-tab showed empty state when API returned 0 rows | Sprint v7.1 — frontend fallback shows all 19 universe tickers as monitoring rows |
| ✅ O-02 | QuantData credential refresh required SSH access | Sprint v7.1 — Settings → QuantData Credentials UI writes to both config files. Full runbook in `operations/04_Incident_Recovery_Playbook.md` §5 |
| ✅ O-03 | `chart.py` used deprecated `tool/OPTIONS_*` QuantData endpoints (400 errors, account revocation risk) | Sprint v7.1 — replaced with widget-UUID REST endpoints matching `market_intelligence.py` pattern |
| ✅ O-04 | Market Intel page crashed with `TypeError: Cannot read properties of null (reading 'toFixed')` | Sprint v7.1 — null guard on `current_price` |
| ✅ O-05 | Market Intel had no sort, no per-card refresh, no metric explanations | Sprint v7.1 — sort dropdown, per-card refresh button, and hover tooltips added |
| ✅ O-06 | Candidates All-tab only showed actionable signals; monitoring tickers not visible | Sprint v7.0 — All tab now shows full 19-ticker universe with actionable at top and monitoring below divider |
| ✅ O-07 | Documentation stale across 9 files after Sprint v7.x | May 18, 2026 — all docs updated to v3.7/Sprint v7.1 baseline |

---

## Active Backlog

### High Priority

| ID | Item | Notes |
|---|---|---|
| P-01 | **QuantData OAuth 2.0** — eliminate manual credential refresh entirely | QuantData may offer a proper OAuth flow. Investigate their API docs. Would remove the recurring O-02 class of incidents. |
| P-02 | **Automated IV Crush workflow schedule** — currently manual trigger only | Add a cron job on the VPS to run `workflow_05_iv_crush_report.py` at 09:00 ET on weekdays. Requires valid QuantData credentials. |

### Medium Priority

| ID | Item | Notes |
|---|---|---|
| P-03 | **IBKR OAuth 2.0** — eliminate CP Gateway daily push approval | IBKR is rolling out OAuth 2.0 for the Web API. Monitor their developer portal. |
| P-04 | **Strategy Workspace UI** — scenario planning | A page where the trader can model hypothetical positions (add/remove legs) and see the impact on portfolio Greeks, concentration, and delta bias before committing. |
| P-05 | **Vol analytics panel** — IV term structure, skew chart | Per-ticker IV term structure (30/60/90 DTE IV) and put/call skew chart. Requires QuantData IV history endpoint. |

### Low Priority

| ID | Item | Notes |
|---|---|---|
| P-06 | **Trade journal export** — CSV/PDF download | Allow exporting the journal to CSV or PDF for tax/review purposes. |
| P-07 | **Roll calculator UI** — interactive roll modeller | A modal on the Positions tab that shows the P&L impact of rolling a position to different strikes/expiries. |
| P-08 | **Multi-account support** — separate IBKR accounts | Currently assumes a single IBKR account. Would require account-level filtering on all position/Greeks endpoints. |

---

## Deferred / Won't Do

| ID | Item | Reason |
|---|---|---|
| D-01 | Real-time WebSocket streaming for Greeks | IBKR Web API polling at 60s is sufficient for the strategy's time horizon. WebSocket adds complexity without meaningful benefit. |
| D-02 | Mobile app | The dashboard is used at a desktop workstation. Responsive design improvements are sufficient. |
