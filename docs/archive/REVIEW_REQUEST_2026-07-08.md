# Review Request — v3.11 Package (r2, 2026-07-07 ~18:00 UTC)
**For Gemini (challenger) and Manus (v6 writer). Paste this together with the attached documents. Answers will be applied by the live-data copilot (Claude), so follow the answer-format rules at the bottom — they exist so every answer can be turned into a rule change, a settings edit, or an order ticket without a second round-trip.**

**r2 changes (from both reviewers' meta-feedback):** Q1 now carries LIVE AMZN quotes (no estimates needed) · Q3 reframed around the soft-gate working hypothesis (validate-or-beat, no third framings) · Q7 is now critique-only (checklist pre-drafted). **Process: Manus starts v6 immediately with everything known** (AMZN mechanics + final cap text marked NEEDS-LIVE-DATA placeholders), **Gemini answers Q1–Q7 in parallel**; v6.1 patch folds in the resolved sections.

## Documents attached

**Core (both reviewers):**
1. `STRATEGY_v3_11_UPDATE_2026-07-07.md` — the canonical rules now in force (sections A–K). Review THIS, not older strategy text, wherever they conflict.
2. `AI_REVIEW_BRIEF_2026-07-07.md` — account, objective ("big profits reliably", max DD −20%, 2–3 sessions/wk), constraints, honest performance record.
3. `LEAP_SALVAGE_MSFT_CROSSCHECK_2026-07-07.md` — the corrected salvage mechanics + verdict table on the previous review round (executed 07-07).

**Additionally for Manus (v6):**
4. `01_Portfolio_Strategy_v3_9.md` — base spec that v3.11 amends (needed for the v6 rewrite).
5. `WORKFLOW.md` (v2.9) — operating procedures incl. the Trade Session Procedure and the new cadence section.
6. `STRATEGY_AMENDMENT_TWO_BUCKET_2026-07-07.md` — decision record for the two-bucket adoption.

**Do NOT review:** session logs, backlog, infrastructure docs — out of scope.

## Already decided — do not re-litigate
Bucket A = VWCE only at 20% NLV (revisit Q4) · hybrid income book (XSP base + ≤2-name post-earnings sleeve) · MSFT salvage executed (310/450 vertical + 340C-unit exit) · hedge tranche 3 cancelled · same-strike out-rolls forbidden on keep-names · weekly-close de-risk + retained 395 strength-trim · compliance-score measurement until n≥30.

## Questions (open items only)

**Q1 — AMZN salvage (most urgent; spot ~$245.5, β-DD ~$31.2k = 45% of NLV vs 30% cap).** Book: 2× Jan'28 200C LEAPs (Δ~0.79) + 1× Oct'26 280C short (Δ~0.30). AMZN is technically HEALTHY (above weekly-200, monthly uptrend). **Live IBKR quotes, pulled 2026-07-07 17:54 UTC — use these, not estimates:**

| Contract | Bid/Ask | Mid | Our basis | Position |
|---|---|---|---|---|
| AMZN Jan'28 200C | 77.20/80.05 | **78.625** | 81.82 | long ×2 (−$3.2/sh) |
| AMZN Oct16'26 280C | 8.45/8.70 | **8.575** | 6.985 cr | short ×1 (−$1.6/sh) |
| AMZN Jan'28 280C | 41.30/42.05 | **41.675** | — | candidate short (vertical conversion) |
| AMZN Jan'28 300C | 35.25/35.75 | **35.50** | — | candidate short (vertical conversion) |

Using the MSFT template (healthy/weak-leg classification, package breakevens, expiry-matched verticals, combos only — never add shorts without handling existing ones): propose the exact structure that brings AMZN under 30%. Candidate moves to evaluate at minimum: (a) second short call against the uncovered LEAP (strike/expiry?), (b) roll the Oct'26 280C + convert one or both LEAPs to Jan'28 verticals (280 or 300 caps — show both), (c) trim one LEAP outright (~$7.9k freed, realizes ≈ −$320), (d) mixes. Show package breakeven, cap level, credit/debit, and resulting β-DD per option. Remember the difference vs MSFT: AMZN is a KEEP-name in an uptrend — roll doctrine v2 forbids same-strike out-rolls here, and capping a healthy compounder has real opportunity cost; weigh that explicitly.

**Q2 — AAPL over cap on a healthy name (2 LEAPs Δ0.85/0.72 vs 2× Jan'27 340C shorts Δ0.40; β-DD ~$23.4k = 33%).** AAPL is in a clean uptrend. Does the 30% cap justify cutting a winner, or should the cap rule carry a trend exception? Answer Q3 first, then apply it here.

**Q3 — Cap design.** **Working hypothesis (validate or beat it — do not invent a third framing):** the 30% β-DD cap is a SOFT gate — while a ticker is over cap: no new risk on that name (no new LEAPs, no widening, no size-up on rolls), reduction happens only via existing strength-rungs, salvage rungs, or weekly-close break rules; plus one hard backstop: any single ticker > 40% β-DD triggers a mandatory salvage analysis within one session (not a mandatory trade). Either tag this **ADOPT-AS-IS** (with the rule text tightened for v3.11 §C), or propose specific replacement rule text that is strictly better and say why in ≤3 lines.

**Q4 — First XSP ladder, concretely.** With index IVR currently modest, VIX ~15.6, contango 0.85: does the base book open now or stay empty? If it opens, specify the initial ladder for a ~$25–30k engine income allocation: expiries (45–60+ DTE), short deltas, spread width, number of spreads per expiry, max total XSP margin. If it stays empty, specify the exact trigger values that open it.

**Q5 — B-2 formula precision.** Define "Bucket B positive β-DD" operationally: which positions count (LEAPs at leg delta? verticals at package delta? short calls net against their LEAPs? exclude the hedge itself and OST?), and write the Aug 21 re-run playbook (Aug legs expire → payout drops ~$22.5k → what replacement structure/tenor, sized by the formula, within the ≤5% NLV/yr budget?).

**Q6 — Weekly-close rule mechanics.** For "MSFT Fri close < wk-200 (~383) → cut 50% Monday": which close is authoritative (yfinance weekly bar vs TradingView — they disagreed by $5 on this exact SMA in July), what time Monday (open, first 30 min, or first session), and what happens if price gaps far through the level over the weekend? Write it as executable rule text.

**Q7 — Compliance checklist: ALREADY DRAFTED, critique only.** The following 10-field per-trade checklist is the working template (score = passed / applicable, close-fields scored at close). Flag only fields that are wrong, missing, or unmeasurable — do not redesign from scratch:

| Field | Pass criterion |
|---|---|
| `backbone_fresh` | web_api authenticated + staleness <2h at analysis time |
| `ivr_gate` | base book: index IVR ≥25 · sleeve: post-earnings crush entry |
| `vrp_gate` | IV − HV20 ≥ 3.5 vol-points |
| `term_gate` | VIX term structure in contango |
| `catalyst_gate` | no high-impact macro event inside defer window (sleeve: earnings already reported) |
| `dte_band` | base book 45–60+ DTE · shorts written 60+ days |
| `delta_band` | short leg in band (PCS 0.15–0.20, PMCC 0.20–0.30) |
| `cap_pacing` | post-trade per-ticker β-DD <30% AND entry within the VIX pacing band |
| `mid_execution` | combo worked from the mid; leg directions verified pre-submit |
| `logged_same_session` | journal + outcome logged before session close |

**Q8 — (Manus only) v6 integration.** Fold v3.11 A–K into the proposal; decision log gets D-08 (v3.11 adoption), D-09 (GOOGL LEAP exit), D-10 (MSFT salvage execution + tranche-3 cancellation). Apply the standing corrections: no margin debt exists; hedge-decay footnote (payout falls to ~$45.5k after Aug 21, marginally under band); AAPL also over cap (33%), salvage queue = AMZN then AAPL.

## Answer format (so answers can be applied directly)
1. Reference v3.11 sections by letter (A–K) when proposing changes; quote the rule text you'd replace.
2. Every recommendation ends with one tag: **ADOPT-AS-IS** (rule text ready to paste) / **NEEDS-LIVE-DATA** (state exactly which numbers to pull) / **DECISION-REQUIRED** (state the trade-off in ≤3 lines for the operator).
3. Trade proposals must be exact tickets: per-leg action (BTC/STO/BUY/SELL) · qty · expiry · strike · right · limit basis (mid) · and the invalidation condition.
4. No estimates presented as quotes — mark every price you did not verify as an estimate; the copilot re-prices everything against live IBKR data before execution.
5. Do not propose anything requiring daily monitoring or >5 h/week of operator time.
