# Fortress V4 — Permanent Operations Notes

**Version:** 4.1.0
**Updated:** 2026-06-01
**Status:** PERMANENT — critical operational knowledge that must survive context loss.

> ⚠️ **WSL deployment only.** The VPS (76.13.138.194) is decommissioned. No SSH to remote servers. Everything runs in WSL on Windows.

---

## Critical Rules — Read Before Any Command

### No VPS. Everything is WSL.
- Backend: `~/fortress-v4-api/` in WSL
- Frontend: `~/fortress-v4-frontend/` in WSL
- Service: `fortress-dashboard-v4` (not `fortress-dashboard`)
- Deploy target: `/var/www/fortress-v4/` (not `/var/www/fortress-v2/`)
- API port: **8081** (not 8080)

### MCP Write Tools Require a Flag
`stage_order`, `run_script`, `trigger_ibkr_sync`, `approve_order` all require `FORTRESS_MCP_ALLOW_WRITES=1` in Claude Desktop config. If a write tool returns "Write tools are disabled", add the env var and restart Claude Desktop.

### IBKR auto-sync is enabled
`ibkr_auto_sync_enabled: true`, interval 15 min. No manual sync needed at startup unless data looks stale (check `staleness.hours` in briefing).

### EUR account — NLV is FX-converted
The IBKR account is EUR-based. `base_currency=EUR` in technical settings causes `briefing.py` to multiply NLV by EUR/USD FX rate. The Net Liq shown is USD-equivalent (~$97K = ~96K EUR × 1.163). Concentration %s are calculated on this USD-equivalent.

### QuantData session expires — auto re-auth at 06:00 + 12:00 ET
If IV data shows zeros or near-zero intraday, QuantData token has expired. Use `refresh_iv_data()` MCP tool (triggers `iv_crush` scan) or run `qd_refresh_session.py` manually. The scheduler runs `qd_refresh` at both 06:00 and 12:00 ET to prevent this.

### Frontend deploy is two steps
```bash
cd ~/fortress-v4-frontend && npm run build
sudo cp -r dist/public/* /var/www/fortress-v4/ && sudo nginx -s reload
```
Forgetting the `cp` step means the build succeeds but the old version is still served.

### StrategySection is the single source of truth for strategy params
`client/src/components/settings/StrategySection.tsx` — no slider version exists anymore. Edit this file for any strategy parameter changes.

### Sub-clustering detection is structural, not by label
`groupAllLegs()` in `PositionsPage.tsx` detects strategy types from leg direction + right + sec_type. Individual legs have `strategy=null`. Never revert to strategy-label detection.

### TradeLanding must stay in TradeBuilderPage
The active positions + universe candidates landing page is the entry point to Trade. Do not replace with a minimal empty state.

### Vol analytics IV cleaning
`_clean_iv()` in `options.py` detects binary-fraction yfinance IVs (multiples of 1/128) and recalculates from bid/ask mid via py_vollib BS. IV < 3% or > 200% is filtered as noise.

### NVDA vs NVDIA
NVDA is the correct ticker and is in tier1 universe. NVDIA was a typo — it is now in the excluded list with reason "Typo — correct ticker is NVDA".

### sidebar_pinned localStorage key
Click the Fortress logo to pin/unpin the sidebar. Persisted in `localStorage('sidebar_pinned')`.

---

## Common Mistakes

| Mistake | Correct |
|---|---|
| Wrong service name | `fortress-dashboard-v4` not `fortress-dashboard` |
| Wrong deploy path | `/var/www/fortress-v4/` not `/var/www/fortress-v2/` |
| Wrong API port | 8081 not 8080 |
| Trying to SSH to VPS | Don't — VPS is decommissioned |
| Running write MCP tools and getting permission error | Set `FORTRESS_MCP_ALLOW_WRITES=1` in Claude Desktop config |
| Calling `.toFixed()` on null | Always guard: `value != null ? value.toFixed(n) : '—'` |
| Putting derived values in useEffect deps before declaration | Causes Vite TDZ crash — declare before useEffect |
