# Fortress V4 — Permanent Operations Notes

**Version:** 4.0.0
**Status:** PERMANENT — update whenever new operational knowledge is discovered
**Last updated:** 2026-05-27 (post Sprint v8.24)
**Purpose:** Hard-won VPS operational knowledge. Read this before touching the VPS.

---

## ⚠️ CRITICAL — READ FIRST

### SSH: Always use `root`, never `ubuntu`

```bash
# CORRECT
ssh root@76.13.138.194

# WRONG — ubuntu user does not accept the key
ssh ubuntu@76.13.138.194
```

---

### Service restart: kill -9 + start, NOT systemctl restart

`systemctl restart` times out at 45 seconds because uvicorn waits for in-flight connections to drain.

```bash
# CORRECT
kill -9 $(pgrep -f "fortress-dashboard-v4" | head -1)
systemctl start fortress-dashboard-v4

# WRONG — will time out
systemctl restart fortress-dashboard-v4
```

---

### Frontend build: run from repo root, NOT client/

```bash
# CORRECT
cd /home/ubuntu/fortress-v4-frontend
/home/ubuntu/fortress-v4-frontend/node_modules/.bin/vite build

# WRONG — vite not found, or builds to wrong output dir
cd /home/ubuntu/fortress-v4-frontend/client
vite build
```

After building, copy to the nginx web root:
```bash
cp -r /home/ubuntu/fortress-v4-frontend/dist/* /var/www/fortress-v4/
```

---

### Deploy target: `/var/www/fortress-v4/` for V4, `/var/www/fortress-v2/` for V3

```
/var/www/fortress-v4/    ← V4 frontend (HTTPS, port 443)
/var/www/fortress-v2/    ← V3 frontend (legacy, port 3000)
```

Do not confuse them. Deploying V4 assets to `/var/www/fortress-v2/` will silently overwrite V3.

---

### V4 API is on port 8081, V3 is on port 8080

| Port | Service | Status |
|---|---|---|
| `8081` | V4 FastAPI (`fortress-dashboard-v4.service`) | **Active — V4 production** |
| `8080` | V3 FastAPI (`fortress-dashboard.service`) | Legacy fallback |
| `5000` | IBKR CP Gateway (native Java, `cp-gateway.service`) | Active |
| `3306` | MySQL 8 | Active (127.0.0.1 only) |
| `6379` | Redis 7 | Active (127.0.0.1 only) |
| `443` | nginx HTTPS | Active → /var/www/fortress-v4 + 127.0.0.1:8081 |
| `3000` | nginx → redirects to HTTPS | Active |

---

## VPS Environment

| Property | Value |
|---|---|
| IP | `76.13.138.194` |
| Hostname | `srv1321374.hstgr.cloud` |
| OS | Ubuntu Linux |
| SSH user | `root` |
| V4 API service | `fortress-dashboard-v4.service` |
| V4 code path | `/home/ubuntu/fortress-v4-api/` |
| V4 venv | `/home/ubuntu/fortress-v4-api/venv/` |
| V4 frontend source | `/home/ubuntu/fortress-v4-frontend/` |
| V4 frontend serve path | `/var/www/fortress-v4/` |
| MCP server | `/home/ubuntu/fortress-mcp/fortress-mcp.py` |
| TLS cert | Let's Encrypt, expires 2026-08-25 |
| MySQL db | `fortress_v4` |
| Bearer token | In systemd service `Environment=FORTRESS_API_TOKEN=...` |

---

## Systemd Service

```bash
# View service file
systemctl cat fortress-dashboard-v4

# View live logs
journalctl -u fortress-dashboard-v4 -f

# Start / stop
systemctl start fortress-dashboard-v4
systemctl stop fortress-dashboard-v4

# Check status
systemctl status fortress-dashboard-v4
```

The service uses a Python venv:
```
ExecStart=/home/ubuntu/fortress-v4-api/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8081
```

---

## Git Repositories

| Repo | Local path | Branch | Remote |
|---|---|---|---|
| `fortress-v4-api` | `/home/ubuntu/fortress-v4-api` | `master` | `origin` |
| `fortress-v4-frontend` | `/home/ubuntu/fortress-v4-frontend` | `main` | `v4` remote |
| `fortress-mcp` | `/home/ubuntu/fortress-mcp` | `master` | `origin` |

**Frontend push note:** The `fortress-v4-frontend` directory has two remotes:
- `origin` → `citychip/fortress-app` (**ARCHIVED** — V2/V3 legacy, do not push)
- `v4` → `citychip/fortress-v4-frontend` (correct V4 repo — push here)

Always use `git push v4 main` for frontend, not `git push origin main`.

---

## Scheduler Notes

All APScheduler times are **UTC**. The VPS system clock is UTC.

| Script | UTC schedule | ET equivalent |
|---|---|---|
| Premarket scanner | 11:00 UTC Mon–Fri | 07:00 ET (EDT) |
| IV Crush Monitor | Every 30 min, market hours | — |
| Position Monitor | Every 5 min, 13:35–19:55 UTC | 09:35–15:55 ET |
| Dark Pool Alert | Every 15 min, 13:30–19:55 UTC | 09:30–15:55 ET |
| EOD Review | 20:05 UTC Mon–Fri | 16:05 ET (EDT) |
| EOD Portfolio Snapshot | 20:10 UTC Mon–Fri | 16:10 ET (EDT) |
| Whale Flow | 12:00 + 16:00 UTC | 08:00 + 12:00 ET |
| Max Pain | 13:00 + 18:00 UTC | 09:00 + 14:00 ET |
| GEX/OI Update | 13:05 + 17:00 UTC | 09:05 + 13:00 ET |

Note: All times above use EDT (UTC-4). In winter (EST, UTC-5) adjust by 1 hour.

Scheduler logs: `journalctl -u fortress-dashboard-v4 | grep scheduler`

---

## MySQL

```bash
# Connect
mysql -u fortress -p fortress_v4

# Key tables
SELECT COUNT(*) FROM positions;          -- 19 rows (live)
SELECT COUNT(*) FROM greeks;             -- ~2750 rows
SELECT COUNT(*) FROM config;             -- 115 rows
SELECT COUNT(*) FROM journal;            -- growing
SELECT COUNT(*) FROM portfolio_snapshots; -- 1+ rows (post EOD)

# Backup manually
mysqldump -u fortress -p fortress_v4 > /tmp/fortress_v4_backup_$(date +%Y%m%d).sql
```

---

## IBKR Authentication

Two modes — switch via **Settings → Security → IBKR Auth: Use ibind OAuth**:

### Mode A — ibind OAuth 1.0a (recommended, fully headless)

No daily login required. Credentials are in `/etc/systemd/system/fortress-dashboard-v4.service.d/override.conf`.

```bash
# Check OAuth status (should show authenticated: true once IBKR activates)
curl -sk https://localhost:5000/v1/api/iserver/auth/status | python3 -m json.tool

# Check from API
curl -s https://srv1321374.hstgr.cloud/api/ibkr/capability \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

**Activation:** IBKR activates consumer keys at their weekend server restart. Can take up to 2 weeks after registration. Error `401 invalid consumer` means not yet activated — wait for weekend.

**Toggle:** Set `ibkr_use_ibind_oauth: true` in Settings → Security (takes effect immediately, no restart needed).

### Mode B — CP Gateway (fallback, requires daily browser login)

Native Java gateway running as `cp-gateway.service` at port 5000.

```bash
# Check service
systemctl status cp-gateway

# Check session status
curl -sk https://localhost:5000/v1/api/iserver/auth/status | python3 -m json.tool

# Login: open browser to https://srv1321374.hstgr.cloud:5000
# (your IP 188.90.232.9 is in the conf.yaml allowlist — no SSH tunnel needed)

# Session expiry: ~24 hours. Re-login via browser when it expires.
```

**Config:** `/home/ubuntu/clientportal.gw/root/conf.yaml` — IP allowlist under `ips.allow`.

---

## Navigation Structure: LOCKED — 8 Items

The sidebar has exactly 8 items and does not change without explicit request:

1. Dashboard
2. Market Intel
3. Positions
4. Trade
5. Analysis
6. Performance
7. Earnings
8. Config

New features go inside existing pages (new tab, panel, section) — never a new sidebar item.

---

## Strategy v3.7 Quick Reference

| Parameter | Value | Rule |
|---|---|---|
| Delta target | 0.35 net long | §5 |
| Delta max (add hedge) | 0.55 | §5 |
| Delta min (trim hedge) | 0.20 | §5 |
| VIX warn | 25 (advisory) | §4 |
| VIX max (hard block) | 35 | §4 |
| IVR minimum | 25 | §4 |
| PCS max positions | 5 | §7 |
| Put-side notional max | $25,000 | §7 |
| Trades per week max | 2 | §7 |
| PCS earnings blackout | 10 days before | §4 |
| LEAP entry blackout | 14 days before earnings | §4 |
| SPY hedge coverage min | 25% of portfolio delta | §2.D |
| Stop-loss L1 | 50% of credit received | §6 |
| Stop-loss L2 | 75% of credit | §6 |
| Stop-loss L3 | 100% of credit | §6 |
| Stop-loss L4 | 150% of credit (emergency) | §6 |
| Standard roll DTE | ≤ 21 DTE | §6 |

---

## Source of Truth Hierarchy

When data sources conflict:

1. **TradingView** — technical levels, chart analysis
2. **IBKR** — execution prices, official position data
3. **QuantData** — market structure (order flow, dark pool, OI, GEX)
4. **Portfolio Strategy v3.7** — all risk rules and thresholds (overrides everything)

---

## Known Fixed Issues (reference)

| ID | Issue | Fixed in |
|---|---|---|
| K-01 | OPRA symbol 21-char padding inconsistency | v8.6 |
| K-02 | Config not backed up before writes | v8.4 |
| K-03 | IBKR snapshot upload had no retry | v8.9 |
| K-04 | Journal lacked closed-loop P&L linkage | v8.8 |

---

## QuantData Notes

- Both `QUANTDATA_AUTH_TOKEN` and `QUANTDATA_INSTANCE_ID` must be set for `qd_*` MCP tools.
- Valid `session_date` must be a trading day (no weekends, no holidays like Good Friday).
- SPX/SPY/QQQ have daily (Mon–Fri) expirations. Equity options: weekly/monthly only — always specify `expiration_date` explicitly.
- Rate limits: wait 30 seconds on `rate_limited` errors.
