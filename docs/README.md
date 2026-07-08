# Fortress — Documentation Index
**Status:** LIVING · **Last updated:** 2026-07-08 · **Owner-of-truth:** the map of what every doc is for.

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
| **`STRATEGY_v3_11_UPDATE_2026-07-07.md`** | **CANONICAL RULES DELTA (v3.11, in force):** two-bucket (VWCE 20%), hybrid XSP income, per-ticker β-DD caps (30/40), B-2 hedge formula, roll doctrine v2 (matched-vertical exemption), weekly-close de-risk, dynamic pacing, compliance-score n≥30. Read WITH the v3.9 spec. | LIVING (canonical delta) |
| `01_Portfolio_Strategy_v3_9.md` | Base strategy spec: governance, strategies, entry/exit/risk, post-earnings playbook. v3.11 delta overrides where they conflict. | LIVING (spec) |
| `STRATEGY_ENHANCEMENTS_v3_10.md` | Research-codified rules addendum (VRP gate, 50% take, PMCC guardrails, β-vega, cluster, §8 LEAP call-writing). | LIVING (addendum) |
| `MULTITIMEFRAME_PROCEDURE.md` | Monthly/Weekly/Daily/4h technical procedure + source-split + decision matrix (v1.1). | LIVING |
| `REVISED_RECOVERY_STRATEGY_2026-06-26.md` | The recovery plan (loss attribution + 5 pillars + de-concentration glide). | LIVING |

## 🔍 External review loop (active until Manus v6 lands — then archive all three)
| Doc | Purpose | Status |
|---|---|---|
| `AI_REVIEW_BRIEF_2026-07-07.md` | The 10-question review brief sent to Gemini/Manus. | SNAPSHOT 2026-07-07 |
| `REVIEW_REQUEST_2026-07-08.md` | Follow-up request (incl. Q7 compliance checklist). | SNAPSHOT 2026-07-08 |
| `LEAP_SALVAGE_MSFT_CROSSCHECK_2026-07-07.md` | Live-data cross-check that caught the external AIs' errors (naked-upside trap, β-DD ranking, hedge already in band). | SNAPSHOT 2026-07-07 |

## 🏗 System — how it's built
| Doc | Purpose | Status |
|---|---|---|
| `SYSTEM.md` | Architecture, services, IBKR auth, deploy commands, repos, key paths, token-rotation runbook. | LIVING |
| `PARAPET.md` | Frontend reference / component map. | LIVING |

## 🗺 Plan — what's next
| Doc | Purpose | Status |
|---|---|---|
| `BACKLOG_SPRINT_PLAN.md` | Active backlog only. Sprints 0–26 archived; Sprint 27 (v3.11 wiring) shipped 07-08; open smalls O-1…O-8. | LIVING |
| `JOURNAL_FEEDBACK_LOOP.md` | Trade-outcomes store + `journal_analytics.py` design (expectancy/win-rate by IVR/DTE/delta). | Reference |

## 🕮 History
| Doc | Purpose | Status |
|---|---|---|
| `SESSION_LOG.md` | Dated session history, most-recent-first (3–6 lines/entry). | LIVING (append-only) |
| `archive/` | Superseded/shipped docs — proposals, old handoff, shipped change-lists. Recoverable, out of the active set. | Immutable |

**Archived 2026-07-04:** `archive/PORTFOLIO.md` (live state = `get_briefing` + HANDOFF Current State; stale since 06-15), `archive/Sprint21_ChangeList.md` (shipped), `archive/PARAPET_SPRINT.md` (frontend sprint history).

**Archived 2026-07-08:** `archive/DOC_CONSOLIDATION_PROPOSAL.md` (executed), `archive/ENHANCEMENT_PROPOSAL_v1.md` (Sprints 21–24 shipped), `archive/IMPROVEMENT_RESEARCH_2026-06-22.md` (v3.10 source material), `archive/STRATEGY_AMENDMENT_TWO_BUCKET_2026-07-07.md` (folded into `STRATEGY_v3_11_UPDATE`). Sprint 25/26 backlog tables → `archive/BACKLOG_COMPLETED.md`. Deleted (code, not docs): `route_settings.py`, `route_briefing.py`, `route_journal.py`, `route_options_analytics.py`, `route_pnl.py` — all stale, unmapped duplicates of files whose current copies are mapped (or live only in the repo).

---

## Maintenance rules (keeps this from rotting)
- **Only these change routinely** (the CLOSE protocol): `HANDOFF.md` (Current State / priorities), `BACKLOG_SPRINT_PLAN.md` (status), `SESSION_LOG.md` (one short entry).
- **Snapshots are immutable** — never edit a `SNAPSHOT`; supersede it and archive the old one.
- **SESSION_LOG:** 3–6 line entries; roll the oldest half into `archive/` past ~40 entries.
- **BACKLOG:** move a fully-shipped sprint's table into `archive/BACKLOG_COMPLETED.md` (one-line summary link left behind).
- **New doc → add a row here**, with category + LIVING/SNAPSHOT. Add its path to `sync_check.sh` MAP so drift-tracking follows it.
- Full reorg rationale + phased plan: `DOC_CONSOLIDATION_PROPOSAL.md`.
