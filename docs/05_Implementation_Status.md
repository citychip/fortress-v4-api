# Fortress Dashboard — Implementation Status

**As of 2026-05-13 — All UX/Automation improvements (A-M), Trade Reports Tab, and Dashboard/Positions Tab Merge deployed**

This document is the single source of truth for what's actually deployed on the VPS. It supersedes whatever the spec docs say when reality diverges. Replaces the 2026-05-09 version.

---

## Deployment

VPS: `srv1321374` (76.13.138.194), Ubuntu 26.04 LTS, account `ubuntu`.

**Two systemd services running:**
- `fortress-dashboard.service` — uvicorn on `0.0.0.0:8080`, app at `/home/ubuntu/Fortress_Dashboard/app/`
- `fortress_orchestrator.service` — APScheduler driving the QuantData workflow scripts

**Docker containers:**
- `cp-gateway` (`voyz/ibeam:latest`) on host port 5000 — **active broker integration**, authenticated to account U7453366, healthy. Replaces the legacy TWS Gateway.
- *(Legacy `ib-gateway-ib-gateway-1` is `docker compose down`d. Code path remains for diagnostics; container not running.)*

**Working directory layout:**

```
/home/ubuntu/Fortress_Dashboard/
├── app/
│   ├── main.py
│   ├── routes/      # 15 modules: briefing, positions, candidates, calendar,
│   │                #              universe, alerts, journal, uploads, run,
│   │                #              manage, ibkr, playbook, chart, earnings_fetch,
│   │                #              settings (new)
│   ├── services/    # state, ocr, chain, roll, stop_loss, playbook, ibkr_sync,
│   │                #  ibkr_sync_web (new), ibkr_sync_synthetic (new),
│   │                #  bs_fallback, fx, config_store (new)
│   │   └── ibkr_web/    # client, session, snapshot, portfolio, capability (new pkg)
│   └── static/      # index.html, app.js, phase4.js, chart.js, settings.js (new),
│                    #  style.css, phase4.css
├── quant/           # state files + reports + workflow scripts +
│                    #  fortress_config.json (new — settings)
├── ib-gateway/      # legacy TWS gateway compose (stopped)
├── cp-gateway/      # CP Gateway (voyz/ibeam) compose (new) + conf/conf.yaml
├── docs/            # this consolidated documentation set
├── venv/
└── _phase4_backup_2026-05-03/
```

`FORTRESS_DATA_DIR` env var → `/home/ubuntu/Fortress_Dashboard/quant`.

---

## Phase status

| Phase | Status | Notes |
|---|---|---|
| 1 — read-only briefing/positions/candidates/calendar/universe | ✅ Live | Net-MV concentration math correct; aggregator collapses per-leg into one row per ticker. |
| 2 — write CRUD (alerts, calendar, journal, universe) | ✅ Live | Universe CRUD added (`/api/universe/add\|move\|exclude*`); alerts PATCH added. |
| 3 — uploads (OCR + chart annotations) | ✅ Live (legacy fallback) | Superseded in practice by Web API direct sync. |
| 3 — IBKR Gateway direct sync (TWS path) | ⚠ Stopped | TWS code remains; container down. New default is Web API. |
| 3 — TradingView Lightweight Charts widget | ✅ Live | DP/GEX overlays from QuantData reports. |
| 3 — Earnings auto-fetch | ✅ Live | `POST /api/calendar/fetch-earnings`. Universe tab button. |
| **3 (new) — IBKR Web API + CP Gateway** | ✅ Live | `voyz/ibeam` container; `/api/ibkr/capability`; per-leg Greeks via OPRA. **Active backend.** |
| 4 — stop-loss aggregator | ✅ Live | 3-signal logic per Strategy §6. |
| 4 — roll candidate evaluator | ✅ Live | Top-3 candidates + IBKR ticket text. |
| 4 — post-earnings playbook | ✅ Live | §10 matrix + §7 high-conc override + thesis health gate. |
| 4 — Jade Lizard credit gate (Strategy §2.E) | ✅ Live | Hard FAIL if credit ≤ width. |
| 4 — SPY hedge MV tracker (Strategy §2.D) | ✅ Live | USD-native target. |
| 4 — pre-trade gate checker | ✅ Live | §3.3 → §4 → §7 → §7 (excl/earnings/conc/VIX). |
| 4 — Portfolio Greeks aggregation | ✅ Live | **All four Greeks live** when web_api backend active. |
| **4.5 (new) — Settings tab + config_store** | ✅ Live | Schema-driven editor; live-tunable thresholds; `fortress_config.json` is canonical. |
| **4.5 (new) — Backend dispatcher** | ✅ Live | `cfg("technical.greeks_backend")` ∈ {auto, web_api, bs_yfinance, tws_ibkr}. |
| **4.5 (new) — Mode 3: Live Strategy Narrative** | ✅ Live | `GET /api/settings/narrative` → 4 paragraphs + observations + what-if. Rendered in Settings tab above the form. |
| **4.6 (new) — Security toggles + runtime guards** | ✅ Live | `security.use_ibkr_web_api` and `security.use_quantdata` in Settings → Security. Amber banners in UI. Runtime guards in `/api/ibkr/sync`, `/api/run/{script}`, `/api/chart/{ticker}`, `/api/manage/stop_loss/{id}`. |
| **5 (new) — Header UI / Sync** | ✅ Live | Sync dot/text, auto-refresh rename to Live, IBKR auto-sync background task, QuantData test. |
| **6 (new) — Manage/Trade Batch** | ✅ Live | Auto-run stop-loss/roll tables, pre-trade matrix, Positions colour coding. |
| **| 7 (new) — Dashboard / Journal | ✅ Live | Live alerts banner from Position Monitor, Journal auto-populate from sync, time-of-day scripts. **Positions tab merged into Dashboard.** |
| **8 (new) — Trade Reports Tab** | ✅ Live | New tab with new trade, roll, buy, sell evaluation reports. |
| **9 (new) — Market Intelligence Skill** | ✅ Live | `/api/market-intelligence` endpoint aggregating live GEX, DP, and Net Drift for the MCP tool. |

---

## Architecture changes since 2026-05-04 status

### IBKR Web API + CP Gateway (Phase 3, primary broker integration)

`voyz/ibeam` container running CP Gateway at `https://localhost:5000` is the new live broker integration. Replaces the legacy TWS Gateway (which had a known dialog-popup issue corrupting Greeks).

**Stack:**
- `app/services/ibkr_web/` package: `client.py` (httpx wrapper, `/tickle` session-token cookie), `session.py`, `portfolio.py`, `secdef.py`, `snapshot.py`, `capability.py`.
- `app/services/ibkr_sync_web.py` — sync producing same per-leg schema as the legacy TWS path but with all four Greeks (delta/gamma/theta/vega/IV/mark) when OPRA is subscribed.
- `app/services/ibkr_sync_synthetic.py` — `bs_yfinance`-only path that refreshes BS deltas against the existing book without touching the broker.
- `app/services/bs_fallback.py` — runs after every sync; respects `current_delta_source == "web_api"` (skip override when broker-sourced is good); fills nulls.

**Result:** 25 of 26 option positions now have authoritative IBKR Greeks. Portfolio Greeks reports delta/theta/vega all non-zero (was delta-only previously).

**Operational:** CP Gateway session expires every ~24h. `voyz/ibeam` re-authenticates automatically but requires an IBKR Mobile push approval each cycle. Capability badge in the header shows session state in real-time.

### Settings system (Phase 4.5)

`fortress_config.json` (in `quant/`) is the canonical runtime config. Sections:
- **security** — `use_ibkr_web_api` (default `true`), `use_quantdata` (default `true`), IBKR account ID, QuantData API key/base URL, CP Gateway URL/SSL/timeout, API token hint. **(NEW v1.8.2)**
- **strategy** — sizing, concentration, deltas, DTE, SPY hedge, stop-loss, playbook bands, credit minimums, VIX thresholds. **`delta_critical_threshold = 0.35`** (was 0.40 in v3.5).
- **technical** — VPS / IBKR / CP Gateway connection params, **`greeks_backend`** (auto / web_api / bs_yfinance / tws_ibkr), data dirs, FX cache TTL.
- **alerts** — delta watch/act, MV drawdown, DTE, concentration alert thresholds.
- **ui** — tab default, refresh interval, theme, currency display, date format, timezone.

`app/services/config_store.py` provides `cfg("strategy.delta_critical_threshold")` etc. for any module to read live values without restart.

`app/routes/settings.py` exposes:
- `GET /api/settings` → `{config: {...}}`
- `GET /api/settings/schema` → `{schema: {section: [field, ...]}}` for the UI
- `PUT /api/settings/{section}` body `{values: {key: value, ...}}`
- `POST /api/settings/reset` → factory defaults

`app/static/settings.js` renders a schema-driven Settings tab. Inline save per section.

### USD-native thresholds (Strategy v3.6 §7)

Briefing's account block now compares USD account values directly against USD floors:
- `available_funds_floor_usd` = 17000
- `excess_liq_floor_usd` = 25000

EUR equivalent shown alongside as informational. Frontend `renderAccountStats` displays `target >$25K · ok` / `target >$17K · ok`.

### Tighter delta critical threshold (Strategy v3.6 §5)

`strategy.delta_critical_threshold = 0.35` (was 0.40). Read by `state._normalize_delta_state`, `state.aggregate_positions_by_ticker`, `positions.compute_delta_state`. Tunable via Settings tab without code deploy.

### IBKR Read-Only API (account-level)

Enabled in IBKR Account Management → Settings → API → Settings on May 5, 2026. Stops the dashboard popup that was corrupting TWS Greeks; benefits CP Gateway too.

### CP Gateway IP-allowlist patch

The default `clientportal.gw/root/conf.yaml` only allowed `172.17.0.*` (Docker default bridge). Our compose creates a `172.18.*` network. Patched the `ips.allow` list to `[10.*, 172.*, 192.*, 127.0.0.1]` and mounted as `/srv/clientportal.gw/root/conf.yaml:ro`. Without this patch, all `/v1/api/*` calls from outside the container return "Access Denied".

---

### UX Phase 2 — Dashboard and Positions tab merge (May 13, 2026)

The standalone "Positions" tab was removed. Its content (the active book table) was moved into the **Dashboard** tab directly below the Account Stats row.
The Dashboard tab now presents a unified view:
1. Account stats (Net Liq, Excess, Available, Cash)
2. Active book (full positions table)
3. Macro regime / Pacing / Concentration cards
4. Today's Actions
5. PCS Exposure (if active)
6. Candidate Scanner

All DOM IDs (`#positions-content`, etc.) were preserved so existing Reports and Manage tab logic continues to work seamlessly. The navigation bar now has 8 tabs instead of 9.

### UX Phase 1 — sticky header + row actions + Uploads card cleanup (May 5, 2026 evening)

Three pre-migration UI inconsistencies were resolved in a single deploy:

- **Sticky persistent header.** `.header-bar` is now `position: sticky` and adds two new chips: NetLiq (`#header-netliq`) reading `briefing.account.net_liq`, and portfolio Δ (`#header-portfolio-delta`) reading `briefing.greeks.portfolio_delta`. Δ chip turns amber over ±1000 and red over ±1500. Chips visible on every tab.
- **Legacy GW chip removed.** `#gw-indicator` hidden via `display:none`; backend health is now expressed solely by the `Δ via …` chip in the header (which is also click-to-Settings).
- **Row-level position actions.** Positions table grew an Actions column with a `⋯` kebab per row. Inline menu offers `Evaluate stop-loss`, `Find roll candidates`, `Open chart` — each switches to Manage, prefills the relevant engine with the row's position, auto-runs it, and scroll-flashes the result. Roll greyed out for SPY hedges and stock-only positions.
- **Uploads card rewrite.** Title `IB Gateway sync` → `Sync from IBKR`. `checkGatewayStatus()` rewritten to read `/api/ibkr/capability` (was `/api/ibkr/status`); pill states: `Web API ready · OPRA Greeks` / `Web API re-auth pending` / `Fallback active — BS-yfinance` / `Legacy TWS gateway`.
- **USD-native sync display.** `triggerIbkrSync()` and `previewIbkrSync()` now format NetLiq / Excess / Available with `fmtUsd(v) = $${Math.round(v).toLocaleString("en-US")}` per Strategy v3.6 §7. Old `€` + `nl-NL` formatting removed.

**Files touched:** `app/static/index.html` (sticky header CSS, GW chip hidden, Uploads card copy), `app/static/app.js` (`renderHeader`, `renderPositions`, `checkGatewayStatus`, `triggerIbkrSync`, `previewIbkrSync`), `app/static/phase4.js` (`window.togglePosActionMenu`, `window.runPositionAction`, `matchPosition`).

**Cache busters bumped:** `?v=20260505ux2`.

**Pre-deploy backup:** `/tmp/static_pre_ux_phase1_20260505-220033.tgz` on the VPS — `index.html`, `app.js`, `phase4.js` from before the changes. Roll back via `tar xzf … -C /home/ubuntu/Fortress_Dashboard/app/static/`.

**Out of scope (UX phase 2 candidates):** Briefing-as-triage rebuild (auto-evaluate book and surface ranked attention list), `Cmd-K` command palette, severity-coded card framing, "diff vs yesterday" on positions, hover tooltips on Strategy `§` references.


## API surface (live, May 5)

```
GET  /                                    → static index.html
GET  /static/*                            → static assets (incl. settings.js, phase4.js, chart.js)
GET  /api/health                          → liveness check + version

# Phase 1 reads
GET  /api/briefing                        → account + actions + regime + pacing + concentration + greeks + FX + USD thresholds
GET  /api/positions                       → per-leg positions (raw IBKR shape)
GET  /api/manage/positions                → aggregated positions (one row per ticker)
GET  /api/candidates                      → IV crush rows + earnings + concentration + exclusion enrichment
GET  /api/calendar                        → earnings calendar
GET  /api/universe                        → tier1 / tier2 / macro / excluded
GET  /api/alerts                          → active alerts
GET  /api/journal                         → entries + 30d outcome metrics
GET  /api/uploads                         → upload audit (ibkr + chart)

# Phase 2 writes
PUT    /api/calendar/{ticker}             → upsert earnings date
POST   /api/calendar/{ticker}/confirm     → mark confirmed
DELETE /api/calendar/{ticker}             → remove ticker
POST   /api/calendar/fetch-earnings       → auto-fetch from yfinance
POST   /api/alerts                        → create alert
PATCH  /api/alerts/{id}                   → update alert
DELETE /api/alerts/{id}                   → delete alert
POST   /api/journal                       → append entry
DELETE /api/journal/{id}                  → remove entry
POST   /api/universe/add                  → add to tier
POST   /api/universe/move                 → move between tiers
POST   /api/universe/exclude              → add to excluded list
DELETE /api/universe/exclude/{ticker}     → remove from excluded
DELETE /api/universe/{tier}/{ticker}      → remove from tier

# Phase 3 broker integration
POST   /api/uploads/ibkr                  → OCR screenshot upload (legacy)
POST   /api/uploads/ibkr/{id}/confirm     → apply OCR
POST   /api/uploads/chart                 → chart image
POST   /api/uploads/chart/{id}/annotate   → annotate chart
GET    /api/ibkr/status                   → legacy TWS gateway status
GET    /api/ibkr/preview                  → live data without disk write (TWS-only)
POST   /api/ibkr/sync                     → backend dispatcher; ?backend= to override
GET    /api/ibkr/capability               → web_api + tws_gateway probe + OPRA test (cached 60s; ?refresh=1 forces)

# Phase 3 chart widget
GET    /api/chart/{ticker}                → OHLCV candles + DP/GEX overlay levels
GET    /api/chart/{ticker}/levels         → overlay levels only

# Phase 4 strategy logic
GET    /api/manage/stop_loss/{position_id} → §6 multi-signal verdict
GET    /api/manage/roll/{position_id}     → §5 roll candidates + IBKR ticket text
POST   /api/manage/validate_jade_lizard   → §2.E credit-vs-width gate
GET    /api/manage/spy_hedge_coverage     → §2.D coverage check
POST   /api/playbook/post_earnings        → §10 matrix + thesis gate

# Phase 1 utility
GET    /api/run/scripts                   → list whitelisted workflow scripts
POST   /api/run/{script_key}              → trigger one whitelisted script

# Phase 4.5 settings (new)
GET    /api/settings                      → {config: {security, strategy, technical, alerts, ui}}
GET    /api/settings/schema               → {schema: {section: [field, ...]}}
PUT    /api/settings/{section}            → body {values: {key: value}}
POST   /api/settings/reset               → factory defaults
GET    /api/settings/test_quantdata       → tests QuantData live API connection

# Phase 5/6/7/8 Batch & Reports (new)
GET    /api/manage/stop_loss_all          → batch stop-loss for all positions
GET    /api/manage/roll_all               → batch roll evaluator for all positions
GET    /api/manage/pretrade_all           → batch pre-trade gate for all universe tickers
GET    /api/manage/trade_report           → comprehensive evaluation report for a ticker
GET    /api/manage/monitor_alerts         → checks active book and creates URGENT/ACT alerts
GET    /api/journal/suggest               → auto-populates journal entry from last IBKR sync
POST   /api/run/group/{group_name}        → time-of-day workflow script runner
```

Total: 46 routes under `/api/*`.

---

## Known issues

### IBKR-side

1. **CP Gateway daily 2FA push.** Sessions expire every ~24h. `voyz/ibeam` re-authenticates automatically but requires an IBKR Mobile push approval each cycle. If missed, capability badge falls back to `bs_yfinance`. *Mitigation candidate:* OAuth 2.0 direct (deferred per migration plan §10).

2. **Brokerage-session conflict.** IBKR allows only one brokerage session per username. Logging into TWS or the IBKR Mobile app while CP Gateway is active flips its session to `competing: true` and the dashboard auto-falls back to `bs_yfinance`. Recovery: log out of TWS and call `POST /iserver/reauthenticate`.

3. **Theta/vega zero on bs_yfinance backend.** When `greeks_backend == bs_yfinance`, only delta is computed. Theta/vega = 0 in Portfolio Greeks aggregation. Could be addressed with BS-from-IV theta/vega computation.

4. **`qty=0` legs persist in legacy TWS path.** `ibkr_sync_web.py` filters them at sync time; legacy `ibkr_sync.py` does not.

### CP Gateway

5. **`conf.yaml` IP-allowlist is volume-mounted from the host.** Required for our Docker compose network (172.18.*). If you upgrade `voyz/ibeam` and the upstream conf.yaml changes structure, the mount may need re-syncing.

6. **TWS Gateway healthcheck wrong port.** `ib-gateway/docker-compose.yml` healthcheck tests `localhost:4001` (paper) instead of `localhost:4003` (live). Container stopped, so no impact.

### Schema and naming

7. **`dashboard_settings.json` is orphaned.** Created during early Web API work; superseded by `fortress_config.json`. Either delete or leave as historical.

8. **`/etc/systemd/system/fortress-dashboard.service` drifts from repo copy.** Live unit has env overrides not in the repo file.

9. **Git repo has zero commits.** No version history.

### Security

10. **Port 8080 still publicly reachable.** UFW inactive. Highest-priority unaddressed risk.

### Operational

11. **Strategy doc divergence intentional and documented.** Per Strategy v3.6 §15.3, the strategy doc and dashboard now agree at 0.35 / USD. Older docs (v3.4, v3.5) say 0.40 / EUR — superseded.

12. **Hard-refresh required after deploy** (Cmd-Shift-R). Browser caches static assets.

---

## Operational notes

### Daily routine

- **Trigger an IBKR sync to refresh:** `POST /api/ibkr/sync`. Backend chosen per `cfg("technical.greeks_backend")` — usually `auto` → web_api when capability check passes. 30–60 seconds.
- **Capability badge** in the header shows the active backend. Hover for last-checked timestamp.
- **CP Gateway re-auth** required ~daily — approve the IBKR Mobile push when it arrives. `voyz/ibeam` retries every 60s if missed.
- **Strategy thresholds in USD** since v3.6. EUR equivalent shown as info only.
- **Excluded tickers display but never recommend.** Add via `POST /api/universe/exclude` or directly in `ticker_universe.json`.

### Backend selection

| `greeks_backend` | When to use | What it does |
|---|---|---|
| `auto` (default) | Always | Resolves per capability — web_api if OPRA + session OK, else bs_yfinance |
| `web_api` | Force CP Gateway | Errors loudly if OPRA / session not ready |
| `bs_yfinance` | Diagnostics / broker offline | Synthetic sync — refreshes BS deltas against existing book |
| `tws_ibkr` | Diagnostics only | Reactivate the legacy TWS gateway first |

Switch via Settings tab → Technical → Greeks backend.

### Settings live-tuning
`fortress_config.json` is hot-reloaded — Settings tab edits take effect on the next API call, no restart.

### Security toggles (NEW v1.8.2)

Settings → Security exposes two master enable/disable toggles:

| Toggle | Key | Default | Effect when disabled |
|---|---|---|---|
| Enable IBKR Web API | `security.use_ibkr_web_api` | `true` | `/api/ibkr/sync` forces `bs_yfinance` regardless of `greeks_backend`; response includes `ibkr_web_api_enabled: false`. Greeks are BS-estimated; positions are from last snapshot; NetLiq is stale. |
| Enable QuantData | `security.use_quantdata` | `true` | All QuantData workflow scripts blocked (HTTP 503) at `/api/run/{script_key}`; chart DP/GEX overlays return empty arrays; stop-loss DP floor signal suppressed. `position_monitor` is exempt. |

Amber warning banners appear in the Settings UI immediately when a toggle is turned off (before save). No restart required.

---

## Backups and rollback

### Live state-file backups

`quant/backups/<filename>.<YYYYMMDDTHHMMSS>.json` — last 50 retained per file. Atomic writes via `state.write_json`. Restore: `cp quant/backups/active_positions.20260505T143821.json quant/active_positions.json && systemctl restart fortress-dashboard`.

### Pre-deploy snapshots

Each round of patches leaves `*.pre-{change}-bak` siblings:

- `app/services/state.py.pre-aggregator-bak`, `.pre-config-store-bak`, `.pre-settings-bak`
- `app/services/ibkr_sync.py.pre-bsfallback-bak`
- `app/services/config_store.py.pre-greeks-backend-bak`
- `app/routes/manage.py.pre-aggregator-bak`
- `app/routes/briefing.py.pre-aggregator-bak`, `.pre-fx-bak`
- `app/routes/candidates.py.pre-excluded-bak`
- `app/routes/ibkr.py.pre-capability-bak`, `.pre-dispatcher-bak`
- `app/routes/settings.py.pre-config-store-bak`
- `app/static/app.js.pre-fx-bak`
- `app/static/phase4.js.pre-excluded-bak`, `.pre-settings-ui-bak`
- `app/static/index.html.pre-settings-bak`, `.pre-card-removal-bak`
- `app/main.py.pre-settings-bak`
- `quant/ticker_universe.pre-excluded-bak.json`
- `quant/active_positions.pre-ibkr-sync.json`
- `_phase4_backup_2026-05-03/app/` (full pre-Phase-4 tree)

Each is recoverable with `cp <file>.pre-*-bak <file>` + service restart.

---

## Next-step recommendations (ranked)
1. **Install MCP server in Claude Desktop.** Copy `fortress_mcp.py` to your laptop, add the config snippet from `fortress_mcp/`
**Utility Scripts: /home/ubuntu/Fortress_Dashboard/scripts/ — 34 scripts, see scripts/README.md.mdclaude_desktop_config_snippet.json` to Claude Desktop config, restart Claude Desktop. ~5 minutes.
2. **Lock down port 8080 with UFW.** `ufw allow ssh && ufw allow from <home_ip> to any port 8080 && ufw enable`. Highest-priority unaddressed security risk.
3. **End-to-end MCP test.** Run all 19 Tier 1 tools in Claude Desktop. Verify error handling and degraded-mode warnings per `07_MCP_Workflow_and_Prompts_v1_1.md §10`.
4. **Enable Tier 2 write tools.** Add `FORTRESS_MCP_ALLOW_WRITES=1` to Claude Desktop MCP env once Tier 1 is stable (~1-2 weeks of use).
5. **Add BS-from-IV theta/vega** in `bs_fallback.py` so Portfolio Greeks works when on the bs_yfinance backend (currently delta-only). ~1 hour.
6. **Make initial git commit.** Sync the live service file and commit the codebase. ~15 minutes.
7. **OAuth 2.0 direct migration** to remove the daily 2FA push. Deferred. ~1 day when ready.

— End of document —
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     
## Mode 4: Trader Personas & Expanded Strategy Catalogue (2026-05-09)
* **Goal**: Expand the dashboard from a single PMCC-focused tool to a universal options platform supporting multiple trader types.
* **Status**: Complete.
* **Implementation**:
  * Added 5 trader personas (Income Seeker, Speculator, Volatility Trader, Hedger, PMCC Income) via `/api/settings/trader_presets`.
  * Expanded strategy catalogue to 24 distinct strategies (Iron Condor, Straddle, Collar, Wheel, etc.).
  * Added `trader_profile` config section with `trader_type`, `active_strategies`, `risk_tolerance`, and `primary_objective`.
  * Added strategy-specific config parameters (e.g., `iron_condor_short_delta`, `collar_protective_put_delta`).
  * Updated `state.py` to automatically infer all 24 strategy types from leg structures.
  * Rebuilt the Strategy tab frontend with interactive persona cards that apply preset configs dynamically.

## Mode 5 — Public GitHub Release (2026-05-09)

| Component | Status | Notes |
|---|---|---|
| Security section in Settings tab | ✅ Complete | API keys, tokens, account IDs moved to dedicated Security section |
| Backup & Restore UI | ✅ Complete | Export/import all settings as JSON from Settings tab |
| Strategy tab readability | ✅ Complete | Collapsible sections, persona cards, strategy group headers |
| GitHub Actions CI/CD | ✅ Complete | Auto-deploy to VPS on push to main via SSH |
| Codebase sanitisation | ✅ Complete | All personal values replaced with placeholders |
| install.sh | ✅ Complete | One-command installation script |
| README.md | ✅ Complete | Full installation and configuration guide |
| GitHub repository | ✅ Published | https://github.com/citychip/options-portfolio-strategy-dashboard-2026 |

---

## Mode 6 — v2 Dashboard + Analysis Enhancements (2026-05-15)

### Backend fixes (v3.6 patch)

| Change | File | Notes |
|---|---|---|
| `fetchEarningsDates()` now uses `apiFetch()` | `app/static/index.html` | Was calling bare `fetch()` without the Authorization header — caused `invalid_token` on the auto-fetch button in the Earnings calendar |
| SPY hedge classifier broadened | `app/routes/manage.py` | Now counts any untagged SPY put as a hedge leg in addition to positions explicitly tagged `SPY_HEDGE`, covering bear-put-spread legs that arrive without a strategy tag |

### New MCP scripts

| Script | Purpose |
|---|---|
| `scripts/mcp_briefing.py` | Morning briefing via MCP — calls `/api/briefing` and formats output for Claude Desktop |
| `scripts/mcp_full_analysis.py` | Full ticker analysis via MCP |
| `scripts/mcp_gex2.py` | GEX level extraction via MCP |
| `scripts/mcp_position_analysis2.py` | Per-position analysis via MCP |

### v2 Dashboard (fortress-v2) — features shipped

The React/TypeScript v2 dashboard (served at port 3000 via nginx) received the following additions:

**DashboardPage — Trade Report panel**

- Post-earnings candidates section: renders tickers where earnings occurred within the last 3 days. Shows a days-since badge (TODAY / 1D AGO / 2D AGO), IVR post-earnings chip (amber if IVR >= 50, green if 25–49, dim if crushed), current price, PLAYBOOK action chip, and the API note. Section is hidden when count is zero.
- Summary count grid expanded from 5 to 6 columns, adding a Post-Earnings chip alongside Entry / Stop-Loss / Exit / Roll / Urgent.
- Roll candidates DTE ring: the same SVG countdown ring used on exit candidates is now also shown on roll candidates, using `current_dte`, cyan ring colour, and urgency badge (URGENT / THIS_WEEK / WATCH). EXPIRING pulse fires at <= 7 DTE.
- Null-safety hardening: all `.toFixed()` calls on nullable fields guarded — `iv_rank`, `concentration_pct`, `net_liq_pct`, `hedge_pct_of_netliq` — prevents a runtime crash when IBKR is not synced or IV data is unavailable.

**AnalysisPage**

- Greeks Summary panel: 6-cell grid showing Net Delta, Net Gamma, Net Theta, Net Vega, Avg IV, and Leg count, all aggregated from live position data (greek x qty x multiplier). Color-coded green/red/amber by sign and magnitude. Only renders when OPT positions exist for the selected ticker.
- Earnings overlay: amber vertical dashed ReferenceLine at the `next_earnings` date from `/api/calendar`, snapped to the nearest candle. Added to the chart legend.
- Deep-link navigation: roll candidate and post-earnings rows on DashboardPage are now clickable (cursor-pointer, hover highlight). Clicking sets `fortress_analysis_ticker` in sessionStorage and navigates to `/analysis`, which reads and clears it on mount to pre-select the ticker.

**SettingsPage**

- Settings sync indicator: `SyncBadge` component in the page header shows "Saving…" (pulsing dot), "Saved ✓" (green), or "Sync failed" (red) based on `prefsSaveStatus` exposed from `ConfigContext`.
- Connection Health panel: two manual-trigger test cards placed after the API Connection section. IBKR Web API card hits `/api/ibkr/capability?refresh=1` and shows session status, active backend, account ID, OPRA subscription, latency, and checked-at timestamp. QuantData API card hits `/api/settings/test_quantdata` and shows status, SPY IV Rank (live probe), result message, latency, and checked-at timestamp. Both cards have animated status dots (grey = untested, amber pulse = in-flight, green/red = result).

### IBKR Web API — option chain capability confirmed

The IB Gateway Web API (running at `localhost:5000`) supports full option chain access with no additional configuration:

| Capability | Endpoint |
|---|---|
| Available expirations per ticker | `GET /v1/api/iserver/secdef/search?symbol=X&secType=STK` |
| Strikes per expiry | `GET /v1/api/iserver/secdef/strikes?conid=X&sectype=OPT&month=MMMYY` |
| Option conids (call and put per strike) | `GET /v1/api/iserver/secdef/info?conid=X&sectype=OPT&month=MMMYY&right=C&strike=Y` |
| Live market snapshot (bid, ask, last, mark, delta, gamma, theta, vega, IV%) | `GET /v1/api/iserver/marketdata/snapshot?conids=X,Y,Z&fields=84,86,7308,7309,7310,7311,7633` |

Batch snapshot supports up to ~100 conids per call. The snapshot endpoint requires a 2-second warm-up on first call per conid as IBKR starts a market data subscription in the background. Subsequent calls return instantly.

This capability unlocks a live option chain viewer, pre-trade strike suggester, and IV surface heatmap as planned future features.

---

*— End of document —*
