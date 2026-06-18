# Fortress — System Reference
**v4.4 · Updated 2026-06-08**

---

## Architecture

```
Claude (MCP) ──────────────────────────────────────────────┐
                                                           │
Parapet v5  ──► nginx :4000  ─┐                           │
                               ├──► FastAPI :8081 ─────────┤
Fortress v4 ──► nginx :80  ───┘         │                  │
                                         ├──► IBKR CP Gateway :5000
                                         ├──► QuantData API (cloud)
                                         └──► SQLite / state
MCP server (Windows)
  C:\Users\cityc.000\fortress_mcp\fortress_mcp.py
```

### Services

| Service | Location | Command |
|---|---|---|
| **Backend** | `~/fortress-v4-api/` | `sudo systemctl restart fortress-dashboard-v4` |
| **Parapet (v5)** | nginx :4000 | `cd ~/fortress-parapet && npm run build && sudo cp -r dist/* /var/www/fortress-parapet/` |
| **Fortress v4** | nginx :80 | `cd ~/fortress-v4-frontend && npm run build && sudo cp -r dist/public/* /var/www/fortress-v4/ && sudo nginx -s reload` |
| **IBKR Gateway** | Docker :5000 | `docker restart cp-gateway` then auth at https://localhost:5000 |

### Logs

```bash
journalctl -u fortress-dashboard-v4 -n 50 --no-pager
journalctl -u fortress-dashboard-v4 -f          # live tail
```

---

## GitHub Repos

| Repo | Branch | Purpose |
|---|---|---|
| `citychip/fortress-v4-api` | `main` | Backend, scripts, docs |
| `citychip/fortress-mcp` | `main` | MCP server for Claude |
| `citychip/fortress-v4-frontend` | `main` | Fortress v4 (port 80) — stable, maintained |
| `citychip/fortress-parapet` | `master` | Parapet v5 (port 4000) — active dev |

**PAT:** Stored in WSL `~/.git-credentials` — do not paste in docs.

Set remotes:
```bash
git -C ~/fortress-parapet remote set-url origin https://citychip:$(cat ~/.pat)@github.com/citychip/fortress-parapet.git
```

**API token:** `07f03fb6e664859ac5e8113eaf1102ac43a3cb785c581af756671072b426db21`

---

## Key File Paths

| What | Path |
|---|---|
| Backend routes | `~/fortress-v4-api/app/routes/` |
| Briefing route | `~/fortress-v4-api/app/routes/briefing.py` |
| Candidates route | `~/fortress-v4-api/app/routes/candidates.py` |
| QD proxy routes | `~/fortress-v4-api/app/routes/qd.py` |
| Parapet source | `~/fortress-parapet/src/` |
| Parapet pages | `~/fortress-parapet/src/pages/` |
| Parapet API client | `~/fortress-parapet/src/lib/api.ts` |
| MCP server | `C:\Users\cityc.000\fortress_mcp\fortress_mcp.py` |

---

## Parapet Deploy (standard)

```bash
# Copy changed files from Windows mount, then:
cd ~/fortress-parapet && npm run build && sudo cp -r dist/* /var/www/fortress-parapet/
```

Copy pattern:
```bash
cp /mnt/c/Users/cityc.000/OneDrive/_Stocks26/2606Fortress/fortress-parapet/src/pages/XPage.tsx \
   ~/fortress-parapet/src/pages/XPage.tsx
```

---

## IBKR Auth

**iBeam is headless — it authenticates automatically via Selenium.**
No manual browser login required. Check Parapet → System → Settings → Connections.

**Daily startup:**
1. Open Parapet → System → Settings → Connections
2. If IBKR ● green → already authenticated, click **↻ Sync** to pull fresh data
3. If IBKR ● red → click **⟳ Reconnect** → waits ~35s → auto-syncs on success

**Reconnect button (added 2026-06-08):**
Appears in the IBKR Connection card header when disconnected. Calls `POST /api/ibkr/reconnect` → restarts `cp-gateway` → polls status every 3s → auto-syncs. Hidden when already connected.

**If Reconnect fails:**
```bash
docker logs cp-gateway --tail 30   # check iBeam errors
docker restart cp-gateway          # manual restart
```

**Auth modes:**
- `web_api` (active) — iBeam headless via CP Gateway, auto-authenticates
- `oauth` — OAuth 1.0a, consumer key SHARMILAH. Stage 1 ✅ 2026-06-04. Stage 2 ❌ pending IBKR activation (re-tested 2026-06-15 via `test_ibkr_oauth.py`, still 401 "Invalid signature" at `ssodh/init`). ⚠ Do NOT trust `get_ibkr_status.oauth` (reports authenticated:true while the real handshake fails) — only the script confirms Stage 2.

---

## QuantData

Config: `~/.quantdata-mcp/config.json`  
JWT token managed by QuantData MCP.

**Known issues (as of 2026-06-15):**
- `qd_get_iv_rank` — ❌ **BROKEN**: ticker arg ignored upstream, every ticker returns identical values. Use fortress **`get_iv_rank(ticker)`** instead. (Corrected 2026-06-15 — the prior "confirmed working ✓" note was wrong.)
- `qd_get_exposure_by_strike` — returns no options data during market hours → use fortress `get_gex`
- `qd_get_volatility_skew` — same issue → use fortress `get_vol_skew`
- `qd_get_dark_pool_levels` / `qd_get_order_flow` — SPX widget-locked

**QuantData reliable ONLY for:** order flow, dark pool, max pain, OI, net flow, live contract prices (`qd_get_contract_price`).

---

## New Backend Endpoints (added 2026-06-08)

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/ibkr/reconnect` | POST | Restart cp-gateway, poll until authenticated |
| `/api/orders/pending/{id}/force` | DELETE | Force-cancel any order regardless of status |
| `/api/orders/expire-stale` | POST | Bulk-expire all stale DAY `submitted` orders (run at EOD) |

```bash
TOKEN="07f03fb6e664859ac5e8113eaf1102ac43a3cb785c581af756671072b426db21"

# Force-cancel a stuck order
curl -s -X DELETE "http://localhost:8081/api/orders/pending/{ID}/force" \
  -H "Authorization: Bearer $TOKEN"

# Expire stale orders (EOD cleanup)
curl -s -X POST "http://localhost:8081/api/orders/expire-stale" \
  -H "Authorization: Bearer $TOKEN"
```

---

## After changes

| What changed | Command |
|---|---|
| Backend `.py` file | `sudo systemctl restart fortress-dashboard-v4` |
| MCP server `.py` | Fully quit and relaunch Claude Desktop |
| Parapet `.tsx` file | Copy → build → deploy (see above) |
| MCP write tools | Requires `FORTRESS_MCP_ALLOW_WRITES=1` in Claude Desktop config |
