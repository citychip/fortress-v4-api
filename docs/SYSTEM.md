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

**Sync convention (OneDrive ↔ repos):** the OneDrive `2606Fortress` folder is the dev/edit copy; deploys copy files **into** the repos, which push to GitHub. A file edited in OneDrive but never deployed/committed leaves GitHub stale while `git status` looks clean. Run `bash sync_check.sh` (in the OneDrive folder) at every session wrap to content-diff all mapped files + show per-repo git status. Canonical repo copy: `~/fortress-v4-api/scripts/sync_check.sh` (it self-checks via its own `MAP` entry, added 2026-06-19). Any new OneDrive *backend* script must be added to that script's `MAP` (and to `deploy_data_sources.sh` if backend-related). **Parapet `src/` is auto-tracked (2026-06-19):** `sync_check.sh` derives the frontend file list from `deploy_parapet.sh`'s `FILES=()`, so adding a new Parapet file to that deploy list is enough to drift-check it — no second list. `deploy_data_sources.sh` now reads the token from `~/.fortress_api_token` (no hardcoded secret) — keep it OneDrive-only by convention regardless. Runtime-state policy: gitignore `iv_history.json` / `pending_orders.json` / `*.pre-ibkr-bak`; commit `conditional_alerts.json` / `macro_events.json` / `trade_outcomes.json`.

Set remotes:
```bash
git -C ~/fortress-parapet remote set-url origin https://citychip:$(cat ~/.pat)@github.com/citychip/fortress-parapet.git
```

**API token:** stored untracked in WSL `~/.fortress_api_token` (single line, no quotes) and in the systemd unit's `FORTRESS_API_TOKEN`. Scripts read it via `TOKEN=$(cat ~/.fortress_api_token)`. **Never paste the literal token into any tracked file.**

**Token-rotation runbook** (do this if the token is ever exposed, or on a routine cycle). The token lives in **5 places** — all must move together: (1) backend systemd unit, (2) `~/.fortress_api_token`, (3) packaged-app `claude_desktop_config.json`, (4) OneDrive config backup, (5) the Parapet build (Vite inlines `VITE_API_TOKEN` at build time → must rebuild). A 401 in Parapet (`localhost:4000`) after rotation = step 5 was missed.
```bash
# 1. Generate + set on the backend (systemd), then reload + restart
NEW=$(openssl rand -hex 32)
sudo sed -i "s|FORTRESS_API_TOKEN=[^ \"]*|FORTRESS_API_TOKEN=$NEW|" /etc/systemd/system/fortress-dashboard-v4.service
sudo systemctl daemon-reload && sudo systemctl restart fortress-dashboard-v4 && sleep 3

# 2. Update the untracked WSL secret file
printf '%s' "$NEW" > ~/.fortress_api_token   # no trailing newline

# 3. Verify: new token works, old token is dead
curl -s http://localhost:8081/api/briefing -H "Authorization: Bearer $(cat ~/.fortress_api_token)" | head -c 120; echo
curl -s -o /dev/null -w "old => HTTP %{http_code}\n" http://localhost:8081/api/briefing -H "Authorization: Bearer <OLD_TOKEN>"  # expect 401
```
4. **Desktop app (Cowork) — live MCP launcher config (4th place):** the connector reads `env.FORTRESS_API_TOKEN` from the **packaged-app** `claude_desktop_config.json` (NOT the OneDrive copy — that's only a backup the app does not read, though keep it in sync). Live path:
   `C:\Users\cityc.000\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\claude_desktop_config.json`
   ```bash
   LIVE="/mnt/c/Users/cityc.000/AppData/Local/Packages/Claude_pzs8sxrjxfjjc/LocalCache/Roaming/Claude/claude_desktop_config.json"
   cp "$LIVE" "$LIVE.bak"
   sed -i -E 's/("FORTRESS_API_TOKEN":[[:space:]]*")[^"]*(")/\1'"$NEW"'\2/' "$LIVE"
   grep FORTRESS_API_TOKEN "$LIVE"   # confirm new value
   ```
   ⚠ The **Customize → Connectors** UI only sets per-tool permissions — it does NOT expose the token. Edit the file, then **fully quit + reopen** the app. Test with `get_briefing`; a 401 = connector still on the old value. (Also sync the OneDrive copy + `claude_desktop_config.json` backup to match.)
   **How to (re)locate this file** if the path ever changes (e.g. new package ID): Claude Desktop is an MSIX/Store-packaged app, so its AppData is redirected under `Local\Packages\Claude_*\LocalCache\Roaming\Claude\` — NOT the plain `%APPDATA%\Roaming\Claude\`. Find it by **filename (no shallow depth limit** — a `-maxdepth 3` misses it):
   ```bash
   find /mnt/c/Users/cityc.000/AppData -iname "claude_desktop_config.json" 2>/dev/null
   # or by content:
   grep -rls "FORTRESS_API_TOKEN" /mnt/c/Users/cityc.000/AppData/Local/Packages/ 2>/dev/null
   ```
   Cross-check: the package folder (`Claude_pzs8sxrjxfjjc`) matches the `bundleId` prefix returned by the computer-use `request_access` grant.
5. **Parapet frontend (5th place):** Vite inlines `VITE_API_TOKEN` into the built JS at build time, so the bundle must be **rebuilt** — it won't pick up a new token otherwise. `deploy_parapet.sh` (fixed 2026-06-19) now reads the token from `~/.fortress_api_token` and writes **both `.env` and `.env.local`**, then rebuilds + redeploys:
   ```bash
   bash /mnt/c/Users/cityc.000/OneDrive/_Stocks26/2606Fortress/deploy_parapet.sh
   grep -H VITE_API_TOKEN ~/fortress-parapet/.env*    # .env AND .env.local must both = new token
   curl -s http://localhost:4000/ | grep -o 'index-[A-Za-z0-9_]*\.js'   # hash MUST change vs last build
   ```
   **Hard-won gotchas (all caused 401 `invalid_token` during the 2026-06-19 rotation — verify each):**
   - **`.env.local` overrides `.env`** in Vite (`.env.local` > `.env`). A stale `.env.local` silently ships the OLD token even after you fix `.env`. The deploy now writes both; if editing by hand, fix `.env.local`. **Tell: the bundle hash does NOT change after rebuild → Vite read a stale env file.**
   - **Never scrape the token from the systemd line** (`grep '(?<=FORTRESS_API_TOKEN=)\S+'`) — surrounding quotes leak in as a trailing `"` → bad token. Read `~/.fortress_api_token` instead.
   - **`umask`**: if your shell has `umask 077` (e.g. after creating the token file), `sudo cp` into `/var/www` makes files unreadable by nginx → **403 Forbidden**. The deploy now forces `umask 022`; otherwise `sudo chmod -R a+rX /var/www/fortress-parapet`.
   - **Browser cache**: hard-refresh (Ctrl+Shift+R) is unreliable in Edge — verify in an **InPrivate** window (Ctrl+Shift+N).
   - **Definitive backend check** of the token Parapet will send: `curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8081/api/briefing -H "Authorization: Bearer $(tr -d '\"[:space:]' < ~/fortress-parapet/.env.local | sed 's/.*VITE_API_TOKEN=//')"` → expect **200**.
- ⚠ Rotation does NOT scrub the old token from git history. If it was ever committed (it was, pre-2026-06-19), rotation is what makes the old value harmless; optional `git filter-repo`/BFG history scrub is cosmetic afterward.

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
| `/api/data-integrity` | GET | **(2026-06-19)** Gateway-down integrity guard — live IBKR snapshot probe (SPY) → `live`/`fallback`/`down` verdict + `source`/`spot`/`message`. Bypasses the false-fresh `staleness` field; drives the Parapet top-bar source badge. In `options_analytics.py` |

```bash
TOKEN=$(cat ~/.fortress_api_token)   # never hardcode — read the untracked secret file

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
