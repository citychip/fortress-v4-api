# Catalyst Gate — Macro-Event & News Layer Proposal

**v1.0 · 2026-06-16 · backend → MCP → Parapet · companion to Strategy v3.9 / Workflow v2.6**

Codifies and displays the rules the framework already states in prose — Strategy §4
binary-event timing ("wait 3–5 days after news-driven spikes"; earnings/macro
blackouts) — so they become a *surfaced, advisory* signal rather than a memory
check. **Advisory only: nothing here blocks a trade (§15.1). Backend computes and
surfaces; Parapet displays; Claude decides.**

This supersedes/implements the open **Sprint 14 backlog item #3 — "FMP economic
calendar → `intel.events` for the Briefing event horizon"** (see
`archive/HANDOFF_full_2026-06-15.md`), using the Claude-curated store pattern
(same as `earnings_blocklist.json`) instead of putting FMP/FRED credentials in the
backend.

---

## 1. Why (the gap)

- The macro-event defer rule lived only in prose + operator memory. On 2026-06-16
  the FOMC (Jun 17) was the decisive reason to defer new entries, yet nothing in
  the dashboard encoded it — exactly the case `PARAPET_V25_ANALYSIS.md` #87 cited.
- `DATA_SOURCES.md` §5 already says macro events (CPI/PPI/FOMC) are *"FMP/FRED MCP
  via Claude — not in backend,"* with the Briefing event horizon showing
  `intel.events` *"if backend ever provides them."* The display slot (Parapet #87)
  shipped in Sprint 13 but was never fed.
- Per-ticker news/sentiment had no home at all.

## 2. Design principles honored

| Principle | How this respects it |
|---|---|
| Advisory, not automated (§1, §15.1) | The gate emits a `defer_advisory` flag rendered **amber**. No path is disabled. |
| Claude is the brain; Parapet displays | Claude curates the calendar (it has FRED/FMP); backend stores/computes; Parapet only renders. No analysis logic in the frontend; no news reader / sentiment engine in Parapet (that interpretation stays Claude-side, per "What NOT to build"). |
| Settings-driven, no hardcode (#80) | `defer_days` is a query param (default 2) → promote to `settings.json` (§6). |
| Source-tagged + graceful (DATA_SOURCES) | Payload carries `source: claude_curated`, `stale`, `updated_at`; empty store returns cleanly, never 500. |
| Strategy doc > tool > memory | The gate references §4; thresholds are tunable but the rule is the doc's. |

## 3. Architecture

```
FRED / FMP (macro dates)  ──┐
                            │  Claude curates
                            ▼
        MCP set_macro_events(events)        [Tier-2 write]
                            │
                            ▼
   POST /api/options/macro-events  → data/macro_events.json   (backend store)
                            │
        GET /api/options/macro-events  → days_until + defer_advisory
              │                                   │
              ▼                                   ▼
   MCP get_macro_events()              Parapet getMacroEvents()
   (pre-trade narration)              (event-horizon row + amber defer banner)
```

## 4. What shipped in this change (2026-06-16)

### Backend — `options_analytics.py` (already-registered router; deploys via `deploy_data_sources.sh`)
- `GET /api/options/macro-events?defer_days=2` — reads the store, prunes past
  events, computes `days_until`, classifies impact (FOMC/CPI/PPI/NFP/PCE → high),
  returns `defer_advisory` + `defer_reason` + `nearest_high_impact`. Stdlib only;
  reuses `_utcnow`; NaN-safe; returns cleanly when the store is missing (`stale: true`).
- `POST /api/options/macro-events` — replaces the store from a curated
  `{events:[{label,date,impact?,note?}]}` body; drops invalid/dateless rows.
- Store path: `FORTRESS_MACRO_EVENTS` env or `~/fortress-v4-api/data/macro_events.json`.

### MCP — `fortress_mcp_v452.py` (v4.6.0)
- `get_macro_events(defer_days=2)` — Tier 1 read.
- `set_macro_events(events)` — Tier 2 write (needs `FORTRESS_MCP_ALLOW_WRITES=1`).

### Parapet — `lib/api.ts` + `pages/BriefingPage.tsx`
- `getMacroEvents()` + `MacroEvent`/`MacroEventsData` types.
- Event-horizon chip row now merges macro events with proximity coloring
  (high-impact ≤ defer window = red, other high = amber, lower = muted).
- New **amber "⚠ Catalyst defer"** banner under the regime banner when
  `defer_advisory` is true. Display-only; both files were already in the Parapet
  deploy list.

## 5. Deploy & seed

```bash
# 1. Backend (route rides in options_analytics.py — already copied by the script)
bash /mnt/c/Users/cityc.000/OneDrive/_Stocks26/2606Fortress/deploy_data_sources.sh

# 2. MCP (manual): copy dev → live, then fully quit + relaunch Claude Desktop
cp /mnt/c/Users/.../2606Fortress/fortress_mcp_v452.py  C:\Users\cityc.000\fortress_mcp\fortress_mcp.py

# 3. Parapet
bash /mnt/c/Users/cityc.000/OneDrive/_Stocks26/2606Fortress/deploy_parapet.sh

# 4. Seed the calendar (Claude, writes enabled): pull FRED/FMP dates and call
#    set_macro_events([... FOMC, CPI, PPI, NFP, PCE ...]) for the next ~6 weeks.
```

## 6. Follow-ups (next slices, not in this change)

1. **Settings promotion (#80):** move `defer_days` + a `news_spike_cooldown_days`
   (default 5, §4) into `settings.json` and read via `useThresholds()`; surface in
   System > Settings > Config.
2. **Pre-trade wiring:** add the `macro_event` advisory into `pretrade_check()` /
   `/api/manage/pretrade_all` so the Candidates gate badge shows an amber sub-flag.
   (Backend file lives on WSL, outside the repo mount — patch noted here.)
3. **Per-ticker news scan:** `/api/market/news/{ticker}` proxying QuantData
   `qd_get_news_articles` (FMP `news` fallback) + a backend "days since last
   material headline" signal (operationalizes the §4 cooldown). Passive "news <Nd"
   indicator chip on Candidates/Triage — *not* a reader.
4. **Social sentiment (situational):** LunarCrush via Claude for retail-driven
   names (MSTR-type) — Claude-side only.
5. **Automation:** a scheduled pre-event briefing note / conditional alert that
   fires when `defer_advisory` flips true.

## 7. Acceptance checks

- `GET /api/options/macro-events` returns `{events:[], defer_advisory:false, stale:true}`
  before seeding (no 500).
- After `set_macro_events([{label:"FOMC",date:"2026-06-17"}])`:
  `defer_advisory:true`, `defer_reason` cites FOMC, impact auto = high.
- Past-dated events are absent from the read.
- Parapet Briefing shows the amber defer banner + a red FOMC chip in the horizon.
- Empty/missing store and malformed rows never raise (graceful, NaN-safe).

## 8. Change log
- **v1.1 (2026-06-16):** Sibling profitability/reliability work shipped alongside:
  `get_vix_term` (VIX-vs-VIX3M term-structure regime input, backend + MCP v4.7.0);
  `journal_analytics.py` expectancy feedback loop (+ recommended journal schema
  enrichment: `ivr_at_entry`/`dte_at_entry`/`short_delta_at_entry`/`days_held`/`exit_reason`);
  NaN route smoke-test wired into `deploy_data_sources.sh`; FMP `dividends-calendar`
  verified on-tier → ex-div assignment-risk check documented in `WORKFLOW.md`.
  Follow-up #3 (per-ticker news scan) still open; dividends piece is done.
- **v1.0 (2026-06-16):** Initial backend route + MCP tools + Parapet display.
  Implements Sprint 14 #3 via the Claude-curated store pattern.
