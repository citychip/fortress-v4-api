# Fortress — Documentation Index
**Status:** LIVING · **Last updated:** 2026-07-04 · **Owner-of-truth:** the map of what every doc is for.

Start any session at **`HANDOFF.md`**. This index is the map: every doc, its purpose, and whether it's **LIVING** (kept current) or a **SNAPSHOT** (immutable, point-in-time — superseded, never edited). Any new doc must be added here or it doesn't exist.

> **Layout:** flat `docs/` — grouped below by purpose, not by folder. Versions live in filenames + headers. Superseded material lives in `archive/`.

---

## ▶ Start here
| Doc | Purpose | Status |
|---|---|---|
| **`HANDOFF.md`** | Session START-HERE: current state, open priorities, OPEN/CLOSE protocols, this index. Read top-to-bottom every session. | LIVING |

## ⚙ Operate — how to run a session / the book
| Doc | Purpose | Status |
|---|---|---|
| `WORKFLOW.md` | Daily workflow, entry/roll/stop mechanics, thresholds, common issues. | LIVING |
| `DATA_SOURCES.md` | Data-source reliability ledger + source-of-truth per attribute (which tool owns which number). | LIVING |
| `07_MCP_Workflow_and_Prompts_v1_9.md` | MCP prompt playbook — exact phrasings per phase. | Reference |

## ♟ Strategy — the rules
| Doc | Purpose | Status |
|---|---|---|
| `01_Portfolio_Strategy_v3_9.md` | Canonical strategy spec: governance, strategies, entry/exit/risk, post-earnings playbook. | LIVING (spec) |
| `STRATEGY_ENHANCEMENTS_v3_10.md` | Research-codified rules addendum (VRP gate, 50% take, PMCC guardrails, β-vega, cluster, §8 LEAP call-writing). | LIVING (addendum) |
| `MULTITIMEFRAME_PROCEDURE.md` | Monthly/Weekly/Daily/4h technical procedure + source-split + decision matrix (v1.1). | LIVING |
| `REVISED_RECOVERY_STRATEGY_2026-06-26.md` | The recovery plan (loss attribution + 5 pillars + de-concentration glide). | LIVING |

## 🏗 System — how it's built
| Doc | Purpose | Status |
|---|---|---|
| `SYSTEM.md` | Architecture, services, IBKR auth, deploy commands, repos, key paths, token-rotation runbook. | LIVING |
| `PARAPET.md` | Frontend reference / component map. | LIVING |

## 🗺 Plan — what's next
| Doc | Purpose | Status |
|---|---|---|
| `BACKLOG_SPRINT_PLAN.md` | Sprint backlog. Sprints 0–24 shipped; 25 mostly shipped (25.1 open). Completed detail should archive as it ages. | LIVING |
| `ENHANCEMENT_PROPOSAL_v1.md` | Source proposal behind Sprints 21–24. | SNAPSHOT 2026-07-02 |
| `IMPROVEMENT_RESEARCH_2026-06-22.md` | External best-practice scan + sources behind v3.10. | SNAPSHOT 2026-06-22 |
| `JOURNAL_FEEDBACK_LOOP.md` | Trade-outcomes store + `journal_analytics.py` design (expectancy/win-rate by IVR/DTE/delta). | Reference |
| `DOC_CONSOLIDATION_PROPOSAL.md` | This reorg proposal. | SNAPSHOT 2026-07-04 |

## 🕮 History
| Doc | Purpose | Status |
|---|---|---|
| `SESSION_LOG.md` | Dated session history, most-recent-first (3–6 lines/entry). | LIVING (append-only) |
| `archive/` | Superseded/shipped docs — proposals, old handoff, shipped change-lists. Recoverable, out of the active set. | Immutable |

## 🗄 Stale / superseded (archive candidates)
| Doc | Why | Status |
|---|---|---|
| `PORTFOLIO.md` | Live state is `get_briefing` + HANDOFF Current State; not updated since 2026-06-15. | STALE → archive |
| `Sprint21_ChangeList.md` | Sprint 21 shipped; historical change-list. | SHIPPED → archive |
| `PARAPET_SPRINT.md` | Frontend sprint history, not a living reference. | archive candidate |

---

## Maintenance rules (keeps this from rotting)
- **Only these change routinely** (the CLOSE protocol): `HANDOFF.md` (Current State / priorities), `BACKLOG_SPRINT_PLAN.md` (status), `SESSION_LOG.md` (one short entry).
- **Snapshots are immutable** — never edit a `SNAPSHOT`; supersede it and archive the old one.
- **SESSION_LOG:** 3–6 line entries; roll the oldest half into `archive/` past ~40 entries.
- **BACKLOG:** move a fully-shipped sprint's table into `archive/BACKLOG_COMPLETED.md` (one-line summary link left behind).
- **New doc → add a row here**, with category + LIVING/SNAPSHOT. Add its path to `sync_check.sh` MAP so drift-tracking follows it.
- Full reorg rationale + phased plan: `DOC_CONSOLIDATION_PROPOSAL.md`.
