# External AI Review Brief — Fortress Portfolio Strategy
**Prepared 2026-07-07 · Self-contained: no access to our systems is needed or assumed. Reviewer: challenge everything; we want the strongest counter-arguments, not validation. Where you disagree, propose a concrete alternative with sizing/mechanics, not just a critique.**

---

## 1. Who and what this is

Retail account, Interactive Brokers, single margin account, base currency EUR, resident in the Netherlands (Box 3 wealth tax: deemed-return regime — realized vs unrealized gains are taxed identically, so turnover is tax-neutral; reform toward actual-return taxation expected ~2028). One operator, assisted by an AI copilot with live data tooling (IBKR real-time, options analytics, GEX/dark-pool/order-flow data, TradingView). Execution is manual in IBKR Desktop.

**Owner's objective (stated 07-07): "big profits in a reliable way."** We interpret this as: maximize expectancy subject to a hard reliability constraint — **max acceptable drawdown −20% from current $70k (floor ≈ $56k)**. New capital: occasional, not plannable. **Time budget: 2–3 sessions/week** (note: several current mechanisms assume near-daily attention — flag anything that breaks at this cadence).

## 2. Account snapshot (live 2026-07-07)

- Net liq **$70.1k** (≈€61.3k) · available funds $36.4k · excess liquidity $39.3k (self-imposed floors: $17k / $25k)
- Greeks: β-weighted Δ **−71** (temporarily net short beta after today's pre-CPI hedge+trim; policy target +0.25–0.35 β-Δ), Θ −57/day, vega +914 (β-vega +835 net long — mostly SPY puts + LEAPs, i.e. protective)
- Concentration (market value / NLV): MSFT 23.2%, AMZN 20.9%, AAPL 19.2%, SPY 13.3%, GOOGL 10.9%, NVDA 7.9% · **Mag-7 cluster 82.1%** vs a 60% policy cap (was 97.3% this morning; a GOOGL LEAP was sold today)
- SPY hedge: $9.3k market value of bear put spreads vs a $20–30k policy floor (under-hedged; being rebuilt in tranches pre-CPI Jul 14)
- Drawdown context: ≈ **−$21k from peak**, attributed ~100% to long mega-cap tech LEAPs bought near highs + one dead micro-cap ($4.5k→$75); the option-income side has been net positive

## 3. Current book (07-07, complete)

**Long LEAPs (all Jan 2028 calls):** MSFT 310C + 340C (basis $115.0/$124.0) · AAPL 240C + 290C ($85.4/$49.9) · GOOGL 310C ×1 ($109.6) · AMZN 200C ×2 ($81.8) · NVDA 170C ($85.6). Spots: MSFT ~394, AAPL ~314, GOOGL ~369, AMZN ~243, NVDA ~194.
**Short calls against them (PMCC):** MSFT Jan'27 410C ×2 (Δ0.52) · AAPL Jan'27 340C ×2 (Δ0.42) · GOOGL Jan'27 390C ×1 (Δ0.50) · AMZN Oct'26 280C (Δ0.29) · NVDA Aug'26 220C (Δ0.22). Plus one long MSFT Aug'26 465C (residual).
**Income:** AMD Jul31 450/430 put credit spread (only single-name PCS left).
**Hedge:** SPY bear put spreads — 8× Sep18 745/700, 5× Aug21 710/665, 1× Sep18 745/650.
**Dead:** 44 sh OST (~$75, ignored by policy).

Recovery-to-basis odds we computed (Black-Scholes at current IVs, ~18mo): AAPL ~45–55%, MSFT 310C ~40–50%, GOOGL ~35–45%, AMZN ~35–45%, MSFT 340C ~30–40%, NVDA ~25–35% — and short calls cap the payoff even when recovery happens. MSFT is the technically broken name (below its daily 200-SMA ~443, monthly downtrend, ~2.6% above its weekly 200-SMA "thesis stop" at ~383).

## 4. Strategy summary (v3.9 + the v3.11 amendment adopted today)

**Core engine:** sell option premium on liquid US underlyings — PMCC short calls against the LEAPs, put credit spreads, occasional CSP/covered call/collar. Entry gates: IV rank ≥25 (dual-source verified), IV−HV spread (variance-risk premium ≥3pp preferred), earnings blackout, ex-div assignment check, macro-event defer window (CPI/FOMC ±2d), VIX term structure (contango required for full size), weekly-200-SMA trend gate (no bullish premium below it), max 5 new entries/week, per-name cap 20% of NLV, Mag-7 cluster cap 60% (currently violated legacy — glide path in force), short-leg delta bands (PMCC 0.20–0.30, PCS 0.15–0.20). Management: roll at short-leg Δ>0.40 or ≤21 DTE; take profit at 50%; stop framework keyed to 200-SMA breaks and delta breaches; close-confirmed (daily-close) alerts to avoid intraday-wick false fires. Portfolio target β-Δ +0.25–0.35, θ positive, SPY put-spread hedge floor $20–30k.

**v3.11 amendment (adopted 07-07):**
- **Bucket A (20% of NLV target, ~$14k):** accumulating UCITS world ETF (VWCE) inside the same account; seeded $5.5k now + $5.5k post-CPI; grown further from trim proceeds. Purpose: structural de-concentration and reliability (no management, no expiry, no venue/session risk).
- **Bucket B (the engine, remainder):** income book goes **hybrid** — base = XSP (mini-SPX, cash-settled European) put credit spreads/condors, 2–3 laddered expiries; single-name premium selling restricted to **≤2 concurrent names, post-earnings IV-crush entries only** (pre-earnings single-name selling discontinued after a near-miss: a name we had a put spread on fell −20% this month right through where the strikes had been).
- Open design question (B-2): re-derive the SPY hedge floor as a function of Bucket B's beta-notional instead of the fixed $20–30k.

## 5. Performance record (honest version)

Closed-trade outcomes store is young (**n=6**): SPY hedge roll +$1,724 · MSFT LEAP trim −$1,385 (concentration de-risk) · MSFT BPS −$241 (closed pre-assignment) · META PCS −$235 (delta-breach stop pre-earnings) · NVDA PCS −$65 (21-DTE/CPI de-gamma) · GOOGL LEAP trim −$84 (breakeven-quality de-risk). **Known gap: three profitable-or-unknown PCS closes (ARM ×4, MU, V) and two June wins (V +$272, AMD +$131) were closed manually and never recorded; fill data is unrecoverable.** So the store under-represents income wins and over-represents de-risking losses — treat its −$202 total and 17% win rate as unusable for expectancy; the prose journal (~40 entries) is the better record. This measurement problem is itself a review topic (Q7).

## 6. Constraints the reviewer must respect

US-domiciled ETFs are inaccessible (EU PRIIPs) — UCITS wrappers only for Bucket A. Options must stay on US exchanges (EU single-name options too illiquid; our data tooling is US-only). One IBKR session per username (desktop execution kills the data gateway during trade placement — workflow already handles this). No shorting stock; no naked short options (margin discipline); manual execution only, orders worked at the mid. Operator time: 2–3 sessions/week going forward.

## 7. Questions for the reviewer (answer these specifically)

1. **Bucket split:** Is 20% VWCE enough to change outcomes, or symbolic? Given the −20% DD constraint and "big but reliable profits," what allocation between (a) unlevered core, (b) defined-risk index premium, (c) single-name/LEAP risk would you run on $70k, and why?
2. **LEAP salvage:** Given the recovery odds in §3 and capped upside from the short calls, what maximizes recovery per unit of risk: (a) current plan — trim on strength rungs, keep writing calls; (b) convert LEAPs to call verticals (sell a higher long call) to cut theta/vega and lock partial value; (c) roll LEAPs down-and-out; (d) accelerate exits and redeploy into the income engine? Rank them, show the math on one example (MSFT 310C basis $115, mark ~$125, spot 394).
3. **Premium regime timing:** With VIX ~16, index IVR modest, term in contango — is selling XSP premium now positive-expectancy after costs, or should the base book wait for IVR/VRP thresholds? Propose concrete entry thresholds (IVR, VRP in vol points, term-structure ratio).
4. **Hedge design (B-2):** Propose a formula for hedge sizing as f(Bucket B beta-dollar-delta), a maximum annual hedge budget as % of NLV, and structure (put spreads vs put ratio vs VIX calls vs collar-on-LEAPs). Our current hedge is ~13% of NLV in put-spread MV with a $20–30k fixed floor — critique it.
5. **Roll doctrine:** Policy says broken/concentrated names roll same-strike out for credit (accepting that delta RISES), healthy names roll up-and-out for small debit. The same-strike out-rolls left two short calls at Δ~0.50 flagged "act" indefinitely. Validate or replace this doctrine.
6. **De-risk ladder:** MSFT exit is gated by a 3-rung daily-close alert ladder (close<382 break / close<375 deeper / close>395 strength). Is this over-engineered vs a single weekly-close rule? Does it fit a 2–3-session/week operator?
7. **Measurement with tiny n:** With n=6 (biased, see §5), how should we make go/no-go strategy decisions? Suggest a practical framework (priors from published PCS/PMCC base rates, per-trade checklists vs outcome stats, minimum n before changing rules).
8. **Concentration metric:** We measure concentration as position market value / NLV. For an options book this is distorted (a deep-ITM LEAP's MV understates exposure; spreads net to ~0). Should the caps run on beta-dollar-delta share instead? Propose the metric and the cap level.
9. **Pacing:** Max 5 new entries/week is a flat cap. Should pacing scale with regime (VIX, term structure) and account cushion? Propose a rule.
10. **Cadence risk:** Which current mechanisms silently assume daily attention, and how would you harden the strategy for a 2–3-session/week operator (alert design, defensive defaults, position types to avoid)?

## 8. What NOT to bother with

Infrastructure/tooling critique (gateway, scanners, dashboards) — out of scope. Tax optimization beyond the Box 3 facts stated. Crypto, futures, FX trading — not in mandate. Suggestions requiring >5 h/week of operator time.

---
*Companion docs exist for every § (strategy spec v3.9, recovery plan 06-26, two-bucket amendment 07-07) but this brief is intentionally self-sufficient. Numbers verified live 2026-07-07 ~17:00 UTC.*
