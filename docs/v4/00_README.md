commit f73ad3afd99446d6f2ccba7e2fb1ae9cb88cc112
Author: Fortress <fortress@citychip.dev>
Date:   Wed May 27 10:29:19 2026 +0200

    docs: comprehensive V4 documentation update (post-v8.24)
    
    - README.md: full rewrite for V4 (was V3 architecture, wrong ports/paths/repos)
    - 00_README.md: update status from Design Phase to Production; correct repo map
    - 09_Operations_Notes.md: rewrite with accurate VPS facts (port 8081, service name,
      correct restart procedure, frontend build path, git remote notes, fixed K-issues)
    - 05_MCP_Spec.md: update to 64 tools (was 61 planned); add all new tools; correct tiers
    - 08_Developer_Guide.md: correct repo names (fortress-v4-api/frontend); fix push instructions
    - scripts/README.md: rewrite for V4 (was referencing V3 paths and old port 8080)

diff --git a/docs/v4/00_README.md b/docs/v4/00_README.md
index 663962a..b5bd238 100644
--- a/docs/v4/00_README.md
+++ b/docs/v4/00_README.md
@@ -1,65 +1,63 @@
 # Fortress V4 — Documentation Index
 
-**Version:** 4.0.0  
-**Status:** Design Phase — Pre-implementation  
-**Date:** May 2026  
+**Version:** 4.0.0
+**Status:** Production — V4 is live at `https://srv1321374.hstgr.cloud`
+**Last updated:** 2026-05-27 (post Sprint v8.24)
 
-> **Note:** Fortress V3 is the current running system. These documents describe the planned V4 architecture. V3 documentation remains in `docs/` (parent directory) and is the operational reference until V4 is deployed.
+> V4 is the active running system. V3 (`fortress-api` repo, port 8080) is legacy fallback only.
 
 ---
 
-## Document Set
+## Ground-Truth Documents (read these first)
 
-| # | File | Purpose | Phase |
-|---|---|---|---|
-| 1 | `01_Master_Design_Proposal.md` | Vision, goals, architectural seams, ADRs, phase structure | P0 |
-| 2 | `02_System_Architecture.md` | Four engines, data layer, SSE, API surface, file tree | P0 |
-| 3 | `03_Design_System.md` | Obsidian Edge design system — tokens, components, page layouts | P0/P1 |
-| 4 | `04_Phase_Backlog.md` | Full sprint backlog with acceptance criteria for all phases | P0 |
-| 5 | `05_MCP_Spec.md` | All 61 MCP tools — request/response schemas, tier breakdown | P0/P2 |
-| 6 | `06_Operations_Guide.md` | Daily workflow, 8 APScheduler scripts, VPS operations, incident procedures | P0/P2 |
-| 7 | `07_Migration_Guide.md` | JSON → MySQL 8 migration scripts, rollback, validation | P0/P2 |
-| 8 | `08_Developer_Guide.md` | Local setup, Docker Compose, env vars, module layout, test commands | P0/P2 |
-| 9 | `09_Operations_Notes.md` | Permanent hard-won operational knowledge — read before touching VPS | Permanent |
-| 10 | `10_GitHub_App_Setup_Archive.md` | Archived setup guide for the deleted 8081 GitHub app instance | Archive |
-| 11 | `11_Upgrade_Plan.md` | Sprint-ready V3→V4 upgrade backlog (v8.3–v8.11), pre-coding steps, rollback strategy | Live |
+| File | Purpose |
+|---|---|
+| `V4_REALITY_CHECK.md` | VPS-verified snapshot of what is actually built and working |
+| `V4_OPEN_REQUIREMENTS.md` | All requirements with current status checkboxes |
+| `V4_SPRINT_PLAN.md` | Sprint history (v8.3–v8.24 complete) + upcoming work |
 
 ---
 
-## Phase Overview
+## Reference Documents
 
-| Phase | Goal | Status |
-|---|---|---|
-| **Phase 0** | Architecture documentation | ✅ Complete |
-| **Phase 1** | Design system + component library | ⬜ Pending |
-| **Phase 2** | Developer and operational documentation | ⬜ Pending |
-| **Phase 3** | Front-end coding (React 19 + Tailwind 4 + tRPC 11) | ⬜ Pending |
-| **Phase 4** | Backend coding (FastAPI + MySQL 8 + Redis 7 + APScheduler) | ⬜ Pending |
-| **Phase 5** | MCP server update (61 tools) | ⬜ Pending |
-| **Phase 6** | Infrastructure (Docker, systemd, NGINX) | ⬜ Pending |
-
-**Golden Rule:** Phases 0–2 must be complete and signed off before any Phase 3–6 coding begins.
+| # | File | Purpose | Status |
+|---|---|---|---|
+| 2 | `02_System_Architecture.md` | Architecture diagram, data layer, API surface | Design reference (partially implemented) |
+| 3 | `03_Design_System.md` | Obsidian Edge design tokens and component specs | Design reference |
+| 4 | `04_Phase_Backlog.md` | Full phase backlog with acceptance criteria | Superseded by V4_OPEN_REQUIREMENTS.md |
+| 5 | `05_MCP_Spec.md` | MCP tool catalogue — all 64 tools | Updated post-v8.24 |
+| 6 | `06_Operations_Guide.md` | Daily workflow, scheduler scripts, incident procedures | Authoritative |
+| 7 | `07_Migration_Guide.md` | JSON → MySQL migration notes | Complete — all migrations done |
+| 8 | `08_Developer_Guide.md` | Repo setup, env vars, build commands | Authoritative |
+| 9 | `09_Operations_Notes.md` | **CRITICAL** — hard-won VPS operational knowledge | Permanent — read before touching VPS |
+| 10 | `10_GitHub_App_Setup_Archive.md` | Archived GitHub App setup (historical) | Archive |
+| 11 | `11_Upgrade_Plan.md` | Sprint-ready V3→V4 upgrade backlog | Historical reference |
 
 ---
 
-## Key V4 Changes from V3
+## Repository Map
 
-| Area | V3 | V4 |
+| Repo | Role | Branch |
 |---|---|---|
-| State storage | 5 JSON files | MySQL 8 |
-| Cache / pub-sub | None | Redis 7 |
-| Real-time updates | Polling | Server-Sent Events (SSE) |
-| MCP tools | 29 tools | 61 tools (47 + 10 + 4 new Tier 1.5) |
-| Backend framework | FastAPI (existing) | FastAPI (refactored into 4 engines) |
-| Scheduled workflows | 5 workflows | 8 workflows |
-| Front-end | React 19 + Tailwind 4 + tRPC 11 (existing) | Same stack, full redesign with Obsidian Edge design system |
+| `citychip/fortress-v4-api` | FastAPI backend | `master` |
+| `citychip/fortress-v4-frontend` | React frontend | `main` |
+| `citychip/fortress-mcp` | Claude MCP server | `master` |
 
 ---
 
-## Repository Structure (V4 Target)
+## Current Phase Status (post v8.24)
 
-| Repo | Purpose |
+| Area | Status |
 |---|---|
-| `citychip/fortress-app` | React front-end (this repo) |
-| `citychip/fortress-api` | FastAPI backend, four engines, scheduler |
-| `citychip/fortress-mcp` | Claude MCP server (61 tools) |
+| Backend API (all endpoints) | ✅ Complete |
+| MySQL migrations (config, journal, positions, snapshots) | ✅ Complete |
+| APScheduler (8 jobs + EOD snapshot) | ✅ Complete |
+| Strategy gates (F-01 through F-07) | ✅ Complete |
+| Frontend widgets (all E-series except E-11) | ✅ Complete |
+| MCP server (64 tools, v4.0.0) | ✅ Complete |
+| HTTPS/TLS | ✅ Complete |
+| GitHub Actions CI — frontend | ❌ Not done (H-04b) |
+| MySQL backup cron | ❌ Not done (H-05) |
+| Docker Compose local dev | ❌ Not done (H-03) |
+
+**Estimated remaining effort to full production:** ~8 hours
