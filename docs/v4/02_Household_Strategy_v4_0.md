# Household Portfolio Strategy — v4.0 (Two-Leaf)

**Version 4.0 · Status: LIVING (separate strategy) · 2026-07-09**

> **This does NOT supersede `01_Portfolio_Strategy_v3_11.md`.** It sits *above* it. v3.11 remains the canonical execution rulebook for the IBKR options engine — now read as the **Leaf B engine rules**. v4.0 is the **household-level** strategy: it governs capital allocation across two leaves (eToro + IBKR) and re-mandates Leaf B from *premium income* to *responsible growth*. Where the two documents differ, the rule is explicit: **v4.0 sets the mandate and household risk caps; v3.11 still governs how individual Leaf-B trades are constructed, priced, rolled, and stopped.** See §7 for the full difference map.
>
> Advisory, not automated (same governance as v3.11 §1). Not personalized investment advice. Source-of-truth hierarchy: this document (household) > v3.11 (engine) > tool behavior > memory.

---

## 1. Architecture — two leaves, one household

| Leaf | Account | Contents | Management | Hedge |
|---|---|---|---|---|
| **A — Growth-Beta** | eToro | Copy of Jeppe Kirk Bonde (61 long-only positions) | **Not managed.** Levers = allocation size + periodic review of the copied trader. | **Self-hedged by the copied trader.** You never hedge Leaf A. |
| **B — Responsible Growth** | IBKR / Fortress | LEAP/equity growth core, optional income, tail hedge | Full Fortress workflow (v3.11 mechanics) under the v4.0 mandate | Tail hedge only (§5) |

Household ≈ €85k as of 2026-07-09 (IBKR €60.4k / 71% · eToro €25.0k / 29%). **Rule:** measure concentration, sector and factor exposure on the *combined* book; **act only on Leaf B.** Leaf B exists to *complement* Leaf A, never to duplicate it.

---

## 2. Why v4.0 exists (evidence)

- Every Leaf-B long (AAPL, GOOGL, AMZN, MSFT, NVDA) is **also** held in eToro — the leaves stack the same factor rather than diversifying.
- The household is **~57% big-tech / AI / chips** (semis alone ~15%), most of it outside your control in Leaf A.
- The old Leaf-B income mandate underperformed structurally: covered/PMCC caps throttled the same names eToro let run; the SPY overlay dragged; a single-name blow-up (OST −$4.5k) plus salvage churn produced an 11% win rate and −$272 expectancy over 9 closed trades. Premium-selling into a trending, high-IV tape was the wrong tool.
- Conclusion: stop running a *second, capped, correlated tech book*. Let Leaf A be the uncapped beta engine; repurpose Leaf B for diversified growth.

---

## 3. Leaf B mandate — Responsible Growth (any sector)

**Objective:** capital appreciation via a diversified long core (LEAPs as stock replacements, plus outright equity), across sectors the household lacks.

### 3.1 Staged uncap protocol
Remove short-call caps **gradually and conditionally**. Stage ladder (coverage on a given LEAP): `Stage 0 = 100% → Stage 1 = 50% → Stage 2 = 25% → Stage 3 = uncapped`.

**Advance one stage only when ALL gates are green:** (1) name < 15% of household net liq; (2) cash buffers ≥ floors (excess-liq ≥ $25k, available-funds ≥ $17k — carried from v3.11 §7); (3) regime not bearish; (4) name above its weekly-200 SMA (the v3.11 §8 thesis stop, reused as the trend gate).

**De-stage (add coverage back) if ANY:** regime → bearish · weekly close < 200-SMA · position/leaf drawdown > 10%. Keep coverage on laggards and low-conviction names — uncapping is earned by conviction + trend.

### 3.2 Diversification framework ("any ticker, responsibly")
- **Single-name cap:** 15% household (hard 20%). *AAPL 15.5% → trim.*
- **Sector cap (Leaf B):** 25% GICS. *Leaf B currently 41.6% Technology.*
- **Big-tech / AI / chips group cap (household):** 35%. *Currently ~57% → the gap to close.*
- **Build into what the household lacks:** healthcare, energy, financials, industrials, consumer staples/defensives, materials, utilities, international.
- **Names stay rules-based, not tip-based:** screen with `get_candidates` + TradingView scanner, gate with `get_technical_gate` (above 200-SMA), verify earnings with `get_earnings_history`, confirm liquidity with `check_liquidity`.

### 3.3 Position construction
Core: long LEAP Δ0.70–0.85 as stock replacement, staged-uncapped per 3.1. Sizing: new positions **5–8% of net liq, scaled in over 2–3 tranches** (the OST lesson). Premium selling: demoted from primary to opportunistic — never such that it caps a Stage-3 conviction name.

---

## 4. Concentration remediation (sequenced)
1. **Trim AAPL** 21.5% Leaf B (15.5% household) → ≤15% household. It's the only name over both the 15% household cap and v3.11's 40% β-DD hard backstop (44.6%, frozen).
2. **Reduce the semiconductor overlap** (NVDA + MU + TSM + ASML×2 + Samsung ≈ 15% household). Trim NVDA in Leaf B (the controllable side) → household semis < 12%.
3. **Resolve the OST stub** (−$4.5k, 0.1%).
4. **Redeploy freed capital** into the non-tech diversifiers (see `Combined_Portfolio.xlsx` → Candidates tab), staged per 3.3.

---

## 5. Hedge posture — tail hedge only
Retire the delta-neutralizing SPY overlay (it currently pushes Leaf B net short: portfolio delta −64, beta-weighted −185). Replace with a cheap far-OTM crash hedge: SPY/SPX puts ~15–25% OTM, 3–6 months, rolled quarterly, budget ~**0.75% of net liq / quarter**. **No day-to-day delta hedging** — primary risk controls are cash buffers + position sizing + the 200-SMA/stop rules. This *replaces* the v3.11 §7 B-2 formula for Leaf B.

---

## 6. Governance & cadence
- **Weekly:** household concentration & sector caps · Leaf-B stage status · delta/cash floors · quick eToro copy check.
- **Monthly:** return + expectancy per leaf; confirm the leaves are diverging, not converging.
- **Regime-linked:** in bearish regime, prioritize trimming + tail hedge, defer new uncapping, deploy diversifiers slowly.
- **What NOT to do:** don't hedge Leaf A · don't add big-tech/AI/chips in Leaf B while the household group > 35% · don't run premium-selling as the core strategy in a trending/high-IV regime · don't enter a name in a single fill · no name > 20% household.

---

## 7. Differences from v3.11 — the map

| Dimension | v3.11 (Leaf-B engine / income) | v4.0 (household / growth) |
|---|---|---|
| **Objective** | Premium income + capital preservation | Household capital appreciation |
| **Scope** | IBKR only, two buckets (A VWCE / B engine) | Household: eToro (Leaf A) + IBKR (Leaf B) |
| **Primary strategy** | Hybrid XSP put spreads / income book | Diversified long LEAP/equity growth; premium-selling opportunistic only |
| **Short-call coverage** | Strict 1:1 PMCC, never uncovered | Staged uncap ladder (100→50→25→0) on conviction + trend |
| **Hedge** | B-2: SPY bear-put-spread payout = 25–33% of engine β-DD | Tail hedge only (far-OTM crash puts, ~0.75% NLV/qtr); no delta-neutral overlay |
| **Concentration metric** | per-ticker β-DD, soft 30% / hard 40% of NLV | Household single-name 15% (hard 20%), sector 25%, AI/tech/chips 35% |
| **Universe** | tech-heavy tier1/tier2 | widened to non-tech diversifiers |
| **eToro** | out of scope | Leaf A — self-hedged, constituents unmanaged |
| **Measurement** | compliance-over-P&L until n ≥ 30 | per-leaf return + household concentration + stage tracking |

**Carried over from v3.11 unchanged** (still binding on every Leaf-B trade): earnings discipline (§5) · liquidity filters / `check_liquidity` short-leg grading · the weekly-close 200-SMA thesis stop (§8 — now doubles as the v4.0 trend/de-stage gate) · cash floors $25k / $17k (§7) · advisory "signaling not blocking" governance (§1, §13) · source-of-truth hierarchy · roll mechanics / naked-upside trap protection when a short *is* written.

**Note on Bucket A (VWCE).** v3.11's 20%-NLV all-world core is compatible with v4.0 and can remain as Leaf B's own ballast — it already diversifies away from the tech stack. Treat it as a Leaf-B holding that counts toward household sector caps.

---

## 8. Change Log
- **v4.0 (Jul 9, 2026):** two-leaf household architecture; Leaf B re-mandated income → responsible growth; staged uncap ladder; tail-hedge-only (retires B-2 for Leaf B); household concentration caps (15/25/35); widened non-tech universe; eToro added as self-hedged Leaf A. Companion artifacts: `Combined_Portfolio.xlsx` (exposure + candidates), `PROPOSAL_Two_Leaf_Dashboard_and_Docs_2026-07-09.md`. Does not supersede v3.11 — coexists as the household overlay.

— End of document —
