# Fortress — Improvement Research (Parapet functionality + strategy/results)
**2026-06-22 · external best-practice scan mapped against current Fortress capabilities**

> Not financial advice. This is a research synthesis + a tooling/framework backlog. Each
> idea is grounded in (a) a published best practice and (b) a specific gap in the current
> system. Anything that changes trade behaviour should be backtested against your own
> trade-outcomes store before adopting. You make the calls.

## How to read this
Fortress already implements a large share of "best practice" (IV rank, GEX, vol skew, VIX
term structure, dark-pool floors, the catalyst/ex-div gates, the 5 pretrade gates,
SMA200 stop-loss, roll alerts at Δ>0.30 / DTE≤21, pacing, the trade-outcomes journal,
β-weighted **delta**, strategy ranking, forward P&L). The items below are the **genuine
gaps** the research surfaced — ranked by value/effort, quick wins first.

---

## A. Strategy / trading-results (research-backed)

### A1. Take profit on defined-risk credit spreads near ~50% of max — *quick win, config-only*
Your `strategy.profit_target_pct` is currently **80%**. tastytrade's study of 4,000+ SPY
put-credit-spread trades found **managing winners at ~50% of max profit** produced better
risk-adjusted/annualized returns than holding to expiration — because the last leg of
profit comes with disproportionate gamma risk for little remaining theta. Holding to 80%
keeps capital tied up and exposed precisely where the payoff is worst.
- **Action:** consider lowering the PCS/defined-risk profit target toward 50–60% (keep the
  LEAPS leg on its own `leaps_profit_take_pct`). One settings flip; backtest first against
  your closed-trade store via `journal_analytics.py`.

### A2. Gate entries on the variance-risk premium (IV − realized vol), not IVR alone — *low effort, data already exists*
The real premium-selling edge is the **variance risk premium**: the spread between implied
and *realized* vol — "IV at 30% sounds rich until you discover RV is 28%." Your candidate
scanner **already computes IV − HV20** (that *is* VRP); right now it only ranks on it.
- **Action:** promote IV−HV to an explicit (advisory) entry gate — e.g. require IV−HV20 >
  ~3–5pp **in addition to** IVR ≥ 25 (`ivr_min_entry`). Surfaces "rich IVR but no real
  edge" names (your scan already tagged several `IV_HIGH/HV_HIGH` today — those are exactly
  the ones to skip). Pairs naturally with the new IBKR-first IV.

### A3. Confirm 21-DTE is a *management* trigger, not just an alert — *verify*
The 21-DTE rule (final 21 days carry outsized gamma vs remaining theta) is best applied as
a **close/roll-winners** action. You have `dte_roll_threshold = 21` driving roll alerts —
verify it also prompts closing *profitable* shorts by ~21 DTE rather than only flagging
delta-breached ones.

### A4. PMCC guardrail: short-call strike must exceed LEAP strike + net debit — *medium*
A documented PMCC trap: selling a short call with **strike < LEAP strike + net debit paid**
locks in a guaranteed loss at expiry. Also: roll the LEAP at ~**0.70 delta** or **90–120
DTE** remaining to a new 12–18-month LEAP. You already close shorts before earnings (good).
- **Action:** add a PMCC-specific pretrade check (short strike > long-leg breakeven) and a
  LEAP-roll alert at 0.70Δ / ≤120 DTE.

### A5. Tail hedge — keep it selective; consider a put *spread* over naked puts — *validate*
Research: continuous protective puts cost ~2–5%/yr in decay, but **hedging only ahead of
identifiable catalysts cuts that ~in half** — which is exactly what your catalyst gate +
SPY hedge already do, so you're aligned. Two refinements: (1) a **put spread** (or a collar
funded by your existing short calls) trims the bleed vs naked long puts; (2) size the hedge
off **β-vega**, not just delta (see B1) — a premium-selling book's worst day is a vol spike,
not just a price drop.

---

## B. Parapet / dashboard functionality (the real gaps)

### B1. β-weighted **VEGA** panel — *highest-value dashboard gap*
You display β-weighted **delta** but not **vega**. You are a **net-short-vega** book
(selling PCS/calls across many names) concentrated in **high-beta tech** — your single
worst scenario is a market-wide IV spike, where short vega produces immediate
mark-to-market losses (the classic VIX-spike margin trap). A **β-weighted vega** number =
"how much do I lose if SPY-implied vol jumps 1 point" — the missing risk dial, and it
**directly sizes the SPY hedge**. You already compute portfolio vega + per-name betas, so
this is β-weighting data you have.
- **Build:** `get_portfolio_vega` (β-weighted) → Briefing stat + a hedge-coverage cross-check.

### B2. Correlation / "cluster" concentration — *high relevance to your specific book*
Your concentration view is single-name + sector, but MSFT/AAPL/GOOGL/AMZN/NVDA are **one
correlated cluster** (~70%+ of the book) that moves together — so your *effective*
concentration is far higher than any single 20–27% name. Research keeps flagging mega-cap
correlation as the hidden 2025/26 risk. A **correlation-weighted exposure** or a simple
"Mag-7 cluster %" metric surfaces what the per-name caps miss.
- **Build:** a correlation/cluster chip on Briefing (even a static beta/sector-cluster
  grouping is a useful first cut; full pairwise correlation later).

### B3. Expected-move bands on Candidates (16-delta ≈ 1SD) — *medium*
The 16-delta short strike ≈ the 1-standard-deviation expected move. You target Δ 0.25–0.35;
showing the **1SD expected-move band** (and where 16Δ sits) per candidate makes
strike-selection explicit and ties directly to the VRP edge. You already have earnings
implied-move; this generalizes it to non-earnings strike picks.

### B4. Payoff / what-if scenario slider on Positions — *medium, backend mostly exists*
You have `forward_pnl` + `scenario_estimate` on the backend. Surfacing an **interactive
payoff diagram** (price × IV × time sliders) on the Positions page turns those into a live
"what if SPY −5% and VIX +6" tool — high decision value, modest UI work.

---

## Suggested sequencing (a "Sprint 19" shape)
- **Quick wins (config / small):** A1 (50% profit target — backtest first), A2 (VRP gate),
  A3 (verify 21-DTE management).
- **High-value builds:** B1 (β-vega) and B2 (cluster concentration) — both speak directly to
  *your* concentrated, short-vega book and the SPY hedge sizing.
- **Then:** A4 (PMCC guardrail), B3 (expected-move bands), B4 (payoff slider), A5 (hedge
  refinement).

Net: the single highest-leverage idea is **B1 (β-vega)** — it's the one risk number a
concentrated premium-selling book is currently flying without. The single cheapest
win is **A1** (one settings change, well-supported by data).

---

## Sources
- Poor Man's Covered Call management / roll rules: [Sharpnel](https://www.sharpnel-trading.com/learn/poor-mans-covered-call/), [Days to Expiry](https://www.daystoexpiry.com/blog/poor-mans-covered-call), [TradeStation](https://www.tradestation.com/insights/2026/04/07/poor-mans-covered-call-strategy/)
- Manage winners at 50% / 21-DTE rule (tastytrade research): [Days to Expiry — 21 DTE](https://www.daystoexpiry.com/blog/the-21-dte-rule-explained-when-and-why-to-close-options-positions-early), [Days to Expiry — best DTE](https://www.daystoexpiry.com/blog/best-dte-for-credit-spreads-a-data-driven-comparison-of-30-45-and-60-day-trades), [tastytrade close-at-profit-%](https://support.tastytrade.com/support/s/solutions/articles/43000435423)
- Variance risk premium / IV vs realized / 16-delta = 1SD: [SharpeTwo](https://sharpetwo.com/blog/implied-volatility-options-trading/), [optionsJive](https://optionsjive.com/blog/implied-volatility-explained/), [Volatility Box — expected move](https://volatilitybox.com/research/expected-move-options/)
- Dashboard features (portfolio greeks, β-weighted vega, correlation, what-if): [TradesViz Options Command Center](https://www.tradesviz.com/blog/options-command-center/), [QuestDB — vega exposure](https://questdb.com/glossary/vega-exposure-in-options-portfolios/), [Option Alpha — beta weighting](https://optionalpha.com/blog/beta-weighting-bots-and-positions-portfolio-management)
- Vega-spike risk for premium sellers: [QuantStrategy — vega risk](https://quantstrategy.io/blog/vega-risk-management-hedging-against-sudden-shifts-in/), [Options Trading IQ — hedge vega](https://optionstradingiq.com/how-to-hedge-vega-risk/)
- Tail-risk hedging cost / selective hedging / put spreads & collars: [Global X — collars](https://www.globalxetfs.com/articles/options-collar-strategies-as-a-risk-management-tool), [Maverick — SPX hedging](https://mavericktrading.com/how-to-use-spx-options-for-market-hedging-and-portfolio-protection/), [HeyGoTrade — sizing hedge cost](https://www.heygotrade.com/en/blog/protective-put-portfolio-insurance-tail-risk-hedging/)
- Mega-cap concentration / correlation risk: [BlackRock — megacap exposure](https://www.blackrock.com/us/financial-professionals/insights/fine-tuning-megacaps-build-etfs), [CME Group — diversify vs tech giants](https://www.cmegroup.com/articles/2025/how-to-diversify-equities-portfolio.html), [Invesco — concentration](https://www.invesco.com/qqq-etf/en/market-outlook/navigating-market-concentration-wisely.html)
