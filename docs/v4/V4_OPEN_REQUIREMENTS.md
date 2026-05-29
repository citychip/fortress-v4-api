commit 5077058a0a311d79555034a89039d3c2376c36df
Author: Fortress <fortress@citychip.dev>
Date:   Wed May 27 10:18:12 2026 +0200

    docs: update V4 docs post-sprint v8.24 (MCP audit complete)
    
    - V4_REALITY_CHECK: MCP section updated — 64 tools, v4.0.0, 5 fixes, 3 new
    - V4_OPEN_REQUIREMENTS: Group G fully complete; priority list trimmed; ~8h remaining
    - V4_SPRINT_PLAN: v8.24 marked complete with full breakdown; effort table updated

diff --git a/docs/v4/V4_OPEN_REQUIREMENTS.md b/docs/v4/V4_OPEN_REQUIREMENTS.md
index 1a83777..8627b6c 100755
--- a/docs/v4/V4_OPEN_REQUIREMENTS.md
+++ b/docs/v4/V4_OPEN_REQUIREMENTS.md
@@ -2,7 +2,7 @@
 ## All Requirements With Current Status
 
 **Prepared:** 2026-05-26
-**Updated:** 2026-05-27 (post Sprint v8.22)
+**Updated:** 2026-05-27 (post Sprint v8.24)
 **Governing rule:** Portfolio Strategy v3.7 wins over everything.
 
 Status: `[ ]` not started · `[~]` in progress · `[x]` done
@@ -119,12 +119,12 @@ Status: `[ ]` not started · `[~]` in progress · `[x]` done
 | G-02 | `get_sector_exposure` tool | [x] | v8.16 | Calls /api/portfolio/sector-exposure |
 | G-03 | `get_capital_efficiency` tool | [x] | v8.16 | Calls /api/portfolio/capital-efficiency |
 | G-04 | `get_earnings_volatility` tool | [x] | v8.16 | Calls /api/market/earnings-volatility |
-| G-05 | Audit all 29 V3 tools against V4 endpoints | [ ] | Next | |
-| G-06 | Expand to 61 total tools | [ ] | Future | |
-| G-07 | Prompt library updated for V4 tools | [ ] | Future | |
-| G-08 | MCP server version to 4.0.0 | [ ] | Future | |
+| G-05 | Audit all MCP tools against V4 endpoints; fix broken tools | [x] | v8.24 | 5 tools fixed; 3 new tools added; 64 total |
+| G-06 | Expand to 61+ total tools | [x] | v8.24 | 64 tools live (exceeded target) |
+| G-07 | Prompt library updated for V4 tools | [x] | v8.24 | Server instructions updated to v4.0.0 |
+| G-08 | MCP server version to 4.0.0 | [x] | v8.24 | FORTRESS_MCP_VERSION = "4.0.0" |
 
-**Group G: G-01 through G-04 done. G-05 through G-08 remaining.**
+**Group G: complete.**
 
 ---
 
@@ -152,7 +152,7 @@ Status: `[ ]` not started · `[~]` in progress · `[x]` done
 | I-03 | fortress-api README updated for V4 | [ ] | |
 | I-04 | V4_09_Operations_Notes.md committed to repo | [ ] | |
 | I-05 | OpenAPI spec descriptions complete | [ ] | |
-| I-06 | V4_REALITY_CHECK.md kept current | [x] | Updated 2026-05-27 post-v8.22 |
+| I-06 | V4_REALITY_CHECK.md kept current | [x] | Updated 2026-05-27 post-v8.24 |
 | I-07 | V4_OPEN_REQUIREMENTS.md kept current | [x] | This document |
 | I-08 | V4_SPRINT_PLAN.md maintained | [x] | See V4_SPRINT_PLAN.md |
 
@@ -177,14 +177,12 @@ Status: `[ ]` not started · `[~]` in progress · `[x]` done
 
 1. **H-04b** — GitHub Actions CI for frontend (~1 hr) — eliminates manual deploy step
 2. **H-05** — MySQL daily backup cron (~30 min) — data safety
-3. **G-05** — Audit all V3 MCP tools against V4 endpoints (~2 hr)
-4. **H-06** — Rollback procedure documented (~1 hr)
-5. **G-06/G-07/G-08** — MCP expansion to 61 tools + prompt library (~3 hr)
-6. **H-03** — Docker Compose for local dev (~2 hr)
-7. **I-01 through I-05** — documentation gaps (~3 hr)
+3. **H-06** — Rollback procedure documented (~1 hr)
+4. **H-03** — Docker Compose for local dev (~2 hr)
+5. **I-01 through I-05** — documentation gaps (~3 hr)
 
-**Estimated hours to fully complete V4 production:** ~13 hr
+**Estimated hours to fully complete V4 production:** ~8 hr
 
 ---
 
-*Supersedes V4_OPEN_REQUIREMENTS.md updated 2026-05-26 (post-v8.14)*
+*Supersedes V4_OPEN_REQUIREMENTS.md updated 2026-05-27 (post-v8.24)*
