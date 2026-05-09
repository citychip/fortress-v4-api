# Fortress Dashboard — VPS Implementation Guide

**Version 1.5 — May 5, 2026**

End-to-end instructions for deploying the Fortress Dashboard on a fresh VPS. v1.5 promotes **CP Gateway (voyz/ibeam)** to the primary broker integration. The legacy TWS Gateway (`gnzsnz/ib-gateway`) is retained as diagnostics-only and demoted in this guide.

---

## 1. System Requirements & OS Setup

Linux VPS, Ubuntu 22.04 LTS or 24.04 LTS recommended. Deployed instance uses Ubuntu 26.04 — also supported.

### 1.1 Install system dependencies

```bash
sudo apt-get update -y
sudo apt-get install -y python3 python3-pip python3-venv curl wget git nc tesseract-ocr

# Docker (if not already installed)
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker ubuntu
```

### 1.2 Directory structure

```bash
mkdir -p /opt/fortress-dashboard/app/{routes,services,services/ibkr_web,static}
mkdir -p /opt/fortress-dashboard/quant/backups
mkdir -p /opt/fortress-dashboard/cp-gateway/conf
mkdir -p /opt/fortress-dashboard/ib-gateway   # legacy, optional
mkdir -p /opt/fortress-dashboard/docs
```

---

## 2. Python Environment Setup

### 2.1 Create the virtual environment

```bash
cd /opt/fortress-dashboard
python3 -m venv venv
source venv/bin/activate
```

### 2.2 Install dependencies

`requirements.txt`:

```text
fastapi>=0.110.0
uvicorn[standard]>=0.27.0
python-multipart>=0.0.6
ib_async>=2.1.0          # legacy TWS path
yfinance>=1.3.0          # chain provider, BS fallback, FX, OHLCV, earnings auto-fetch
httpx>=0.28              # CP Gateway client
pytesseract>=0.3.10
Pillow>=10.0.0
APScheduler>=3.11
```

```bash
pip install -r requirements.txt
```

---

## 3. CP Gateway (voyz/ibeam) Setup — primary broker integration

NEW in v1.5: this section is the primary broker setup. The legacy TWS Gateway (§4) is retained for diagnostics only.

### 3.1 Why CP Gateway

- Headless integration — no TWS GUI, no IBC dialog interruption.
- HTTP+JSON protocol — easier to debug and monitor.
- All four Greeks (delta/gamma/theta/vega) come back live when OPRA is subscribed.
- voyz/ibeam handles automated login + tickle loop.

Trade-off: session expires every ~24h. ibeam re-authenticates automatically but **requires an IBKR Mobile push approval each cycle** (the trader taps to approve). Future migration to OAuth 2.0 direct would eliminate this.

### 3.2 IBKR account-level prerequisite

Before starting the container, enable Read-Only API at the **IBKR account** level (not just the gateway env var):

1. Log into IBKR Account Management at `https://www.interactivebrokers.com/sso/Login`.
2. Settings → Account Settings → API → Settings.
3. Enable "Read-Only API".
4. Save and confirm.

Without this, the dashboard popup interrupts snapshots even on the Web API path.

### 3.3 Docker Compose file

Save as `/opt/fortress-dashboard/cp-gateway/docker-compose.yml`:

```yaml
services:
  ibeam:
    image: voyz/ibeam:latest
    container_name: cp-gateway
    restart: unless-stopped
    env_file:
      - .env
    ports:
      - "127.0.0.1:5000:5000"   # CP Gateway HTTPS
      - "127.0.0.1:5001:5001"   # ibeam health/control endpoint
    healthcheck:
      test: ["CMD", "curl", "-fsk", "https://localhost:5000/v1/api/one/user", "-o", "/dev/null"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 120s
    volumes:
      - ibeam_inputs:/srv/inputs
      - ./conf/conf.yaml:/srv/clientportal.gw/root/conf.yaml:ro

volumes:
  ibeam_inputs:
```

### 3.4 IP-allowlist patch (REQUIRED)

The default `clientportal.gw/root/conf.yaml` baked into the image only allows `172.17.0.*` (Docker default bridge). Compose creates a `172.18.*` network. Without this patch, `/v1/api/*` from the host (port-mapped) returns "Access Denied".

Pull the conf out, patch the IPs section, mount it back via the volume in 3.3.

```bash
# Start the container once to extract the conf
cd /opt/fortress-dashboard/cp-gateway
docker compose up -d
sleep 30  # wait for the gateway to write the conf
docker cp cp-gateway:/srv/clientportal.gw/root/conf.yaml ./conf/conf.yaml

# Edit conf/conf.yaml — replace the bottom 'ips:' block with:
cat >> /tmp/ips_patch.txt <<'EOF'
ips:
  allow:
    - 10.*
    - 172.*
    - 192.*
    - 127.0.0.1
EOF

# Apply (using Python for safety on the YAML structure)
python3 - <<'PY'
import re
p = '/opt/fortress-dashboard/cp-gateway/conf/conf.yaml'
with open(p) as f: c = f.read()
new_ips = """ips:
  allow:
    - 10.*
    - 172.*
    - 192.*
    - 127.0.0.1
"""
c = re.sub(r'ips:\s*\n.*\Z', new_ips, c, flags=re.DOTALL)
open(p, 'w').write(c)
PY

# Recreate the container to pick up the volume-mounted conf
docker compose down && docker compose up -d
```

### 3.5 Configure credentials

Create `/opt/fortress-dashboard/cp-gateway/.env`:

```text
# IBeam (CP Gateway) configuration
IBEAM_ACCOUNT=your_username
IBEAM_PASSWORD=your_password

# 2FA via IBKR Mobile push
IBEAM_TWO_FA_HANDLER=PUSH

# Trading mode
IBEAM_TRADING_MODE=live

# Health endpoint
IBEAM_HEALTH_SERVER_PORT=5001

# Logs
IBEAM_LOG_LEVEL=INFO

# Timeouts — start with 60s and bump if first login fails
IBEAM_PAGE_LOAD_TIMEOUT=180
IBEAM_OAUTH_TIMEOUT=180
IBEAM_GATEWAY_STARTUP=60
IBEAM_MAX_FAILED_AUTH=3

# Persistence directory (matches docker-compose volume)
IBEAM_INPUTS_DIR=/srv/inputs
```

Restrict file permissions: `chmod 600 .env`. Never commit to git.

### 3.6 First-time login

```bash
cd /opt/fortress-dashboard/cp-gateway
docker compose up -d
```

Within ~30 seconds, an **IBKR Mobile push notification** arrives on the trader's phone. Tap "Approve" within ~3 minutes.

Verify login completed:

```bash
docker logs cp-gateway 2>&1 | grep -E "AUTHENTICATED|Login attempt|Logging in succeeded" | tail -5
```

Expect: `AUTHENTICATED Status(running=True, session=True, connected=True, authenticated=True, ...)`.

### 3.7 Daily re-auth ergonomics

Sessions expire every ~24h. ibeam's maintenance loop re-authenticates automatically; the trader gets a fresh push notification when this happens. Approve to continue.

If the push is missed:
- Capability badge in the dashboard header turns amber within 60s.
- ibeam retries every 60s — another push will arrive.
- During the fallback window the dashboard still works on `bs_yfinance` path (Black-Scholes from yfinance).

### 3.8 Verify session

```bash
# /tickle with the current session token
curl -sk -X POST https://localhost:5000/v1/api/tickle | head -c 200

# Or from the dashboard:
curl -s http://127.0.0.1:8080/api/ibkr/capability | python3 -m json.tool
```

Look for `"web_api"."session_status"."established": true`.

### 3.9 OPRA verification

OPRA market-data subscription is required for live Greeks. Verify:

```bash
curl -s "http://127.0.0.1:8080/api/ibkr/capability?refresh=1" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('opra_subscribed:', d['web_api']['opra_subscribed'])
print('test_delta:', d['web_api'].get('opra_test', {}).get('test_delta'))
"
```

Expect: `opra_subscribed: True`, `test_delta: "0.318"` (or similar non-null value).

If `opra_subscribed: False`: enable OPRA at IBKR Account Management → Subscriptions → Market Data → US Securities Snapshot and Futures Value Bundle.

---

## 4. Legacy TWS Gateway (diagnostics only)

Demoted in v1.5. Retained for cases where you want to compare backends or debug Web API-specific issues. **Skip this section if you don't need it.**

### 4.1 Compose

`/opt/fortress-dashboard/ib-gateway/docker-compose.yml`:

```yaml
services:
  ib-gateway:
    image: ghcr.io/gnzsnz/ib-gateway:stable
    restart: unless-stopped
    environment:
      TWS_USERID: ${TWS_USERID}
      TWS_PASSWORD: ${TWS_PASSWORD}
      TRADING_MODE: ${TRADING_MODE:-live}
      READ_ONLY_API: ${READ_ONLY_API:-yes}
      TWOFA_TIMEOUT_ACTION: ${TWOFA_TIMEOUT_ACTION:-exit}
      AUTO_RESTART_TIME: ${AUTO_RESTART_TIME:-11:59 PM}
      TWS_ACCEPT_INCOMING: accept
      TRUSTED_TWS_API_CLIENT_IPS: 127.0.0.1
      TIME_ZONE: Europe/Amsterdam
    ports:
      - "127.0.0.1:4001:4003"   # Live (host 4001 → container 4003)
      - "127.0.0.1:4002:4001"   # Paper (host 4002 → container 4001)
    healthcheck:
      test: ["CMD-SHELL", "nc -z localhost 4003 || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 60s
    volumes:
      - ib_gateway_config:/root/ibc
      - ib_gateway_jts:/root/Jts

volumes:
  ib_gateway_config:
  ib_gateway_jts:
```

### 4.2 Issues

- The Read-Only API setting at IBKR account level (§3.2) addresses the dialog popup that previously corrupted snapshot Greeks.
- Container is currently `docker compose down`d in production. Start with `docker compose up -d` if needed.
- One brokerage session per username globally — if CP Gateway is active, TWS Gateway claims `competing: true`. To use TWS, stop CP Gateway first.
- `GATEWAY_TIMEOUT=90` in `app/services/ibkr_sync.py` accommodates BS fallback compute time. Diagnostic-only setting.

---

## 5. FastAPI Service Configuration

### 5.1 systemd service file

`/etc/systemd/system/fortress-dashboard.service`:

```ini
[Unit]
Description=Fortress Trading Dashboard
After=network.target docker.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/fortress-dashboard
Environment="PATH=/opt/fortress-dashboard/venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment="FORTRESS_DATA_DIR=/opt/fortress-dashboard/quant"
Environment="TESSERACT_CMD=/usr/bin/tesseract"
ExecStart=/opt/fortress-dashboard/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8080
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable fortress-dashboard.service
sudo systemctl start fortress-dashboard.service
```

### 5.2 Companion service: orchestrator

`/etc/systemd/system/fortress_orchestrator.service` (unchanged from v1.4).

---

## 6. Security & Firewall

The dashboard binds to `0.0.0.0:8080` and currently has **no built-in authentication**. Must not be exposed to the open internet without IP whitelisting or a VPN/Tailscale tunnel.

### 6.1 UFW (recommended)

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow from YOUR_HOME_IP to any port 8080
sudo ufw enable
```

### 6.2 Tailscale (multi-device)

Install on VPS + each device. Dashboard accessible at `http://<tailscale-name>:8080` with no public exposure.

### 6.3 Bearer token (planned)

Auth at the API layer — Bearer token on `/api/*`, env-var-configured. Prerequisite for the MCP wrapper. Not yet implemented.

---

## 7. TradingView Lightweight Charts Integration

Live in the Manage tab. Backend: `app/routes/chart.py` serves yfinance OHLCV + DP/GEX overlays from QuantData reports. Frontend: `app/static/chart.js` loads `lightweight-charts@4.2.0` from unpkg CDN.

Endpoints:
- `GET /api/chart/{ticker}?period=3mo` — OHLCV + overlays.
- `GET /api/chart/{ticker}/levels` — overlays only (fast refresh).

Periods: `1mo`, `3mo`, `6mo`, `1y`.

QuantData report parser expects the format:

```markdown
### MSFT Execution Profile
- **Dark Pool Hard Floors:** $389.00 (982.6M), $384.47 (260.5M), $386.49 (28.9M)
- **GEX Walls:** Calls at $390, $400, $395 | Puts at $320, $325, $300
```

---

## 8. Settings & Runtime Configuration (NEW v1.5)

### 8.1 fortress_config.json

Lives in `FORTRESS_DATA_DIR` (`/opt/fortress-dashboard/quant/fortress_config.json`). Auto-created from `app/services/config_store.py` `DEFAULTS` on first startup.

Sections:
- **strategy** — sizing, concentration, deltas, DTE, SPY hedge band, stop-loss, playbook bands, credits, VIX
- **technical** — VPS / IBKR / CP Gateway connection params, `greeks_backend` selector
- **alerts** — delta watch/act, MV drawdown, DTE, concentration alert thresholds
- **ui** — tab default, refresh interval, theme, currency display, date format, timezone

### 8.2 Settings tab UI

Schema-driven editor at the dashboard's Settings tab. Inline save per section. Multiselect / dropdown / number / text / password / boolean field types.

### 8.3 API

- `GET /api/settings` → `{config: {...}}`
- `GET /api/settings/schema` → `{schema: {section: [field, ...]}}`
- `PUT /api/settings/{section}` body `{values: {key: value}}`
- `POST /api/settings/reset` → factory defaults

### 8.4 Hot-reload

Settings edits take effect on the next API call — no restart required. Atomic write via tmp + rename. Backups not yet wired (state.write_json's pattern would be the right model).

---

## 9. Automated Earnings Fetcher

`POST /api/calendar/fetch-earnings` reads ticker_universe (tier1/tier2/macro), queries yfinance for next earnings dates, merges into `earnings_blocklist.json`. Confirmed future dates preserved. SPX/SPY skipped.

Universe tab → "Auto-fetch from Yahoo ↻" button.

---

## 10. Operational checklist after first install

1. **Apply the §3.4 IP-allowlist patch** — required for CP Gateway.
2. **Apply the §3.2 IBKR Read-Only API setting** in Account Management.
3. **Verify CP Gateway login:** check docker logs for `AUTHENTICATED`.
4. **Verify capability:**
   ```bash
   curl -s http://127.0.0.1:8080/api/ibkr/capability | python3 -m json.tool
   ```
   Expect: `web_api.session_status.established: true`, `web_api.opra_subscribed: true`.
5. **Run the first sync:**
   ```bash
   curl -s -X POST http://127.0.0.1:8080/api/ibkr/sync --max-time 110
   ```
   Expect: `backend: "web_api"`, positions count, NetLiq, ExcessLiq, AvailableFunds.
6. **Verify Greeks coverage:**
   ```bash
   curl -s http://127.0.0.1:8080/api/positions | \
     jq '[.positions[] | select(.sec_type=="OPT") | .current_delta_source] | group_by(.) | map({src: .[0], n: length})'
   ```
   Expect: most or all `bs_estimate` entries replaced with `web_api`.
7. **Lock down port 8080** — apply §6.1 UFW rules.
8. **Verify briefing renders:** open `http://<vps-ip>:8080`. Confirm USD primary + EUR sub-text on account cards, header backend badge green ("Δ: Web API+OPRA").
9. **Verify Settings tab renders:** click Settings tab, confirm 4 sections populate, edit a value and save round-trips.

---

## 11. Backups and rollback

### 11.1 Atomic state-file backups

Every write through `state.write_json` produces:

```
~/Fortress_Dashboard/quant/backups/<filename>.<YYYYMMDDTHHMMSS>.json
```

Last 50 retained per file. Restore example:

```bash
ls ~/Fortress_Dashboard/quant/backups/active_positions.*.json | tail -5
cp ~/Fortress_Dashboard/quant/backups/active_positions.20260505T143821.json \
   ~/Fortress_Dashboard/quant/active_positions.json
sudo systemctl restart fortress-dashboard
```

### 11.2 fortress_config.json backups

Not yet wired into `config_store.save()`. Improvement candidate: copy `state.write_json`'s pattern.

### 11.3 Pre-deploy snapshots

Patched files leave `*.pre-{change}-bak` siblings. Listed in `05_Implementation_Status.md` § Backups.

### 11.4 Full backup of `app/`

Pre-Phase-4 snapshot at `_phase4_backup_2026-05-03/app/`.

---

## 12. Change Log

- **v1.5 (May 5, 2026):** New §3 CP Gateway via voyz/ibeam — primary broker integration. §3.4 IP-allowlist patch. §3.7 daily 2FA push reality. Legacy TWS Gateway demoted to §4. New §8 Settings & runtime configuration. Operational checklist (§10) updated for Web API + Settings verification.
- **v1.4 (May 4, 2026 PM):** Healthcheck port fix (4001 → 4003 for live). IBKR account-level Read-Only API. `GATEWAY_TIMEOUT=90`. Operational checklist with sync verification.
- **v1.3 (May 4, 2026 AM):** TradingView Lightweight Charts. Earnings auto-fetcher.
- **v1.0 (May 3, 2026):** Initial release.
