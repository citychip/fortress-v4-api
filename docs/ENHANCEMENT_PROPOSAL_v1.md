# Fortress Enhancement Proposal

**Version:** 1.0 (for review)
**Date:** 2026-07-02
**Author:** Claude (advisory) — for account-holder & AI review
**Scope:** Documentation updates, Fortress logic/frontend proposals, and a data-grounded strategy-optimization plan.
**How to use this doc:** each item is numbered and atomic — accept / reject / improve each independently. "Review prompts" at the end of each section are written so another AI (or you) can critique and refine. *Not investment advice.*

---

## 0. Two rules now adopted (from this session)

- **Watchlist = dynamic:** every ticker with an open position (any leg) **plus** any ticker added in Claude or Fortress (`add_universe_ticker`). Not a fixed list. *(Already folded into the Multi-Timeframe Procedure §7.2.)*
- **Data-source availability:** in an interactive Cowork session, **always tell the user first** if any source is unavailable or on fallback before presenting analysis. Scheduled tasks may use fallback but **must label it**. *(Folded into the Procedure §2.)*

---

## 1. Findings that drive this proposal (evidence)

Pulled live 2026-07-02 (IBKR `web_api`, authenticated):

**A. The premium environment is rich but being wasted.** IV-rank across the book: GOOGL 90.9, MSFT 77.6, AMZN 77.1, AAPL 67.0, NVDA 64.4, SPY 58.3. High IVR = good premium-selling conditions.

**B. Your LEAP names are capital-inefficient** (annualized income ÷ capital at risk): GOOGL **0.25×**, AMZN **0.15×**, AAPL 0.63×, MSFT 0.61× — vs SPY 2.9×, NVDA 2.2×. The big LEAPs tie up ~$76k and barely earn.

**C. Root cause is a Fortress bug (not just under-trading).** `get_strategy_metrics` PMCC/Diagonal outputs place the short call absurdly far OTM with **$0.00 estimated credit**:

| Ticker | Spot | PMCC short strike suggested | Est. credit |
|---|---|---|---|
| MSFT | $391 | **$780C** | $0.00 |
| GOOGL | $358 | **$715C** | $0.00 |
| AMZN | $244 | **$490C** | $0.00 |
| AAPL | $307 | **$615C** | $0.00 |
| NVDA | $193 | **$385C** | $0.00 |
| SPY | $742 | **$1485C** | $0.00 |

The engine is picking ~2× spot as the covered-call strike → zero income. This is *why* the real book's LEAPs earn almost nothing.

**D. `recommended=True` is not singular** — 4–5 strategies are all flagged "recommended" per name, defeating the purpose of a recommendation.

**E. Regime signals conflict:** per-name `market_intelligence` regime = **bullish**, portfolio macro overlay = **bearish**, SPY GEX regime = **negative**. No single labeled gate.

**F. Track record reflects the entry problem:** 4 closed trades, **25% win rate**, expectancy **−$34**; losses were spreads sold on names that then broke their 200-SMA. Several records note entry IVR/DTE/delta "not captured at open."

**G. Persona mismatch:** settings = *"Strategic Speculator, directional, aggressive, no hedge configured,"* but the live book is a *hedged PMCC/PCS income book*. The 20% single-name concentration cap is set but breached (GOOGL 26%, MSFT 22%).

---

## 2. Documentation review — what to update

| Document | Status | Proposed update |
|---|---|---|
| **Daily post-open briefing (SKILL.md)** | Good staleness guard already | Add the **Technical Gate** step (weekly+daily `get_chart_data`); add explicit **fallback labeling**; add optimization KPIs (capital-efficiency flag, cluster-glide, hedge coverage) to the standard output |
| **Strategy v3.9.0** | Directional persona | Re-baseline as **hedged premium-seller**; add the multi-timeframe layer, the **trend-filter entry gate**, the **collar overlay** for concentrated LEAPs, and a **manage-at-50%** option for the defined-risk sleeve |
| **Multi-Timeframe Procedure (new draft)** | Updated today (watchlist + data rule) | Fold in the optimization decisions once approved here; add per-name collar rules |
| **Prognosis report** | Current | Living doc; weekly column added; refresh on weekly close |

**Review prompt:** *Is any existing doc missing from this list? Should the Strategy doc be split into "Policy" (rarely changes) vs "Playbook" (tactical, changes weekly)?*

---

## 3. Fortress logic proposals

Ordered by impact. Each is independently adoptable.

1. **Fix covered-call / PMCC / Diagonal short-strike selection (highest priority).** Target a **configurable short-call delta (default ~0.30) at 30–45 DTE**, not a fixed multiple of spot. Add a sanity check: reject any income structure whose `estimated_credit == 0`. This single fix converts the LEAP book from dead-weight to income and repairs the 0.15–0.6× efficiencies.
2. **Make `recommended` singular.** One `best` per name (highest regime_score × yield, subject to gates); rename the others `eligible`. Prevents "everything is recommended."
3. **Unify the regime signal.** Reconcile `market_intelligence` (per-name), macro overlay, and GEX regime into one **labeled** gate, and show which one drives entry eligibility. Today bullish/bearish/negative coexist with no precedence.
4. **Add a trend-filter entry gate.** Do not mark a premium-selling structure "recommended/eligible" on a name trading **below its weekly 200-SMA** (the Thesis Stop). Directly targets the 25% win-rate problem. Requires ingesting weekly SMA (already available via `get_chart_data interval=1wk`).
5. **Enforce/surface concentration as a hard gate.** Block or warn on new entries that push a single name >20% or the Mag-7 cluster >60%, in candidate/entry logic — not just as a report metric.
6. **Auto-capture entry conditions** (IVR/DTE/short-delta) at open for every trade, so the expectancy loop (`get_trade_outcomes`) is complete.
7. **Align the settings persona** to a hedged premium-seller with the hedge module on, so greeks/sizing/signals match reality.
8. **Add β-weighted vega stat** (already backlog, Sprint 19.1) and a **vega-flip alert** (short→long vega), plus multi-timeframe technical fields in the payloads.

**Review prompt:** *Which of these are quick wins vs backend refactors? Is #1 a strike-selection config change or a deeper options-model fix? Any that conflict with existing v3.9.0 behavior?*

---

## 4. Fortress frontend proposals

1. **Data-source status banner** — web_api vs fallback, TradingView attached (y/n), last-sync age. Makes the availability rule visible at a glance.
2. **Multi-timeframe technical panel** — Monthly/Weekly/Daily/4h with the Thesis Stop (200-wk) line per name; ingest `get_chart_data` + TradingView.
3. **Capital-efficiency heatmap** — per-position efficiency (data already exists) to spotlight under-monetized LEAPs.
4. **Fixed strategy-comparison view** — single recommendation, with a credit≠0 sanity flag surfaced.
5. **Cluster-glide tracker** — current cluster % vs the 60% target with the glide path.
6. **Collar/overlay builder** — one-click structure to sell a call + buy a put against a held LEAP.
7. **Dynamic watchlist** — reflect "positions + user additions" in the UI.

**Review prompt:** *Which panels are highest value for daily use? Should the status banner also gate write actions when on fallback?*

---

## 5. Strategy-optimization plan (grounded)

Goal: **more profit AND more reliability.** Levers, with the evidence behind each.

**Reliability first**

- **Trend-gate entries** (logic #4): stop selling premium on names below their weekly 200-SMA — the direct fix for the 25% win rate.
- **Collar the two weakest-efficiency LEAPs (GOOGL 0.25×, AMZN 0.15×):** sell a ~0.30Δ call to fund a protective put. Converts naked-long LEAPs into risk-defined, income-producing, downside-protected positions — exactly what a 94% cluster needs.
- **Enforce the 20% / 60% caps** (logic #5).
- **Diversify the premium sleeve** off Mag-7 (index or non-tech CSP/PCS) so one tech air-pocket doesn't hit cores + income together.

**Profit next**

- **Monetize the LEAPs properly** (logic #1): consistent ~0.30Δ, 30–45 DTE covered calls rolled monthly. High IVR (65–91) makes this especially valuable right now — it is currently being wasted.
- **Manage the defined-risk sleeve at ~50%** of max profit (vs 80%) to raise win rate and cut tail; accept higher turnover.
- **Prefer Diagonals over full PMCC** where capital matters: for MSFT the Diagonal needs ~$4.5k vs PMCC ~$12.5k for the same short — once the short strike is fixed to earn real credit.

**What the metrics say per name (caveat: PMCC credits are the $0 bug):** in the current high-IVR, per-name-bullish read, **defined-risk PCS** scores top with POP ~0.75–0.82 and ~$180–360 credit / 45d on $0.8–1.6k risk. But given concentration, **monetizing existing LEAPs beats adding new same-name PCS** — same premium, no new directional exposure.

**Review prompt:** *Should we cap the number of correlated Mag-7 premium positions? What non-tech underlyings fit the liquidity/size profile? Is a full collar preferred, or a call-write + occasional tactical put?*

---

## 6. Suggested sequencing

1. Adopt the two rules (done) + fix persona/caps (logic #5, #7) — low effort, high safety.
2. Fix short-strike selection (logic #1) — unlocks LEAP income.
3. Add trend-gate (logic #4) — fixes win rate.
4. Roll out collars on GOOGL/AMZN.
5. Frontend: status banner + capital-efficiency heatmap first.

---

## 7. Open decisions for you / AI reviewer

- Confirm short-call **default delta** (0.30?) and DTE (30–45?) for the strike-selection fix.
- Full **collar** vs call-write-only on the concentrated LEAPs.
- **Manage-at-50%** for the whole defined-risk sleeve, or only put spreads?
- Which **non-tech underlyings** to whitelist for diversification.
- Priority order for the **frontend** panels.
- Should the trend-gate be a **hard block** or a **warning** on new entries?

---

*Draft proposal — for decision support only, not investment advice. All figures sourced live from IBKR web_api and the Fortress analytics backend on 2026-07-02.*
