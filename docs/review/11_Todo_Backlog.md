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

---

## Completed (V4 Sprints — May 26, 2026)

| ID | Item | Resolved |
|---|---|---|
| ✅ V4-K01 | OPRA 21-char symbol padding — silent wrong-greeks on option lookups | Sprint v8.6 — `app/services/opra.py` normalises all symbols at sync + load time |
| ✅ V4-K02 | Config backup/restore missing — any write could corrupt settings with no recovery | Sprint v8.4 — `POST /api/config/backup` + `POST /api/config/restore` + auto-backup on every write |
| ✅ V4-K04 | Journal close linkage — no FK between close and open trade entries | Sprint v8.8 — `POST /api/journal/close/{id}` stamps `open_entry_id`, `iv_crush_realized`, `dte_at_close`; back-links open entry |
| ✅ V4-P01 | Portfolio endpoints missing — no beta, sector-exposure, or capital-efficiency data | Sprint v8.5 — `GET /api/portfolio/beta`, `/sector-exposure`, `/capital-efficiency` |
| ✅ V4-P02 | APScheduler not wired — 8 workflows ran manually only | Sprint v8.3 — BackgroundScheduler auto-runs briefing, IBKR sync, backup, reports |
| ✅ V4-P03 | MySQL data layer not wired — `fortress_v4` DB existed but routes used JSON only | Sprint v8.7 — positions + greeks written on every IBKR sync; `GET /api/positions` reads MySQL first |
| ✅ V4-P04 | Null guard missing on `current_iv` / `current_theta` in PositionsPage | Hotfix — `!= null` guard applied to both V3 and V4 frontends |
| ✅ V4-CI | GitHub Actions CI/CD pipeline broken (SSH action CDN failure + GITHUB_TOKEN 403) | Fixed — inline SSH setup + `git pull` on VPS; all 4 repos now have working pipelines |

## Completed (V4 Sprints — May 30, 2026)

| ID | Item | Resolved |
|---|---|---|
| ✅ V4-K03 | IBKR upload retry | v8.10 — `POST /api/ibkr/upload/retry` + `retry_ibkr_sync()` MCP tool |
| ✅ V4-F01 | Forward P&L panel | v8.13 — wired to PositionsPage |
| ✅ V4-F02 | Regime label formatting | v8.12 — Title Case throughout |
| ✅ P-02 | Automated IV Crush + premarket schedule | v8.15/v8.16 — APScheduler at 07:00 ET and every 30 min |
| ✅ V4-QD | QuantData auto-refresh | v8.15 — `qd_refresh_session.py` runs daily at 06:00 ET |
| ✅ V4-SEC | Security hardening | 2026-05-30 — /api/token localhost-only, CORS restricted, sensitive files gitignored |
| ✅ V4-THEME | Colour constant deduplication | 2026-05-30 — `lib/theme.ts` single source of truth, 16 files updated |
| ✅ V4-MI | Market Intel portfolio/universe split | 2026-05-30 — portfolio tickers shown first with position badges |
| ✅ V4-MI-CACHE | Market Intel server-side cache | 2026-05-30 — 5-min TTL, Refresh All button |

## Active Backlog — V4 Remaining

| ID | Priority | Item | Notes |
|---|---|---|---|
| V4-QD-TICKER | Low | QuantData per-ticker proxy | Won't fix — architectural limitation. update_tool (PUT) pattern proven broken. Future path: per-ticker tool instances via POST /api/tool. See MASTER_DOC §6 |
| V4-F03 | Low | `qd_status()` MCP tool | 30m — check if QD credentials are valid before calling qd_* |
| V4-F04 | Low | Regime badge colour | 30m — red → amber/green based on direction |
| V4-F05 | Low | DTE countdown on Earnings rows | 30m |
| V4-F06 | Low | Colour-coded Quick Nav cards | 1h |
| V4-F07 | Medium | Split SettingsPage.tsx (1,692 lines) | 3h — extract sub-components |
| V4-F08 | Medium | Split AnalysisPage.tsx (1,469 lines) | 3h — extract sub-components |
| V4-F09 | Low | Standardise backend logging | 2h — print() → logger.* |
| V4-F10 | Low | Frontend unit tests | 1 day — msw-based hooks |
| V4-F11 | Low | MySQL migration alerts/journal | 2 days — currently JSON files |
