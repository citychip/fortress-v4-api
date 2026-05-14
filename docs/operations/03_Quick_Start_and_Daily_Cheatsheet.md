# Fortress Dashboard — Quick-Start & Daily Cheatsheet

**Version 1.2 — May 13, 2026**

One-page operational reference for live sessions. This is the document to open first each morning. For full detail on any item, see the linked documents.

---

## System URLs & Access

| Service | URL / Command | Notes |
|---|---|---|
| Fortress Dashboard | `http://srv1321374:8080` or `http://<tailscale-name>:8080` | Main interface |
| Dashboard health | `GET /api/health` | Liveness check |
| IBKR Gateway status | `GET /api/ibkr/status` | Gateway connection + account ID |
| API docs | `http://srv1321374:8080/docs` | FastAPI auto-docs |
| VPS SSH | `ssh ubuntu@YOUR_VPS_IP` | srv1321374 |
| IBKR Account Mgmt | `https://www.interactivebrokers.com/sso/Login` | For Read-Only API fix |

---

## Morning Startup Sequence (5 minutes)

Run through this in order before placing any trade. **Current book state requires de-risking over new entries.**

**1. Check system health & sync** — MCP: *"Sync IBKR and tell me if it succeeded."*
- Gateway connected? Data fresh (<24h)?
- If gateway disconnected: `docker compose restart ib-gateway` on VPS, wait 90s.

**2. Morning Preflight (The Triad)** — MCP: *"Run my morning preflight: briefing, SPY hedge coverage, today's calendar, and any positions where evaluate_stop_loss returns 'act'. Flag concentration and delta-bias violations."*
- **Briefing:** Account thresholds, concentration top-3 (especially MSFT), and portfolio delta vs target.
- **Hedge:** SPY hedge coverage vs $22k–$33k target band.
- **Actions:** Any stop-loss triggers in `ACT` state and earnings on major positions today.
- *Do not look at candidates until the triad is clear.*

**3. Macro regime & flow validation (Entry days only)** — MCP: *"Show me get_market_intelligence for SPY. Then for any name from get_candidates with IVR > 50 and no earnings in the next 21 days, run get_market_intelligence for those tickers. Run pretrade_check on each."*
- SPY flip zone and DP floors set the day's bias.
- Pre-trade check is mandatory to catch size caps on concentrated positions.

---

## Key Thresholds (quick reference)

| Metric | Floor / Target | Action if breached |
|---|---|---|
| Available Funds | >€17K (>$18.7K) | Pause new entries; review margin |
| Excess Liquidity | >€25K (>$27.5K) | Pause new entries; review margin |
| SPY Hedge MV | $22K–$33K USD | Add spreads if below; trim if above |
| VIX | <25 for new entries | Pause if >25; stress regime if >35 |
| Non-MSFT concentration | <20% per name | Flag; no forced trim |
| MSFT concentration | ~70% accepted | Offset by SPY hedge |
| Pacing | ≤2 new positions/week | Flag if exceeded |
| Short call delta | ≤0.30 normal | Watch 0.30–0.40; roll if >0.40 |

---

## Pre-Trade Checklist (before every new entry)

Run through this for every new position. Do not skip steps under time pressure.

- [ ] Entry score run for this ticker today? (`workflow_02_entry_scoring.py <TICKER>`)
- [ ] Pre-trade gates clear? (exclusion, earnings blackout, concentration, VIX)
- [ ] TradingView Clean Decision Chart reviewed? (D timeframe, 50/200 SMA, volume)
- [ ] Earnings date verified? (not within 10 days for PCS/Jade Lizard/Diagonal; 14 days for PMCC)
- [ ] Structural levels checked? (DP floors, GEX walls from Manage tab chart)
- [ ] Beta and sector impact checked? (does this push portfolio outside hedge band or >80% sector?)
- [ ] Strike selected from live IBKR chain? (bid/ask spread ≤10% mid, OI >100)
- [ ] Jade Lizard? → validate credit > spread width first
- [ ] Post-earnings entry? → run playbook + confirm all 4 thesis checks
- [ ] Limit order placed at mid? (never pay ask, never chase)

---

## Key MCP Prompts (copy-paste ready)

### Morning Preflight (The Triad)

```
Run my morning preflight: briefing, SPY hedge coverage, today's calendar, and any positions where evaluate_stop_loss returns 'act'. Flag concentration and delta-bias violations.
```

### Market Open (Entry Days Only)

```
Show me get_market_intelligence for SPY. Then for any name from get_candidates with IVR > 50 and no earnings in the next 21 days, run get_market_intelligence for those tickers. Run pretrade_check on each.
```

### Intraday Alerts

```
Add stop-loss alerts at the act threshold for every position over 5% of NetLiq, and a delta-watch alert at 0.7 for any position with delta > 0.6.
```

### Regime Change Check

```
Compare today's get_market_intelligence for MSFT against yesterday's get_market_intelligence for MSFT — has the dominant DP floor or GEX put wall migrated down?
```

### Pre-Trade

```
I'm thinking [TICKER] [STRATEGY]. Run the pre-trade gates.
```
```
Run the entry scorer on [TICKER].
```
```
If I add a [TICKER] [STRATEGY], what does that do to my portfolio beta and sector exposure?
```

### Post-Earnings

```
[TICKER] opened [X]%, IV crushed [Y]%. Thesis confirmed. Walk me through the playbook.
```

### Mid-Day

```
Anything I should be rolling right now?
```
```
Run the stop-loss aggregator on [TICKER]. Anything firing?
```
```
Quick pulse — anything moved into watch since the morning sync?
```

### Pre-Close

```
Pre-close sweep. What needs action before the bell?
```

### End of Day

```
What's the EOD regime signal? What's the next-day bias?
```
```
Log: [OPEN/CLOSE/ROLL] on [TICKER] [description]. Reasoning: [reasoning]. Framework rules: [§X].
```

### Weekly (Sunday ~18:00 ET)

```
Run a full portfolio audit: briefing, all positions aggregated and non-aggregated, concentration breakdown, SPY hedge coverage, and current Greeks. Then for each position over 10% of NetLiq, run evaluate_roll and tell me three concrete options to reduce concentration: roll out, scale down, or convert to a debit spread. Show me get_market_intelligence for the underlying for context.
```
```
Pull the last 30 days of journal. What patterns do you see?
```

---

## Key Dashboard Tabs

| Tab | Primary use |
|---|---|
| **Dashboard** | Unified view: Account limits, Active Book (positions + Greeks + stop-loss), macro regime, and candidate scanner |
| **Manage** | Aggregated positions, stop-loss evaluator, roll evaluator, price chart with DP/GEX overlays |
| **New Trade** | Pre-trade gate checker, Jade Lizard validator |
| **Playbook** | Post-earnings matrix entry |
| **Universe** | Editable Tier 1/2/Macro/Excluded list — add, remove, move, exclude tickers inline; earnings auto-fetch |
| **Journal** | Trade log, outcome metrics, pacing budget |
| **Settings** | Change strategy thresholds, technical variables, and display preferences without editing code |
| **Uploads** | IBKR screenshot OCR (legacy), TradingView chart upload + annotation |

---

## Key API Endpoints (for direct curl or MCP)

| Endpoint | Use |
|---|---|
| `POST /api/ibkr/sync` | Trigger IBKR sync |
| `GET /api/briefing` | Full briefing (account + actions + regime + Greeks) |
| `GET /api/manage/positions` | Aggregated positions |
| `GET /api/manage/stop_loss/{ticker}` | 4-level stop-loss verdict |
| `GET /api/manage/roll/{ticker}` | Top 3 roll candidates + IBKR ticket text |
| `POST /api/playbook/post_earnings` | Post-earnings matrix verdict |
| `POST /api/manage/validate_jade_lizard` | Credit-vs-width gate |
| `GET /api/manage/spy_hedge_coverage` | SPY hedge MV vs $22–33K target |
| `GET /api/manage/portfolio_beta` | Beta-weighted delta (pending build) |
| `GET /api/manage/sector_exposure` | Sector concentration (pending build) |
| `GET /api/manage/capital_efficiency` | BP utilisation + ROC (pending build) |
| `GET /api/manage/earnings_volatility/{ticker}` | Implied vs historical move (pending build) |

---

## VPS Quick Commands

```bash
# Check service status
sudo systemctl status fortress-dashboard
sudo systemctl status fortress_orchestrator

# Restart services
sudo systemctl restart fortress-dashboard
sudo systemctl restart fortress_orchestrator

# Check logs
sudo journalctl -u fortress-dashboard -f
sudo journalctl -u fortress_orchestrator -f

# IB Gateway
cd /opt/fortress-dashboard/ib-gateway
docker compose ps
docker compose restart ib-gateway
docker logs ib-gateway-ib-gateway-1 --tail 50

# Run a workflow script manually
source /opt/fortress-dashboard/venv/bin/activate
python3 /opt/fortress-dashboard/quant/workflow_01_premarket_scanner.py
```

---

## If Something Is Wrong

| Symptom | First action | Reference |
|---|---|---|
| Gateway disconnected | `docker compose restart ib-gateway`, wait 90s | `operations/04_Incident_Recovery_Playbook.md §2` |
| Data stale (>24h) | Trigger IBKR sync; check orchestrator service | `operations/04_Incident_Recovery_Playbook.md §3` |
| Theta/vega = 0 | Known issue (S-02 in backlog) — enable IBKR Read-Only API | `review/11_Todo_Backlog.md S-02` |
| QuantData 401 error | Refresh QuantData API token | `operations/04_Incident_Recovery_Playbook.md §4` |
| Dashboard not loading | Check `fortress-dashboard` service status | `operations/04_Incident_Recovery_Playbook.md §1` |
| VPS unreachable | Check VPS provider console; SSH from backup device | `operations/04_Incident_Recovery_Playbook.md §5` |
