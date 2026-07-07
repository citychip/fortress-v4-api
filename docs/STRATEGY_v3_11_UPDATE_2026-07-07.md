# Portfolio Strategy v3.11 — Consolidated Rules Update
**Status: ADOPTED 2026-07-07 (all items executed or in force same day unless marked ⏳). This document is the canonical DELTA against `01_Portfolio_Strategy_v3_9.md` — where they conflict, THIS document wins. Written for external review (Gemini / Manus): every rule states what it replaces and why. Sources: two-bucket amendment + external AI review + live-data cross-check + MSFT salvage execution, all 2026-07-07.**

---

## A. Architecture — Two-Bucket Portfolio (NEW, extends v3.9 §2)

| Bucket | Contents | Target | Management |
|---|---|---|---|
| **A — Core** | VWCE (accumulating UCITS all-world), bought on Euronext inside the IBKR account | **20% of NLV (~$14k)**, revisit Q4'26 | None. Never touched by the options workflow. |
| **B — Engine** | Everything else: LEAPs/verticals, PMCC shorts, income spreads, SPY hedge | remainder | Full Fortress workflow |

Funding glide: seed 1 ~$5.5k (⏳ Euronext order, next session) · seed 2 ~$5.5k post-CPI Jul 14 · thereafter topped up from trim/salvage proceeds until target.
Rationale: de-concentration by removal; reliability (bucket A has no gamma, expiry, venue, or session risk); fits the 2–3 sessions/week operator cadence.

## B. Income book — HYBRID (replaces v3.9 §2 income strategies + §4 entry flow)

1. **Base book = XSP** (mini-SPX, cash-settled European) put credit spreads / iron condors, 2–3 laddered expiries, **minimum 45–60 DTE**. No assignment, no ex-div, no earnings gates apply.
2. **Single-name sleeve: max 2 concurrent names, POST-earnings IV-crush entries only** (enter after the binary event). Pre-earnings single-name premium selling is **DISCONTINUED**. Prefer non-Mag-7 (tier2 rotation sleeve).
3. **Entry gates for the XSP base book (FINAL — Gemini Q4 ADOPT, VIX trigger aligned to §H per Manus):** open the book when **(index IVR ≥ 25 OR VIX ≥ 18)** AND **VRP (IV − HV20) ≥ 3.5 vol-points** AND **VIX/VIX3M < 0.95 (contango)**. As of 07-07 (VIX 15.6): **book stays EMPTY** — low-IV index premium is high gamma for nominal reward.
4. **Stored ladder blueprint (execute when the gate opens, ~$21k income allocation):** Tranche 1 — XSP put credit spreads, **45 DTE, short Δ0.15, 10-wide, ×10** (~$10k margin) · Tranche 2 — same at **60 DTE** (~$10k margin). Work combos at the mid; ladder the two expiries; re-check gates per tranche.
   Rationale: one single-name gap through both strikes (MU-type, −20%) erases 6–8 index wins; the hybrid keeps the documented post-crush edge and deletes the tail.

## C. Concentration — β-Dollar-Delta caps (replaces MV/NLV as the control metric, v3.9 §7) — FINAL TEXT (Gemini Q3 ADOPT, cross-checked 07-07)

- **Metric: per-ticker β-DD = Σ(position delta × 100 × spot)** per underlying. MV/NLV remains a REPORTING metric only (it understates spread risk and misstates LEAP exposure).
- **Soft gate (30% of NLV):** while a ticker's β-DD exceeds 30%, a freeze is enforced on that name — no new long entries, no duration additions, no size-ups on rolls, no spread-widening. Risk reduction happens ONLY via strength-trims, salvage restructurings (§G), or weekly trend-break rules (§F). No forced liquidation at 30%.
- **Hard backstop (40% of NLV):** a ticker printing >40% β-DD at a weekly (Friday) close triggers a mandatory salvage analysis per §G within one session — modeling is mandatory, execution remains an operator decision.
- Mag-7 cluster glide target ≤60% (MV basis, legacy KPI) retained until re-based on β-DD.
- Live ranking 07-07 (net delta × 100 × spot): **AMZN ~$31.2k (45%) ⚠ over BOTH thresholds — salvage ticket specified in §G, pending GO** · **AAPL ~$23.4k (33%) — soft-gate frozen, NO trade** (healthy uptrend; Q2 ruling: bar expansion, let it run until a strength-rung or weekly trend-break) · MSFT ~$17.3k (25%) ✓ · GOOGL ~$10.0k (14%) ✓ · NVDA ~$9.8k (14%) ✓ · AMD ~$2.8k (4%) ✓.

## D. Hedging — B-2 formula (replaces the fixed $20–30k MV floor, v3.9 §2.D) — FINAL TEXT (Gemini Q5 ADOPT, cross-checked 07-07)

- **Engine β-DD definition (what the hedge covers):** Σ of long LEAP deltas NET of their short calls, plus net delta of open verticals — β-weighted to SPY. EXCLUDE: the hedge contracts themselves, settlement cash, Bucket A (VWCE), and inert equity lines (OST).
- **Hedge sizing: SPY bear-put-spread MAX PAYOUT (qty × width × 100) must span 25–33% of Engine β-DD.** Premium market value is NOT the metric (it measures cost, not protection).
- **Budget cap: ≤5% of NLV per year in net hedge debits (~$3.5k).**
- Live 07-07: Engine β-DD ≈ $200k → band $50–66k; payout ≈ $68k → **in band; tranche 3 CANCELLED**.
- **Aug 21 re-run playbook:** Aug 710/665 legs lapse → payout drops to ~$45.5k. Recompute Engine β-DD live THAT week (post-AMZN restructure it falls toward ~$150–185k → band ~$37–61k). If $45.5k is inside the recomputed band: **no replacement legs, $0 outlay**. If below: add the smallest Sep/Oct spread that re-enters the band, within budget. ⚠ Gemini's "$150k, squarely inside" is an estimate — the recomputation is mandatory, the conclusion is conditional.

## E. Roll doctrine v2 (replaces v3.9 §5 roll rules)

- **Names slated to KEEP:** short call tested (Δ > 0.40) → roll **out-and-up for a small debit** (delta relief), or close the spread. Same-strike out-rolls are FORBIDDEN on keep-names (they raise delta and trap you short at levels you don't want).
- **Names slated to EXIT:** the tight cap IS the hedge on the way out — same-strike credit rolls remain allowed, but the position must carry an active exit rule (see F).
- **Expiry-matched verticals (e.g. Jan'28 310/450) are EXEMPT from roll flags** — they are defined-risk packages managed at the package level. ⏳ backend: exempt matched-expiry verticals in `get_roll_all`/stop-loss actions (currently false-flags the MSFT 450C at Δ0.55).

## F. De-risk rules — weekly close protocol (replaces the 3-rung MSFT ladder, v3.9 §6/§7) — FINAL TEXT (Gemini Q6 ADOPT with TWO time corrections)

- **Authoritative close: the TradingView weekly bar close on the primary exchange feed (e.g. NASDAQ:MSFT) at Friday's New York close.** Rationale: yfinance serves dividend-adjusted history — the source of the ~$5 weekly-200-SMA divergence seen on MSFT in July; TV default feed is unadjusted.
- **Break rule:** Friday weekly close < the active weekly-200-SMA → reduce the position 50%, routed **the following Monday in the first 30 minutes of regular trading (09:30–10:00 ET)**. ⚠ Rule is written in ET on purpose: both external reviewers stated it in UTC and both got the season wrong (Gemini's 15:30 UTC = 11:30 ET summer; Manus's "corrected" 14:30 UTC = 10:30 ET summer). ET is DST-proof.
- **Catastrophic-gap exception:** if the underlying gaps >5% beyond the SMA over the weekend, do NOT market-order the open; defer to the next session's Phase-1 pricing pass and work limits at the adjusted mid once early IV expansion cools.
- **Strength rule (RETAINED): trim-into-bounce.** MSFT close ≥ 395 (alert `baa3bc98`) → trim. The only mechanism that de-risks into strength — never delete it.
- **In force for MSFT:** Fri close < ~383 (wk-200) → cut the 310/450 vertical 50% Monday 09:30–10:00 ET. ⏳ housekeeping: delete daily-close alerts `f9be085a` (382) and `de612a78` (375) — superseded.

## G. LEAP salvage doctrine (NEW — from the 07-07 MSFT execution)

For each underwater LEAP unit (LEAP + its short call), classify then act:
- **Healthy leg** (recovery odds ≥ ~40%, technicals hold): **convert to an expiry-matched vertical** — BTC the mismatched short, STO a same-expiry higher strike for net credit. Buys: lower package breakeven, duration match, credit. (MSFT 310C → Jan'28 310/450 @ +$21.35 cr, breakeven ~$369.)
- **Weak leg** (recovery odds ≤ ~35%, technicals broken): **accelerated exit** — sell the LEAP + BTC its short. Sunk cost is irrelevant (Box 3). (MSFT 340C unit exited @ +$70.18 combo, −$1,979 realized, ~$7k freed.)
- Execution rule: always structure as COMBOS; never sell new shorts without closing existing ones first (naked-upside trap — caught live twice on 07-07: reviewer's blanket advice + TWS Roll Builder pre-filling qty 2).
- **AMZN salvage ticket (Gemini Q1 hybrid, LIVE-VERIFIED 07-07 ~18:05 UTC — PENDING OPERATOR GO):**
  - Ticket 1: BTC 1× AMZN Oct16'26 280C + STO 1× AMZN Jan21'28 280C — combo **~$33.10 CREDIT** (mids 41.675 − 8.575) → Unit 1 becomes **Jan'28 200/280 vertical**, package outlay ≈ 81.82+1.59−41.68 = $41.7 vs max 80, breakeven ~$242 (below spot).
  - Ticket 2: STO 1× AMZN Jan21'28 300C — **~$35.50 CREDIT** → Unit 2 becomes **Jan'28 200/300 vertical**, package outlay ≈ $46.3 vs max 100, breakeven ~$246 (≈spot).
  - **Verified deltas (BS at live IV, not Gemini's estimates): 280C Δ0.545, 300C Δ0.489** → post-restructure AMZN β-DD ≈ 0.542 × 100 × 245.5 = **~$13.3k = 19% of NLV** (Gemini's 14.7% used overstated deltas; conclusion unchanged, magnitude corrected). ~$6.9k premium harvested. Invalidation: skip if AMZN < $241 before routing; re-mid at execution.
  - ⚠ Portfolio-level consequence: removes ~72 raw AMZN deltas → book β-Δ moves ~−87 → ~−130 (firmly short-beta). Acceptable ONLY as a pre-CPI package deal: harvested premium goes to VWCE seeds and the hedge band re-bases at Aug 21; if CPI clears benign, restoring engine delta (post-crush entries) becomes priority #1.
- **AAPL: NO trade** — soft-gate frozen at 33% per §C (healthy uptrend; expansion barred, reduction only via strength-rung / weekly break).

## H. Pacing — dynamic (replaces flat 5/week, v3.9 §4)

| Regime | Max new entries/week |
|---|---|
| VIX < 18 | 2 |
| 18 ≤ VIX ≤ 25 | 3 |
| VIX > 25 | 5 |

Rolls, closes, and hedge maintenance do not count. ⏳ backend: `entries_per_week_max` becomes regime-derived (config keys exist; wiring is a backlog item — until then, enforce manually).

## I. Measurement — compliance over P&L until n≥30 (NEW, extends v3.9 §15)

- The outcomes store (n=7, known bias: 5 unrecorded wins/closes, documented `e7e737c8`) **must not drive rule changes**.
- Until **n ≥ 30 fully-logged trades**: assume published base rates (0.15–0.20Δ PCS ≈ 70–80% win rate); score each trade on **entry-gate compliance** (gates passed at entry = success, regardless of P&L); log EVERY close same-session (CLOSE protocol). The 10-field checklist lives in `REVIEW_REQUEST_2026-07-08.md` Q7 and Manus v6 Part V; note per Gemini: `cap_pacing` checks the XSP engine margin ceiling (≤$30k) for index entries, and the 30% per-ticker β-DD soft gate for single-name entries.
- No strategy-rule changes justified by short-term P&L in the interim.

## J. Operator cadence — 2–3 sessions/week (NEW constraint, affects everything)

Standing consequences: base book minimum 45–60 DTE (no short-dated gamma); PMCC shorts written 60+ days out; de-risk rules keyed to WEEKLY closes; alerts must be close-confirmed (wick-immune); trade sessions follow WORKFLOW §Trade Session Procedure (validated end-to-end 07-07, twice).

## K. Executed 07-07 under this update (for the reviewer's decision log)

GOOGL LEAP trim −$84 (cluster 97.3→82.1) · SPY hedge tranche 2 4× Sep 745/700 @ 9.53 · MSFT Unit-1 conversion → Jan'28 310/450 vertical (+$21.35 cr) · MSFT Unit-2 exit (+$70.18 combo, −$1,979 realized) · **cluster 97.3% → 69.5% in one day** · hedge tranche 3 cancelled · XSP + 14 tier2 names added to universe · trader_profile aligned (income_seeker) · ~$9.1k cash freed earmarked: seed 1+2 VWCE.

## Open items (⏳)

1. VWCE seed 1 order (~$5.5k USD→EUR→VWCE) — next session, Euronext hours.
2. AMZN salvage analysis — next session.
3. Backend wiring: matched-vertical roll-flag exemption · weekly-close alert type · regime-derived pacing · β-DD per-ticker in the briefing.
4. Manus v6 proposal — incorporates this doc; corrections list already delivered (no margin debt; hedge decay footnote).
5. B-2 re-run at Aug 21 expiry.
