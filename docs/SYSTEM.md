# Fortress — System Reference
**v4.3 · Updated 2026-06-03**

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

**Daily startup (2 min):**
1. Open `https://localhost:5000` → accept cert → log in with IBKR credentials
2. Parapet → System → Infrastructure → click **Sync**
3. Verify: Overview → IBKR Web API dot green, positions populated

**If stuck:**
```bash
docker restart cp-gateway
# Then re-authenticate at localhost:5000
```

**Auth modes (toggle in Parapet → System → Infrastructure):**
- `ibeam` — default, daily browser login via CP Gateway
- `oauth` — OAuth 1.0a, consumer key SHARMILAH. Stage 1 (LST) confirmed ✅ 2026-06-04. Stage 2 (brokerage session) pending IBKR weekend activation — test Monday 2026-06-08.

---

## QuantData

Config: `~/.quantdata-mcp/config.json`  
JWT token managed by QuantData MCP.

**Known issues (as of 2026-06-04):**
- `qd_get_exposure_by_strike` — returns no options data during market hours (GitHub issue pending)
- `qd_get_volatility_skew` — same issue
- `qd_get_dark_pool_levels` / `qd_get_order_flow` — SPX widget-locked

**Working confirmed:** `qd_get_iv_rank(ticker)` ✓

---

## After changes

| What changed | Command |
|---|---|
| Backend `.py` file | `sudo systemctl restart fortress-dashboard-v4` |
| MCP server `.py` | Fully quit and relaunch Claude Desktop |
| Parapet `.tsx` file | Copy → build → deploy (see above) |
| MCP write tools | Requires `FORTRESS_MCP_ALLOW_WRITES=1` in Claude Desktop config |
