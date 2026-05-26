# Fortress Dashboard — Incident Recovery Playbook

**Version 1.1 — May 18, 2026**

Recovery procedures for all known failure modes. Read this document during an incident, not before. Each section is self-contained.

---

## 1. VPS Unreachable

**Symptoms:** Dashboard at `http://76.13.138.194:3000` returns connection refused or times out.

**Steps:**

1. Log into the VPS provider control panel and verify the instance is running.
2. If stopped: start the instance. Wait 60 seconds for services to come up.
3. SSH in: `ssh -i ~/.ssh/fortress_vps ubuntu@76.13.138.194`
4. Check service status:
   ```bash
   sudo systemctl status fortress-dashboard
   sudo systemctl status nginx
   ```
5. If `fortress-dashboard` is inactive:
   ```bash
   sudo systemctl start fortress-dashboard
   journalctl -u fortress-dashboard -n 50
   ```
6. If nginx is inactive:
   ```bash
   sudo systemctl start nginx
   sudo nginx -t  # check config
   ```
7. Verify health: `curl http://localhost:8080/api/health`

---

## 2. IBKR Gateway Disconnected

**Symptoms:** Dashboard header shows amber "IBKR" badge. `GET /api/ibkr/status` returns `connected: false`. Greeks show as `—` or stale.

**Steps:**

1. Check CP Gateway container:
   ```bash
   docker ps | grep cp-gateway
   docker logs cp-gateway --tail 20
   ```
2. If container is stopped:
   ```bash
   cd /home/ubuntu/Fortress_Dashboard/cp-gateway
   docker compose up -d
   ```
3. Wait ~30 seconds. An **IBKR Mobile push notification** will arrive. Tap **Approve**.
4. Verify authentication:
   ```bash
   docker logs cp-gateway 2>&1 | grep -E "AUTHENTICATED|Login attempt" | tail -5
   ```
   Expect: `AUTHENTICATED Status(running=True, session=True, connected=True, authenticated=True, ...)`
5. Verify from dashboard:
   ```bash
   TOKEN=$(cat ~/.fortress_api_token)
   curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/ibkr/capability | python3 -m json.tool
   ```
   Expect: `web_api.session_status.established: true`

**If push notification doesn't arrive within 3 minutes:**
- ibeam retries every 60 seconds. Another push will arrive.
- During the fallback window, the dashboard still works on `bs_yfinance` path (Black-Scholes from yfinance).

---

## 3. Dashboard Service Crash

**Symptoms:** `http://76.13.138.194:3000` returns 502 Bad Gateway (nginx can't reach the backend).

**Steps:**

1. SSH to VPS.
2. Check service:
   ```bash
   sudo systemctl status fortress-dashboard
   journalctl -u fortress-dashboard -n 100
   ```
3. Look for Python tracebacks in the journal. Common causes:
   - Import error (missing dependency): `pip install -r requirements.txt` in the venv.
   - Port conflict: check if something else is on 8080: `ss -tlnp | grep 8080`
   - Config file corruption: restore from backup in `quant/backups/`.
4. Restart:
   ```bash
   sudo systemctl restart fortress-dashboard
   ```
5. Verify: `curl http://localhost:8080/api/health`

---

## 4. Frontend Not Loading (Fortress V3 React App)

**Symptoms:** Browser shows blank page, 404, or old version of the frontend at `http://76.13.138.194:3000`.

**Steps:**

1. Check nginx is serving the correct static files:
   ```bash
   ls -la /home/ubuntu/Fortress_Dashboard/app/static/
   # Should contain index.html and assets/ directory from the React build
   ```
2. If files are missing or old, redeploy from the sandbox:
   ```bash
   # On the development machine (Manus sandbox):
   cd /home/ubuntu/fortress-v2 && pnpm build
   scp -i ~/.ssh/fortress_vps -r dist/* ubuntu@76.13.138.194:/home/ubuntu/Fortress_Dashboard/app/static/
   ```
3. Restart nginx:
   ```bash
   sudo systemctl restart nginx
   ```
4. Hard-refresh the browser (Ctrl+Shift+R) to clear cached assets.

---

## 5. QuantData Credentials Expired

**Symptoms:** IV Rank Heatmap shows "no data" for all tickers. Candidates tab shows 0 rows or only placeholder rows. Market Intelligence cards show `—` for GEX/DP/Net Drift fields. VPS logs show `403 Forbidden` on outgoing QuantData requests.

**This is the most common recurring incident.** QuantData session tokens expire periodically (days to weeks).

### 5.1 Refresh via Dashboard UI (recommended — no SSH required)

1. Open the Fortress Dashboard → **Settings** → scroll to **QuantData Credentials**.
2. Click **Update Credentials**.
3. In a separate browser tab, go to [v3.quantdata.us](https://v3.quantdata.us) and log in.
4. Open DevTools (F12) → **Network** tab.
5. Filter requests by `core-lb-prod.quantdata.us`.
6. Click any request in the list.
7. In the **Headers** panel, find the **Request Headers** section.
8. Copy the value of the `authorization` header (starts with `Bearer eyJ...`).
9. Copy the full value of the `cookie` header.
10. Back in the Fortress Dashboard Settings form, paste:
    - **Auth Token** field: the `authorization` header value (with or without the `Bearer ` prefix — the backend strips it).
    - **Cookie** field: the full `cookie` header value.
11. Click **Save Credentials**.
12. The status indicator should turn green within a few seconds.

### 5.2 Verify credentials are working

```bash
TOKEN=$(cat ~/.fortress_api_token)
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8080/api/market-intelligence?ticker=SPY" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('regime_score:', d.get('regime', {}).get('overall'))
print('gex_call_wall:', d.get('gex', {}).get('call_wall'))
print('dp_floor_1:', d.get('dark_pool', {}).get('floors', [{}])[0].get('price'))
"
```

Expect non-null values for all three fields. If still null, repeat step 5.1 — the session may have been partially expired.

### 5.3 Re-run IV Crush workflow

After refreshing credentials, regenerate today's candidate data:

```bash
ssh ubuntu@76.13.138.194
cd /home/ubuntu/Fortress_Dashboard
source venv/bin/activate
python3 quant/workflow_05_iv_crush_report.py
```

This takes ~2–3 minutes (fetches data for all 19 universe tickers). When complete, the Candidates tab and IV Rank Heatmap will show live data.

### 5.4 Fallback via SSH (if dashboard UI is unavailable)

```bash
ssh ubuntu@76.13.138.194
# Edit the config file directly
nano /home/ubuntu/.quantdata-mcp/config.json
# Update "auth_token" and "cookie" fields with fresh values
# Save and exit (Ctrl+X, Y, Enter)

# Restart the dashboard service to pick up new credentials
sudo systemctl restart fortress-dashboard
```

---

## 6. Data File Corruption

**Symptoms:** Dashboard shows incorrect data, API returns 500 errors, or JSON parse errors in logs.

**Steps:**

1. Identify the corrupted file from the error log:
   ```bash
   journalctl -u fortress-dashboard -n 50 | grep -i "json\|error\|corrupt"
   ```
2. Restore from backup:
   ```bash
   ls -lt /home/ubuntu/Fortress_Dashboard/quant/backups/ | head -20
   # Find the most recent backup of the corrupted file
   cp /home/ubuntu/Fortress_Dashboard/quant/backups/<filename>_<timestamp>.json \
      /home/ubuntu/Fortress_Dashboard/quant/<filename>.json
   ```
3. Restart the service:
   ```bash
   sudo systemctl restart fortress-dashboard
   ```

---

## 7. IBKR Sync Returns 0 Positions

**Symptoms:** Positions tab is empty after sync. `GET /api/positions` returns empty array.

**Steps:**

1. Check CP Gateway session:
   ```bash
   TOKEN=$(cat ~/.fortress_api_token)
   curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/ibkr/capability | python3 -m json.tool
   ```
2. If `established: false`: follow §2 (IBKR Gateway Disconnected).
3. If `established: true` but positions still empty:
   ```bash
   # Check if IBKR account has positions
   curl -sk -X POST https://localhost:5000/v1/api/tickle | head -c 200
   curl -sk "https://localhost:5000/v1/api/portfolio/accounts" | python3 -m json.tool
   ```
4. If account shows positions in the IBKR API but not in the dashboard, trigger a fresh sync:
   ```bash
   curl -s -X POST -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/ibkr/sync --max-time 110
   ```
5. If sync still returns 0: check `active_positions.json` directly and compare to IBKR account.

---

## 8. nginx Configuration Issues

**Symptoms:** 502 Bad Gateway, or frontend loads but API calls fail with CORS errors.

**Verify nginx config:**

```bash
sudo nginx -t
cat /etc/nginx/sites-enabled/fortress
```

Expected config structure:
```nginx
server {
    listen 3000;
    root /home/ubuntu/Fortress_Dashboard/app/static;
    index index.html;

    location /api/ {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

If config is wrong: edit, then `sudo systemctl reload nginx`.

---

## Document History

| Version | Date | Changes |
|---|---|---|
| 1.1 | 2026-05-18 | Added §5 QuantData Credentials Expired (full runbook). Added §4 Frontend Not Loading. Added §8 nginx Configuration Issues. Updated all service names and paths for Fortress V3. |
| 1.0 | 2026-05-09 | Initial release. VPS, IBKR gateway, service crash, data corruption, sync procedures. |
