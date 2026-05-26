# Fortress V4 — Operations Guide

**Version:** 4.0.0  
**Status:** Authoritative  
**Audience:** Daily operator (Steven)  

---

## 1. Daily Workflow Overview

Fortress V4 is designed around three operating windows per trading day.

```
PRE-MARKET (07:00–09:30 ET)
  ├─ Morning briefing
  ├─ IV environment check
  ├─ Premarket scanner
  └─ Position health scan

REGULAR SESSION (09:30–16:00 ET)
  ├─ Monitor SSE alert stream
  ├─ Pre-trade validation before any entry
  └─ Position management (rolls, stops)

POST-MARKET (16:00–18:00 ET)
  ├─ EOD review
  ├─ Journal closed-loop
  └─ Next-day prep
```

The 8 APScheduler scripts automate most of the scanning. The primary human decision points are: trade entry approval, roll decisions, and stop-loss actions.

---

## 2. APScheduler Scripts

All 8 scripts run automatically on the configured schedule. They can also be triggered manually via `run_script` (MCP Tier 2, write guard required) or directly via the Config page.

### Script 1 — Premarket Scanner
**Schedule:** 07:00 ET, Monday–Friday  
**Purpose:** Scans the universe for high-scoring trade candidates  
**Actions:**
1. Fetches current IVR, IV percentile, and next earnings date for all universe tickers
2. Scores each ticker 0–1 against entry criteria (IVR ≥ 25, earnings ≥ 10 days, no exclusion)
3. Pushes candidates list to SSE stream (`candidates_update` event)
4. Logs results to `scheduler.log`

**Expected output:** Candidates list refreshed on Dashboard; candidates with score > 0.75 highlighted.

---

### Script 2 — IV Crush Monitor
**Schedule:** Every 30 minutes, 14 days before each tracked earnings event  
**Purpose:** Monitors IV inflation heading into earnings; flags the optimal exit window for IV crush harvest  
**Actions:**
1. Identifies positions with earnings within 14 days
2. Checks current IV vs pre-earnings historical average
3. When IV > 1.2× historical average: fires `iv_crush_alert` SSE event
4. Triggers alert banner on Dashboard

**Expected output:** Alert when IV has inflated sufficiently to justify closing or reducing before earnings.

---

### Script 3 — Position Monitor
**Schedule:** Every 5 minutes during regular session (09:35–15:55 ET)  
**Purpose:** Monitors open positions against stop-loss levels and roll triggers  
**Actions:**
1. Fetches hydrated positions (current prices + greeks)
2. Evaluates each position against 4-level stop-loss (§6 of strategy v3.7):
   - Level 1 (50% of credit): Warning alert
   - Level 2 (75% of credit): Roll evaluation triggered
   - Level 3 (100% of credit): Stop-loss alert, action required
   - Level 4 (150% of credit): Emergency close alert
3. Evaluates DTE-based roll triggers (≤ 21 DTE for standard positions)
4. Pushes `position_update` events to SSE stream

**Expected output:** Real-time position cards on Dashboard reflect current status; alerts fire at each level.

---

### Script 4 — Dark Pool Alert
**Schedule:** Every 15 minutes during regular session  
**Purpose:** Detects unusual dark pool activity on universe tickers  
**Actions:**
1. Fetches dark pool levels for all positions + watchlist
2. Compares current DP activity vs 5-day average
3. If DP volume > 2× average on any ticker with an open position: fires `dark_pool_alert`
4. Updates Market Intel dark pool panel via SSE

**Expected output:** Alert when dark pool activity suggests unusual institutional flow.

---

### Script 5 — EOD Review
**Schedule:** 16:05 ET, Monday–Friday  
**Purpose:** Generates end-of-day portfolio summary  
**Actions:**
1. Calculates daily P&L: realised + unrealised
2. Identifies any positions that were stop-loss triggered today
3. Lists positions expiring within next 5 trading days
4. Lists upcoming earnings within 10 days for all positions
5. Pushes `eod_summary` event to SSE stream

**Expected output:** EOD summary card on Dashboard; journal suggestions generated for any closes.

---

### Script 6 — Whale Flow Scanner
**Schedule:** 08:00 ET and 12:00 ET, Monday–Friday  
**Purpose:** Scans for unusual institutional options flow on universe tickers  
**Actions:**
1. Fetches QuantData order flow for all universe tickers
2. Identifies transactions > $500K premium (whale threshold)
3. Filters to directional flow (single-leg, not spread)
4. Fires `whale_flow_alert` for significant signals

**Expected output:** Market Intel order flow panel updated; alert if whale flow detected on held tickers.

---

### Script 7 — Max Pain Calculator
**Schedule:** 09:00 ET and 14:00 ET, Monday–Friday  
**Purpose:** Updates max pain levels for all positions' expiry dates  
**Actions:**
1. Calculates max pain strike for each unique expiry across open positions
2. Computes distance from current price to max pain
3. If current price > 5% from max pain on a position near expiry: fires advisory alert
4. Updates Analysis page max pain chart via SSE

**Expected output:** Analysis page max pain always current; advisory alert when price diverges significantly.

---

### Script 8 — GEX / OI Update
**Schedule:** 09:05 ET and 13:00 ET, Monday–Friday  
**Purpose:** Updates gamma exposure and open interest data  
**Actions:**
1. Fetches GEX levels for SPY and all held tickers
2. Fetches OI by strike for current expiry of each position
3. Identifies key gamma levels (positive/negative GEX flip points)
4. Updates Market Intel via SSE
5. Fires `gex_flip_alert` if price approaches a major GEX level

**Expected output:** Market Intel dark pool and GEX panels current; alert when approaching a GEX flip.

---

## 3. Pre-Trade Procedure

**Never skip pre-trade validation.** Before placing any order:

1. **Run `pretrade_check`** with the proposed trade parameters
2. Confirm all 12 gate checks pass (no blocking failures)
3. **Confirm position limits** with `get_position_limits`
4. If the trade touches an earnings-adjacent ticker: run `get_earnings_volatility`
5. **Preview the order** with `preview_order` before approving
6. Only after all checks pass: use `approve_order` (Tier 2, write guard required)

**Blocking rules (hard stops — cannot override):**
- VIX > 25: advisory warning on all new entries (non-blocking)
- VIX ≥ 35: no new entries of any type (hard block — matches `VIXRegimeRule` in `V4_02_Architecture.md` §4)
- IVR < 25: no new short premium entries
- PCS count = 5: no new PCS entries
- Put notional ≥ €25,000: no new put-side entries
- Earnings within 10 days: no PCS entries on that ticker
- Earnings within 14 days: no new LEAP entries on that ticker
- Hard exclusion list: no entries on excluded tickers
- Weekly pace = 2: no more entries this week

---

## 4. Alert Management

### Alert Types

| Type | Source | Action Required |
|---|---|---|
| `price_target` | Manual / position monitor | Review position |
| `stop_loss_l1` | Script 3 | Monitor — warning |
| `stop_loss_l2` | Script 3 | Evaluate roll |
| `stop_loss_l3` | Script 3 | Action required — roll or close |
| `stop_loss_l4` | Script 3 | Emergency close |
| `iv_crush` | Script 2 | Consider closing before earnings |
| `dark_pool` | Script 4 | Review order flow |
| `whale_flow` | Script 6 | Review position / entry opportunity |
| `max_pain_diverge` | Script 7 | Advisory — monitor |
| `gex_flip` | Script 8 | Advisory — watch for reversal |
| `pcs_cap_warning` | Alert Engine | Check PCS count before new entry |
| `weekly_pace_warning` | Alert Engine | 1 more trade allowed this week |

### Dismissing Alerts

- **Advisory alerts** (dark pool, max pain, gex flip): dismissible after reading
- **Warning alerts** (stop_loss_l1, pcs_cap_warning): dismissible; resolved automatically when condition clears
- **Action-required alerts** (stop_loss_l3, stop_loss_l4): cannot be dismissed without logging an action in the journal

---

## 5. SSE Stream Events

The `GET /api/stream` endpoint delivers these event types to the front-end:

| Event | Trigger | Front-end Effect |
|---|---|---|
| `position_update` | Script 3 every 5 min | Dashboard positions table refreshes |
| `alert_trigger` | Any engine / script | Alert banner appears |
| `alert_clear` | Condition resolved | Alert banner disappears |
| `market_snapshot` | Market Engine every 60s | KPI strip updates |
| `order_status` | Order approved/declined/filled | Pending orders table updates |
| `scheduler_status` | Each script run completes | Status indicator in Config page |
| `candidates_update` | Script 1 | Candidates panel refreshes |
| `eod_summary` | Script 5 | EOD summary card appears |
| `iv_crush_alert` | Script 2 | Alert + IV panel update |
| `whale_flow_alert` | Script 6 | Alert + order flow update |
| `gex_flip_alert` | Script 8 | Alert + GEX chart update |

**SSE reconnection:** The front-end client reconnects automatically with exponential back-off (1s, 2s, 4s, max 30s). Connection status chip shows state.

---

## 6. VPS Operations

### SSH Access
```bash
ssh -i ~/.ssh/fortress_vps root@76.13.138.194
```
**Always use root, not ubuntu.** The ubuntu user does not accept the key.

### Service Management
```bash
# Status
systemctl status fortress-dashboard

# Restart
systemctl restart fortress-dashboard

# Logs
journalctl -u fortress-dashboard -f

# APScheduler logs
tail -f /var/www/fortress-v2/logs/scheduler.log
```

### Deployment
**Deploy target:** `/var/www/fortress-v2/` **ONLY**  
**Never deploy to:** `/home/ubuntu/Fortress_Dashboard/app/static/`

```bash
# Pull and deploy
cd /var/www/fortress-v2
git pull origin main
pip install -r requirements.txt --break-system-packages
systemctl restart fortress-dashboard
```

### Database Operations
```bash
# MySQL shell
mysql -u fortress -p fortress_db

# Alembic migrations
cd /var/www/fortress-v2
alembic upgrade head

# Backup config
curl -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/config/backup \
  > /var/backups/fortress-config-$(date +%Y%m%d).json
```

### Port Reference
| Port | Service | Status |
|---|---|---|
| 8080 | Fortress Dashboard (FastAPI) | Active |
| 5000 | IBKR CP Gateway (ibeam Docker) | Active |
| 3306 | MySQL 8 | Active (local only) |
| 6379 | Redis 7 | Active (local only) |
| 80/443 | NGINX | Active |
| 8081 | Fortress API (old) | **CLOSED — removed** |

---

## 7. IBKR Gateway Management

The IBKR CP Gateway runs as a Docker container managed by systemd.

```bash
# Check status
docker ps | grep ibeam

# View logs
docker logs ibeam --tail 50

# Restart gateway
docker restart ibeam

# Manual session re-auth (if session expires)
# Navigate to https://localhost:5000 in browser, log in
```

**Session management:**
- Sessions expire after ~24 hours if not refreshed
- ibeam auto-refreshes by default; check `competing_sessions` field in `get_ibkr_status`
- If `competing_sessions: true`: another IBKR session is logged in — log out from all other devices

---

## 8. Monitoring Checklist

### Daily (automated, verify if concerns arise)
- [ ] All 8 scripts ran on schedule (Config page scheduler status)
- [ ] SSE stream connected (top bar chip shows LIVE)
- [ ] IBKR connected (top bar chip shows IBKR ✓)
- [ ] No unresolved action-required alerts

### Weekly
- [ ] Review `scheduler.log` for errors
- [ ] Run `get_pnl` for week period
- [ ] Check `get_position_limits` — headroom for next week
- [ ] Config backup: `GET /api/config/backup`

### Monthly
- [ ] Run full performance review (Prompt 16)
- [ ] Universe review (Prompt 19)
- [ ] Database backup:
  ```bash
  mysqldump -u fortress -p fortress_db > /var/backups/fortress-$(date +%Y%m).sql
  ```
- [ ] Review and update `Portfolio_Strategy_v3_7.md` if rules have changed

---

## 9. Incident Procedures

### API returns 500 / service down
1. `systemctl status fortress-dashboard`
2. `journalctl -u fortress-dashboard -n 50`
3. Fix the issue, then: `systemctl restart fortress-dashboard`
4. Verify: `curl -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/capability`

### IBKR disconnected
1. `GET /api/ibkr/status` — check `connected` and `competing_sessions`
2. If competing session: log out of all other IBKR sessions
3. If session expired: navigate to IBKR CP Gateway UI on port 5000, re-authenticate
4. `trigger_ibkr_sync` once reconnected

### SSE stream not delivering
1. Check NGINX config — `/api/stream` must have `proxy_buffering off` and `X-Accel-Buffering: no`
2. Check Redis pub/sub: `redis-cli subscribe fortress:stream`
3. Restart services if needed

### MySQL connection failure
1. `systemctl status mysql`
2. Check disk space: `df -h` (MySQL stops writing if disk full)
3. `systemctl restart mysql`
4. Verify connections: `mysql -u fortress -p -e "SELECT 1"`

---

*Fortress V4 Operations Guide — refer to V4_09_Operations_Notes.md for permanent edge-case notes.*
