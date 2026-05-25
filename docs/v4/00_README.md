# Fortress V4 — Documentation Index

**Version:** 4.0.0  
**Status:** Design Phase — Pre-implementation  
**Date:** May 2026  

> **Note:** Fortress V3 is the current running system. These documents describe the planned V4 architecture. V3 documentation remains in `docs/` (parent directory) and is the operational reference until V4 is deployed.

---

## Document Set

| # | File | Purpose | Phase |
|---|---|---|---|
| 1 | `01_Master_Design_Proposal.md` | Vision, goals, architectural seams, ADRs, phase structure | P0 |
| 2 | `02_System_Architecture.md` | Four engines, data layer, SSE, API surface, file tree | P0 |
| 3 | `03_Design_System.md` | Obsidian Edge design system — tokens, components, page layouts | P0/P1 |
| 4 | `04_Phase_Backlog.md` | Full sprint backlog with acceptance criteria for all phases | P0 |
| 5 | `05_MCP_Spec.md` | All 61 MCP tools — request/response schemas, tier breakdown | P0/P2 |
| 6 | `06_Operations_Guide.md` | Daily workflow, 8 APScheduler scripts, VPS operations, incident procedures | P0/P2 |
| 7 | `07_Migration_Guide.md` | JSON → MySQL 8 migration scripts, rollback, validation | P0/P2 |
| 8 | `08_Developer_Guide.md` | Local setup, Docker Compose, env vars, module layout, test commands | P0/P2 |
| 9 | `09_Operations_Notes.md` | Permanent hard-won operational knowledge — read before touching VPS | Permanent |
| 10 | `10_GitHub_App_Setup_Archive.md` | Archived setup guide for the deleted 8081 GitHub app instance | Archive |

---

## Phase Overview

| Phase | Goal | Status |
|---|---|---|
| **Phase 0** | Architecture documentation | ✅ Complete |
| **Phase 1** | Design system + component library | ⬜ Pending |
| **Phase 2** | Developer and operational documentation | ⬜ Pending |
| **Phase 3** | Front-end coding (React 19 + Tailwind 4 + tRPC 11) | ⬜ Pending |
| **Phase 4** | Backend coding (FastAPI + MySQL 8 + Redis 7 + APScheduler) | ⬜ Pending |
| **Phase 5** | MCP server update (61 tools) | ⬜ Pending |
| **Phase 6** | Infrastructure (Docker, systemd, NGINX) | ⬜ Pending |

**Golden Rule:** Phases 0–2 must be complete and signed off before any Phase 3–6 coding begins.

---

## Key V4 Changes from V3

| Area | V3 | V4 |
|---|---|---|
| State storage | 5 JSON files | MySQL 8 |
| Cache / pub-sub | None | Redis 7 |
| Real-time updates | Polling | Server-Sent Events (SSE) |
| MCP tools | 29 tools | 61 tools (47 + 10 + 4 new Tier 1.5) |
| Backend framework | FastAPI (existing) | FastAPI (refactored into 4 engines) |
| Scheduled workflows | 5 workflows | 8 workflows |
| Front-end | React 19 + Tailwind 4 + tRPC 11 (existing) | Same stack, full redesign with Obsidian Edge design system |

---

## Repository Structure (V4 Target)

| Repo | Purpose |
|---|---|
| `citychip/fortress-app` | React front-end (this repo) |
| `citychip/fortress-api` | FastAPI backend, four engines, scheduler |
| `citychip/fortress-mcp` | Claude MCP server (61 tools) |
