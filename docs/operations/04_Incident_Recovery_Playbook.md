# Fortress Dashboard — Incident Recovery Playbook

**Version 1.2 — 2026-06-01**

Recovery procedures for all known failure modes. Each section is self-contained.

> ⚠️ **WSL deployment only.** The VPS is decommissioned. All commands run in WSL on Windows.

---

## 1. Service Down / Dashboard Unreachable

**Symptoms:** `http://localhost` returns connection refused or blank page.

```bash
sudo systemctl status fortress-dashboard-v4
sudo systemctl restart fortress-dashboard-v4
journalctl -u fortress-dashboard-v4 -n 50 --no-pager
```

If service fails to start, check logs for Python errors. Common causes:
- Syntax error in recently edited Python file
- Missing dependency (`pip install <package> --break-system-packages`)
- Port 8081 already in use (`lsof -i :8081`)

---

## 2. IBKR Disconnected / No Greeks

**Symptoms:** Status bar shows IBKR amber. Greeks show as 0 or missing.

1. Navigate to `https://localhost:5000` in browser
2. Log in with IBKR credentials + approve push notification on IBKR Mobile
3. Wait ~30 seconds for session to establish
4. MCP: `trigger_ibkr_sync()` or `POST /api/ibkr/sync`
5. Verify: `get_ibkr_status()` — `connected: true`, `authenticated: true`

If CP Gateway container is down:
```bash
docker ps | grep cp-gateway
docker restart cp-gateway
```

---

## 3. Stale Position Data

**Symptoms:** Briefing shows `staleness.hours > 1` or `state: "stale"`.

IBKR auto-sync is enabled (15 min). If still stale:
```bash
# Via MCP
trigger_ibkr_sync()

# Or direct API
curl -X POST -H "Authorization: Bearer 07f03fb6e664859ac5e8113eaf1102ac43a3cb785c581af756671072b426db21" \
  http://localhost:8081/api/ibkr/sync
```

---

## 4. IV Data Zeros / Candidates Empty Intraday

**Symptoms:** IVR shows 0 or near-zero for all tickers intraday. Candidates table shows no actionable signals.

Root cause: QuantData JWT token expired mid-session.

**Quick fix via MCP:**
```
refresh_iv_data()
```

**Manual fix:**
```bash
cd ~/fortress-v4-api
source venv/bin/activate
python3 quant/qd_refresh_session.py
sudo cp ~/.quantdata-mcp/config.json /root/.quantdata-mcp/config.json
sudo systemctl restart fortress-dashboard-v4
```

The scheduler auto-refreshes at 06:00 ET and 12:00 ET to prevent this.

---

## 5. QuantData Credential Refresh (full re-auth)

When `qd_refresh_session.py` fails or QuantData shows 401 errors:

1. Go to `https://v3.quantdata.us` in browser
2. Log in with QuantData credentials
3. Your session cookie is now valid
4. Dashboard → **Settings → QuantData Auto-Login** to write the new JWT
5. Or manually:
   ```bash
   # The JWT is in the browser cookie — copy it after logging in
   # Then update the config file:
   nano ~/.quantdata-mcp/config.json
   sudo cp ~/.quantdata-mcp/config.json /root/.quantdata-mcp/config.json
   sudo systemctl restart fortress-dashboard-v4
   ```

---

## 6. Frontend Not Updating After Code Change

**Symptoms:** Code change pushed, service restarted, but UI still shows old version.

The frontend is a static build served by nginx. Code changes require a rebuild:

```bash
cd ~/fortress-v4-frontend && git pull
npm run build
sudo cp -r dist/public/* /var/www/fortress-v4/
sudo nginx -s reload
```

Hard-refresh browser (`Ctrl+Shift+R`) to clear cached assets.

---

## 7. MCP Tools Not Connecting

**Symptoms:** Claude says "I don't have access to Fortress tools" or tools return errors.

1. Fully quit Claude Desktop (system tray → Quit)
2. Verify `fortress-dashboard-v4` service is running: `sudo systemctl status fortress-dashboard-v4`
3. Verify API token in `claude_desktop_config.json` matches: `07f03fb6e664859ac5e8113eaf1102ac43a3cb785c581af756671072b426db21`
4. Relaunch Claude Desktop

For write tools returning "Write tools are disabled":
- Add `FORTRESS_MCP_ALLOW_WRITES=1` to the env block in `claude_desktop_config.json`
- Restart Claude Desktop

---

## 8. 502 Bad Gateway

**Symptoms:** Browser shows 502 when accessing `http://localhost`.

```bash
# Check nginx
sudo nginx -t
sudo nginx -s reload

# Check backend
sudo systemctl status fortress-dashboard-v4
sudo systemctl restart fortress-dashboard-v4
```

---

## 9. Git / Deploy Issues

```bash
# Pull latest from GitHub
cd ~/fortress-v4-api && git pull
cd ~/fortress-v4-frontend && git pull

# Set auth token if needed
git -C ~/fortress-v4-api remote set-url origin https://citychip:<GIT_TOKEN>@github.com/citychip/fortress-v4-api.git
git -C ~/fortress-v4-frontend remote set-url origin https://citychip:<GIT_TOKEN>@github.com/citychip/fortress-v4-frontend.git
# GIT_TOKEN is in HANDOFF.md (not stored in this repo)
```

---

## Document History

| Version | Date | Changes |
|---|---|---|
| 1.2 | 2026-06-01 | Full rewrite for WSL deployment. Removed all VPS references. Added MCP-first recovery steps. Added QuantData intraday fix. |
| 1.1 | 2026-05-18 | Updated QuantData credential refresh flow. Added CP Gateway Docker restart. |
