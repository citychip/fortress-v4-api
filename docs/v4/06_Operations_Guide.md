# Fortress V4 — Operations Guide

**Version:** 4.1.0
**Updated:** 2026-06-01
**Status:** Authoritative
**Audience:** Daily operator (Steven)

> ⚠️ **WSL deployment only.** The old Hostinger VPS (76.13.138.194) is decommissioned. Everything runs on WSL (Ubuntu) on Windows. There is no SSH to a remote server — all commands run in WSL locally.

---

## 1. Daily Workflow Overview

```
PRE-MARKET (07:00–09:30 ET)
  ├─ get_briefing() — check Net Liq, regime, concentration, pacing
  ├─ refresh_iv_data() — trigger fresh IV scan if stale
  ├─ get_pretrade_all() — check which tickers are actionable
  └─ Position health scan

REGULAR SESSION (09:30–16:00 ET)
  ├─ Monitor conditional alerts
  ├─ Pre-trade validation before any entry
  ├─ stage_order() → preview_order() → approve_order() for new trades
  └─ Position management (rolls, stops)

POST-MARKET (16:00–18:00 ET)
  ├─ EOD review script
  ├─ Journal closed-loop
  └─ Next-day prep
```

---

## 2. Service Management (WSL)

```bash
# Status
sudo systemctl status fortress-dashboard-v4

# Restart
sudo systemctl restart fortress-dashboard-v4

# Logs (last 50 lines)
journalctl -u fortress-dashboard-v4 -n 50 --no-pager

# Follow live logs
journalctl -u fortress-dashboard-v4 -f
```

**API token:** `07f03fb6e664859ac5e8113eaf1102ac43a3cb785c581af756671072b426db21`

---

## 3. Frontend Deployment (after code changes)

```bash
cd ~/fortress-v4-frontend && npm run build
sudo cp -r dist/public/* /var/www/fortress-v4/
sudo nginx -s reload
```

---

## 4. APScheduler Scripts

All scripts run automatically. Trigger manually via MCP `run_script()` (requires `FORTRESS_MCP_ALLOW_WRITES=1`) or via the System → Scripts tab.

| Key | Schedule (ET) | Purpose |
|---|---|---|
| `premarket` | 07:00 Mon–Fri | Universe IV scan + candidate scoring |
| `iv_crush` | Every 30 min, 13:00–20:00 UTC | IV crush monitor |
| `position_monitor` | Every 5 min, 09:35–15:55 | Stop-loss + roll triggers |
| `dark_pool_alert` | Every 15 min, 09:30–15:55 | Unusual DP activity |
| `eod_review` | 16:05 Mon–Fri | Daily P&L + journal suggestions |
| `whale_flow` | 08:00 + 12:00 Mon–Fri | Institutional order flow |
| `max_pain` | 09:00 + 14:00 Mon–Fri | Max pain strike updates |
| `gex_oi` | 09:05 + 13:00 Mon–Fri | GEX / OI updates |
| `qd_refresh` | 06:00 + 12:00 Mon–Fri | QuantData session re-auth |

---

## 5. MCP Order Workflow

Full programmatic trade workflow via MCP (requires `FORTRESS_MCP_ALLOW_WRITES=1`):

```
1. refresh_iv_data()           — get fresh IV scan
2. get_candidates()            — find actionable tickers
3. pretrade_check(ticker)      — run pre-trade gate
4. stage_order(ticker, ...)    — create order in Build Center queue
5. preview_order(order_id)     — IBKR whatif (margin/commission estimate)
6. approve_order(order_id)     — submit to IBKR
```

**stage_order legs format:**
```python
legs = [{"ticker": "GOOGL", "sec_type": "OPT", "right": "P",
          "strike": 340.0, "expiry": "20260717",
          "action": "SELL", "ratio": 1}]
```

---

## 6. Pre-Trade Rules (hard blocks)

| Rule | Threshold | Action |
|---|---|---|
| IVR minimum | < 25 | No new short premium |
| Earnings blackout (PCS) | ≤ 10 days | Hard block |
| Earnings blackout (LEAP) | ≤ 14 days | Hard block |
| VIX extreme | ≥ 35 | No new entries |
| Concentration | > 20% NL per ticker | Block (MSFT exception active) |
| Weekly pacing | 5 entries/week | Block until next Monday |
| Available funds | < $17K | Block |
| Excess liquidity | < $25K | Block |

---

## 7. IBKR Gateway Management

```bash
# Check Docker container status
docker ps | grep cp-gateway

# Restart gateway
docker restart cp-gateway

# View gateway logs
docker logs cp-gateway --tail 50
```

Auto-sync is enabled at 15-minute intervals (`ibkr_auto_sync_enabled: true`).
If data looks stale: `trigger_ibkr_sync()` via MCP, or `POST /api/ibkr/sync`.

**Daily CP Gateway login:** Navigate to `https://localhost:5000` in a browser and approve via IBKR Mobile. Sessions last ~24 hours.

---

## 8. QuantData Management

Auto-refreshes at 06:00 ET and 12:00 ET daily.

**Manual refresh:**
```bash
cd ~/fortress-v4-api && source venv/bin/activate
python3 quant/qd_refresh_session.py
sudo cp ~/.quantdata-mcp/config.json /root/.quantdata-mcp/config.json
sudo systemctl restart fortress-dashboard-v4
```

Or via MCP: `refresh_iv_data()` triggers a fresh IV scan using current credentials.

---

## 9. Port Reference

| Port | Service |
|---|---|
| 80 | nginx → React frontend |
| 8081 | Fortress FastAPI backend |
| 5000 | IBKR CP Gateway (Docker) |
| 3306 | MySQL 8 (local only) |

---

## 10. Monitoring Checklist

### Daily
- [ ] `get_briefing()` — Net Liq, concentration, pacing, staleness
- [ ] Regime check — bearish/neutral/bullish flag
- [ ] IBKR connected — `get_ibkr_status()`
- [ ] No unresolved stop-loss alerts

### Weekly
- [ ] `get_pnl()` — week P&L summary
- [ ] `get_roll_all()` — positions needing roll
- [ ] Universe review — any tickers to add/remove

### Monthly
- [ ] Performance review — `get_pnl_history(days=30)`
- [ ] Strategy doc review — confirm rules still match `Portfolio_Strategy_v3_7.md`

---

## 11. Incident Procedures

| Symptom | Action |
|---|---|
| Service down | `sudo systemctl restart fortress-dashboard-v4` |
| IBKR disconnected | Login at `https://localhost:5000`, then `trigger_ibkr_sync()` |
| 502 Bad Gateway | `sudo nginx -s reload` |
| IV data zeros / stale | `refresh_iv_data()` via MCP, or run `qd_refresh_session.py` |
| Candidates empty | `refresh_iv_data()` |
| MCP not connecting | Fully quit and relaunch Claude Desktop |
| Stale positions | `trigger_ibkr_sync()` via MCP |

*See `operations/04_Incident_Recovery_Playbook.md` for detailed step-by-step recovery.*
