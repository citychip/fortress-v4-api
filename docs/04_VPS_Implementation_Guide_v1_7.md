# Fortress Dashboard — VPS Implementation Guide

**Version 1.6 — May 18, 2026**

Complete guide for setting up and maintaining the Fortress Dashboard on a fresh VPS, or for understanding the current live configuration.

**v1.6 changes from v1.5.1:** Updated for Fortress V3 React/tRPC frontend. Added §5 (Frontend Deployment). Added §6 (QuantData Credentials Management). chart.py fix documented. All paths and service names verified against live VPS.

---

## 1. VPS Specification

| Item | Value |
|---|---|
| Provider | Vultr (or equivalent) |
| OS | Ubuntu 22.04 LTS |
| IP | 76.13.138.194 |
| RAM | 4 GB minimum (8 GB recommended) |
| Disk | 40 GB SSD |
| SSH key | `~/.ssh/fortress_vps` |
| User | `ubuntu` (sudo) |

---

## 2. Directory Structure

```
/home/ubuntu/
├── Fortress_Dashboard/          ← Main application
│   ├── app/
│   │   ├── routes/              ← Python FastAPI route files
│   │   │   ├── market_intelligence.py
│   │   │   ├── chart.py
│   │   │   ├── settings.py
│   │   │   ├── manage.py
│   │   │   └── ...
│   │   ├── static/              ← Deployed React build (index.html + assets/)
│   │   └── main.py              ← FastAPI app entry point
│   ├── quant/
│   │   ├── fortress_config.json ← Strategy configuration
│   │   ├── active_positions.json
│   │   ├── ticker_universe.json
│   │   ├── workflow_05_iv_crush_report.py
│   │   └── backups/             ← Auto-backups of JSON state files
│   ├── docs/                    ← All documentation (this file lives here)
│   ├── cp-gateway/              ← Docker Compose for IBKR CP Gateway
│   │   └── docker-compose.yml
│   └── venv/                    ← Python virtual environment
├── fortress_mcp/                ← MCP server
│   ├── fortress_mcp.py
│   └── README.md
├── .quantdata-mcp/
│   └── config.json              ← QuantData credentials (auth_token, cookie, widget_ids)
└── .fortress_api_token          ← Bearer token for API authentication
```

---

## 3. Services

### 3.1 fortress-dashboard (Python FastAPI backend)

```bash
# Service file
/etc/systemd/system/fortress-dashboard.service
/etc/systemd/system/fortress-dashboard.service.d/override.conf

# Commands
sudo systemctl status fortress-dashboard
sudo systemctl start fortress-dashboard
sudo systemctl stop fortress-dashboard
sudo systemctl restart fortress-dashboard
journalctl -u fortress-dashboard -f

# Health check
curl http://localhost:8080/api/health
```

The service runs as `ubuntu` user, activates the Python venv, and starts `uvicorn app.main:app --host 0.0.0.0 --port 8080`.

### 3.2 nginx (reverse proxy + static file server)

nginx listens on port 3000 and:
- Serves static files from `/home/ubuntu/Fortress_Dashboard/app/static/` (React build)
- Proxies `/api/*` to `http://127.0.0.1:8080`
- Handles SPA routing via `try_files $uri $uri/ /index.html`

```bash
# Config file
/etc/nginx/sites-enabled/fortress

# Commands
sudo systemctl status nginx
sudo systemctl restart nginx
sudo nginx -t  # test config
```

### 3.3 CP Gateway (IBKR Web API)

Docker Compose container providing IBKR Web API access via voyz/ibeam.

```bash
cd /home/ubuntu/Fortress_Dashboard/cp-gateway
docker compose ps
docker compose restart
docker logs cp-gateway --tail 20
```

Session expires every ~24h. An IBKR Mobile push notification is required to re-authenticate.

---

## 4. Python Backend Setup

### 4.1 Virtual Environment

```bash
cd /home/ubuntu/Fortress_Dashboard
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4.2 Environment Variables (systemd override)

```ini
# /etc/systemd/system/fortress-dashboard.service.d/override.conf
[Service]
Environment="FORTRESS_API_TOKEN=<token>"
Environment="QUANTDATA_CONFIG_PATH=/home/ubuntu/.quantdata-mcp/config.json"
Environment="IBKR_GATEWAY_URL=https://localhost:5000"
```

After editing: `sudo systemctl daemon-reload && sudo systemctl restart fortress-dashboard`

### 4.3 QuantData Configuration

```json
// /home/ubuntu/.quantdata-mcp/config.json
{
  "auth_token": "Bearer eyJ...",
  "cookie": "session=...; __cf_bm=...",
  "base_url": "https://core-lb-prod.quantdata.us",
  "widget_ids": {
    "gex_by_strike": "2e4d7ea4-ae92-4209-bca4-ccb2908ec9f6",
    "dark_pool_levels": "a1b2c3d4-...",
    "net_drift": "e5f6g7h8-...",
    "iv_rank": "i9j0k1l2-..."
  }
}
```

> **Important:** All QuantData API calls use the widget-UUID REST endpoints listed in `widget_ids`. The deprecated `tool/OPTIONS_*` tool IDs were removed in Sprint v7.1 after causing 400 errors. Do not add them back.

---

## 5. Frontend Deployment (Fortress V3)

The React frontend is built locally (in the Manus sandbox) and deployed to the VPS.

### 5.1 Build

```bash
# On the development machine (Manus sandbox)
cd /home/ubuntu/fortress-v2
pnpm install
pnpm build
# Output: /home/ubuntu/fortress-v2/dist/
```

### 5.2 Deploy

```bash
# Copy built files to VPS
scp -i ~/.ssh/fortress_vps -r /home/ubuntu/fortress-v2/dist/* \
    ubuntu@76.13.138.194:/home/ubuntu/Fortress_Dashboard/app/static/

# Restart nginx to pick up new files
ssh -i ~/.ssh/fortress_vps ubuntu@76.13.138.194 "sudo systemctl restart nginx"
```

### 5.3 Verify

Open `http://76.13.138.194:3000` in a browser. Hard-refresh (Ctrl+Shift+R) to clear cached assets. Verify the version in the footer or header matches the expected build.

### 5.4 Rollback

If the new build breaks the frontend, restore the previous build from the Manus sandbox's git history:

```bash
cd /home/ubuntu/fortress-v2
git log --oneline -10  # find the previous working commit
git checkout <commit> -- dist/  # restore the dist folder
# Then re-deploy using the scp command above
```

---

## 6. QuantData Credentials Management

### 6.1 Via Dashboard UI (recommended)

Navigate to **Settings → QuantData Credentials** in the Fortress Dashboard. Follow the on-screen instructions to extract and paste fresh credentials from a QuantData browser session.

### 6.2 Via SSH (fallback)

```bash
ssh ubuntu@76.13.138.194
nano /home/ubuntu/.quantdata-mcp/config.json
# Update "auth_token" and "cookie" fields
# Save: Ctrl+X, Y, Enter
sudo systemctl restart fortress-dashboard
```

### 6.3 Verify

```bash
TOKEN=$(cat ~/.fortress_api_token)
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8080/api/market-intelligence?ticker=SPY" | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print('score:', d['regime']['score'])"
```

Expect a non-null integer score. If null, credentials are still invalid.

---

## 7. IV Crush Workflow

The IV Crush workflow generates the `Workflow_05_IV_Crush_YYYY-MM-DD.md` file that powers the Candidates tab.

```bash
ssh ubuntu@76.13.138.194
cd /home/ubuntu/Fortress_Dashboard
source venv/bin/activate
python3 quant/workflow_05_iv_crush_report.py
```

Runtime: ~2–3 minutes (fetches data for all 19 universe tickers from QuantData + yfinance).

**Requires valid QuantData credentials.** If credentials are expired, the workflow generates an empty table and the Candidates tab will show only placeholder rows.

**Automation (P-02 backlog item):** A cron job to run this at 09:00 ET on weekdays is planned but not yet implemented.

---

## 8. MCP Server

The Fortress MCP server is installed in Claude Desktop.

```bash
# Location on VPS
/home/ubuntu/fortress_mcp/fortress_mcp.py

# GitHub repo
https://github.com/citychip/fortress-mcp

# Claude Desktop config snippet
/home/ubuntu/fortress_mcp/claude_desktop_config_snippet.json
```

The MCP server connects to the Fortress Dashboard API using the bearer token stored in `~/.fortress_api_token`. If the token changes, update the Claude Desktop config.

---

## 9. Backup and Recovery

### 9.1 Auto-backups

The dashboard automatically backs up JSON state files to `quant/backups/` on every write. Backups are timestamped: `active_positions_2026-05-18T09:00:00.json`.

### 9.2 Manual backup

```bash
cd /home/ubuntu/Fortress_Dashboard/quant
cp active_positions.json backups/active_positions_$(date +%Y%m%dT%H%M%S).json
cp fortress_config.json backups/fortress_config_$(date +%Y%m%dT%H%M%S).json
```

### 9.3 Restore

```bash
ls -lt /home/ubuntu/Fortress_Dashboard/quant/backups/ | head -20
cp backups/<filename>_<timestamp>.json <filename>.json
sudo systemctl restart fortress-dashboard
```

---

## Document History

| Version | Date | Changes |
|---|---|---|
| 1.6 | 2026-05-18 | Fortress V3 React frontend deployment (§5). QuantData credentials management (§6). chart.py deprecated tool IDs removal noted. All paths verified against live VPS. |
| 1.5.1 | 2026-05-13 | Market Intelligence endpoint. Trade Reports tab. |
| 1.5.0 | 2026-05-09 | Security section. Bearer token. CP Gateway primary. |
| 1.4.0 | 2026-05-05 | MCP server. IBKR Web API. Docker Compose. |
