# Fortress Dashboard — Incident Recovery Playbook

**Version 1.0 — May 5, 2026**

Step-by-step runbooks for the most likely failure scenarios during live trading. Each runbook identifies the symptom, the root cause, the recovery steps, and the fallback procedure if recovery is not possible within the trading session.

**Governing principle:** When the system is degraded, default to IBKR directly. The dashboard is a decision-support layer, not a trading requirement. Every trade can be placed manually in IBKR without the dashboard. The dashboard's job is to make decisions faster and more consistent — not to gate execution.

---

## 1. Dashboard Not Loading

**Symptom:** Browser shows connection refused or timeout on `http://srv1321374:8080`.

**Root cause:** `fortress-dashboard.service` has crashed or the VPS is unreachable.

### Recovery steps

**Step 1 — Check if VPS is reachable:**
```bash
ping YOUR_VPS_IP
ssh ubuntu@YOUR_VPS_IP
```

If SSH fails, go to §5 (VPS Unreachable).

**Step 2 — Check service status:**
```bash
sudo systemctl status fortress-dashboard
sudo journalctl -u fortress-dashboard --since "10 minutes ago"
```

**Step 3 — Restart the service:**
```bash
sudo systemctl restart fortress-dashboard
sleep 5
sudo systemctl status fortress-dashboard
```

**Step 4 — Verify it's back:**
```bash
curl http://localhost:8080/api/health
```
Expected: `{"status": "ok"}`.

**Step 5 — If service fails to start, check for Python errors:**
```bash
sudo journalctl -u fortress-dashboard -n 100
```
Common causes: missing dependency (run `pip install -r requirements.txt` in venv), port conflict (check `sudo ss -tlnp | grep 8080`), or corrupt state file (check `quant/` directory for malformed JSON).

### Fallback (if recovery takes >10 minutes)

Use IBKR directly for all position monitoring and trade execution. The QuantData reports are still available as markdown files in `~/quantdata_reports/` — SSH into the VPS and read them directly. The dashboard is not required to trade.

---

## 2. IB Gateway Disconnected

**Symptom:** Dashboard shows stale data; `GET /api/ibkr/status` returns `connected: false`; Briefing tab shows stale-data banner that won't clear after sync.

**Root cause:** IB Gateway Docker container has crashed, lost its session, or is in the "write access dialog" loop.

### Recovery steps

**Step 1 — Check container status:**
```bash
cd /opt/fortress-dashboard/ib-gateway
docker compose ps
docker logs ib-gateway-ib-gateway-1 --tail 50
```

**Step 2 — Look for the write-access dialog symptom:**
In the logs, look for repeated lines like:
```
API client needs write access action confirmation
remove Client 11
```
This is the known issue (Todo S-02). The IBC layer dismisses each dialog after ~30 seconds, but it corrupts in-flight Greeks snapshots. Recovery: complete the IBKR account-level Read-Only API fix (see §2.1 below).

**Step 3 — Restart the gateway:**
```bash
docker compose restart ib-gateway
```
Wait 60–90 seconds for the gateway to authenticate and open the API port.

**Step 4 — Verify health:**
```bash
docker compose ps
# Status should show (healthy) within 90 seconds
```
Then trigger a fresh sync from the dashboard or via:
```bash
curl -X POST http://localhost:8080/api/ibkr/sync
```

**Step 5 — If restart doesn't fix it:**
```bash
docker compose down
docker compose up -d
```
Wait 90 seconds, then re-verify.

### 2.1 Permanent fix: IBKR Read-Only API (Todo S-02)

This fix eliminates the write-access dialog loop permanently.

1. Log into IBKR Account Management: `https://www.interactivebrokers.com/sso/Login`
2. Navigate to: Settings → Account Settings → API → Settings
3. Enable "Read-Only API"
4. Save and confirm
5. Restart the gateway: `docker compose restart ib-gateway`

After this fix: the dialog stops appearing, Greeks subscriptions stabilise, theta and vega start populating in Portfolio Greeks.

### Fallback (if gateway cannot be recovered during market hours)

The dashboard continues to function in read-only mode using the last synced state from `active_positions.json`. The BS-fallback delta computation uses yfinance IV (end-of-day), so delta estimates will be less precise but still usable for monitoring.

For position decisions requiring live Greeks: use IBKR TWS or the IBKR mobile app directly. Do not rely on the dashboard's delta values when the gateway has been disconnected for >2 hours.

---

## 3. Data Stale (Orchestrator Not Running)

**Symptom:** Briefing tab shows stale-data banner; `briefing.staleness.state == "stale"`; QuantData reports are from a previous day.

**Root cause:** `fortress_orchestrator.service` has crashed or the QuantData API is returning errors.

### Recovery steps

**Step 1 — Check orchestrator status:**
```bash
sudo systemctl status fortress_orchestrator
sudo journalctl -u fortress_orchestrator --since "1 hour ago"
```

**Step 2 — Restart the orchestrator:**
```bash
sudo systemctl restart fortress_orchestrator
sleep 10
sudo systemctl status fortress_orchestrator
```

**Step 3 — Manually trigger the missed scripts:**
```bash
source /opt/fortress-dashboard/venv/bin/activate
cd /opt/fortress-dashboard/quant

# Run the scripts that should have fired
python3 workflow_01_premarket_scanner.py
python3 quantdata_daily.py
python3 workflow_05_iv_crush_report.py
python3 workflow_07_whale_flow_report.py
```

Or trigger via the dashboard Run tab (POST `/api/run/{script_key}`).

**Step 4 — Verify reports updated:**
```bash
ls -lt ~/quantdata_reports/ | head -10
```
Reports should show today's date.

### Fallback

If the orchestrator cannot be recovered, the QuantData API can be queried directly via Python scripts run manually. The dashboard's Briefing and Candidates tabs will show stale data until a fresh report is generated. For position monitoring, use IBKR directly.

---

## 4. QuantData API 401 Error

**Symptom:** Workflow scripts fail with HTTP 401 or "Unauthorized" errors; QuantData reports are not generated; orchestrator logs show repeated API errors.

**Root cause:** The QuantData API token has expired or been revoked.

### Recovery steps

**Step 1 — Confirm the error:**
```bash
sudo journalctl -u fortress_orchestrator --since "1 hour ago" | grep -i "401\|unauthorized\|token"
```

**Step 2 — Locate the token configuration:**
The QuantData API token is stored in the environment configuration for the orchestrator. Check:
```bash
cat /etc/systemd/system/fortress_orchestrator.service
# or
cat /opt/fortress-dashboard/quant/.env
```
Look for `QUANTDATA_API_KEY` or similar.

**Step 3 — Refresh the token:**
Log into the QuantData platform at `https://v3.quantdata.us` (or the relevant portal) and generate a new API key.

**Step 4 — Update the token:**
```bash
# If stored in systemd override:
sudo systemctl edit fortress_orchestrator
# Add/update: Environment="QUANTDATA_API_KEY=<new_token>"

# If stored in .env file:
nano /opt/fortress-dashboard/quant/.env
# Update the QUANTDATA_API_KEY line
```

**Step 5 — Restart the orchestrator and verify:**
```bash
sudo systemctl daemon-reload
sudo systemctl restart fortress_orchestrator
sleep 30
# Manually run a script to confirm it works
source /opt/fortress-dashboard/venv/bin/activate
python3 /opt/fortress-dashboard/quant/workflow_01_premarket_scanner.py
```

### Fallback

During the token refresh window, QuantData data is unavailable. For trade decisions:
- Use the last available QuantData reports (markdown files in `~/quantdata_reports/`).
- Use TradingView for chart structure and support/resistance.
- Use IBKR option chain for live IV and delta.
- Do not enter new positions based on stale QuantData IV/IVR data — the IV crush signal requires fresh data.

---

## 5. VPS Unreachable

**Symptom:** SSH fails; ping fails; dashboard is unreachable; no response from `YOUR_VPS_IP`.

**Root cause:** VPS provider outage, network issue, or the server has been shut down.

### Recovery steps

**Step 1 — Check VPS provider status:**
Log into the VPS provider console (Hetzner, DigitalOcean, Vultr, or equivalent). Check if `srv1321374` is running. If it shows as stopped, start it.

**Step 2 — Check provider status page:**
If the server shows as running but is unreachable, check the provider's status page for regional outages.

**Step 3 — Use VPS console (if SSH is down):**
Most VPS providers offer a web-based console. Use it to check if the OS is running and if the services are up.

**Step 4 — If the server needs to be rebuilt:**
Follow `technical/06_VPS_Implementation_Guide_v1_5.md` to redeploy from scratch. The state files in `quant/` should be backed up to a separate location (see §5.1 below).

### 5.1 State file backup (recommended, not yet automated — Todo O-01)

The following files contain live trading state and should be backed up regularly:

```
/opt/fortress-dashboard/quant/active_positions.json
/opt/fortress-dashboard/quant/alerts.json
/opt/fortress-dashboard/quant/journal.json
/opt/fortress-dashboard/quant/earnings_blocklist.json
/opt/fortress-dashboard/quant/ticker_universe.json
/opt/fortress-dashboard/ib-gateway/.env
```

Recommended: daily `rsync` or `rclone` backup to a cloud storage bucket. This is in the Todo Backlog as O-01.

### Fallback (VPS down during market hours)

This is the most severe scenario. Fallback procedure:

1. **Position monitoring:** use IBKR TWS or IBKR mobile app directly. All position data is in IBKR — the dashboard is a view layer.
2. **Stop-loss decisions:** apply Strategy §6 rules manually. The 4-level verdict requires: (a) check if stock is below 200-day SMA in TradingView, (b) check if stock is below the last known DP floor from the most recent QuantData report, (c) assess LEAP MTM from IBKR.
3. **Roll decisions:** use IBKR option chain directly. Apply Strategy §5 rules: 30–45 DTE, delta 0.20–0.25, net credit.
4. **New entries:** defer until the system is back online. Do not enter new positions without the pre-trade gate and entry scorer.
5. **ACT_IMMEDIATELY verdict:** if two or more stop-loss signals are firing and the VPS is down, execute the close in IBKR directly. Do not wait for the dashboard.

---

## 6. ACT_IMMEDIATELY at Market Close

**Symptom:** Stop-loss aggregator returns `ACT_IMMEDIATELY` verdict (3 signals fired) with less than 30 minutes to market close.

This is a time-critical scenario. The following procedure overrides the normal "discuss before acting" principle per Strategy §15.1 — when 3 signals fire, the strategy rule is to close immediately.

### Recovery steps

**Step 1 — Confirm the verdict:**
MCP: *"Run the stop-loss aggregator on {TICKER}. Anything firing?"*
Or: Dashboard → Manage tab → Evaluate stop-loss.

Confirm all three signals are genuinely fired, not a data artifact (check if IBKR sync is fresh; check if the DP floor data is from today's report).

**Step 2 — Identify the position to close:**
Go to IBKR TWS. Find the position. Confirm the current market value and the legs to close.

**Step 3 — Execute the close in IBKR:**
- For PMCC: close the short call first (buy to close), then evaluate the LEAP separately.
- For PCS: close the entire spread (buy to close the short put, sell to close the long put) as a spread order.
- Use limit orders at mid. If not filled within 2 minutes, walk the limit toward the ask.

**Step 4 — Log the decision immediately after close:**
MCP or Journal tab: *"Log: CLOSE on {TICKER}. Reasoning: ACT_IMMEDIATELY verdict — 3 stop-loss signals fired. Framework rules: §6 ACT_IMMEDIATELY."*

**Step 5 — Post-close review:**
After market close, review whether the signals were genuine or a data artifact. If a data artifact caused a false ACT_IMMEDIATELY, document it in the journal and flag it as a tool issue per Strategy §15.4.

---

## 7. False Alarm Handling

**Symptom:** Dashboard shows a HIGH action or ACT verdict that appears to be based on stale or incorrect data.

### How to identify a false alarm

- `current_delta_source == "unavailable"` on the affected position — delta-drift signals won't fire correctly.
- `briefing.staleness.state == "stale"` — data is old; DP floor levels may be from a previous session.
- IBKR sync timestamp is >2 hours old — Greeks and MV may not reflect current market.

### Recovery steps

1. Trigger a fresh IBKR sync: `POST /api/ibkr/sync`.
2. Re-run the affected workflow script manually.
3. Re-evaluate the stop-loss or roll verdict with fresh data.
4. If the verdict changes after fresh data, the original was a false alarm — log it in the journal.
5. If the verdict persists with fresh data, treat it as genuine.

**Never dismiss a HIGH action without verifying the underlying data is fresh.** The cost of a false negative (missing a genuine signal) is higher than the cost of a false positive (investigating a stale signal).
