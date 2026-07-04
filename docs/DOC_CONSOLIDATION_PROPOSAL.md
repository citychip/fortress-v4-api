# Fortress — Documentation Consolidation Proposal
**Version:** 1.0 (for review) · **Date:** 2026-07-04 · **Status:** Proposal — approve before executing.

Goal: make the docs **findable, non-redundant, and low-maintenance**. One entry point, a small category taxonomy, a clear split between *living* docs and *dated snapshots*, and stable filenames (versions live in headers, not names).

---

## 1. Principles

1. **One index, one entry point.** A single `README.md` maps every doc to its purpose. Start every session there.
2. **Category over chronology.** Group by *what it's for* (operate / strategy / system / plan / history), not by date or sprint number.
3. **Living vs snapshot is explicit.** Every doc header declares `Status: LIVING` (kept current) or `Status: SNAPSHOT YYYY-MM-DD` (immutable point-in-time). Snapshots never get edited — they get superseded.
4. **One source of truth per fact.** Each fact lives in exactly one doc; everything else links to it. No duplicated procedures.
5. **Stable filenames.** No version numbers in filenames (`STRATEGY.md`, not `01_Portfolio_Strategy_v3_9.md`). The version + last-updated live in the doc header, so a version bump doesn't rename the file or break links.
6. **Archive aggressively.** Shipped change-lists, completed sprints, and superseded proposals move to `archive/` — out of the active set but still recoverable.

---

## 2. Target structure

```
docs/
  README.md                     ← THE INDEX (living map: doc → purpose → living/snapshot)

  operate/                      ← "how I run a session / the book"
    HANDOFF.md                  ← lean START-HERE: current state + open priorities + OPEN/CLOSE protocols + pointers
    WORKFLOW.md                 ← daily workflow, entry/roll/stop mechanics, thresholds, common issues
    DATA_SOURCING.md            ← the single Step-0 data-backbone procedure + source-of-truth ledger (merges the HANDOFF §0 + DATA_SOURCES.md)
    MCP_PLAYBOOK.md             ← MCP prompt patterns per phase (was 07_MCP_Workflow_and_Prompts_v1_9)

  strategy/                     ← "the rules"
    STRATEGY.md                 ← canonical strategy spec (was 01_Portfolio_Strategy_v3_9)
    STRATEGY_ENHANCEMENTS.md    ← research-codified addendum (was …_v3_10)
    MULTITIMEFRAME_PROCEDURE.md ← MTF technical procedure (dedup: keep this, delete the root DRAFT)
    RECOVERY_PLAN.md            ← the live recovery plan (was REVISED_RECOVERY_STRATEGY_2026-06-26)

  system/                       ← "how it's built"
    SYSTEM.md                   ← architecture, services, IBKR auth, deploy, repos, key paths
    PARAPET.md                  ← frontend reference / component map (living)

  plan/                         ← "what's next"
    BACKLOG.md                  ← ACTIVE backlog only (open items; completed sprints → archive)
    proposals/                  ← active proposals (Enhancement Proposal, this doc, change-lists in flight)
    research/                   ← IMPROVEMENT_RESEARCH_*, JOURNAL_FEEDBACK_LOOP

  history/
    SESSION_LOG.md              ← reformatted, recent entries; older ones rolled into archive
    archive/                    ← everything superseded/shipped (existing archive + retired change-lists + old session log)
```

Five top-level categories (`operate / strategy / system / plan / history`) — shallow enough to scan, deep enough to separate concerns. `README.md` is the map so you never have to guess.

---

## 3. File-by-file migration

| Current file | Action | New home / note |
|---|---|---|
| `docs/HANDOFF.md` | **KEEP + slim** | `operate/HANDOFF.md`. Move the §0 data procedure into `DATA_SOURCING.md`; keep Current State + priorities + protocols + the index pointer. |
| `docs/WORKFLOW.md` | move | `operate/WORKFLOW.md` |
| `docs/DATA_SOURCES.md` | **MERGE** | fold into `operate/DATA_SOURCING.md` (procedure + reliability ledger in one) |
| `docs/07_MCP_Workflow_and_Prompts_v1_9.md` | rename | `operate/MCP_PLAYBOOK.md` |
| `docs/01_Portfolio_Strategy_v3_9.md` | rename | `strategy/STRATEGY.md` (version → header) |
| `docs/STRATEGY_ENHANCEMENTS_v3_10.md` | rename | `strategy/STRATEGY_ENHANCEMENTS.md` |
| `docs/MULTITIMEFRAME_PROCEDURE.md` | **KEEP (canonical)** | `strategy/MULTITIMEFRAME_PROCEDURE.md` |
| `./Fortress_MultiTimeframe_Procedure_v1_DRAFT.md` (root) | **DELETE** | duplicate of the above — retire it |
| `docs/REVISED_RECOVERY_STRATEGY_2026-06-26.md` | rename | `strategy/RECOVERY_PLAN.md` (living; drop the date from the name) |
| `docs/SYSTEM.md` | move | `system/SYSTEM.md` |
| `docs/PARAPET.md` | move | `system/PARAPET.md` |
| `docs/PARAPET_SPRINT.md` | **ARCHIVE** | `history/archive/` — it's sprint history, not a living reference |
| `docs/BACKLOG_SPRINT_PLAN.md` | **SPLIT** | `plan/BACKLOG.md` = open items only; completed Sprints 0–24 → `history/archive/BACKLOG_COMPLETED.md` |
| `./Fortress_Enhancement_Proposal_v1.md` (root) | move | `plan/proposals/ENHANCEMENT_PROPOSAL_v1.md` |
| `docs/Sprint21_ChangeList.md` | **ARCHIVE** | shipped — `history/archive/` |
| `docs/IMPROVEMENT_RESEARCH_2026-06-22.md` | move | `plan/research/` |
| `docs/JOURNAL_FEEDBACK_LOOP.md` | move | `plan/research/` |
| `docs/PORTFOLIO.md` | **ARCHIVE** | stale since 06-15; live state = `get_briefing` + HANDOFF Current State. Archive it (or replace with a 3-line pointer). |
| `docs/SESSION_LOG.md` | **REFORMAT** | `history/SESSION_LOG.md`, fix the one-line-per-entry problem; roll pre-July entries into `history/archive/SESSION_LOG_pre_2026-07.md` |
| `docs/archive/*` | keep | already the right pattern — becomes `history/archive/` |

Net effect: **root cleared** (2 loose files homed), **1 duplicate deleted**, **1 merge** (DATA_SOURCES → DATA_SOURCING), **2 splits/reformats** (BACKLOG, SESSION_LOG), **~5 archived**, everything renamed to stable names.

---

## 4. The header standard (every living doc gets this)

```
# <Title>
**Status:** LIVING · **Version:** x.y · **Last updated:** YYYY-MM-DD · **Owner-of-truth:** <what this doc is the sole source for>
**Supersedes / see also:** <links>
```

Snapshots use `**Status:** SNAPSHOT 2026-07-04` and are never edited afterward.

---

## 5. Maintenance model (keeps it from rotting again)

- **The CLOSE protocol edits only living docs** — HANDOFF (Current State / priorities), BACKLOG (status), SESSION_LOG (one short entry). Everything else changes only when its subject changes.
- **SESSION_LOG discipline:** 3–6 line entries, most-recent-first; when it passes ~40 entries, roll the oldest half into `history/archive/`.
- **BACKLOG discipline:** when a sprint is fully shipped + verified, move its table out of `plan/BACKLOG.md` into `history/archive/BACKLOG_COMPLETED.md` with a one-line summary link. The active backlog stays short.
- **README is the contract:** any new doc must be added to `README.md` with its category + living/snapshot status, or it doesn't exist.
- **`sync_check.sh` MAP** gets the new paths so drift-tracking follows the moves (and root docs become tracked for the first time).

---

## 6. Execution plan (phased, low-risk — all `git mv`, no content loss)

1. **Scaffold + index:** create the folders + `README.md` map. (No moves yet — safe.)
2. **Move + rename** via `git mv` (preserves history); update cross-links.
3. **Merges/splits:** DATA_SOURCING (merge), BACKLOG split, SESSION_LOG reformat — the only content edits.
4. **Delete the duplicate**, archive the shipped/stale set.
5. **Rewire** `sync_check.sh` MAP + `deploy_*` doc lists to the new paths; run `sync_check.sh` green.
6. **One commit per phase** so any step is trivially revertible.

Estimated ~1 focused session. Phases 1–2 are pure moves (reversible); phase 3 is the only judgement work.

*Proposal — approve or adjust the taxonomy/names, then I can execute it phase by phase.*
