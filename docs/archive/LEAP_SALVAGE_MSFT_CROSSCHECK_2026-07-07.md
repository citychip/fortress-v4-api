# MSFT LEAP Salvage — Live-Data Cross-Check of the External Review
**2026-07-07 ~17:15 UTC · Live IBKR quotes. Companion to `AI_REVIEW_BRIEF_2026-07-07.md` and the external reviewer's answers. Decision doc — nothing executed.**

## 1. Live quotes (source: ibkr, spreads 1–3.5%)

| Contract | Bid/Ask | Mid | Our basis | Position |
|---|---|---|---|---|
| MSFT Jan'28 310C | 125.90/127.30 | **126.60** | 114.96 | long ×1 (**+$11.6/sh unrealized**) |
| MSFT Jan'28 340C | — | ~107.98 (mark) | 123.98 | long ×1 (−$16.0/sh) |
| MSFT Jan'27 410C | 37.65/38.40 | **38.03** | 34.43 cr | short ×2 (−$3.6/sh) |
| MSFT Jan'28 450C | 58.50/60.60 | **59.55** | — | candidate short |

## 2. Errors found in the external review (live-data catches)

1. **It ignored the existing Jan'27 410C shorts ×2.** "Sell the Jan'28 450C against your 310C" as written would create 4 shorts vs 2 longs — a ratio short / naked upside, violating the no-naked rule. The executable form is a **roll**: BTC 410C → STO Jan'28 450C.
2. **"The 450C yields intrinsic premium" — wrong.** Spot 394 < strike 450: the $59.55 is 100% extrinsic. (Its price estimate of $40–50 was also low — the real mid is better for us, so the trade is *stronger* than it claimed.)
3. **"Your $9.3k hedge market win should be partly cashed" — wrong.** $9.3k is the current MV of premium we *paid* (~at cost); there is no gain to harvest.
4. **It flagged MSFT as the concentration offender; by its own proposed metric (β-dollar-delta), AMZN is worse.** Per-ticker net-delta dollars: **AMZN ≈ $31.2k (45% of NLV)** (2× Δ0.79 LEAPs, far-OTM short), MSFT ≈ $26.6k (38%), GOOGL ≈ $10.1k (14%). Any β-DD cap regime must start with AMZN, not only MSFT.
5. **Its Q4 hedge formula actually shows we may NOT be under-hedged.** Positive β-DD ex-hedge ≈ $217k; its 25–33% coverage rule → $54–72k of protection. Our hedge **max payout ≈ $68k** (8×$45-wide + 5×$45-wide + 1×$95-wide) — already inside the band. The "under-hedged" reading comes from the legacy fixed **MV** floor ($20–30k premium value), which measures premium spent, not protection carried. This confirms retiring the fixed floor (B-2) and likely means **tranche 3 is unnecessary** — a real cost saving.

## 3. The salvage math, executable form (per the reviewer's Method B/D, corrected)

**Proposed hybrid — treat the two LEAP units differently (strong asset ≠ weak asset):**

**Unit 1 (310C — the healthy leg, in profit):** convert to an expiry-matched vertical.
- BTC 1× Jan'27 410C @ ~38.03 · STO 1× Jan'28 450C @ ~59.55 → **net credit ~$21.5/sh (+$2,152)**
- Result: **Jan'28 310/450 bull call spread**. Package net outlay after all credits: 114.96 − 34.43 − 21.5 ≈ **$59.0** vs max value $140 (spot ≥450). **Package breakeven at expiry drops to spot ≈ $369** (vs ~$425 for the naked LEAP). Upside room extends 410→450 (+$4,000/unit potential). Calendar mismatch (Jan'27 short vs Jan'28 long) eliminated. New short Δ ≈ 0.50 — delta roughly unchanged; this trade buys breakeven, cap-room, duration-match, and credit, not delta relief.

**Unit 2 (340C — the weak leg, 30–40% recovery odds, worst breakeven):** accelerated exit.
- SELL 1× Jan'28 340C @ ~108 mid · BTC 1× Jan'27 410C @ ~38.03 → **frees ~$7,000 cash**, realizes ≈ −$1,960 (sunk cost; Box 3 = no tax effect)
- Rationale: paying theta for 18 months on a ~1-in-3 recovery, with capped payoff, fails the "reliable" constraint. The freed cash funds **Bucket A seed 2 (+$5.5k) immediately** instead of waiting for CPI-window timing on new cash.

**Combined effect:** MSFT reduced to one clean Jan'28 310/450 vertical · cash freed ≈ **$9.1k** · MSFT β-DD ≈ $12k (**17% of NLV** — under the reviewer's proposed 30% cap) · realized ≈ −$1,960 · the MSFT de-risk ladder simplifies to one rule on ONE remaining structure.

**Why not pure Method B on both (reviewer's rank #1):** converting the 340C to a 340/450 vertical leaves package breakeven ~$408 — MSFT must rally +4% just to get out flat, on the technically broken name. Converting winners and exiting losers beats converting everything.

**Why not pure Method D on both:** the 310C package at $59 net outlay with breakeven $369 (spot 394) is now a *positive-expectancy defined-risk position* — no longer the problem child. Keeping it preserves recovery participation with a floor under the thesis.

## 4. Verdicts on the reviewer's 10 answers

| Q | Its answer | Verdict |
|---|---|---|
| 1 | 40/40/20 buckets | Challenge accepted but Steven decided 20% today (Q4 revisit). NB: the salvage trades above *organically* shrink bucket C toward its number. Don't re-decide; let the glide do it. |
| 2 | Method B ranked #1 | **Directionally right, execution wrong** (missed the 410Cs). Adopt the corrected hybrid (§3). |
| 3 | XSP gates: VIX>20, VRP≥3.5pp, contango | Adopt VRP + contango; soften VIX to **index IVR-based** gate (a VIX-20 hard gate leaves the base book empty for quarters). |
| 4 | Hedge = 25–33% of β-DD, budget ≤5% NLV/yr | **Adopt as B-2.** Live check shows current payout already in band → skip tranche 3, redirect that cash. |
| 5 | Trash same-strike out-rolls | Half-adopt: correct for names we keep; the tight-cap roll remains correct *for names slated for exit* (the cap IS the hedge on the way out). Now largely moot post-§3. |
| 6 | One weekly-close rule replaces the ladder | Adopt for the break side (Fri close <383 → cut 50% Monday). **Keep the 395 strength-trim rung** — it's the trim-into-bounce lever, losing it only hurts. |
| 7 | Base rates + compliance score, no rule changes until n≥30 | **Adopt wholesale.** Best single answer in the review. |
| 8 | Per-ticker β-DD cap 30% NLV | Adopt the metric. First offender is **AMZN (45%)**, then MSFT (38% → 17% post-§3). AMZN needs the same treatment next. |
| 9 | Dynamic pacing by VIX bands | Adopt, inverted logic is right (low IV = trade less). |
| 10 | Min 45–60 DTE, longer PMCC shorts | Adopt for the XSP base book. NVDA Aug'26 220C (45 DTE) is acceptable; don't churn it. |

## 5. Its closing question: "Convert MSFT before CPI Jul 14?"

**Recommendation: yes, this week, in the §3 hybrid form** — both legs are credit/cash-positive, reduce risk, and are executable in two combo orders at the mid. Pre-CPI timing is favorable: IV is bid (36.6–38%), which is exactly when you want to be *selling* the 450C extrinsic. Gate: Steven's explicit go, then it enters the next trade-session order list via the standard Phase 1 pricing pass.

**Follow-up the reviewer missed: AMZN (β-DD 45% of NLV) gets the same analysis next session.**
