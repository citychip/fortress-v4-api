# GitHub App Setup — Archive

> ⚠️ **DEPRECATED — ARCHIVED 2026-05-24**
>
> This document describes the setup of a separate GitHub app instance that ran on port 3001 and connected to a cloned Fortress API on port 8081. **Both services have been permanently removed.**
>
> - The port 8081 clone was stopped, disabled, and its directory deleted on 2026-05-23.
> - The port 3001 GitHub app was also removed at the same time.
> - This document is preserved for historical reference only.
> - **Do not follow any instructions in this document.** The paths, ports, and service names it references no longer exist.
>
> For the current deployment configuration, see:
> - `docs/v4/09_Operations_Notes.md` — authoritative VPS operational knowledge
> - `docs/04_VPS_Implementation_Guide_v1_6.md` (v1.7) — current V3 deployment guide

---

## Original Content (Archived)

The original `FORTRESS_GITHUB_APP_FINAL_SETUP.md` described:

- A GitHub integration app running on port 3001 (`fortress-github` directory)
- A dedicated Fortress API clone on port 8081 (`fortress-github-api` directory)
- `localStorage` token configuration for the 3001 app to authenticate against 8081
- CORS configuration for cross-port requests
- Troubleshooting steps for wrong-port API calls

All of these components were removed because:

1. The 8081 clone had no git history and was out of sync with the main codebase.
2. The 3001 GitHub app was not in active use.
3. Running two API instances on the same VPS created confusion about which was the authoritative service.
4. The orchestrator crash loop (2700+ crashes, 2026-05-23) was partially caused by the stale 8081 service consuming resources.

The single authoritative Fortress API is on port 8080. The single authoritative frontend is served by nginx on port 3000 from `/var/www/fortress-v2/`.

---

*Archived: 2026-05-24 | Original document: `FORTRESS_GITHUB_APP_FINAL_SETUP.md`*
