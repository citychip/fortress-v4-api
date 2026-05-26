# Trading Dashboard — Build Specification

**Version 1.9.1 — May 13, 2026**

End-to-end specification for the Fortress Dashboard. Covers architecture, data contracts, all UI features, the strategy logic engines, the upload pipeline, the IBKR Web API + CP Gateway integration, the chart widget, the schema-driven settings system, and the per-leg → aggregated position view.

v1.9.0 reflects the completion of the 13 UX/Automation improvements (A-M) and the addition of the Trade Reports tab:
1. **Batch Endpoints & UI:** Auto-run stop-loss and roll tables, pre-trade matrix.
2. **Automation:** Position monitor (live alerts banner), journal auto-populate from sync, time-of-day script runner, IBKR auto-sync background task.
3. **Trade Reports Tab:** Comprehensive evaluation reports for new trades, rolls, buys, and sells.
4. **UX Polish:** Sync dot/text, auto-refresh renamed to Live, QuantData test button, Positions colour coding.

---

## 1. Overview & Goals

### 1.1 Why this exists

QuantData pipeline produces 4–5 markdown reports per day plus state JSON. Cross-referencing them takes 10–15 minutes every morning. The dashboard consolidates this into one interface, adds direct IBKR sync for live position state, and code-enforces complex multi-signal decisions.

### 1.2 What it is and isn't

**It IS:**
- A consolidated view of QuantData reports (briefing, positions, candidates, calendar)
- A direct sync from IBKR via Web API for positions, account values, and option Greeks (delta/gamma/theta/vega/IV/mark)
- A schema-driven settings editor — strategy thresholds, alert thresholds, technical params, UI prefs all tunable without code deploy
- An editor for state JSON files (alerts, journal, calendar, universe)
- An execution layer that triggers existing scripts on demand
- A workflow runner for multi-step decisions (post-earnings playbook, roll evaluation, stop-loss aggregation, Jade Lizard validation, SPY hedge coverage, pre-trade gate)
- An upload target for IBKR screenshots (legacy OCR) and TradingView charts with structured capture
- A chart viewer overlaying QuantData levels on yfinance OHLCV

**It IS NOT:**
- An auto-trader.
- A real-time market data tool.
- A replacement for IBKR position screen.
- A replacement for TradingView for charting.
- A backtesting platform.

### 1.3 Phasing

| Phase | Status | Scope |
|---|---|---|
| 1 | Live | Static read-only briefing/positions/candidates/calendar/universe |
| 2 | Live | Write capability — alerts/calendar/journal/universe CRUD |
| 3 | Live | OCR pipeline (legacy), Web API direct sync (primary), TradingView Lightweight Charts widget, earnings auto-fetcher |
| 4 | Live | Strategy logic engines — stop-loss, roll, post-earnings playbook, Jade Lizard validator, SPY hedge coverage, pre-trade gate, Portfolio Greeks |
| **4.5 (new in v1.8)** | Live | Schema-driven Settings tab + `config_store`. Backend dispatcher selects greeks_backend per `cfg("technical.greeks_backend")`. |
| **4.6 (new in v1.8.2)** | Live | Security section in `fortress_config.json`: `use_ibkr_web_api` and `use_quantdata` toggles with runtime guards across all dependent routes. |
| **5/6/7 (new in v1.9)** | Live | UX & Automation improvements: Live alerts banner, Journal auto-populate, IBKR auto-sync, batch stop-loss/roll tables, pre-trade matrix, time-of-day scripts. Positions tab merged into Dashboard tab. |
| **8 (new in v1.9)** | Live | Trade Reports Tab — comprehensive evaluation reports for new trades, rolls, buys, and sells. |

---

## 2. Architecture

### 2.1 Stack

- **Backend:** Python 3.14 with FastAPI (uvicorn[standard]).
- **Frontend:** Single-page HTML + vanilla JS. No build step. TradingView Lightweight Charts loaded from CDN.
- **State storage:** JSON files in `FORTRESS_DATA_DIR` (default `/home/ubuntu/Fortress_Dashboard/quant/`). Atomic writes with timestamped backups.
- **Runtime config:** `fortress_config.json` (in `FORTRESS_DATA_DIR`) — loaded once at startup into `config_store._config`, hot-edited via Settings UI, persisted atomically.
- **Broker integration:**
  - Primary: `voyz/ibeam` Docker container running CP Gateway at `https://localhost:5000`. `httpx` client with cookie-based session token from `/tickle`.
  - Legacy: `ib_async` against `gnzsnz/ib-gateway:stable` (TWS API). Stopped; available for diagnostics.
- **Market-data fallback:** `yfinance>=1.3.0` for option chains, IV, OHLCV, EUR/USD rate.
- **OCR (legacy):** `pytesseract` + `Pillow`.
- **Process model:** Two systemd services + one Docker container (CP Gateway).

### 2.2 Component diagram

```
[ Master Orchestrator (fortress_orchestrator.service) ]
         |
         | writes JSON outputs every 5–60 min, runs workflow_*.py on schedule
         v
[ ${FORTRESS_DATA_DIR}/*.json + reports/*.md ]
         ^
         | reads (FastAPI handlers)
         | writes (POST endpoints, IBKR sync, Settings)
         |
[ FastAPI Dashboard (fortress-dashboard.service, uvicorn :8080) ] ──── reads ──── [ CP Gateway (Docker, voyz/ibeam :5000) ]
         |                                                                                  |
         | serves HTML + JSON                                                              | Web API → IBKR backend
         v                                                                                  v
[ Browser / MCP / curl ]                                                              [ IBKR account U7453366 ]
```

### 2.3 Directory layout

```
/home/ubuntu/Fortress_Dashboard/
├── app/
│   ├── main.py
│   ├── routes/
│   │   ├── briefing.py            # GET /api/briefing
│   │   ├── positions.py           # GET /api/positions (per-leg)
│   │   ├── candidates.py          # GET /api/candidates
│   │   ├── calendar.py            # GET/PUT/POST/DELETE /api/calendar/*
│   │   ├── universe.py            # GET + add/move/exclude/* writes
│   │   ├── alerts.py              # GET/POST/PATCH/DELETE /api/alerts
│   │   ├── journal.py             # GET/POST/DELETE /api/journal
│   │   ├── uploads.py             # POST /api/uploads/* (OCR + chart)
│   │   ├── manage.py              # GET /api/manage/* + validate_jade_lizard
│   │   ├── playbook.py            # POST /api/playbook/post_earnings
│   │   ├── ibkr.py                # GET/POST /api/ibkr/* (status/sync/preview/capability)
│   │   ├── chart.py               # GET /api/chart/{ticker} + /levels
│   │   ├── earnings_fetch.py      # POST /api/calendar/fetch-earnings
│   │   ├── settings.py            # /api/settings + schema + section + reset (NEW v1.8)
│   │   └── run.py                 # POST /api/run/{script_key}
│   ├── services/
│   │   ├── state.py               # JSON IO + aggregator + concentration + helpers
│   │   ├── ocr.py
│   │   ├── chain.py               # yfinance chain provider, BS delta
│   │   ├── ibkr_sync.py           # Legacy TWS path
│   │   ├── ibkr_sync_web.py       # NEW — CP Gateway path
│   │   ├── ibkr_sync_synthetic.py # NEW — bs_yfinance-only sync
│   │   ├── ibkr_web/              # NEW — CP Gateway client package
│   │   │   ├── client.py          # httpx wrapper, /tickle session token
│   │   │   ├── session.py
│   │   │   ├── portfolio.py
│   │   │   ├── snapshot.py        # 2-step preflight + read pattern
│   │   │   └── capability.py      # session + OPRA test
│   │   ├── bs_fallback.py
│   │   ├── fx.py                  # EUR/USD rate
│   │   ├── playbook.py
│   │   ├── stop_loss.py
│   │   ├── roll.py
│   │   └── config_store.py        # NEW — runtime config (fortress_config.json)
│   └── static/
│       ├── index.html
│       ├── app.js                 # tabs + briefing/positions/candidates/calendar/journal
│       ├── phase4.js              # Manage / New Trade / Playbook
│       ├── chart.js               # TradingView Lightweight Charts
│       ├── settings.js            # NEW — schema-driven Settings tab
│       ├── style.css
│       └── phase4.css
├── quant/
├── ib-gateway/                    # legacy TWS compose (stopped)
├── cp-gateway/                    # NEW — CP Gateway compose + conf/conf.yaml
├── docs/
├── venv/
└── requirements.txt
```

### 2.4 Authentication

**Currently absent.** The dashboard binds to `0.0.0.0:8080` with no authentication layer. UFW IP whitelisting is the only access control until a Bearer token middleware is added (planned, see Implementation Status doc).

### 2.5 Performance targets

- Initial page load: under 2 seconds.
- Tab switch: instant.
- State refresh interval: 60 seconds polling, configurable via `cfg("ui.refresh_interval_s")`.
- IBKR sync (Web API path): 30–45 seconds typical for ~25 positions.
- Roll evaluator: under 5 seconds (5-minute chain cache hits).
- Capability check: cached 60s (in-process); ~3 seconds on cache miss.

---

## 3. Data Contracts

All data flows through JSON files in `FORTRESS_DATA_DIR`. Atomic writes; timestamped backups in `quant/backups/` (last 50 retained per file).

### 3.1 active_positions.json

Source of truth: IBKR (via CP Gateway Web API in v1.8). Per-leg shape — one record per option leg.

#### 3.1.1 Per-leg record fields

| Field | Required | Description |
|---|---|---|
| `ticker` | yes | Underlying ticker (uppercase) |
| `sec_type` | yes | `OPT` / `STK` |
| `qty` | yes | Contract count, signed |
| `avg_cost` | yes | IBKR's per-contract total cost |
| `expiry` | options | YYYY-MM-DD |
| `short_strike` | options | The leg's strike (semantically just "strike") |
| `right` | options | `C` / `P` (mapped from IBKR's `putOrCall`) |
| `multiplier` | options | typically `100` |
| `local_symbol` | options | IBKR contract identifier |
| `conid` | options | IBKR contract ID (for direct lookup) |
| `market_value` | yes | Signed MV |
| `current_delta` | optional | Long-equivalent delta (call positive, put negative) |
| `current_delta_source` | optional | `web_api` / `ibkr` (legacy TWS) / `bs_estimate` / `unavailable` |
| `current_gamma` | optional | from web_api OPRA snapshot |
| `current_theta` | optional | from web_api OPRA snapshot |
| `current_vega` | optional | from web_api OPRA snapshot |
| `current_iv` | optional | per-strike IV (field 7633) |
| `current_mark` | optional | mark price (field 7635) |
| `_ibkr_delta_raw` | optional | preserved IBKR value for audit |
| `delta_state` | optional | `normal` / `watch` / `critical` / `unknown` per §5.5.3 |
| `alert_state` | optional | `safe` / `watch` / `approaching` / `breaking` / `broken` / `critical_gamma` / `hedge` / `unknown` |
| `net_liq_pct` | optional | `abs(market_value) / net_liq * 100` per leg |
| `strategy` | optional | `PMCC` / `DIAGONAL` / `PCS` / `JADE_LIZARD` / `SPY_HEDGE` |
| `notes` | optional | Free-text trade thesis |
| `_ibkr_synced` | optional | True when written by IBKR sync |
| `_ibkr_sync_time` | optional | ISO timestamp |

#### 3.1.2 Top-level fields

| Field | Description |
|---|---|
| `_last_updated` | ISO timestamp of latest write |
| `ibkr_last_sync` | Timestamp of last successful IBKR sync |
| `ocr_last_sync` | Timestamp of last OCR confirm (legacy) |
| `net_liq` | Net Liquidity (USD) |
| `excess_liquidity` | Excess Liquidity (USD) |
| `available_funds` | Available Funds (USD) |
| `buying_power` | Buying Power (USD) |
| `daily_pnl` | (when available) |
| `unrealized_pnl` | (when available) |
| `concentration` | `{ticker: pct}` map (computed if absent) |
| `spy_hedge_coverage` | §2.D coverage object |
| `greeks_backend_used` | which backend produced this sync (`web_api` / `tws_ibkr` / `bs_yfinance`) |

#### 3.1.3 Aggregated view (computed at read time)

`state.aggregate_positions_by_ticker(positions_data)` collapses per-leg records into one row per underlying:

```json
{
  "ticker": "MSFT",
  "strategy": "PMCC",
  "leg_count": 6,
  "net_market_value": 60067.42,
  "net_liq_pct": 70.6,
  "short_strike": 445.0,
  "short_expiry": "2026-06-05",
  "long_strike": 310.0,
  "long_expiry": "2028-01-21",
  "expiry": "2026-06-05",
  "current_delta": 0.2246,
  "delta_state": "normal",
  "alert_state": "safe",
  "notes": "Primary engine, DTE exception on Dec18 480 short",
  "qty": 3,
  "legs": [...]
}
```

Selection rules:
- **Primary short call**: nearest-expiry leg with `right="C"` and `qty<0`.
- **Primary long call**: longest-expiry leg with `right="C"` and `qty>0`.
- **`current_delta`**: from primary short call (or primary long if no short).
- **`alert_state`**: from primary short, promoted to `critical_gamma` when `|current_delta| > cfg("strategy.delta_critical_threshold")` (default 0.35).
- **`net_market_value`**: signed sum of per-leg `market_value`.
- **`net_liq_pct`**: `net_market_value / net_liq * 100`.

`/api/manage/positions` returns aggregated view. `/api/positions` returns per-leg list.

#### 3.1.4 SPY hedge coverage (§2.D)

Computed at sync time and stored at top level:

```json
"spy_hedge_coverage": {
  "hedge_market_value": 1756.26,
  "hedge_pct_of_netliq": 2.03,
  "target_min": 22000,
  "target_max": 33000,
  "coverage_ok": false,
  "legs_count": 2,
  "source": "ibkr_sync_cached"
}
```

Target band sourced from `cfg("strategy.spy_hedge_min_usd")` and `spy_hedge_max_usd`. **USD-native in v1.8** (matches Strategy v3.6 §2.D).

#### 3.1.5 Concentration computation

`state.compute_concentration` rules:
- If `positions_data["concentration"]` is set, return it.
- Else if `net_liq` is available: `{ticker: round(sum(market_value)/net_liq*100, 1)}`.
- Else fall back to summing per-leg `net_liq_pct`.

#### 3.1.6 Graceful degrade

- Account header card hidden if all account fields null. Replaced with info banner.
- `current_delta` missing: BS-fallback fills it post-sync; if BS also fails, `delta_state` defaults to `unknown` with gray dot.
- `concentration` absent: computed at read time.

### 3.2 earnings_blocklist.json

Auto-fetched by `POST /api/calendar/fetch-earnings` (yfinance). Confirmed dates in the future preserved on auto-fetch.

### 3.3 ticker_universe.json

```json
{
  "tier1": [...], "tier2": [...], "macro": [...],
  "excluded": [
    {"ticker": "COIN", "reason": "regulatory", "until_cleared": true},
    {"ticker": "OST",  "reason": "ignored_entirely", "until_cleared": false, "note": "..."}
  ]
}
```

`reason` values: `regulatory`, `ignored_entirely`, `pmcc_incompatible`, free-form. Universe CRUD endpoints (`/api/universe/add`, `/move`, `/exclude`, `/exclude/{ticker}`) write here atomically.

### 3.4 alerts.json, 3.5 journal.json, 3.6 chart_annotations.json, 3.7 ibkr_uploads.json

Unchanged from v1.7.

### 3.8 fortress_config.json (NEW in v1.8)

Runtime configuration. Loaded once at startup by `config_store.load()`. Edited via `/api/settings/{section}` + `config_store.save()` (atomic write).

Sections: **`security`**, `strategy`, `alerts`, `technical`, `ui`. Defaults defined in `app/services/config_store.py` `DEFAULTS`. Live values accessed anywhere in the codebase via `cfg("section.key")`.

Key fields:
- **`security.use_ibkr_web_api`** = `true` — when `false`, forces `bs_yfinance` backend for all syncs (NEW v1.8.2)
- **`security.use_quantdata`** = `true` — when `false`, blocks QuantData-dependent workflow scripts, clears chart overlays, suppresses DP floor signal (NEW v1.8.2)
- `strategy.delta_critical_threshold` = 0.35 (Strategy v3.6 §5)
- `strategy.available_funds_min_usd` = 17000 (USD-native, v1.8 §7.9)
- `strategy.excess_liq_min_usd` = 25000
- `strategy.spy_hedge_min_usd` = 22000, `spy_hedge_max_usd` = 33000
- `technical.greeks_backend` = "auto" (auto / web_api / bs_yfinance / tws_ibkr)
- `technical.cp_gateway_url` = "https://localhost:5000"
- `alerts.delta_watch_threshold` = 0.30, `delta_act_threshold` = 0.35
- `ui.currency_display` = "USD"
- (~50 more — full list in `config_store.DEFAULTS` and `routes/settings.SCHEMA`)

---

## 4. API Endpoints

All return JSON. Errors use FastAPI defaults.

### 4.1 Read endpoints

| Method | Path | Returns | Phase |
|---|---|---|---|
| GET | `/api/briefing` | Account + actions + regime + pacing + concentration + Greeks + FX + USD thresholds | 1+3+4 |
| GET | `/api/positions` | Per-leg positions (raw) | 1+3 |
| GET | `/api/manage/positions` | Aggregated positions (1 row per ticker) | 4 |
| GET | `/api/candidates` | IV crush + earnings + concentration + exclusion | 1+3.3 |
| GET | `/api/calendar` | Earnings calendar with computed days-to-earnings | 1 |
| GET | `/api/universe` | tier1 / tier2 / macro / excluded | 1 |
| GET | `/api/alerts` | Active alerts | 2 |
| GET | `/api/journal` | Entries + 30d outcome metrics | 2 |
| GET | `/api/uploads` | Recent uploads (ibkr + chart) | 3 |
| GET | `/api/manage/stop_loss/{position_id}` | §6 multi-signal verdict | 4 |
| GET | `/api/manage/roll/{position_id}` | §5 roll candidates + IBKR ticket text | 4 |
| GET | `/api/manage/spy_hedge_coverage` | §2.D coverage check | 4 |
| GET | `/api/ibkr/status` | Legacy TWS gateway status | 3 |
| GET | `/api/ibkr/preview` | TWS-path live data without disk write | 3 |
| **GET** | **`/api/ibkr/capability`** | **Web API + TWS probe + OPRA test (NEW v1.8)** | 3 |
| GET | `/api/chart/{ticker}` | OHLCV + DP/GEX overlay levels | 3 |
| GET | `/api/chart/{ticker}/levels` | Overlay levels only | 3 |
| GET | `/api/run/scripts` | Whitelisted workflow scripts | 1 |
| **GET** | **`/api/settings`** | **`{config: {...}}` (NEW v1.8)** | 4.5 |
| **GET** | **`/api/settings/schema`** | **`{schema: {...}}` for the Settings UI (NEW v1.8)** | 4.5 |
| **GET** | **`/api/market-intelligence`** | **Live GEX, DP, Net Drift + Portfolio Context (NEW v1.9)** | 9 |
| GET | `/api/health` | Liveness + version | all |

### 4.2 Write endpoints

| Method | Path | Body / behavior | Phase |
|---|---|---|---|
| PUT | `/api/calendar/{ticker}` | Upsert earnings date | 2 |
| POST | `/api/calendar/{ticker}/confirm` | Mark confirmed | 2 |
| DELETE | `/api/calendar/{ticker}` | Remove ticker | 2 |
| POST | `/api/calendar/fetch-earnings` | Auto-fetch from yfinance | 3 |
| POST | `/api/alerts` | Create alert | 2 |
| **PATCH** | **`/api/alerts/{id}`** | **Update alert (NEW v1.8 inventory)** | 2 |
| DELETE | `/api/alerts/{id}` | Delete alert | 2 |
| POST | `/api/journal` | Append entry | 2 |
| DELETE | `/api/journal/{id}` | Remove entry | 2 |
| **POST** | **`/api/universe/add`** | **Add to tier (NEW v1.8 inventory)** | 2 |
| **POST** | **`/api/universe/move`** | **Move ticker between tiers** | 2 |
| **POST** | **`/api/universe/exclude`** | **Add to excluded list** | 2 |
| **DELETE** | **`/api/universe/exclude/{ticker}`** | **Remove from excluded** | 2 |
| **DELETE** | **`/api/universe/{tier}/{ticker}`** | **Remove from tier** | 2 |
| POST | `/api/uploads/ibkr` | OCR screenshot | 3 (legacy) |
| POST | `/api/uploads/ibkr/{id}/confirm` | Apply OCR | 3 (legacy) |
| POST | `/api/uploads/chart` | Chart image | 3 |
| POST | `/api/uploads/chart/{id}/annotate` | Update chart annotation | 3 |
| POST | `/api/ibkr/sync` | Backend dispatcher (`?backend=` to override) | 3 |
| POST | `/api/manage/validate_jade_lizard` | §2.E credit-vs-width gate | 4 |
| POST | `/api/playbook/post_earnings` | §10 matrix verdict | 4 |
| POST | `/api/run/{script_key}` | Trigger whitelisted script | 1 |
| **PUT** | **`/api/settings/{section}`** | **`{values: {key: value}}` (NEW v1.8)** | 4.5 |
| **POST** | **`/api/settings/reset`** | **Factory defaults (NEW v1.8)** | 4.5 |

Total: 39 routes under `/api/*`.

---

## 5. Phase 1 — Static Read-Only Dashboard

### 5.1 Tabs

9 tabs: Briefing (default), Positions, Manage, New Trade, Playbook, Uploads, Universe, Journal, **Settings** (new in v1.8).

### 5.2 Briefing tab

#### Account header (USD-native in v1.8)

4 stat cards: Net Liquidity, Excess Liquidity, Available Funds, Base Cash. Primary value in USD; sub-text shows EUR equivalent (informational only) and threshold check (`target >$25K · ok`). Threshold breach flips to amber.

Thresholds in USD per Strategy v3.6 §7:
- Available Funds floor: `cfg("strategy.available_funds_min_usd")` = $17K
- Excess Liquidity floor: `cfg("strategy.excess_liq_min_usd")` = $25K

#### Today's actions

Computed from aggregate_positions_by_ticker, alerts, candidates, calendar, staleness, Portfolio Greeks. Priority assignment unchanged from v1.7.

#### Macro regime, Pacing, Concentration cards

Unchanged. Concentration uses net-MV math.

#### Portfolio Greeks card (§7.6)

Net delta, theta, vega from aggregating across legs. **All four populated** when `greeks_backend == web_api` and OPRA active. Bias classification uses `cfg("strategy.delta_bias_long_threshold")` / `delta_bias_short_threshold`.

#### Header indicators

In addition to the existing sync indicator:
- **Gateway indicator** — TWS gateway status (legacy, may show offline).
- **Backend badge (NEW v1.8)** — shows the active Greeks backend (`Δ: Web API+OPRA` / `Δ: BS yfinance` / `Δ: TWS legacy`). Polled every 60s from `/api/ibkr/capability`. Color reflects backend quality.

#### Candidate scanner

Sorted by IV/HV spread descending. Each row: earnings pill (red if blackout), concentration pill, exclusion pill (red if excluded), signal pill. Trade button disabled when blocked.

### 5.3 Positions tab

Per-leg view by default; aggregator view available via `/api/manage/positions`. Columns: Position name, qty, strike(s), expiry, %NetLiq, Δ, Alert, Notes.

### 5.4 Universe tab

Shows tier1, tier2, macro, excluded. Universe write CRUD added (add, move, exclude/remove) — full UI editor pending.

### 5.5 Visual indicators

#### 5.5.1 VIX sensing (briefing border)

Same as v1.7. Thresholds from `cfg("strategy.vix_high")` (default 25) and `vix_extreme` (default 35).

#### 5.5.2 Data health (header staleness)

Same as v1.7.

#### 5.5.3 Delta drift cell highlighting (revised v1.8)

`compute_delta_state(pos)` returns `normal` / `watch` / `critical` / `unknown`.

Returns `normal` when:
- `current_delta` is null → `unknown`
- strategy is `SPY_HEDGE` (delta is by design)
- `leg_type` is `LONG_CALL`
- strategy is `PCS` and `leg_type` is `PUT_SPREAD`

Otherwise, computed from `|current_delta|` against thresholds **read from config_store**:
- `|delta| > cfg("strategy.delta_critical_threshold")` → `critical` (default 0.35; was 0.40 in v1.7)
- `|delta| >= cfg("alerts.delta_watch_threshold")` → `watch` (default 0.30)
- otherwise → `normal`

The aggregator promotes `alert_state` to `critical_gamma` when the primary short's |delta| > critical threshold. `alert_state` set explicitly in JSON takes precedence over computed `delta_state`.

### 5.6 Settings tab (NEW v1.8)

Schema-driven editor. **Five sections (Security, Strategy, Alerts, Technical, UI)** — Security is open by default. For each field: label, unit, type (number / text / password / boolean / select / multiselect), description.

Inline save per section. Multiselect renders as checkbox group; select as dropdown; password as masked input with toggle.

"Reset all to defaults" button at top, with confirmation dialog.

#### Security section (NEW v1.8.2)

Two enable/disable toggles at the top of the Security section:

| Toggle | Default | Effect when disabled |
|---|---|---|
| **Enable IBKR Web API** (`use_ibkr_web_api`) | `true` | `/api/ibkr/sync` forces `bs_yfinance` backend regardless of `technical.greeks_backend`; response includes `ibkr_web_api_enabled: false`. Greeks are estimated via Black-Scholes; positions are read from last snapshot; NetLiq is stale. |
| **Enable QuantData** (`use_quantdata`) | `true` | All QuantData-dependent workflow scripts blocked at `/api/run/{script_key}` (HTTP 503); chart DP/GEX overlays return empty arrays; stop-loss DP floor signal suppressed (Signal 4 never fires). `position_monitor` is exempt — it uses only yfinance/IBKR. |

When a toggle is turned off, an **amber warning banner** appears immediately below the toggle (no save required to see the banner — it reacts to the live checkbox state). The banner lists the exact data degradations in plain English.

### 5.7 Phase 1 acceptance criteria

Same as v1.7 + Settings tab renders, schema fetched from `/api/settings/schema`, save round-trips correctly per section.

---

## 6. Phase 2 — Write Capability

### 6.1 Tabs in scope

Universe & Calendar, Positions (notes editing), Manage > Profit-take alerts, Journal.

### 6.2 Universe & Calendar editors

Same as v1.7. Bulk paste + auto-fetch button live.

### 6.3 Positions tab — notes editing

Disabled for IBKR-synced positions (would be wiped on next sync). Manual notes via direct JSON edit until a Phase 2 positions editor is wired.

### 6.4 Alerts CRUD

Full CRUD live. PATCH endpoint added in v1.8 inventory.

### 6.5 Journal

Full CRUD live.

### 6.6 Phase 2 acceptance criteria

Unchanged from v1.7.

---

## 7. Phase 3 — Upload + Broker Integration + Charts

### 7.1 IBKR screenshot upload (legacy OCR)

Largely superseded by Web API direct sync. Functional fallback for offline backup.

### 7.2 TradingView chart upload

Unchanged from v1.7.

### 7.3 IBKR Gateway direct sync (TWS path — legacy)

`app/services/ibkr_sync.py` connects to `gnzsnz/ib-gateway:stable` via `ib_async`. Container is currently stopped; code path retained for diagnostics. **Greeks corrupted by IBC dialog popup** when the container was running — superseded by Web API path.

### 7.4 Phase 3 acceptance criteria

Unchanged.

### 7.5 TradingView Lightweight Charts widget

Unchanged from v1.7. Manage tab. DP/GEX overlays.

### 7.6 Portfolio Greeks Aggregation

`compute_portfolio_greeks(positions)` aggregates per-leg `current_delta * qty * multiplier`, similar for theta/vega.

**v1.8 status:**
- When `greeks_backend == web_api`: all four Greeks (delta, theta, vega) populated. Bias classification works correctly.
- When `greeks_backend == bs_yfinance`: only delta computed. Theta/vega = 0. Future enhancement: BS-from-IV theta/vega.

Bias thresholds from `cfg("strategy.delta_bias_long_threshold")` (5000) and `delta_bias_short_threshold` (-5000).

### 7.7 Automated Earnings Date Fetcher

Unchanged from v1.7. `POST /api/calendar/fetch-earnings`.

### 7.8 BS-from-chain delta fallback (revised v1.8)

`app/services/bs_fallback.py` runs after every sync. **In v1.8 it respects `current_delta_source == "web_api"`** — skips override for legs that came back with broker-sourced Greeks. Only fills nulls (when Web API didn't return a value) and overrides legacy TWS values (which were known-corrupted).

For LEAPs not in yfinance's first 8 expiries, does a one-shot per-expiry chain pull via `yf.Ticker(ticker).option_chain(expiry)`.

Long-equivalent delta convention: call positive, put negative (`call_delta - 1.0` for puts).

### 7.9 USD-native account thresholds (revised v1.8)

Briefing's account block compares USD account values directly against USD floors:

```json
"account": {
  "net_liq": 84032.58,
  "excess_liq": 31056.24,
  "available_funds": 25775.35,
  "currency": "USD",
  "fx_rate_eur_usd": 1.1695,
  "eur_equivalent": { ... },
  "thresholds": {
    "available_funds_floor_usd": 17000,
    "excess_liq_floor_usd": 25000,
    "available_funds_ok": true,
    "excess_liq_ok": true
  }
}
```

Floors read from `cfg("strategy.available_funds_min_usd")` and `cfg("strategy.excess_liq_min_usd")`. Frontend `renderAccountStats` shows USD primary + EUR sub-text + USD threshold check.

EUR conversion (`app/services/fx.py` via yfinance EURUSD=X) retained for the EUR sub-text display only — not used in threshold logic.

### 7.10 IBKR Web API + CP Gateway (NEW v1.8 — primary broker integration)

`voyz/ibeam` Docker container running CP Gateway at `https://localhost:5000`. Replaces legacy TWS Gateway for broker integration.

#### Architecture

```
ibeam container ─── selenium login ──→ IBKR SSO ──→ CP Gateway authenticated session
ibeam tickle loop ────────────────────────────────→ keeps session alive every 60s
                                                       ↑
                                                       │ httpx (Cookie: api={token})
                                                       │
fortress dashboard ────────────────────────────────────┘
```

#### app/services/ibkr_web/ package

- **`client.py`** — `WebApiClient` wraps `httpx.Client`. On first request POSTs `/tickle`, captures `session` token from response, includes as `Cookie: api={token}` on all subsequent requests. RPS limiter at 8/sec local (under IBKR's 10/sec global cap).
- **`session.py`** — `tickle_once`, `auth_status`, `reauthenticate`, `logout`, `session_summary` (returns 4-flag state: connected/authenticated/established/competing).
- **`portfolio.py`** — `/portfolio/accounts` (must be called first), `/portfolio/{accountId}/positions/{pageId}` (paginated), `/summary`, `/ledger`. `extract_summary_field` parses IBKR's nested format.
- **`snapshot.py`** — Two-step pattern: preflight request seeds IServer streaming, 1.5s sleep, then read returns values. `_PRIMED` set caches conids per process.
- **`capability.py`** — Probes both backends. OPRA test snapshots first 3 option positions from the account; if any return `7308` (delta) populated, `opra_subscribed = true`. Cached 60s.

#### Field tag mapping (cpapi-v1 verified May 4, 2026)

| Tag | Field |
|---|---|
| 31 | Last |
| 84 / 85 / 86 / 88 | Bid / BidSz / Ask / AskSz |
| 7059 | Last Size |
| 7308 | Delta |
| 7309 | Gamma |
| 7310 | Theta |
| 7311 | Vega |
| 7633 | Option IV (per strike) |
| 7635 | Mark |

Snapshot fields list:
```
fields=31,84,85,86,88,7059,7283,7295,7296,7308,7309,7310,7311,7633,7635
```

#### app/services/ibkr_sync_web.py

Same per-leg output schema as legacy `ibkr_sync.py`. Field mapping from IBKR Web API:
- `position` → `qty`
- `avgCost` → `avg_cost`
- `mktValue` → `market_value`
- `expiry` (YYYYMMDD) → `expiry` (YYYY-MM-DD)
- `strike` (string) → `short_strike` (float)
- `putOrCall` → `right` (C/P)
- `assetClass` → `sec_type`
- `conid` → `conid` (used for primary-key matching to existing positions)

After `/portfolio/.../positions` walk + `/portfolio/.../summary` + snapshot Greeks:
1. Filter `qty=0` legs (closed but lingering).
2. Compute `net_liq_pct` from `market_value / net_liq`.
3. Run `bs_fallback.fill_missing_deltas` for legs without Web API Greeks.
4. Compute `spy_hedge_coverage` from `SPY_HEDGE` legs.
5. Tag `greeks_backend_used: "web_api"`.

#### app/services/ibkr_sync_synthetic.py

Used when `greeks_backend == bs_yfinance`. Refreshes BS deltas against existing `active_positions.json` book without touching the broker. Useful when CP Gateway is down or for forced fallback.

### 7.11 Schema-driven Settings system (NEW v1.8)

`app/services/config_store.py` provides:
- **`load()`** — called once at module import; reads `quant/fortress_config.json` (or starts from `DEFAULTS` if missing); deep-merges with `DEFAULTS` so new keys auto-populate after upgrades.
- **`save()`** — atomic write to disk (write-temp + rename).
- **`cfg(key, default)`** — dot-notation getter (`cfg("strategy.delta_critical_threshold")`).
- **`set_value(key, value)`** — single-value write.
- **`update_section(section, dict)`** — bulk section update.
- **`reset_to_defaults()`** — wipe and reload from `DEFAULTS`.

Threading: in-memory `_config` dict + RLock. Read returns a deepcopy (safe across threads).

`app/routes/settings.py` exposes the four endpoints (§4 above) backed by `config_store`. The schema (`SCHEMA` dict in the route module) defines field metadata: label, unit, type, options, description, min/max/step. Settings UI (`app/static/settings.js`) renders from this schema.

Atomic writes via `config_store.save()` use the `tmp + rename` pattern. **Settings backups not yet wired** — could copy the `state.write_json` timestamped-backup pattern.

---

## 8. Phase 4 — Strategy Logic Engines

### 8.0 Pre-trade gate (composite)

New Trade tab. Four checks, hard-fail on any:
1. **§3.3 hard exclusion** (NEW v1.7) — checks `ticker_universe.json` excluded list.
2. **§4 earnings blackout** — days-to-earnings vs strategy window.
3. **§7 concentration** — flags >50% as failed.
4. **§7 VIX state** — fails if VIX > `cfg("strategy.vix_high")`.

Per Strategy §15.1, failures don't mechanically block — they require explicit acknowledgment.

### 8.1 Stop-loss signal aggregator

Same as v1.7. Signal 2 (LEAP MTM 50% drop) threshold from `cfg("strategy.stop_loss_drawdown_pct")`.

### 8.2 Roll candidate evaluator

Same as v1.7. Target DTE / delta bands from `cfg("strategy.target_dte_low")` / `target_dte_high` / `target_delta_low` / `target_delta_high`.

### 8.3 Post-earnings playbook runner

Same as v1.7. IV crush floor from `cfg("strategy.iv_crush_floor_pct")`. Prime entry bands from `prime_entry_gap_low` / `prime_entry_gap_high`. High-conc override bands from `high_conc_prime_low` / `high_conc_prime_high`.

### 8.4 Jade Lizard credit gate (§2.E)

Same as v1.7. Min credit floor from `cfg("strategy.min_credit_jade_lizard")`.

### 8.5 SPY hedge coverage (§2.D)

Same as v1.7. Target band from `cfg("strategy.spy_hedge_min_usd")` and `spy_hedge_max_usd`. **USD-native in v1.8** (was EUR in v1.7).

### 8.6 Backend dispatcher + capability check (NEW v1.8)

`POST /api/ibkr/sync` resolves the active backend per:
0. **`cfg("security.use_ibkr_web_api") == false`** → immediately forces `bs_yfinance`; steps 1–2 are skipped (NEW v1.8.2)
1. `?backend=` query param (one-shot override)
2. `cfg("technical.greeks_backend")`:
   - `"auto"` → `state.resolve_greeks_backend(settings, capability)`:
     - web_api if `capability.web_api.opra_subscribed && session.established`
     - else tws_ibkr if `capability.tws_gateway.connected`
     - else bs_yfinance
   - `"web_api"` → web_api if available, else bs_yfinance
   - `"tws_ibkr"` → tws_ibkr (errors loudly if not running)
   - `"bs_yfinance"` → forced synthetic sync

Dispatcher calls the chosen sync function:
- web_api → `ibkr_sync_web.sync_via_web_api(existing_positions, settings)`
- tws_ibkr → `ibkr_sync.sync_from_gateway(existing_positions)` (legacy)
- bs_yfinance → `ibkr_sync_synthetic.sync_synthetic(existing_positions, settings)`

Tag the result with `greeks_backend_used` and persist. Response includes `ibkr_web_api_enabled` boolean (NEW v1.8.2).

`/api/ibkr/capability` returns:
```json
{
  "checked_at": "...",
  "tws_gateway": { "configured": true, "reachable": false, "connected": false, ... },
  "web_api": {
    "configured": true,
    "session_status": { "connected": true, "authenticated": true, "established": true, "competing": false },
    "account": "U7453366",
    "opra_subscribed": true,
    "opra_test": { "test_conid": ..., "test_delta": "0.318", "test_iv": "29.2%" }
  },
  "settings_value": "auto",
  "active_backend": "web_api",
  "fallback_backend": "bs_yfinance"
}
```

OPRA test re-uses the user's own positions — tries to snapshot the first 3 option conids from the account; if any returns a non-null `7308`, `opra_subscribed = true`. Avoids needing a hardcoded test contract.

### 8.7 Phase 4 acceptance criteria

Unchanged from v1.7 + capability check returns valid JSON in <5s, dispatcher honors `greeks_backend` setting, `/api/ibkr/sync?backend=...` overrides for one-shot.

### 8.8 Data-source runtime guards (NEW v1.8.2)

Runtime enforcement of the `security.use_ibkr_web_api` and `security.use_quantdata` toggles across all dependent routes:

| Route | Guard | Behaviour when disabled |
|---|---|---|
| `POST /api/ibkr/sync` | `use_ibkr_web_api` | Forces `bs_yfinance` backend; `ibkr_web_api_enabled: false` in response |
| `POST /api/run/{script_key}` | `use_quantdata` | HTTP 503 with message directing user to Settings → Security (exempt: `position_monitor`) |
| `GET /api/chart/{ticker}` | `use_quantdata` | Returns candles with empty `dp_floors`, `gex_calls`, `gex_puts` |
| `GET /api/chart/{ticker}/levels` | `use_quantdata` | Returns empty overlay arrays |
| `GET /api/manage/stop_loss/{id}` | `use_quantdata` | DP floor signal suppressed (`dp_floors=[]`); `sources.dp_floors` = `"disabled (QuantData off in Settings > Security)"` |

QuantData-dependent scripts (blocked when `use_quantdata=false`): `premarket`, `daily`, `iv_crush`, `whale_flow`, `dark_pool_alert`, `eod_review`, `max_pain`, `entry_scoring`, `gex_oi`.

Exempt scripts (always runnable): `position_monitor` (uses only yfinance/IBKR data).

---

## 9. Cross-Cutting Concerns

### 9.1 Validation

Pydantic on all write endpoints. `routes/settings.py` validates section + key membership against `SCHEMA`.

### 9.2 Error handling

Same as v1.7. Web API errors map to:
- `GatewayUnreachable` → 503 with hint
- `WebApiError` (4xx, parse, auth) → 500 with detail
- 429 → `WebApiError("rate_limited")`, callers back off

### 9.3 Logging

`journalctl -u fortress-dashboard` captures uvicorn output. BS fallback summary logged after each sync. CP Gateway tickle / auth events logged in `docker logs cp-gateway`.

### 9.4 Backups

State files: timestamped backups in `quant/backups/` (last 50 per file). **`fortress_config.json` not yet backed up** — improvement candidate.

### 9.5 Testing

Unchanged. Manual smoke tests per phase change. Integration tests against sample data not yet wired.

### 9.6 Deployment

See VPS Implementation Guide v1.5.

### 9.7 Known issues

See Implementation Status doc.

---

## 10. Open Questions & Future Enhancements

### 10.1 Open questions

- BS-from-IV theta/vega (so bs_yfinance backend matches Web API in coverage).
- OAuth 2.0 direct migration (replaces CP Gateway, removes daily 2FA push).
- Universe tier UI editor (writes work; UI partial).
- Per-leg roll evaluation (aggregator picks one short call per ticker; deep-roll could pick a specific leg).
- Authentication on `/api/*` (Bearer token middleware — prerequisite for MCP).
- `fortress_config.json` backups (copy `state.write_json` pattern).

### 10.2 Future enhancements

- Live option chain browser inside dashboard.
- Backtest replay against historical data.
- Mobile-responsive variant.
- Multi-account support.
- Email/SMS alert notifications.
- MCP wrapper for Claude integration (proposal in `06_Fortress_MCP_Proposal_v1_1.md`).

### 10.3 Explicitly NOT supported

- Auto-execute trades.
- Real-time market data.
- Replace TradingView for charting.
- Replace IBKR for position truth.
- Replace QuantData for market structure data.

---

## 11. Stopping points

- Stop after Phase 1: 60% of value.
- Stop after Phase 2: 80% of value.
- Stop after Phase 3: 90% of value.
- **Phase 4 + 4.5 (current):** 100% of value. Code-enforced complex decisions + live-tunable thresholds.

---

## 11.5 UX Phase 1 (May 5, 2026 evening)

The dashboard surface had three pieces of pre-migration debt that became confusing once the Web API became primary:
1. The header carried a "GW" chip pointing at the legacy TWS gateway, which is intentionally offline post-migration but rendered red as if it were a problem.
2. The Uploads tab card was titled "IB Gateway sync" and warned "Gateway offline — start the Docker container," which contradicted the "✓ Sync complete" panel rendered immediately below it.
3. The Uploads sync result panel formatted NetLiq as `€84.131` (continental EUR style) while Strategy v3.6 standardized everything to USD.

UX phase 1 ships these changes:

**Sticky header (`.header-bar-sticky`).** The header is now `position: sticky; top: 0; z-index: 50` so capability and sync state remain visible while scrolling and when navigating between tabs. NetLiq and portfolio Δ are now first-class chips in the header (`#header-netliq`, `#header-portfolio-delta`) populated by `renderHeader()` from `briefing.account.net_liq` and `briefing.greeks.portfolio_delta`. The Δ chip turns amber over ±1000 and red over ±1500 (placeholder bands; tunable later via `config_store` if desired).

**Legacy TWS chip removed.** `#gw-indicator` is hidden via `display:none` (kept in DOM as a no-op so any old wiring doesn't break). Backend health is fully expressed by the `Δ via …` chip, which is now click-to-Settings.

**Row-level position actions.** The positions table grew a tenth column with a `⋯` kebab on every row. Click opens an inline menu with three actions:

| Action | Handler | Behavior |
|---|---|---|
| Evaluate stop-loss | `runPositionAction(e, "stop_loss")` | Switch to Manage tab, prefill `#stop-loss-position`, click `#stop-loss-run`, smooth-scroll-and-flash `#stop-loss-result`. |
| Find roll candidates | `runPositionAction(e, "roll")` | Same pattern against the roll evaluator. Disabled for SPY hedges and stock-only positions (`canRoll = pos.strategy !== "SPY_HEDGE" && pos.short_strike != null`). |
| Open chart | `runPositionAction(e, "chart")` | Switch to Manage, set `#chart-ticker-select` to ticker, call `renderChart()`, scroll-and-flash. |

The kebab carries a `data-pos` JSON matcher (`{ticker, short_strike, long_strike, expiry, strategy}`); `matchPosition()` resolves it against `positionsCache` from `/api/manage/positions`. The matcher is JSON-encoded inline; XSS surface is limited to the kebab's `data-pos` attribute and only consumed via `JSON.parse()`.

**Uploads card rewrite.** Title changed from "IB Gateway sync" to "Sync from IBKR." Subtitle now describes the dispatcher behavior (Web API by default, BS-yfinance fallback). The `checkGatewayStatus()` function was rewritten to read `/api/ibkr/capability` instead of the legacy `/api/ibkr/status`; the resulting badge has four states: `Web API ready`, `Web API re-auth pending`, `Fallback active — BS-yfinance`, `Legacy TWS gateway`. The legacy `/api/ibkr/status` route is retained server-side for future debugging but no longer drives any UI.

**USD-native sync display.** Both `triggerIbkrSync()` and `previewIbkrSync()` now use `fmtUsd(v) = $${Math.round(v).toLocaleString("en-US")}` for NetLiq, Excess Liq, and Available Funds. EUR equivalents continue to render in `renderAccountStats()` for the Briefing tab via the existing FX conversion path.

**Cache busters.** `app.js` and `phase4.js` script tags bumped to `?v=20260505ux2` to force browser reload.

**Out of scope (deferred to UX phase 2):** the Briefing-as-triage rebuild, command palette (`Cmd-K`), severity-coded card framing, "diff vs yesterday" mode, strategy-section tooltips on `§` references.

## 12. Change Log

- **v1.8.1 (May 5, 2026 evening) — UX phase 1: persistent header, row actions, Uploads card cleanup, GW chip removal, USD-native sync display.
- **v1.8 (May 5, 2026 PM):** Web API + CP Gateway promoted to primary broker integration (§7.10). Schema-driven Settings system + `config_store` (§7.11). Backend dispatcher + capability check (§8.6). Universe + alerts CRUD endpoints documented. §5.5.3 thresholds read from config_store. §7.9 USD-native account thresholds (was EUR-converted). All Phase 4 logic engines now read tunables from `cfg(...)`. Total endpoint count: 39.
- **v1.7 (May 4, 2026 PM):** Per-leg schema + aggregator (§3.1, §3.8). BS fallback (§7.8). FX conversion (§7.9). Excluded list enforcement (§3.3). SPY hedge endpoint. Portfolio Greeks delta-only.
- **v1.6 (May 4, 2026 AM):** §7.6 Portfolio Greeks. §7.7 Earnings auto-fetcher.
- **v1.4 / v1.5 (May 4, 2026):** §7.5 TradingView Lightweight Charts.
- **v1.2 / v1.3 (May 2, 2026):** Schema reconciliation — active_positions optional/required fields, delta drift inclusion-by-default.
- **v1.1 (May 1, 2026):** §5.5 visual indicators (VIX border, staleness banner, delta glow).
- **v1.0 (May 1, 2026):** Initial complete spec.
