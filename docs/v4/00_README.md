# Fortress V4 — Documentation Index

**Version:** 4.0.0
**Status:** Production — V4 is live at `https://srv1321374.hstgr.cloud`
**Last updated:** 2026-05-27 (post Sprint v8.24)

> V4 is the active running system. V3 (`fortress-api` repo, port 8080) is legacy fallback only.

---

## Ground-Truth Documents (read these first)

| File | Purpose |
|---|---|
| `V4_REALITY_CHECK.md` | VPS-verified snapshot of what is actually built and working |
| `V4_OPEN_REQUIREMENTS.md` | All requirements with current status checkboxes |
| `V4_SPRINT_PLAN.md` | Sprint history (v8.3–v8.24 complete) + upcoming work |

---

## Reference Documents

| # | File | Purpose | Status |
|---|---|---|---|
| 2 | `02_System_Architecture.md` | Architecture diagram, data layer, API surface | Design reference (partially implemented) |
| 3 | `03_Design_System.md` | Obsidian Edge design tokens and component specs | Design reference |
| 4 | `04_Phase_Backlog.md` | Full phase backlog with acceptance criteria | Superseded by V4_OPEN_REQUIREMENTS.md |
| 5 | `05_MCP_Spec.md` | MCP tool catalogue — all 64 tools | Updated post-v8.24 |
| 6 | `06_Operations_Guide.md` | Daily workflow, scheduler scripts, incident procedures | Authoritative |
| 7 | `07_Migration_Guide.md` | JSON → MySQL migration notes | Complete — all migrations done |
| 8 | `08_Developer_Guide.md` | Repo setup, env vars, build commands | Authoritative |
| 9 | `09_Operations_Notes.md` | **CRITICAL** — hard-won VPS operational knowledge | Permanent — read before touching VPS |
| 10 | `10_GitHub_App_Setup_Archive.md` | Archived GitHub App setup (historical) | Archive |
| 11 | `11_Upgrade_Plan.md` | Sprint-ready V3→V4 upgrade backlog | Historical reference |

---

## Repository Map

| Repo | Role | Branch |
|---|---|---|
| `citychip/fortress-v4-api` | FastAPI backend | `master` |
| `citychip/fortress-v4-frontend` | React frontend | `main` |
| `citychip/fortress-mcp` | Claude MCP server | `master` |

---

## Current Phase Status (post v8.24)

| Area | Status |
|---|---|
| Backend API (all endpoints) | ✅ Complete |
| MySQL migrations (config, journal, positions, snapshots) | ✅ Complete |
| APScheduler (8 jobs + EOD snapshot) | ✅ Complete |
| Strategy gates (F-01 through F-07) | ✅ Complete |
| Frontend widgets (all E-series except E-11) | ✅ Complete |
| MCP server (64 tools, v4.0.0) | ✅ Complete |
| HTTPS/TLS | ✅ Complete |
| GitHub Actions CI — frontend | ❌ Not done (H-04b) |
| MySQL backup cron | ❌ Not done (H-05) |
| Docker Compose local dev | ❌ Not done (H-03) |

**Estimated remaining effort to full production:** ~8 hours
