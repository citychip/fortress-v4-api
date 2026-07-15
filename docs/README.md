# Fortress — Documentation Index
**Status:** LIVING · **Last updated:** 2026-07-15 · **Owner-of-truth:** the map of what every doc is for and **where it lives**.

Start any session at **`HANDOFF.md`** (root). This index is the map: every doc, its path, its purpose, and whether it's **LIVING** (kept current) or a **SNAPSHOT** (immutable, point-in-time). Any new doc must be added here or it doesn't exist.

> **Layout (reorganized 2026-07-09):** foldered by lifecycle + strategy line.
> - **root** — the always-open trio: `README.md`, `HANDOFF.md`, `SESSION_LOG.md`.
> - **`shared/`** — version-independent system/ops/plan docs used by both strategy lines.
> - **`v3/`** — the **Engine** (premium-income doctrine, v3.11) + its trade-workflow/procedure docs.
> - **`v4/`** — the **Household** two-leaf overlay (growth mandate) + its proposals.
> - **`archive/`** — superseded/immutable, recoverable, out of the active set.
>
> **Reference convention:** docs cite each other by **bare filename** (e.g. "see `WORKFLOW.md`"); **this index is the locator** for the folder. The `v3`/`v4` split mirrors the Parapet dashboard modes (Engine v3 / Household v4).

---

## ▶ Start here (root)
| Doc | Purpose | Status |
|---|---|---|
| **`HANDOFF.md`** | Session START-HERE: current state, open priorities, OPEN/CLOSE protocols. Read top-to-bottom every session. | LIVING |
| `SESSION_LOG.md` | Dated session history, most-recent-first (3–6 lines/entry). | LIVING (append-only) |

## ♟ Strategy — v3 Engine (`v3/`)
| Doc | Purpose | Status |
|---|---|---|
| **`v3/01_Portfolio_Strategy_v3_11.md`** | **The canonical Leaf-B ENGINE spec** (consolidated 07-08): governance, two-bucket architecture, hybrid XSP income, all strategies, entry/roll/exit rules incl. doctrine v2 + salvage, β-DD caps, B-2 hedge formula, weekly-close protocol, dynamic pacing, compliance measurement. Still LIVING — governs how every IBKR trade is built. | LIVING (spec) |
| `v3/WORKFLOW.md` | Daily workflow, entry/roll/stop mechanics, thresholds, trade-session procedure. | LIVING |
| `v3/MULTITIMEFRAME_PROCEDURE.md` | Monthly/Weekly/Daily/4h technical procedure + decision matrix (v1.1). | LIVING |
| `v3/07_MCP_Workflow_and_Prompts_v1_9.md` | MCP prompt playbook — exact phrasings per phase. | Reference |

## 📊 Strategy — v4 Household (`v4/`)
| Doc | Purpose | Status |
|---|---|---|
| **`v4/02_Household_Strategy_v4_0.md`** | **The household two-leaf overlay** (Leaf A eToro + Leaf B IBKR); re-mandates Leaf B income→growth; staged uncap; tail hedge; household caps (15/25/35). §7 = the full v3.11↔v4.0 difference map. **Coexists with — does not supersede — v3.11.** | LIVING |
| `v4/PROPOSAL_Two_Leaf_Dashboard_and_Docs_2026-07-09.md` | Proposal for the household dashboard layer + doc system that lets v4 and the v3 engine coexist (4-phase). | SNAPSHOT |

## ⚙ Operate & System — shared (`shared/`)
| Doc | Purpose | Status |
|---|---|---|
| `shared/DATA_SOURCES.md` | Data-source reliability ledger + source-of-truth per attribute. | LIVING |
| `shared/SYSTEM.md` | Architecture, services, IBKR auth, deploy commands, repos, key paths, token-rotation runbook. | LIVING |
| `shared/PARAPET.md` | Frontend reference / component map (dashboard). | LIVING |
| `shared/BACKLOG_SPRINT_PLAN.md` | Active backlog only. Sprints 0–28 archived/shipped; v4.0 Phases 2–3 (O-10/O-13) shipped; Phase 4 open. | LIVING |
| `shared/JOURNAL_FEEDBACK_LOOP.md` | Trade-outcomes store + `journal_analytics.py` design (expectancy/win-rate by IVR/DTE/delta). | Reference |

## 🕮 History & archive
| Path | Purpose | Status |
|---|---|---|
| `SESSION_LOG.md` | (root) session history. | LIVING |
| `archive/` | Superseded/shipped docs — recoverable, out of the active set. | Immutable |

**Archived 2026-07-09 (this reorg):** the external-review loop — `STRATEGY_v3_11_UPDATE_2026-07-07.md`, `AI_REVIEW_BRIEF_2026-07-07.md`, `REVIEW_REQUEST_2026-07-08.md`, `LEAP_SALVAGE_MSFT_CROSSCHECK_2026-07-07.md` (the v3.11 rules they reviewed now live in `v3/01_Portfolio_Strategy_v3_11.md`; retained as the review record) — and `REVISED_RECOVERY_STRATEGY_2026-06-26.md` (recovery-by-engine thesis superseded by the v4.0 growth mandate).

**Archived 2026-07-15:** `archive/Fortress_Forward_Prognosis_2026-07-02.docx` (point-in-time forward-P&L snapshot, superseded by the live briefing + v4.0 growth mandate; was flagged in HANDOFF Priority #8c).

**Earlier archives:** `archive/PORTFOLIO.md`, `archive/Sprint21_ChangeList.md`, `archive/PARAPET_SPRINT.md` (07-04); `archive/DOC_CONSOLIDATION_PROPOSAL.md`, `archive/ENHANCEMENT_PROPOSAL_v1.md`, `archive/IMPROVEMENT_RESEARCH_2026-06-22.md`, `archive/STRATEGY_AMENDMENT_TWO_BUCKET_2026-07-07.md`, `archive/01_Portfolio_Strategy_v3_9.md`, `archive/STRATEGY_ENHANCEMENTS_v3_10.md`, `archive/BACKLOG_COMPLETED.md` (07-08).

---

## Maintenance rules (keeps this from rotting)
- **Only these change routinely** (the CLOSE protocol): `HANDOFF.md` · `shared/BACKLOG_SPRINT_PLAN.md` · `SESSION_LOG.md`.
- **Snapshots are immutable** — never edit a `SNAPSHOT`; supersede it and archive the old one.
- **SESSION_LOG:** 3–6 line entries; roll the oldest half into `archive/` past ~40 entries.
- **New doc → add a row here** (correct folder + path + LIVING/SNAPSHOT). Docs are **auto-drift-tracked** by `sync_check.sh` (recursive `find` over `docs/**.md`) — no MAP edit needed; `deploy_data_sources.sh` copies the whole tree recursively (rsync).
- **Folder rule (2026-07-09):** version-independent → `shared/`; v3 engine rules/ops → `v3/`; household overlay → `v4/`; superseded → `archive/`. `README`/`HANDOFF`/`SESSION_LOG` stay at root.
