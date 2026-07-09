# Proposal — Two-Leaf Dashboard & Documentation System

**Status: PROPOSAL (not adopted) · 2026-07-09 · Author: Cowork session**

> Goal: let the new **v4.0 household two-leaf strategy** and the existing **v3.11 engine** coexist cleanly — new *household* layer on top, engine untouched underneath. This document proposes the doc-system changes and the dashboard additions. **Nothing here is built or deleted.** No executable code was changed in this session; the only files written are `docs/02_Household_Strategy_v4_0.md`, this proposal, and the root `Combined_Portfolio.xlsx` / strategy pointer. Adoption is your call, phased.

---

## 1. Principle — additive coexistence, not replacement

v3.11 is a *working, disciplined engine*. v4.0 changes the **mandate and the risk lens**, not the trade mechanics. So the system change is a **layer**, not a rewrite:

```
                 ┌─────────────────────────────────────────┐
   NEW  v4.0 →   │  HOUSEHOLD LAYER  (Leaf A + Leaf B)      │
                 │  concentration · factor caps · stages    │
                 └───────────────┬─────────────────────────┘
                                 │ reads
                 ┌───────────────┴─────────────────────────┐
  EXISTING v3.11 │  FORTRESS ENGINE  (Leaf B / IBKR)        │
                 │  briefing · positions · candidates ·     │
                 │  greeks · alerts · options analytics     │
                 └─────────────────────────────────────────┘
                                 ▲ manual snapshot
                 ┌───────────────┴─────────────────────────┐
   NEW  Leaf A → │  eToro copy (read-only, self-hedged)     │
                 └─────────────────────────────────────────┘
```

The engine keeps running exactly as-is. The household layer *reads* engine data (IBKR positions/greeks) plus an eToro snapshot, and applies the v4.0 caps. It never places or blocks trades — same advisory model as v3.11 §13.

---

## 2. Documentation system

### 2.1 What's already written (this session)
- `docs/02_Household_Strategy_v4_0.md` — the separate v4.0 household strategy with the explicit v3.11 difference map. **LIVING.**
- `Combined_Portfolio.xlsx` (repo root) — live household exposure netting, sector/concentration math, hedge sizing, and the non-tech **Candidates** tab. **Artifact.**

### 2.2 Proposed README index rows (add under the existing sections)
```
## ♟ Strategy — the rules
| `02_Household_Strategy_v4_0.md` | Household two-leaf overlay (Leaf A eToro + Leaf B IBKR);
   re-mandates Leaf B income→growth; staged uncap; tail hedge; household caps. Coexists with —
   does not supersede — v3.11. | LIVING |

## 📊 Household layer (v4.0)
| `PROPOSAL_Two_Leaf_Dashboard_and_Docs_2026-07-09.md` | This proposal. | SNAPSHOT |
| `Combined_Portfolio.xlsx` | Live household exposure + non-tech candidates. | Artifact (LIVING data) |
```
Reframe the v3.11 row's purpose line to "…canonical **Leaf-B engine** spec" so the two-tier relationship is legible at a glance.

### 2.3 What becomes obsolete under v4.0 (recommend **archive**, per your convention — not delete)
- **`REVISED_RECOVERY_STRATEGY_2026-06-26.md`** — the recovery framing (loss-attribution + de-concentration glide) is largely absorbed by the v4.0 growth mandate + household caps. Mark SNAPSHOT, move to `archive/` once v4.0 is adopted.
- **The four external-review-loop snapshots** (`STRATEGY_v3_11_UPDATE_2026-07-07`, `AI_REVIEW_BRIEF_2026-07-07`, `REVIEW_REQUEST_2026-07-08`, `LEAP_SALVAGE_MSFT_CROSSCHECK_2026-07-07`) — already slated in README to archive "when Manus v6 lands." v4.0 doesn't change that; just noting they're the obsolete-candidate cluster.
- **`Fortress_Forward_Prognosis_2026-07-02.docx`** (repo root) — a dated point-in-time prognosis; move to `archive/` or a `snapshots/` folder.
- Nothing in the engine strategy (v3.11) is obsolete — it's demoted to "engine rules," still LIVING.

### 2.4 Drift tracking
Add the two new docs to `sync_check.sh`'s MAP so they're drift-checked like the rest. (Proposed — I did not edit `sync_check.sh`.)

---

## 3. Dashboard system (Parapet additions)

Parapet today is a 6-page passive monitor (Briefing · Triage · Candidates · Market · Positions · System) over the Leaf-B engine. Proposal: **one new page + two chips**, all read-only, mirroring existing patterns (`route_*.py` → `app.services.state` → `api.ts` → page component, tracked in `deploy_parapet.sh`).

### 3.1 New page: **Household** (`h` / `/household`)
Four panels, all computable from data you already have (this is the `Combined_Portfolio.xlsx` logic promoted to a live view):

1. **Overview** — combined net liq, leaf split (A/B %), household delta (**Leaf B only** — Leaf A is self-hedged so excluded by design), cash.
2. **Concentration & Factor** — single-name %, sector %, AI/tech/chips group % and semis complex, each vs its v4.0 cap (15 / 25 / 35), red/amber/green. Netted across both leaves.
3. **Staged-uncap tracker** — per Leaf-B LEAP: current stage (0–3), the four gates (name<15% · cash floor · regime · >200-SMA) as pass/fail chips, and next-stage eligibility.
4. **Tail-hedge monitor** — replaces the B-2 coverage widget for the household view: quarterly budget used/remaining, crash-put strike/DTE, roll date.

### 3.2 Chips (reuse the existing `Badge` pattern)
- **Candidates page:** a `DIVERSIFIER` chip on rows whose sector is one the household is light on (surfacing the v4.0 §3.2 intent inline).
- **Positions page:** a `LEAF-A ↔` chip on any Leaf-B ticker that also appears in the eToro snapshot (the overlap flag from the workbook).

### 3.3 Leaf A (eToro) ingest — the one genuinely new capability
eToro has no API. Proposed lightweight, read-only ingest that mirrors how this session pulled it:
- A `household_state.json` store (analogous to `state.py`'s stores) holding the last eToro snapshot: total value + top holdings + timestamp.
- Populate it either (a) manually on the weekly cadence, or (b) via the same Chrome-assisted read used here, written to the store. **Monitoring only — Leaf A is never traded from Fortress.**
- Staleness surfaced like the existing `SourceBadge` (amber if the eToro snapshot is > N days old).

---

## 4. Proposed MCP tools / routes (names only — not built)

Following your `route_candidates.py` → `state` → `fortress_mcp_v452.py` registration pattern:

| Route / tool | Returns | Reuses |
|---|---|---|
| `get_household_overview` | combined NLV, leaf split, Leaf-B delta, cash | `get_briefing` + household_state |
| `get_household_concentration` | single-name / sector / AI-tech-chips % vs caps | `compute_concentration` + eToro snapshot |
| `get_uncap_stages` | per-LEAP stage + 4-gate status | positions + `get_technical_gate` + briefing regime |
| `get_tail_hedge` | budget used/left, strike, DTE, roll date | positions + settings |
| `get_diversification_candidates` | Fortress-gate + TradingView non-tech scan | `get_candidates` + scanner |
| `ingest_etoro_snapshot` | writes household_state | new (Chrome-assisted or manual) |

All read-only. None blocks a trade. Each is a thin aggregation over existing computations — no change to options/risk logic.

---

## 5. Phased adoption (low-risk order)

1. **Phase 1 — Docs (done/ready):** v4.0 strategy doc + this proposal + workbook. Wire the README rows + `sync_check.sh` MAP. *No system change.*
2. **Phase 2 — Read-only household view:** `get_household_overview` + `get_household_concentration` + the Household page panels 1–2, fed by a manual eToro snapshot. Promotes the workbook to live.
3. **Phase 3 — Trackers:** staged-uncap + tail-hedge panels/tools.
4. **Phase 4 — Automation:** scheduled diversification screen; Chrome-assisted eToro ingest; staleness badge.

Each phase is independently shippable and reversible; the engine is never modified.

---

## 6. What this session did NOT do
- No executable code edited (no `*.py`, no `*.sh`, no Parapet source).
- No files deleted (obsolete docs are *recommended* for `archive/`, your call).
- No trades, orders, or settings changed.
- v3.11 and all engine docs left intact.

## 7. Open decisions for you
1. Adopt v4.0 as a coexisting overlay, or hold it as a proposal? 
2. Approve the README/`sync_check.sh` wiring (Phase 1)?
3. Archive the obsolete-candidate docs in §2.3 now, or wait for Manus v6?
4. Green-light Phase 2 (read-only Household view) as the first build?
