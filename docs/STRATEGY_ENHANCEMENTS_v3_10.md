# Fortress — Strategy Enhancements v3.10 (research-codified)
**2026-06-22 · addendum to `01_Portfolio_Strategy_v3_9.md` · research basis: `IMPROVEMENT_RESEARCH_2026-06-22.md`**

> Not financial advice. These are the governing rules + parameters distilled from the
> 2026-06-22 best-practice scan, mapped to Fortress config and implementation status.
> Behaviour-changing values are **codified but NOT applied live** until you confirm /
> backtest against the trade-outcomes store (`journal_analytics.py`).

Every rule below has: **what** · **why (source)** · **parameter** (`cfg` key) · **status**.

---

## 1. Exit discipline — manage winners earlier (defined-risk)
- **What:** close defined-risk credit spreads (PCS / verticals) at ~**50% of max profit**, not 80%.
- **Why:** tastytrade's 4,000+ SPY-PCS study — managing at 50% beat holding to expiry on
  risk-adjusted/annualized returns; the last leg of profit carries disproportionate gamma
  risk for little remaining theta.
- **Parameter:** `strategy.profit_target_pct` (live = **80**, unchanged) · researched default
  recorded as `strategy.profit_target_pct_recommended = 50`.
- **Status:** 🟡 **codified, NOT applied** — flip `profit_target_pct` to 50–60 only after a
  backtest. LEAPS legs keep their own `leaps_profit_take_pct`.

## 2. Time discipline — 21-DTE management
- **What:** close/roll **profitable** short legs by ~21 DTE, not just delta-breached ones.
- **Why:** the final 21 days hold outsized gamma vs remaining theta (tastytrade).
- **Parameter:** `strategy.dte_roll_threshold = 21` (already drives roll alerts).
- **Status:** 🟢 mostly in place — **verify** the 21-DTE trigger also prompts closing winners,
  not only flagging Δ-breaches (Sprint 19 check).

## 3. Entry edge — gate on the variance risk premium (VRP), not IVR alone
- **What:** require a real **IV − realized-vol** edge before selling, on top of IVR ≥ 25.
- **Why:** the edge is the VRP (implied minus realized); "IV 30% is not rich if RV is 28%."
- **Parameter:** `strategy.vrp_good_spread_pp = 5`, `vrp_fair_spread_pp = 0`,
  `vrp_min_entry_pp = 3` (IV − HV20, percentage points). The candidate scanner already
  computes IV − HV20 and embeds the 5/0 thresholds in its signal.
- **Status:** ✅ **LIVE (2026-06-23, Sprint 19.3):** scanner `classify_signal` reads
  `cfg("strategy.vrp_good/fair_spread_pp")`; `pre_trade_check.advisories.vrp` flags amber when
  IV−HV < `vrp_min_entry_pp` (soft-fails to `unknown` when no fresh scan). 16-delta ≈ the 1SD
  expected-move boundary — strike-selection proxy (expected-move bands = Sprint 19.5).

## 4. PMCC guardrails
- **What (a):** never sell a PMCC short call with **strike < long-leg breakeven** (long
  strike + net debit) — it locks a guaranteed loss at expiry.
- **What (b):** roll the **long LEAP early** — at ~0.70 delta or ≤120 DTE — into a new
  12–18-month LEAP, to preserve position integrity and limit decay.
- **What (c):** always close the short call before the underlying's earnings (already done).
- **Why:** standard PMCC failure modes (decay on a too-short LEAP; spread collapse on a gap;
  guaranteed-loss short strikes).
- **Parameters:** `strategy.pmcc_short_above_breakeven = True` (advisory),
  `strategy.leap_roll_delta = 0.70`, `strategy.leap_roll_dte = 120`.
- **Status:** ✅ **breakeven guardrail LIVE (2026-06-23, 19.4a):** `/api/options/pmcc-breakeven`
  (short strike must clear long breakeven, else GUARANTEED-LOSS). 🔴 LEAP-roll-delta alert (19.4b)
  deferred — needs per-leg greeks not exposed in the aggregated position rows.

## 5. Tail hedge — keep selective; prefer a put spread; size off vega
- **What:** keep hedging **catalyst-timed** (not continuous); consider a **put spread** or a
  short-call-funded **collar** over naked long puts; size the hedge against **β-vega**.
- **Why:** continuous puts cost ~2–5%/yr in decay — selective hedging ~halves that; a
  premium-selling book's worst day is a **vol spike** (short vega), not just a price drop.
- **Parameters:** existing `spy_hedge_*` band + catalyst gate; new `beta_vega_target` (B1).
- **Status:** 🟢 selective hedging + SPY hedge already in place; 🟡 vega-based sizing pending B1.

## 6. Risk visibility — β-weighted vega (the missing dial)
- **What:** a portfolio **β-weighted vega** number = expected P&L per 1-pt move in SPY IV.
- **Why:** you are net-short-vega and concentrated in high-beta tech; an IV spike is the
  un-instrumented risk. β-vega also sizes the SPY hedge.
- **Parameter:** `strategy.beta_vega_target` (0 = informational until shipped).
- **Status:** 🔴 **build (Sprint 19 B1)** — highest-leverage new metric.

## 7. Risk visibility — correlated-cluster concentration
- **What:** track the **summed exposure of the correlated mega-cap cluster**, not just
  per-name/sector caps. MSFT/AAPL/GOOGL/AMZN/NVDA (+META/AVGO/TSLA) move together.
- **Why:** effective concentration ≫ any single 20–27% name when the book is one cluster.
- **Parameter:** `strategy.mag7_cluster` (list), `strategy.cluster_concentration_warn_pct = 60`.
- **Status:** ✅ **LIVE (2026-06-23, Sprint 19.2)** in `get_briefing.concentration.cluster`
  (members + summed % + warn flag). Live read: cluster **74.3%** of NLV vs 25% top single-name.
  Parapet Briefing chip = small follow-up.

## 8. Capital efficiency — systematic LEAP call-writing + income diversification (Sprint 25.9)
- **What (a) — monetize dead LEAP capital:** write **monthly ~0.30Δ, 30–45 DTE covered calls**
  on the naked / under-written long-LEAP cores, turning idle capital into income. Target the
  positions the capital-efficiency page flags **⚠ MONETIZE** (long/LEAP capital earning **< 0.50×**):
  currently **GOOGL (0.25×)** and **AMZN (0.15×)** — ~$38k of capital earning ~$8k/yr. Use the
  Sprint 21.1b **adaptive short-call-delta** engine to pick the strike (it already snaps to ~0.30Δ,
  nudged by IVR / trend / resistance / concentration), and honor the §4 PMCC guardrails
  (short strike above the long-leg breakeven; close before earnings).
- **What (b) — diversify the income sleeve OUT of the Mag-7 cluster:** the book is ~96% correlated
  mega-cap tech (see §7). Route **new premium-selling into non-tech names** so income isn't one
  cluster. Screened + added to the universe (Sprint 25.9 / backlog 23.4): **JPM** (financials,
  IVR 72, above all weekly MAs) + **JNJ** (healthcare, IVR 90, clean weekly uptrend). Trend-gated
  adds on a weekly-200 reclaim: XOM / CVX / COST / WMT.
- **Why:** the −$21.3k drawdown is 100% long mega-cap tech LEAPs; the income engine is green.
  Recover **via the engine** — monetize the dead LEAP capital and spread the income to
  uncorrelated names — not by adding more beta. Directly serves the cluster-glide (91% → ≤60%).
- **Parameters:** reuses `strategy.short_call_base_delta` (0.30) + the adaptive weights (21.1b);
  universe `tier1` now includes JPM/JNJ. Efficiency benchmark `0.12` (12%/yr); MONETIZE flag < 0.50×.
- **Status:** 🟡 **codified + universe seeded (2026-07-03).** JPM/JNJ live in the universe; the
  capital-efficiency page (25.7) surfaces the MONETIZE targets. 🔴 **remaining:** auto-surface the
  covered-call candidate per under-written LEAP in the candidate scanner (the full 23.3 build) —
  the strikes come free from the 21.1b engine; it just needs wiring into `get_candidates`.

---

## Status legend
🟢 in place / mostly in place · 🟡 codified (config/doc) but not yet wired/applied · 🔴 build pending

## Where this lives
- Parameters → `config_store.py` `strategy.*` (this addendum is the rationale of record).
- Build items → `BACKLOG_SPRINT_PLAN.md` **Sprint 19**.
- Research basis → `IMPROVEMENT_RESEARCH_2026-06-22.md` (with sources).
- When a 🟡/🔴 item ships or a value is adopted live, update its **Status** line here.
