commit 5077058a0a311d79555034a89039d3c2376c36df
Author: Fortress <fortress@citychip.dev>
Date:   Wed May 27 10:18:12 2026 +0200

    docs: update V4 docs post-sprint v8.24 (MCP audit complete)
    
    - V4_REALITY_CHECK: MCP section updated — 64 tools, v4.0.0, 5 fixes, 3 new
    - V4_OPEN_REQUIREMENTS: Group G fully complete; priority list trimmed; ~8h remaining
    - V4_SPRINT_PLAN: v8.24 marked complete with full breakdown; effort table updated

diff --git a/docs/v4/V4_SPRINT_PLAN.md b/docs/v4/V4_SPRINT_PLAN.md
index 81d8784..ffb45d2 100755
--- a/docs/v4/V4_SPRINT_PLAN.md
+++ b/docs/v4/V4_SPRINT_PLAN.md
@@ -2,9 +2,9 @@
 ## From v8.15 Onward
 
 **Prepared:** 2026-05-26
-**Updated:** 2026-05-27 (post Sprint v8.22)
+**Updated:** 2026-05-27 (post Sprint v8.24)
 **Baseline:** Sprints v8.3–v8.14 complete (Groups A + B + most of C + partial D + E-01 + E-02)
-**Current status:** v8.22 complete. Next: v8.23 (infra hardening).
+**Current status:** v8.24 complete. Next: v8.23 (infra hardening) or v8.25 (Docker dev env).
 
 ---
 
@@ -104,15 +104,21 @@ Gates added to both `pre_trade_check` and `pretrade_all`. Response now includes
 
 ---
 
-### Sprint v8.24 — MCP Audit + Expansion (~3 hr)
+### ✅ Sprint v8.24 — MCP Audit + Expansion (~2 hr)
 
 **Goal:** Verify all live tools work against V4 endpoints; expand prompt library.
 
-| ID | Task | Acceptance |
+| ID | Task | Status |
 |---|---|---|
-| G-05 | Audit all V3 MCP tools against V4 endpoints | Every tool tested; broken tools fixed or deprecated |
-| G-07 | Prompt library updated for V4 tool names | All daily workflow prompts reference V4 names |
-| G-08 | MCP server version string to 4.0.0 | FORTRESS_MCP_VERSION returns 4.0.0 |
+| G-05 | Audit all MCP tools against V4 endpoints; fix broken tools | ✅ Done — 5 fixed, 3 new tools added, 64 total |
+| G-06 | Expand tool count to 61+ | ✅ Done — 64 tools (46 read + 6 QD + 9 write + 3 order) |
+| G-07 | Prompt library updated for V4 tool names | ✅ Done — server instructions updated to v4.0.0 |
+| G-08 | MCP server version string to 4.0.0 | ✅ Done — FORTRESS_MCP_VERSION = "4.0.0"; GitHub repo initialized |
+
+**Tools fixed:** get_ibkr_status (→ /api/ibkr/capability), pretrade_check (→ /api/manage/pre_trade_check),
+get_position_limits + get_forward_pnl (legs-fetch pattern; iv_adj param).
+**New tools:** get_pcs_exposure, get_pnl_history, get_version.
+**Repo:** citychip/fortress-mcp initialized and pushed (commits 600284e + 38f7e73).
 
 ---
 
@@ -140,11 +146,11 @@ Gates added to both `pre_trade_check` and `pretrade_all`. Response now includes
 | Sprint | Goal | Est. Hours |
 |---|---|---|
 | v8.23 | Infra hardening (H-04b, H-05, H-06) | ~3 hr |
-| v8.24 | MCP audit + prompt library (G-05/G-07/G-08) | ~3 hr |
+| ~~v8.24~~ | ~~MCP audit + prompt library~~ | ✅ Done |
 | v8.25 | Docker Compose local dev (H-03) | ~2 hr |
 | Docs | I-01 through I-04 | ~3 hr |
 
-**Total to full V4 production: ~11 hours remaining.**
+**Total to full V4 production: ~8 hours remaining.**
 
 ---
 
@@ -159,6 +165,7 @@ Gates added to both `pre_trade_check` and `pretrade_all`. Response now includes
 | v8.20 | HTTPS/TLS + NOT READY reason chips on Candidates |
 | v8.21 | Full MySQL migration: config + journal + EOD snapshot writer |
 | v8.22 | Performance page: closed-loop P&L accordion + equity curve |
+| v8.24 | MCP audit: 5 tools fixed, 3 new tools, 64 total, version 4.0.0 |
 
 ---
 
