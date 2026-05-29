commit f73ad3afd99446d6f2ccba7e2fb1ae9cb88cc112
Author: Fortress <fortress@citychip.dev>
Date:   Wed May 27 10:29:19 2026 +0200

    docs: comprehensive V4 documentation update (post-v8.24)
    
    - README.md: full rewrite for V4 (was V3 architecture, wrong ports/paths/repos)
    - 00_README.md: update status from Design Phase to Production; correct repo map
    - 09_Operations_Notes.md: rewrite with accurate VPS facts (port 8081, service name,
      correct restart procedure, frontend build path, git remote notes, fixed K-issues)
    - 05_MCP_Spec.md: update to 64 tools (was 61 planned); add all new tools; correct tiers
    - 08_Developer_Guide.md: correct repo names (fortress-v4-api/frontend); fix push instructions
    - scripts/README.md: rewrite for V4 (was referencing V3 paths and old port 8080)

diff --git a/docs/v4/09_Operations_Notes.md b/docs/v4/09_Operations_Notes.md
index e59c907..2afc852 100644
--- a/docs/v4/09_Operations_Notes.md
+++ b/docs/v4/09_Operations_Notes.md
@@ -1,8 +1,9 @@
 # Fortress V4 — Permanent Operations Notes
 
-**Version:** 4.0.0  
-**Status:** PERMANENT — commit to fortress-api repo root as `OPERATIONS_NOTES.md`  
-**Purpose:** Critical operational knowledge that must survive context loss, session resets, and re-deployments. This document is the authoritative memory of hard-won lessons about this system. Read this before touching the VPS.
+**Version:** 4.0.0
+**Status:** PERMANENT — update whenever new operational knowledge is discovered
+**Last updated:** 2026-05-27 (post Sprint v8.24)
+**Purpose:** Hard-won VPS operational knowledge. Read this before touching the VPS.
 
 ---
 
@@ -12,61 +13,70 @@
 
 ```bash
 # CORRECT
-ssh -i ~/.ssh/fortress_vps root@76.13.138.194
+ssh root@76.13.138.194
 
-# WRONG — hangs waiting for password, ubuntu user does not accept the key
-ssh -i ~/.ssh/fortress_vps ubuntu@76.13.138.194
+# WRONG — ubuntu user does not accept the key
+ssh ubuntu@76.13.138.194
 ```
 
-The SSH key (`ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINyw5MG6ND/grMTMAyahRkQ5v+ErtaRBB+2F+4PaYGIV fortress-vps`) is registered for root only.
-
-The private key lives at `/home/ubuntu/.ssh/fortress_vps` on the VPS itself.
-
 ---
 
-### Deploy Target: `/var/www/fortress-v2/` ONLY
+### Service restart: kill -9 + start, NOT systemctl restart
+
+`systemctl restart` times out at 45 seconds because uvicorn waits for in-flight connections to drain.
 
 ```bash
 # CORRECT
-/var/www/fortress-v2/
+kill -9 $(pgrep -f "fortress-dashboard-v4" | head -1)
+systemctl start fortress-dashboard-v4
 
-# WRONG — legacy path, do not use
-/home/ubuntu/Fortress_Dashboard/app/static/
+# WRONG — will time out
+systemctl restart fortress-dashboard-v4
 ```
 
-All deployments, file copies, and `git pull` operations must target `/var/www/fortress-v2/`. The old path was the V2 deployment location and is now stale. Deploying there will appear to succeed but the running service will be unaffected.
-
 ---
 
-### Orchestrator Path: `quant/master_orchestrator.py` (NOT root)
+### Frontend build: run from repo root, NOT client/
 
-The `fortress_orchestrator.service` systemd unit must point to:
-```
-/home/ubuntu/Fortress_Dashboard/quant/master_orchestrator.py
+```bash
+# CORRECT
+cd /home/ubuntu/fortress-app-fresh
+/home/ubuntu/fortress-app-fresh/node_modules/.bin/vite build
+
+# WRONG — vite not found, or builds to wrong output dir
+cd /home/ubuntu/fortress-app-fresh/client
+vite build
 ```
 
-Not the project root. The service crashed 2700+ times (2026-05-23) because the unit file had the wrong path. If the orchestrator enters a crash loop, check the `ExecStart` path first:
+After building, copy to the nginx web root:
 ```bash
-systemctl cat fortress_orchestrator.service | grep ExecStart
-# Must show: .../Fortress_Dashboard/venv/bin/python3 .../Fortress_Dashboard/quant/master_orchestrator.py
+cp -r /home/ubuntu/fortress-app-fresh/dist/* /var/www/fortress-v4/
 ```
 
 ---
 
-### Nav Structure: LOCKED — 8 Items Only
+### Deploy target: `/var/www/fortress-v4/` for V4, `/var/www/fortress-v2/` for V3
 
-The sidebar navigation has exactly **8 items** and this structure does not change without explicit user request:
+```
+/var/www/fortress-v4/    ← V4 frontend (HTTPS, port 443)
+/var/www/fortress-v2/    ← V3 frontend (legacy, port 3000)
+```
 
-1. Dashboard
-2. Market Intel
-3. Positions
-4. Trade
-5. Analysis
-6. Performance
-7. Earnings
-8. Config
+Do not confuse them. Deploying V4 assets to `/var/www/fortress-v2/` will silently overwrite V3.
+
+---
 
-Never add a sidebar item, rename an item, or reorder items during a coding session. If a feature seems to require a new nav item, it goes inside an existing page (new tab, new panel, new section) — not a new sidebar entry.
+### V4 API is on port 8081, V3 is on port 8080
+
+| Port | Service | Status |
+|---|---|---|
+| `8081` | V4 FastAPI (`fortress-dashboard-v4.service`) | **Active — V4 production** |
+| `8080` | V3 FastAPI (`fortress-dashboard.service`) | Legacy fallback |
+| `5000` | ibeam IBKR CP Gateway (Docker) | Active |
+| `3306` | MySQL 8 | Active (127.0.0.1 only) |
+| `6379` | Redis 7 | Active (127.0.0.1 only) |
+| `443` | nginx HTTPS | Active → /var/www/fortress-v4 + 127.0.0.1:8081 |
+| `3000` | nginx → redirects to HTTPS | Active |
 
 ---
 
@@ -75,89 +85,154 @@ Never add a sidebar item, rename an item, or reorder items during a coding sessi
 | Property | Value |
 |---|---|
 | IP | `76.13.138.194` |
-| OS | Ubuntu Linux 7.0.0-15 |
-| User for SSH | `root` |
-| SSH key name | `fortress-vps` |
-| Key fingerprint | `ssh-ed25519 AAAAC3...YGIv fortress-vps` |
-| Service | `fortress-dashboard.service` (systemd) |
-| Deploy path | `/var/www/fortress-v2/` |
-| API port | `8080` |
-| IBKR Gateway port | `5000` |
+| Hostname | `srv1321374.hstgr.cloud` |
+| OS | Ubuntu Linux |
+| SSH user | `root` |
+| V4 API service | `fortress-dashboard-v4.service` |
+| V4 code path | `/home/ubuntu/Fortress_Dashboard_v4/` |
+| V4 venv | `/home/ubuntu/Fortress_Dashboard_v4/venv/` |
+| V4 frontend source | `/home/ubuntu/fortress-app-fresh/` |
+| V4 frontend serve path | `/var/www/fortress-v4/` |
+| MCP server | `/home/ubuntu/fortress_mcp/fortress_mcp.py` |
+| TLS cert | Let's Encrypt, expires 2026-08-25 |
+| MySQL db | `fortress_v4` |
+| Bearer token | In systemd service `Environment=FORTRESS_API_TOKEN=...` |
 
 ---
 
-## Port Map
+## Systemd Service
 
-| Port | Service | Status |
+```bash
+# View service file
+systemctl cat fortress-dashboard-v4
+
+# View live logs
+journalctl -u fortress-dashboard-v4 -f
+
+# Start / stop
+systemctl start fortress-dashboard-v4
+systemctl stop fortress-dashboard-v4
+
+# Check status
+systemctl status fortress-dashboard-v4
+```
+
+The service uses a Python venv:
+```
+ExecStart=/home/ubuntu/Fortress_Dashboard_v4/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8081
+```
+
+---
+
+## Git Repositories
+
+| Repo | Local path | Branch | Remote |
+|---|---|---|---|
+| `fortress-v4-api` | `/home/ubuntu/Fortress_Dashboard_v4` | `master` | `origin` |
+| `fortress-v4-frontend` | `/home/ubuntu/fortress-app-fresh` | `main` | `v4` remote |
+| `fortress-mcp` | `/home/ubuntu/fortress_mcp` | `master` | `origin` |
+
+**Frontend push note:** The `fortress-app-fresh` directory has two remotes:
+- `origin` → `citychip/fortress-app` (legacy V2 repo — ignore)
+- `v4` → `citychip/fortress-v4-frontend` (correct V4 repo — push here)
+
+Always use `git push v4 main` for frontend, not `git push origin main`.
+
+---
+
+## Scheduler Notes
+
+All APScheduler times are **UTC**. The VPS system clock is UTC.
+
+| Script | UTC schedule | ET equivalent |
 |---|---|---|
-| `8080` | Fortress Dashboard API (production) | Active |
-| `5000` | ibeam IBKR CP Gateway | Active |
-| `3306` | MySQL 8 | Active (bind 127.0.0.1 only) |
-| `6379` | Redis 7 | Active (bind 127.0.0.1 only) |
-| `80` | NGINX (HTTP) | Active |
-| `443` | NGINX (HTTPS) | Active |
-| `8081` | Fortress API (old clone) | **PERMANENTLY CLOSED** — removed 2026-05-23 |
+| Premarket scanner | 11:00 UTC Mon–Fri | 07:00 ET (EDT) |
+| IV Crush Monitor | Every 30 min, market hours | — |
+| Position Monitor | Every 5 min, 13:35–19:55 UTC | 09:35–15:55 ET |
+| Dark Pool Alert | Every 15 min, 13:30–19:55 UTC | 09:30–15:55 ET |
+| EOD Review | 20:05 UTC Mon–Fri | 16:05 ET (EDT) |
+| EOD Portfolio Snapshot | 20:10 UTC Mon–Fri | 16:10 ET (EDT) |
+| Whale Flow | 12:00 + 16:00 UTC | 08:00 + 12:00 ET |
+| Max Pain | 13:00 + 18:00 UTC | 09:00 + 14:00 ET |
+| GEX/OI Update | 13:05 + 17:00 UTC | 09:05 + 13:00 ET |
+
+Note: All times above use EDT (UTC-4). In winter (EST, UTC-5) adjust by 1 hour.
 
-Port 8081 was a stale clone of the API (`/home/ubuntu/fortress-github/fortress-api/`) with `allow_credentials=True` in CORS and no git history. It was stopped, disabled, and the directory removed on 2026-05-23. Do not recreate it.
+Scheduler logs: `journalctl -u fortress-dashboard-v4 | grep scheduler`
 
 ---
 
-## Known Issues and Their Status
+## MySQL
 
-### K-01: OPRA Symbol Padding Inconsistency
-- **Problem:** IBKR option symbols are not always padded to the standard 21-character OPRA format before processing. This causes lookup failures when matching positions to options chain data.
-- **Fix in:** Phase 4 (P4-25) — normalise all symbols to 21-char OPRA format in the IBKR integration layer.
-- **Workaround (V3):** Manually inspect symbols in the IBKR upload if a position shows incorrect greeks.
+```bash
+# Connect
+mysql -u fortress -p fortress_v4
+
+# Key tables
+SELECT COUNT(*) FROM positions;          -- 19 rows (live)
+SELECT COUNT(*) FROM greeks;             -- ~2750 rows
+SELECT COUNT(*) FROM config;             -- 115 rows
+SELECT COUNT(*) FROM journal;            -- growing
+SELECT COUNT(*) FROM portfolio_snapshots; -- 1+ rows (post EOD)
+
+# Backup manually
+mysqldump -u fortress -p fortress_v4 > /tmp/fortress_v4_backup_$(date +%Y%m%d).sql
+```
 
-### K-02: Config Not Backed Up Before Writes
-- **Problem:** The `update_settings_section` endpoint writes directly without creating a backup first. A bad config write has no automatic recovery.
-- **Fix in:** Phase 4 (P4-21, P4-22) — auto-backup before each write; add `/api/config/backup` and `/api/config/restore` endpoints.
-- **Workaround (V3):** Before changing any config, manually export: `GET /api/config` → save the JSON.
+---
 
-### K-03: IBKR Snapshot Upload Has No Retry
-- **Problem:** If an IBKR snapshot upload fails partway through (network drop, gateway timeout), there is no retry mechanism. The upload must be repeated manually.
-- **Fix in:** Phase 4 (P4-24) — add `/api/ibkr/upload/retry` endpoint.
-- **Workaround (V3):** Re-upload the same IBKR export file. Duplicate records are deduplicated by `ibkr_con_id`.
+## IBKR CP Gateway
 
-### K-04: Journal Lacks Closed-Loop P&L Linkage
-- **Problem:** When a position is closed, the journal entry for the close is not linked to the original open entry. P&L calculation requires manually matching open and close entries.
-- **Fix in:** Phase 4 (P4-07, P4-20) — add `journal.close_id` FK and `/api/journal/close/{id}` endpoint.
-- **Workaround (V3):** Match journal entries manually by ticker + strategy + date proximity.
+```bash
+# Check gateway status
+curl -sk https://localhost:5000/v1/api/iserver/auth/status | python3 -m json.tool
+
+# Restart ibeam (Docker)
+cd /home/ubuntu/Fortress_Dashboard_v4
+docker compose restart ib-gateway
+
+# Check from API
+curl -s https://srv1321374.hstgr.cloud/api/ibkr/capability \
+  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
+```
+
+**Session expiry:** IBKR CP Gateway sessions expire ~24 hours. ibeam refreshes automatically. If `competing_sessions: true` appears, another device is logged into IBKR — log out all other IBKR sessions.
 
 ---
 
-## Removed / Legacy Items
+## Navigation Structure: LOCKED — 8 Items
+
+The sidebar has exactly 8 items and does not change without explicit request:
 
-### `fortress-github-api` service (deleted 2026-05-23)
-- Systemd service: `/etc/systemd/system/fortress-github-api.service` — **deleted**
-- Directory: `/home/ubuntu/fortress-github/fortress-api/` — **deleted**
-- Was a stale clone of the dashboard API, added `allow_credentials=True` to CORS, no git history, serving stale sample data
+1. Dashboard
+2. Market Intel
+3. Positions
+4. Trade
+5. Analysis
+6. Performance
+7. Earnings
+8. Config
 
-### V3 Design Proposal
-- File: `Fortress_V3_Design_Proposal.md` — **deleted**
-- Superseded by the V4 document pack (V4_01 through V4_09)
+New features go inside existing pages (new tab, panel, section) — never a new sidebar item.
 
 ---
 
 ## Strategy v3.7 Quick Reference
 
-The full strategy document is `Portfolio_Strategy_v3_7.md`. Key thresholds for operational reference:
-
-| Parameter | Value | Rule section |
+| Parameter | Value | Rule |
 |---|---|---|
 | Delta target | 0.35 net long | §5 |
 | Delta max (add hedge) | 0.55 | §5 |
 | Delta min (trim hedge) | 0.20 | §5 |
-| VIX warn threshold | 25 (advisory, non-blocking) | §4 |
-| VIX max (new entries) | 35 (hard block) | §4 |
+| VIX warn | 25 (advisory) | §4 |
+| VIX max (hard block) | 35 | §4 |
 | IVR minimum | 25 | §4 |
 | PCS max positions | 5 | §7 |
-| Put-side notional max | €25,000 | §7 |
+| Put-side notional max | $25,000 | §7 |
 | Trades per week max | 2 | §7 |
 | PCS earnings blackout | 10 days before | §4 |
 | LEAP entry blackout | 14 days before earnings | §4 |
 | SPY hedge coverage min | 25% of portfolio delta | §2.D |
-| LEAP: short call ratio | 1:1 with long LEAP | §2.A |
 | Stop-loss L1 | 50% of credit received | §6 |
 | Stop-loss L2 | 75% of credit | §6 |
 | Stop-loss L3 | 100% of credit | §6 |
@@ -168,100 +243,29 @@ The full strategy document is `Portfolio_Strategy_v3_7.md`. Key thresholds for o
 
 ## Source of Truth Hierarchy
 
-When data sources conflict, use this precedence:
+When data sources conflict:
 
 1. **TradingView** — technical levels, chart analysis
 2. **IBKR** — execution prices, official position data
 3. **QuantData** — market structure (order flow, dark pool, OI, GEX)
-4. **Portfolio Strategy v3.7** — all risk rules and thresholds
-
-Never let QuantData market structure data override IBKR execution reality. Never let any data source override the strategy rules.
+4. **Portfolio Strategy v3.7** — all risk rules and thresholds (overrides everything)
 
 ---
 
-## Strategies Reference
+## Known Fixed Issues (reference)
 
-| Strategy | Description | Key Rule |
+| ID | Issue | Fixed in |
 |---|---|---|
-| PMCC (Poor Man's Covered Call) | Long deep ITM LEAP call + short OTM call | 1:1 ratio; LEAP must be ≥ 9 months out |
-| PCS (Put Credit Spread) | Short OTM put + long further OTM put | Max 5 positions; max €25K put-side notional |
-| Jade Lizard | Short OTM call + short OTM put spread | No upside risk: total credit ≥ put spread width |
-| SPY Hedge | Long put on SPY (portfolio protection) | Must cover ≥ 25% of net portfolio delta |
+| K-01 | OPRA symbol 21-char padding inconsistency | v8.6 |
+| K-02 | Config not backed up before writes | v8.4 |
+| K-03 | IBKR snapshot upload had no retry | v8.9 |
+| K-04 | Journal lacked closed-loop P&L linkage | v8.8 |
 
 ---
 
-## IBKR Integration Notes
-
-- **Session expiry:** IBKR CP Gateway sessions expire every ~24 hours. ibeam refreshes automatically, but if `competing_sessions: true` appears in `get_ibkr_status`, another device is logged into IBKR — log out from all other sessions.
-- **Order type:** All orders submitted as **limit orders** at mid-price. Never market orders for multi-leg options.
-- **Symbol format:** All option symbols must be in 21-character OPRA format before processing (K-01 fix).
-- **Conid lookup:** IBKR contract IDs (conids) can change after corporate actions. If a position shows unexpected greeks, check whether the conid has changed.
-
----
-
-## QuantData Integration Notes
-
-- **Auth tokens:** `QUANTDATA_AUTH_TOKEN` and `QUANTDATA_INSTANCE_ID` must both be set for live `qd_*` tools to work.
-- **Rate limits:** QuantData enforces rate limits. The MCP server returns `rate_limited` error — wait 30 seconds and retry.
-- **Session dates:** QuantData tools require a valid trading day (`session_date`). Weekends and market holidays (e.g., Good Friday, July 4th) return empty data — not an error.
-- **SPX vs SPY:** SPX has daily (Mon–Fri) expirations. SPY also has daily. Equity options have weekly or monthly expirations — always specify `expiration_date` explicitly for equities.
-
----
-
-## Scheduler Notes
-
-- **Timezone:** All APScheduler times are US Eastern Time (ET). The VPS system clock is UTC — cron expressions must account for UTC offset.
-- **Summer (EDT):** UTC-4. "09:00 ET" = "13:00 UTC"
-- **Winter (EST):** UTC-5. "09:00 ET" = "14:00 UTC"
-- **Log location:** `/var/www/fortress-v2/logs/scheduler.log`
-- **Script failures:** A failed script does not take down the API. Errors are logged and a `scheduler_status` SSE event is emitted.
-- **Manual trigger:** All scripts can be triggered via `POST /api/scheduler/run` with `FORTRESS_MCP_ALLOW_WRITES=1`.
-
----
-
-## Filesystem Layout on VPS
-
-```
-/var/www/fortress-v2/           ← PRODUCTION (deploy here)
-  app/
-    main.py
-    engines/
-    routers/
-    models/
-    services/
-    scheduler/
-  migrations/
-  scripts/
-  logs/
-    scheduler.log
-  app/static/                   ← Built fortress-app (frontend)
-  .env
-  OPERATIONS_NOTES.md           ← This file (committed to repo)
-
-/home/ubuntu/.ssh/
-  fortress_vps                  ← SSH private key
-
-/var/backups/                   ← Backups
-  fortress-json-pre-v4/         ← Pre-migration JSON file backups
-  fortress-*.sql                ← MySQL backups
-
-/home/ubuntu/Fortress_Dashboard/         ← V3 LEGACY (still running during V4 migration)
-  app/routes/market_intelligence.py       ← Active backend (patched 2026-05-23)
-  quant/master_orchestrator.py            ← Orchestrator entry point (NOT root)
-  data/*.json                             ← V3 JSON state files (backup before migration)
-/home/ubuntu/fortress-github/fortress-app/ ← GitHub source mirror (for builds)
-/home/ubuntu/fortress-github/             ← fortress-api deleted 2026-05-23 — do not recreate
-```
-
----
-
-## Git Conventions
-
-- **Main branch:** `main` — production-ready code only
-- **Feature branches:** `feature/v4-<description>`
-- **Tag before V4 migration:** `v3-last-stable` (required for rollback)
-- **Commit format:** `[phase] short description` e.g., `[P4] Add pcs_exposure view`
-
----
+## QuantData Notes
 
-*This document is permanent. Update it when new operational knowledge is discovered. It must be committed to the fortress-api repository root as `OPERATIONS_NOTES.md` so it is always available on the VPS alongside the code.*
+- Both `QUANTDATA_AUTH_TOKEN` and `QUANTDATA_INSTANCE_ID` must be set for `qd_*` MCP tools.
+- Valid `session_date` must be a trading day (no weekends, no holidays like Good Friday).
+- SPX/SPY/QQQ have daily (Mon–Fri) expirations. Equity options: weekly/monthly only — always specify `expiration_date` explicitly.
+- Rate limits: wait 30 seconds on `rate_limited` errors.
