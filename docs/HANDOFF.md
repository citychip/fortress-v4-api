# Fortress — Session Handoff
**2026-06-04 (evening session) | For: Next Cowork session**

---

## Documentation (start here)

| Doc | What's in it |
|---|---|
| `docs/SYSTEM.md` | Architecture, services, deploy commands, GitHub repos, IBKR auth |
| `docs/PORTFOLIO.md` | Current positions, pending actions, strategy rules, universe, LEAP watch list |
| `docs/WORKFLOW.md` | Daily startup, entry/roll/stop workflows, key Claude commands |
| `docs/PARAPET.md` | Component map, API layer, sprint log, design principles |

---

## Immediate Priorities (next session)

**Priority 0 — iBeam auth (do first, every session)**
Open `https://localhost:5000` → log in → verify **IBKR ● green in the sidebar**.

**Priority 1 — OAuth test (Monday morning)**
IBKR weekend maintenance may have activated Stage 2. Run:
```bash
python3 /mnt/c/Users/cityc.000/OneDrive/_Stocks26/2606Fortress/test_ibkr_oauth.py
```
If it prints accounts + positions → OAuth is fully live. Switch backend in Parapet → System → Settings → Connections.

**Priority 2 — AAPL LEAP entry window**
WWDC June 8. Watch for sell-the-news dip to $300-305 → enter Jan28 250C (~$86/contract). Default entry June 10 regardless. Jan28 250C, Δ 0.87, IVR 75.4, IV ~24%.

**Priority 3 — NVDA roll still unfilled**
NVDA Aug21 250C (Δ 0.292, currently safe). Roll to Sep19 265C at ~$0.50 credit still unfilled (order `2572e40c` from Jun2). Re-stage if delta rises above 0.35.

**Priority 4 — AMD Jun26 + MSFT Jun18 expire**
Both near worthless. No action.

**Priority 5 — MSFT de-risking conversation**
Concentration at 93.2% NLV with stock below 200-SMA. No mechanical trigger, but needs a plan. Goal: below 50% by Dec 2026. No new PMCC entries.

**Priority 6 — Commit Parapet v1.7 + v1.8 to GitHub**
Last commit was `d553cd0` (v1.6 base). Two sessions of changes not committed. See commit commands below.

---

## What Happened This Session

### IBKR Status
- Re-authenticated CP Gateway at `localhost:5000`. OPRA subscribed. Active backend: `web_api`.
- WebSocket test (`ws_01_basic.py`) confirmed live P&L streaming.
- OAuth: Stage 1 (LST) ✅ confirmed. Stage 2 (brokerage session) ❌ still pending IBKR activation.

### Rolls Executed (all filled)

| Position | Before | After | Notes |
|---|---|---|---|
| GOOGL PMCC short | Jul17 390C (Δ 0.359) | Aug21 420C (Δ 0.285) | ~$0.20 debit |
| MSFT Sep18 short | 450C ×2 (Δ 0.450) | 490C ×2 (Δ 0.261) | Error: 420C placed manually, fixed with 420→490 roll. ~$24.50/contract debit to fix |
| MSFT Dec18 short | 480C ×3 (Δ 0.394) | 510C ×3 (Δ 0.290) | ~$4.76/contract debit |

Realized P&L from rolls: **-$369.36**

### MSFT Short Structure (cleaned up)
- Aug21 465C ×1 · Δ 0.34 · inside band
- Sep18 490C ×2 · Δ 0.26 · inside band ✅ fixed
- Dec18 510C ×3 · Δ 0.29 · inside band ✅ fixed
- Jun18 380P/370P BPS ×1 · let expire

### LEAP Analysis
- MSFT: BUY signal (IV normalized ~30%) but BLOCKED by concentration + budget
- AAPL: WAIT for WWDC June 8 dip; default entry June 10
- NVDA: IV still elevated (~39%), no entry
- META: IV still elevated (~35%), no entry
- NFLX: Pass (no conviction setup, IVR 38.5)

### Scripts Updated
| File | Change |
|---|---|
| `test_ibkr_oauth.py` | Rewritten using ibind; tests full OAuth flow with clear stage diagnostics |
| `ws_01_basic.py` | New — ibind WebSocket test; confirmed live (Ctrl+C to stop) |
| `rest_08_oauth.py` | New — ibind OAuth REST example from Voyz/ibind |

---

## Account Snapshot (2026-06-04 ~17:30 ET)

| | |
|---|---|
| Net Liq | **$83,722** |
| Available | $28,329 |
| Excess Liq | $33,360 |
| Portfolio Δ | +436 raw / +285.5 beta-weighted |
| Θ/day | +$78 |
| Vega | 341 |
| VIX | 15.54 |
| Regime | **Bearish** |
| Pacing | 0/5 this week |

---

## Open Items / Sprint 16

- OAuth Stage 2 — test Monday after weekend maintenance
- AAPL LEAP — entry June 8-10 window
- NVDA roll re-stage — when delta > 0.35
- MSFT de-risking plan — when/how to start rolling down concentration
- MSFT uncovered LEAPs (partially unhedged) — add covered call legs when conditions allow
- Commit v1.7 + v1.8 changes to `citychip/fortress-parapet`
- File QuantData GitHub issue — `qd_get_exposure_by_strike` and `qd_get_volatility_skew` return no data during market hours

---

## System Status (2026-06-04)

- Backend `fortress-dashboard-v4`: running on WSL
- IBKR CP Gateway `cp-gateway`: Docker, authenticated this session
- iBeam auth_mode: `ibeam` (default) — OAuth Stage 1 working, Stage 2 pending
- QuantData: JWT configured at `~/.quantdata-mcp/config.json`
- MCP server: `C:\Users\cityc.000\fortress_mcp\fortress_mcp.py` (Windows)
- MCP write tools require `FORTRESS_MCP_ALLOW_WRITES=1` in Claude Desktop config

### Key commands
```bash
# Backend status
sudo systemctl status fortress-dashboard-v4
journalctl -u fortress-dashboard-v4 -n 50 --no-pager

# Restart backend
sudo systemctl restart fortress-dashboard-v4

# IBKR gateway
docker restart cp-gateway

# Parapet deploy
rsync -a "/mnt/c/Users/cityc.000/OneDrive/_Stocks26/2606Fortress/fortress-parapet/src/" \
      ~/fortress-parapet/src/ && bash ~/fortress-parapet/scripts/deploy.sh

# Commit Parapet v1.7 + v1.8
cd ~/fortress-parapet
git add -A
git commit -m "feat: Parapet v1.8 — nav restructure, positions as default tab, vega in stat bar, IVR pills, staleness banner"
git push origin master
```

### GitHub PAT
Stored in WSL `~/.git-credentials` — do not paste in docs.
