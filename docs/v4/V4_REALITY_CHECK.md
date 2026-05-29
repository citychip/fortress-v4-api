commit 5077058a0a311d79555034a89039d3c2376c36df
Author: Fortress <fortress@citychip.dev>
Date:   Wed May 27 10:18:12 2026 +0200

    docs: update V4 docs post-sprint v8.24 (MCP audit complete)
    
    - V4_REALITY_CHECK: MCP section updated — 64 tools, v4.0.0, 5 fixes, 3 new
    - V4_OPEN_REQUIREMENTS: Group G fully complete; priority list trimmed; ~8h remaining
    - V4_SPRINT_PLAN: v8.24 marked complete with full breakdown; effort table updated

diff --git a/docs/v4/V4_REALITY_CHECK.md b/docs/v4/V4_REALITY_CHECK.md
index 81298af..b6ca733 100755
--- a/docs/v4/V4_REALITY_CHECK.md
+++ b/docs/v4/V4_REALITY_CHECK.md
@@ -2,7 +2,7 @@
 ## What Is Actually Built vs What the Docs Say
 
 **Prepared:** 2026-05-26 (original)
-**Updated:** 2026-05-27 (post Sprint v8.22)
+**Updated:** 2026-05-27 (post Sprint v8.24)
 **Basis:** Live VPS audit — API calls, git log, file inspection, MySQL query
 **Purpose:** Single source of truth on what exists today.
 
@@ -129,13 +129,19 @@ Deployed build: `/var/www/fortress-v4/` — served at `https://srv1321374.hstgr.
 
 | Feature | Status | Notes |
 |---|---|---|
-| MCP server | ✅ Live | v1.2; 32 tools in Claude Desktop |
-| Tier 1 tools | ✅ Live | ~20 read tools |
-| Tier 2 tools | ✅ Live | 9 write/opt-in tools |
-| Tier 1.5 analytics tools | ✅ Live | get_portfolio_beta, get_sector_exposure, get_capital_efficiency (v8.16) |
-| get_earnings_volatility tool | ✅ Live | v8.16 |
-| FORTRESS_API_URL | ✅ HTTPS | Updated to https://srv1321374.hstgr.cloud (v8.20) |
-| Prompt library | ⚠️ Partial | v1.3; not updated for V4 tool names |
+| MCP server | ✅ Live | v4.0.0; 64 tools total |
+| Tier 1 read-only tools | ✅ Live | 46 tools (incl. 3 new v8.24: get_pcs_exposure, get_pnl_history, get_version) |
+| Tier 1b QuantData live tools | ✅ Live | 6 qd_* tools |
+| Tier 2 write tools (env-gated) | ✅ Live | 9 tools (FORTRESS_MCP_ALLOW_WRITES=1) |
+| Order management tools | ✅ Live | 3 tools (preview_order, approve_order, decline_order) |
+| get_ibkr_status fix | ✅ Fixed | v8.24 — redirected to /api/ibkr/capability (status route has NameError) |
+| pretrade_check fix | ✅ Fixed | v8.24 — now calls /api/manage/pre_trade_check (was calling wrong endpoint) |
+| get_position_limits fix | ✅ Fixed | v8.24 — fetches legs from /api/positions; passes URL-encoded JSON |
+| get_forward_pnl fix | ✅ Fixed | v8.24 — same legs-fetch pattern; iv_multiplier mapped to iv_adj |
+| FORTRESS_API_URL | ✅ HTTPS | https://srv1321374.hstgr.cloud (v8.20) |
+| FORTRESS_MCP_VERSION | ✅ 4.0.0 | v8.24 — constant added; server prompt updated |
+| Prompt library | ✅ Updated | v8.24 — server instructions updated to "Fortress Dashboard MCP v4.0.0" |
+| GitHub repo | ✅ Live | citychip/fortress-mcp (initialized v8.24); commits 600284e + 38f7e73 |
 
 ### Infrastructure
 
@@ -158,7 +164,6 @@ Deployed build: `/var/www/fortress-v4/` — served at `https://srv1321374.hstgr.
 - **H-05** — MySQL daily backup cron on VPS
 - **H-06** — Rollback procedure documented
 - **H-03** — Docker Compose for local dev
-- **G-05/G-06/G-07/G-08** — MCP audit + expansion to 61 tools + prompt library update
 - **I-01 through I-05** — remaining documentation gaps
 
 ---
