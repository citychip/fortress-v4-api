# Fortress V4 — Upgrade Plan
## Sprint-Ready Backlog Based on V4 Documentation + VPS Audit

**Prepared:** 2026-05-26  
**VPS:** 76.13.138.194  
**V4 service:** `/home/ubuntu/Fortress_Dashboard_v4/` → port 8081 → nginx port 3001  
**V3 service:** `/home/ubuntu/Fortress_Dashboard/` → port 8080 → nginx port 3000  

---

## Current Reality vs Target

The V4 documentation describes a fully re-architected system (dedicated engines, APScheduler, MySQL as primary store, full data migration). What actually exists on VPS today is V3 code with V4 enhancements applied in parallel — both are functionally identical as of Sprint v8.2. Key gaps between VPS reality and the V4 target spec:

| Area | Target (per docs) | Reality Today |
|---|---|---|
| Data layer | MySQL as primary store, JSON deprecated | `fortress_v4` DB exists (13 tables), all empty — routes still use JSON/config_store |
| APScheduler | 8 scripts on fixed ET schedules | No APScheduler; only asyncio IBKR auto-sync runs; scripts triggered manually via run.py |
| Engines | PositionEngine, MarketEngine, AlertEngine, ExecutionEngine | Not implemented; logic lives inline in routes |
| Config backup | `/api/config/backup` + `/api/config/restore` | ✅ DONE — Sprint v8.4 |
| OPRA padding | 21-char symbol normalisation | ✅ DONE — Sprint v8.6 |
| Journal close_id | FK linking close→open entries | ✅ DONE — Sprint v8.8 |
| New portfolio endpoints | `/api/portfolio/beta`, `/api/portfolio/sector-exposure`, `/api/portfolio/capital-efficiency` | ✅ DONE — Sprint v8.5 |
| Port 8081 | Docs say permanently closed | V4 is running here — ignore this doc note, it referred to the old stale clone |

---

## Pre-Coding VPS Updates (do before any sprints)

These are one-time infra fixes that don't require app code changes.

### VPS-1: Verify MySQL connector is installed in V4 venv
```bash
/home/ubuntu/Fortress_Dashboard_v4/venv/bin/pip show pymysql
# If missing:
/home/ubuntu/Fortress_Dashboard_v4/venv/bin/pip install pymysql --break-system-packages
```

### VPS-2: Add DB env vars to V4 systemd service
The current `/etc/systemd/system/fortress-dashboard-v4.service` has no `DATABASE_URL` or `REDIS_URL`. Add to the `[Service]` block:
```ini
Environment=MYSQL_USER=fortress
Environment=MYSQL_PASS=fortress_v4_pass
Environment=MYSQL_DB=fortress_v4
Environment=REDIS_URL=redis://localhost:6379/0
```

### VPS-3: Verify APScheduler installed in V4 venv
```bash
/home/ubuntu/Fortress_Dashboard_v4/venv/bin/pip show apscheduler
# If missing:
/home/ubuntu/Fortress_Dashboard_v4/venv/bin/pip install apscheduler==3.10.x --break-system-packages
```

### VPS-4: Tag V3 as last-stable for rollback
```bash
cd /var/www/fortress-v2
git tag v3-last-stable 2>/dev/null || true
git push origin v3-last-stable 2>/dev/null || true
```

### VPS-5: Backup JSON state files (if any exist)
```bash
mkdir -p /var/backups/fortress-json-pre-v4
find /home/ubuntu/Fortress_Dashboard/quant -name '*.json' -exec cp {} /var/backups/fortress-json-pre-v4/ \; 2>/dev/null || true
```

---

## Sprint Backlog — Priority Order

Sprints are ordered by value delivered. Each sprint is self-contained and independently deployable to V4 (port 8081) without touching V3 (port 8080).

---

### Sprint v8.3 — APScheduler (Highest Value, ~2 hours)

**Goal:** The 8 workflow scripts run automatically on their defined ET schedules without any manual trigger.

**Why first:** Currently nothing runs automatically except the IBKR auto-sync. Scripts must be manually triggered via the UI. APScheduler gives the system its autonomous operation capability — the single biggest functional gap between V3/V4 today and the V4 spec.

**Files to change:**
- `/home/ubuntu/Fortress_Dashboard_v4/app/main.py` — add APScheduler startup/shutdown lifecycle
- `/home/ubuntu/Fortress_Dashboard_v4/app/scheduler/runner.py` — new file, APScheduler setup
- `/home/ubuntu/Fortress_Dashboard_v4/app/scheduler/` — new directory with 8 script wrappers

**Implementation:**

1. Create `app/scheduler/runner.py` with `BackgroundScheduler` (APScheduler 3.x):
   - All times in UTC (VPS clock), converting ET schedules as: summer EDT = UTC+4, winter EST = UTC+5
   - Script 1 (Premarket Scanner): `07:00 ET` → `11:00 UTC` summer / `12:00 UTC` winter
   - Script 2 (IV Crush Monitor): Every 30 min during last 14 days before each earnings event
   - Script 3 (Position Monitor): Every 5 min, Mon–Fri 13:35–19:55 UTC (09:35–15:55 ET)
   - Script 4 (Dark Pool Alert): Every 15 min, Mon–Fri 13:30–19:55 UTC
   - Script 5 (EOD Review): `16:05 ET` → `20:05 UTC` summer
   - Script 6 (Whale Flow): `08:00 ET` and `12:00 ET` → `12:00` and `16:00 UTC`
   - Script 7 (Max Pain): `09:00 ET` and `14:00 ET` → `13:00` and `18:00 UTC`
   - Script 8 (GEX/OI Update): `09:05 ET` and `13:00 ET` → `13:05` and `17:00 UTC`

2. Each job calls the existing workflow scripts via `subprocess.run()` (same pattern as `run.py`) with the V4 venv python, logging to `/home/ubuntu/Fortress_Dashboard_v4/logs/scheduler.log`

3. Wire to FastAPI lifespan in `main.py`:
   ```python
   scheduler.start()  # on startup
   scheduler.shutdown()  # on shutdown
   ```

4. Add `SCHEDULER_ENABLED` env var (default `true`; set `false` to disable during development)

5. Add `/api/scheduler/status` endpoint returning last-run time + status for each of the 8 scripts

**Acceptance:** `journalctl -u fortress-dashboard-v4 -f` shows scheduler jobs firing; at least one manual trigger of each script logs to scheduler.log without errors.

---

### Sprint v8.4 — Config Backup + Restore (K-02 Fix, ~1 hour)

**Goal:** `/api/config/backup` and `/api/config/restore` endpoints added to V4. Auto-backup before every write.

**Why second:** K-02 is a data-safety risk. Any config write can corrupt settings with no recovery. With the QuantData auto-login writing to config, this is now more important than before.

**Files to change:**
- `/home/ubuntu/Fortress_Dashboard_v4/app/routes/settings.py` — add two new endpoints

**Implementation:**

1. `GET /api/config/backup` — returns timestamped JSON of `config_store.get_all()`:
   ```json
   {
     "timestamp": "2026-05-26T14:30:00Z",
     "version": "v4",
     "config": { ...full config... }
   }
   ```
   Also writes a copy to `/home/ubuntu/Fortress_Dashboard_v4/quant/config_backups/config_{timestamp}.json`

2. `POST /api/config/restore` — accepts the backup JSON format, validates required keys present, then calls `config_store.reset_to_defaults()` then applies the backup values section by section

3. Wrap every `config_store.update_section()` call in `settings.py` with an auto-backup call before the write

4. Keep only the last 10 backups (rotate old ones out)

**Acceptance:** `GET /api/config/backup` returns full config JSON; `POST /api/config/restore` with that JSON restores the config; bad restore payload returns 400 with clear error.

---

### Sprint v8.5 — Portfolio Endpoints (P4-16, P4-17, P4-18, ~1.5 hours)

**Goal:** Three new read endpoints that power the Tier 1.5 MCP tools.

**Why third:** Beta-weighted delta endpoint is already computed in the briefing — exposing it as a dedicated endpoint unlocks the `get_portfolio_beta`, `get_sector_exposure`, and `get_capital_efficiency` MCP tools from the V4 spec. These are the new analytical tools that don't exist at all in V3.

**Files to change:**
- `/home/ubuntu/Fortress_Dashboard_v4/app/routes/` — new `portfolio.py` router
- `/home/ubuntu/Fortress_Dashboard_v4/app/main.py` — register new router

**New endpoints:**

1. `GET /api/portfolio/beta`
   ```json
   {
     "beta_weighted_delta": 387.9,
     "spy_price": 562.40,
     "component_betas": [
       {"ticker": "AAPL", "beta": 1.24, "delta_contribution": 120.5},
       ...
     ],
     "as_of": "2026-05-26T14:30:00Z"
   }
   ```
   Logic: reuse `state.compute_beta_weighted_delta()` already implemented in Sprint v8.2.

2. `GET /api/portfolio/sector-exposure`
   ```json
   {
     "sectors": [
       {"sector": "Technology", "notional": 85430.00, "pct": 42.1, "tickers": ["AAPL","MSFT"]},
       ...
     ],
     "concentration_max_pct": 40.0,
     "breach": false
   }
   ```
   Logic: group positions by sector (use yfinance `info["sector"]` with 24h TTL cache), sum notional.

3. `GET /api/portfolio/capital-efficiency`
   ```json
   {
     "capital_efficiency": 0.187,
     "threshold": 0.12,
     "above_threshold": true,
     "by_position": [
       {"position_id": "...", "ticker": "AAPL", "efficiency": 0.22},
       ...
     ]
   }
   ```
   Logic: `capital_efficiency = annual_income / capital_at_risk`. Annual income = premium collected × (365/DTE). Capital at risk = max loss on spread / PMCC cost basis.

**Acceptance:** All three endpoints return data for the current portfolio; `get_capability` response updated to reflect new routes.

---

### Sprint v8.6 — OPRA Symbol Padding (K-01 Fix, ~1 hour)

**Goal:** All IBKR option symbols normalised to 21-character OPRA format before processing. Fixes occasional position lookup failures.

**Why fourth:** K-01 causes silent wrong-greeks bugs. Low-complexity fix with high reliability impact.

**OPRA format:** `SYMBOL[padded to 6] + YYMMDD + C/P + STRIKE[8 digits, 3 decimal implied]`
Example: `AAPL  260117C00170000` (AAPL with 2 spaces, 2026-01-17, Call, $170.00 strike)

**Files to change:**
- `/home/ubuntu/Fortress_Dashboard_v4/app/services/` — new `opra.py` utility
- `/home/ubuntu/Fortress_Dashboard_v4/app/routes/positions.py` — apply normalisation
- `/home/ubuntu/Fortress_Dashboard_v4/app/services/state.py` — apply normalisation when building position objects

**Implementation:**
```python
def normalise_opra(symbol: str) -> str:
    """Pad/normalise a symbol to 21-character OPRA format."""
    if len(symbol) == 21:
        return symbol
    # Extract components via regex, reformat with correct padding
    ...
```

**Acceptance:** Unit test: `normalise_opra("AAPL260117C00170000")` → `"AAPL  260117C00170000"` (21 chars); position greeks no longer silently mismatched.

---

### Sprint v8.7 — MySQL Data Layer Wire-up (P4-05 through P4-09, ~3 hours)

**Goal:** Wire the positions endpoint to read from MySQL `fortress_v4` tables; run migration to populate from IBKR data.

**Why fifth:** The DB exists, schema is in place, `db_v4.py` and `models_v4.py` are written — but nothing uses them. This is the foundational V4 architectural shift.

**Approach:** Rather than migrating from JSON files (which don't exist), populate MySQL from the IBKR sync that already runs. When IBKR sync runs, write positions to both the in-memory state AND the `positions` table.

**Files to change:**
- `/home/ubuntu/Fortress_Dashboard_v4/app/services/ibkr_sync_web.py` — add MySQL write after sync
- `/home/ubuntu/Fortress_Dashboard_v4/app/routes/positions.py` — read from MySQL when available, fall back to in-memory state
- `/home/ubuntu/Fortress_Dashboard_v4/app/services/db_v4.py` — verify connection string with new env vars

**Implementation:**

1. After every successful IBKR sync, upsert into `positions` table:
   ```python
   from app.services.db_v4 import SessionLocal
   from app.services.models_v4 import Position
   
   with SessionLocal() as db:
       for pos in synced_positions:
           db.merge(Position(**pos_to_model(pos)))
       db.commit()
   ```

2. `GET /api/positions` reads from MySQL first; falls back to in-memory state if DB unavailable (graceful degradation)

3. Migrate config to MySQL `config` table using script from Migration Guide §4.4 with V4 defaults

**Acceptance:** After IBKR sync, `SELECT COUNT(*) FROM positions` shows rows; `GET /api/positions` returns same data as before; if MySQL goes down, endpoint still returns data (from in-memory state).

---

### Sprint v8.8 — Journal Close Linkage (K-04 Fix, ~1 hour)

**Goal:** `/api/journal/close/{id}` endpoint to link a closing trade to its opening trade via `close_id`. Exposes IV crush realized and DTE at close.

**Files to change:**
- `/home/ubuntu/Fortress_Dashboard_v4/app/routes/journal.py` — add close endpoint
- Journal schema to add `close_id`, `iv_crush_realized`, `dte_at_close` fields

**New endpoint:**
```
POST /api/journal/close/{close_entry_id}
Body: { "open_entry_id": "...", "iv_crush_realized": 0.42, "dte_at_close": 18 }
```

Stores the link; GET /api/journal returns entries with `close_id` populated.

**Acceptance:** After closing a position, can call the endpoint; subsequent GET /api/journal shows the linkage.

---

### Sprint v8.9 — IBKR Upload Retry (K-03 Fix, ~45 min)

**Goal:** `POST /api/ibkr/upload/retry` endpoint that re-attempts the last failed IBKR snapshot upload.

**Files to change:**
- `/home/ubuntu/Fortress_Dashboard_v4/app/routes/ibkr.py` — add retry endpoint

**Implementation:** Store last upload result in Redis. Retry endpoint reads the stored upload data and re-runs the processing pipeline.

**Acceptance:** After a failed upload, `/api/ibkr/upload/retry` succeeds; response confirms rows processed.

---

### Sprint v8.10 — Forward P&L Panel on Position Cards (~1.5 hours)

**Goal:** Wire the existing `GET /api/options/forward-pnl` backend endpoint (already built) to a UI panel inside each position accordion on the Positions page. The backend does all the maths — this is a pure frontend sprint.

**Why added:** The backend endpoint exists and is fully functional — it just has no UI surface. This is the highest-value unrealised feature in the codebase (from todo.md Sprint v5.0 Gap 2). It lets you see "if MSFT reaches 450 by Jun 20, this PMCC earns +$1,240" before making a decision.

**Files to change:**
- `/home/ubuntu/fortress-app-fresh/client/src/pages/PositionsPage.tsx` — add `ForwardPnLPanel` inside each position accordion
- `/home/ubuntu/fortress-app-fresh/client/src/components/ForwardPnLPanel.tsx` — component already exists as a skeleton; wire it up

**UI elements:**
1. Target price slider (±30% of current spot, snapping to $1 increments)
2. Target date picker (today → expiry date of the position)
3. IV adjustment slider (−50% to +50%, default 0%)
4. P&L output: single dollar figure + colour (green/red)
5. Mini P&L-vs-price sparkline curve (11 price points, using the existing Recharts setup)
6. Earnings IV-crush toggle: collapses IV by 40% post-earnings and re-renders

**API call:**
```
GET /api/options/forward-pnl?ticker=MSFT&legs=[...]&target_price=450&target_date=2026-06-20&iv_adjustment=0
```

**Acceptance:** Each position accordion has a "Simulate P&L" section; dragging the target price slider updates the P&L figure in real time (debounced 300ms); earnings toggle rerenders correctly.

---

### Sprint v8.11 — Regime Label Formatting (~30 min)

**Goal:** Standardise regime label display across all views. `STRONGLY_BULLISH` → `"Strongly Bullish"`, `BEARISH` → `"Bearish"`, etc. Currently inconsistent between Trade Builder, Market Intel, Analysis page, and Morning Brief.

**Why added:** Cosmetic but jarring — the same regime shows as `STRONGLY_BULLISH` in one panel and `"Strongly Bullish"` in another. Takes 30 minutes to fix and the `regimeInfo()` helper already exists.

**Files to change:**
- `/home/ubuntu/fortress-app-fresh/client/src/pages/MarketIntelPage.tsx` — audit all `regime` display callsites
- `/home/ubuntu/fortress-app-fresh/client/src/pages/TradeBuilderPage.tsx` — same
- `/home/ubuntu/fortress-app-fresh/client/src/pages/AnalysisPage.tsx` — same
- `/home/ubuntu/fortress-app-fresh/client/src/pages/MorningBriefPage.tsx` — same

**Implementation:** Confirm `regimeInfo()` in utils/lib converts all known regime keys; add any missing keys; replace raw `regime` string renders with `regimeInfo(regime).label`.

**Acceptance:** No raw `SNAKE_CASE` regime strings visible anywhere in the UI; all four pages show human-readable labels.

---

## What NOT to Build Yet

The V4 docs also specify these larger items. They are deferred — current V3/V4 functional parity makes them lower urgency than the above:

| Item | Why deferred |
|---|---|
| Full Engine refactor (PositionEngine, MarketEngine, AlertEngine, ExecutionEngine) | Large scope; current inline logic works correctly. Refactor after MySQL layer is solid (Sprint v8.7). |
| SSE via Redis pub/sub | Current SSE implementation works. Redis pub/sub upgrade is infra complexity with no user-visible benefit yet. |
| DTE exception CRUD endpoints | Minor feature; no current need. |
| V4 fortress-api as separate repo | Would require restructuring the whole VPS layout. Benefit unclear when the monorepo approach works. |
| tRPC 11 / React 19 upgrade | Frontend already functional; upgrade carries risk of breaking working pages. |
| Full APScheduler timezone DST handling | Can use manual UTC offset for now; seasonal DST issue to revisit in November. |

---

## Sprint Sequence Summary

| Sprint | Feature | Est. Time | Phase Backlog IDs |
|---|---|---|---|
| Pre-coding | VPS infra updates (pymysql, env vars, APScheduler pkg) | ✅ DONE | VPS-1 to VPS-5 |
| **v8.3** | **APScheduler — 8 auto workflows** | ✅ DONE | P4-14 |
| **v8.4** | **Config backup/restore + auto-backup on write** | ✅ DONE | P4-21, P4-22 (K-02) |
| **v8.5** | **Portfolio endpoints (beta, sector, capital efficiency)** | ✅ DONE | P4-16, P4-17, P4-18 |
| **v8.6** | **OPRA symbol padding** | ✅ DONE | P4-25 (K-01) |
| **v8.7** | **MySQL data layer (positions write + read)** | ✅ DONE | P4-01, P4-05 to P4-09 |
| **v8.8** | **Journal close linkage** | ✅ DONE | P4-07, P4-20 (K-04) |
| **v8.9** | **IBKR upload retry** | **~45 min** | P4-24 (K-03) |
| **v8.10** | **Forward P&L panel on position cards** | **~1.5 hr** | todo.md Sprint v5.0 Gap 2 |
| **v8.11** | **Regime label formatting** | **~30 min** | todo.md v3.5 open item |

Total estimated: ~12.5 hours of coding across 9 sprints + ~20 min pre-coding.

---

## Rollback Strategy

V3 continues running on port 8080 throughout all V4 upgrades. Every sprint deploys only to V4 (port 8081). If any V4 sprint breaks the service:

```bash
systemctl restart fortress-dashboard      # Restore V3 (port 8080) if affected
systemctl stop fortress-dashboard-v4      # Take down broken V4
# V3 continues serving at port 3000 — no user impact
```

V4 is promoted to primary (replacing port 3000) only after all sprints through v8.7 complete and MySQL layer is stable.

---

*Plan prepared: 2026-05-26 — Updated: 2026-05-26 | Based on: V4 docs zip (06–09), GitHub docs/v4 (00–10), VPS audit*
