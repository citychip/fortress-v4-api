# Fortress Dashboard — Quick-Start & Daily Cheatsheet

**Version 1.3 — May 18, 2026**

One-page operational reference for live sessions. This is the document to open first each morning. For full detail on any item, see the linked documents.

---

## System URLs & Access

| Service | URL / Command | Notes |
|---|---|---|
| **Fortress V3 Dashboard** | `http://76.13.138.194:3000` | Main interface (React frontend) |
| Dashboard health | `GET /api/health` | Liveness check (no auth required) |
| IBKR Gateway status | `GET /api/ibkr/status` | Gateway connection + account ID |
| API docs | `http://76.13.138.194:8080/docs` | FastAPI auto-docs (backend direct) |
| VPS SSH | `ssh -i ~/.ssh/fortress_vps ubuntu@76.13.138.194` | |
| IBKR Account Mgmt | `https://www.interactivebrokers.com/sso/Login` | For Read-Only API fix |
| QuantData | `https://v3.quantdata.us` | For credential refresh |

---

## Morning Startup Sequence (5 minutes)

Run through this in order before placing any trade. **Current book state requires de-risking over new entries.**

**1. Check system health & sync** — MCP: *"Sync IBKR and tell me if it succeeded."*
- Gateway connected? Data fresh (<24h)?
- If gateway disconnected: `docker compose restart cp-gateway` on VPS, wait 90s, approve IBKR Mobile push.

**2. Morning Preflight (The Triad)** — MCP: *"Run my morning preflight: briefing, SPY hedge coverage, today's calendar, and any positions where evaluate_stop_loss returns 'act'. Flag concentration and delta-bias violations."*
- **Briefing:** Account thresholds, concentration top-3 (especially MSFT), and portfolio delta vs target.
- **Hedge:** SPY hedge coverage vs $22k–$33k target band.
- **Actions:** Any stop-loss triggers in `ACT` state and earnings on major positions today.
- *Do not look at candidates until the triad is clear.*

**3. Macro regime & flow validation (Entry days only)** — MCP: *"Show me get_market_intelligence for SPY. Then for any name from get_candidates with IVR > 50 and no earnings in the next 21 days, run get_market_intelligence for those tickers. Run pretrade_check on each."*
- SPY flip zone and DP floors set the day's bias.
- Pre-trade check is mandatory to catch size caps on concentrated positions.
- Use the **Sort dropdown** on the Market Intel page to order tickers by regime score.

---

## Key Thresholds (quick reference)

| Metric | Floor / Target | Action if breached |
|---|---|---|
| Available Funds | >€17K (>$18.7K) | Pause new entries; de-risk first |
| Portfolio Delta | ±200 | Hedge or trim |
| MSFT Concentration | <50% NetLiq | Do not add; roll to reduce |
| SPY Hedge | $22K–$33K notional | Buy puts to close gap |
| IV Rank (entry) | >50 | Minimum threshold for premium selling |
| DTE (short leg) | 21–45 DTE | Entry window |
| DTE (roll trigger) | ≤7 DTE | Roll or close |
| Delta (short call) | 0.25–0.30 | Entry target; roll if >0.35 |
| Stop-loss (short call) | 200% of credit | Mechanical close |
| Profit target (short call) | 80% of credit | Close early |

---

## Quick Commands

```bash
# Service status
sudo systemctl status fortress-dashboard
sudo systemctl status nginx

# Restart services
sudo systemctl restart fortress-dashboard
sudo systemctl restart nginx

# View live logs
journalctl -u fortress-dashboard -f

# Health check
curl http://localhost:8080/api/health

# Authenticated API call
TOKEN=$(cat ~/.fortress_api_token)
curl -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/briefing | python3 -m json.tool

# IBKR sync
curl -X POST -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/ibkr/sync --max-time 110

# Re-run IV Crush workflow (after QuantData credential refresh)
cd /home/ubuntu/Fortress_Dashboard && source venv/bin/activate
python3 quant/workflow_05_iv_crush_report.py

# CP Gateway restart
cd /home/ubuntu/Fortress_Dashboard/cp-gateway && docker compose restart
```

---

## QuantData Credential Refresh (when IV Rank shows "no data")

1. Dashboard → **Settings** → **QuantData Credentials** → **Update Credentials**
2. Open [v3.quantdata.us](https://v3.quantdata.us) → DevTools (F12) → Network → filter `core-lb-prod`
3. Click any request → copy `authorization` header value and `cookie` header value
4. Paste into the Settings form → **Save Credentials**
5. Re-run IV Crush workflow (command above)

Full procedure: `operations/04_Incident_Recovery_Playbook.md` §5.

---

## Incident Quick-Reference

| Symptom | First step | Full procedure |
|---|---|---|
| Dashboard unreachable | Check VPS instance is running | Playbook §1 |
| IBKR amber badge / no Greeks | `docker compose restart cp-gateway` | Playbook §2 |
| 502 Bad Gateway | `sudo systemctl restart fortress-dashboard` | Playbook §3 |
| Frontend blank / old version | Check `/app/static/` has React build files | Playbook §4 |
| IV Rank shows "no data" | Refresh QuantData credentials in Settings | Playbook §5 |
| Candidates shows 0 rows | Refresh QuantData credentials, re-run IV Crush workflow | Playbook §5.3 |
| Data looks wrong / 500 errors | Restore from `quant/backups/` | Playbook §6 |
| Positions tab empty after sync | Check CP Gateway session, trigger fresh sync | Playbook §7 |

---

## Document History

| Version | Date | Changes |
|---|---|---|
| 1.3 | 2026-05-18 | Updated URLs for Fortress V3 (port 3000). Added QuantData credential refresh quick-steps. Updated CP Gateway restart command. Added Sort dropdown note. |
| 1.2 | 2026-05-13 | Added Trade Reports tab. Updated morning sequence for Market Intelligence. |
| 1.1 | 2026-05-09 | Security toggles. Bearer token auth. |
| 1.0 | 2026-05-05 | Initial release. |
