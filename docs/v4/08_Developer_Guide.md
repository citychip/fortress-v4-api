# Fortress V4 — Developer Guide

**Version:** 4.0.0
**Last updated:** 2026-05-27 (post Sprint v8.24)

---

## 1. Repository Structure

| Repo | GitHub | Local path (VPS) | Branch |
|---|---|---|---|
| `fortress-v4-api` | `citychip/fortress-v4-api` | `/home/ubuntu/fortress-v4-api` | `master` |
| `fortress-v4-frontend` | `citychip/fortress-v4-frontend` | `/home/ubuntu/fortress-v4-frontend` | `main` |
| `fortress-mcp` | `citychip/fortress-mcp` | `/home/ubuntu/fortress-mcp` | `master` |

**Note on frontend remotes:** `fortress-v4-frontend` has two git remotes.
- `v4` → `citychip/fortress-v4-frontend` ← **use this** (`git push v4 main`)
- `origin` → `citychip/fortress-app` ← **ARCHIVED** (V2/V3 legacy, do not push)

---

## 2. Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Python | ≥ 3.11 | Backend and MCP server |
| Node.js | ≥ 20 LTS | Frontend |
| pnpm or npm | Latest | Frontend package manager |
| MySQL client | 8.x | For running queries manually |
| Docker | Latest stable | For ibeam IBKR CP Gateway |

---

## 3. Environment Variables

### fortress-v4-api (systemd service environment)

```env
FORTRESS_API_TOKEN=<64-char bearer token>
MYSQL_USER=fortress
MYSQL_PASS=<password>
MYSQL_DB=fortress_v4
MYSQL_HOST=127.0.0.1
REDIS_URL=redis://localhost:6379/0
QUANTDATA_AUTH_TOKEN=<qd token>
QUANTDATA_INSTANCE_ID=<qd instance id>
```

View current values:
```bash
systemctl cat fortress-dashboard-v4 | grep Environment
```

### fortress-mcp (Claude Desktop config)

```json
{
  "mcpServers": {
    "fortress-dashboard": {
      "command": "python3",
      "args": ["/path/to/fortress-mcp.py"],
      "env": {
        "FORTRESS_API_URL": "https://srv1321374.hstgr.cloud",
        "FORTRESS_API_TOKEN": "<token>",
        "FORTRESS_MCP_ALLOW_WRITES": "0",
        "QUANTDATA_AUTH_TOKEN": "<qd token>",
        "QUANTDATA_INSTANCE_ID": "<qd id>"
      }
    }
  }
}
```

---

## 4. Backend Development

### Running locally

```bash
cd /home/ubuntu/fortress-v4-api
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8081 --reload
```

### Installing new packages

```bash
/home/ubuntu/fortress-v4-api/venv/bin/pip install <package> --break-system-packages
```

> Always use `--break-system-packages` with pip on this VPS.

### Service management

```bash
# View logs
journalctl -u fortress-dashboard-v4 -f

# Restart (DO NOT use systemctl restart — it times out at 45s)
kill -9 $(pgrep -f "fortress-dashboard-v4" | head -1)
systemctl start fortress-dashboard-v4
```

---

## 5. Frontend Development

### Build and deploy

```bash
# Build
cd /home/ubuntu/fortress-v4-frontend
/home/ubuntu/fortress-v4-frontend/node_modules/.bin/vite build

# Deploy
cp -r dist/* /var/www/fortress-v4/
```

> Run vite from the repo root. Do NOT `cd client/` first.

### Push to GitHub

```bash
cd /home/ubuntu/fortress-v4-frontend
git add -A
git commit -m "your message"
git push v4 main      # ← always push to v4 remote (fortress-v4-frontend)
```

---

## 6. MCP Development

### Testing a tool

```bash
cd /home/ubuntu/fortress-mcp
python3 -c "
import os; os.environ['FORTRESS_API_TOKEN'] = '...'
from fortress-mcp import get_briefing
print(get_briefing())
"
```

### Push to GitHub

```bash
cd /home/ubuntu/fortress-mcp
git add fortress-mcp.py
git commit -m "your message"
git push origin master
```

---

## 7. MySQL

```bash
# Connect
mysql -u fortress -p fortress_v4

# Useful queries
SELECT ticker, strategy, expiry, qty FROM positions;
SELECT section, key_name, value FROM config LIMIT 20;
SELECT snapshot_date, net_liquidation FROM portfolio_snapshots ORDER BY snapshot_date DESC;
```

---

## 8. GitHub Actions CI

| Repo | CI | Trigger |
|---|---|---|
| `fortress-v4-api` | ✅ Deploy to VPS on push | Push to `master` → SSH → git pull → service restart |
| `fortress-v4-frontend` | ❌ Not configured (H-04b) | Manual: build + copy to /var/www/fortress-v4/ |
| `fortress-mcp` | ❌ Not configured | Manual deploy |

---

## 9. Remaining Infrastructure Work

| ID | Task | Effort |
|---|---|---|
| H-03 | Docker Compose for local dev (API + MySQL + Redis + ibeam) | ~2 hr |
| H-04b | GitHub Actions CI for frontend auto-deploy | ~1 hr |
| H-05 | MySQL daily backup cron on VPS | ~30 min |
| H-06 | Rollback procedure documented and tested | ~1 hr |
