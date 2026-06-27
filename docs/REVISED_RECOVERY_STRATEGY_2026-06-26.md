# Fortress — Revised Recovery Strategy

**2026-06-26 · addendum to `01_Portfolio_Strategy_v3_9.md` + `STRATEGY_ENHANCEMENTS_v3_10.md`**
**Goal: recover the ~$21k unrealized drawdown of the past months with positive-expectancy income, not by doubling down on the beta that caused it.**

> Not financial advice. This is a portfolio-construction and process plan distilled from the live book (IBKR/Parapet/Fortress, 2026-06-26). Steven makes and fires every trade.

---

## 1. Diagnosis — where the loss actually came from

Total unrealized P&L **−$21,299**. Attribution by ticker (live `get_pnl`):

| Bucket | Tickers | P&L |
|---|---|---|
| **Long mega-cap tech LEAPs** | MSFT −5,309 · GOOGL −3,661 · NVDA −3,014 · AMZN −2,794 · AAPL −2,323 | **−$17,101** |
| **Dead micro-cap stock** | OST (cost $4,545 → mv $75, −98%) | **−$4,470** |
| **Income engine (the strategy working)** | V +384 · SPY +183 · AMD +72 · ARM −251 · MU −113 | **+$275** |

**The single takeaway:** the options-selling engine is profitable. ~100% of the drawdown is (a) directional losses on long mega-cap tech held through a bearish tech tape, and (b) one un-cut dead stock. You do not have a strategy problem; you have a **concentration + hedging + dead-capital** problem.

### Root causes (all measured today)
1. **Extreme correlated concentration.** Technology = **70.8%** of notional (cap 40% — *breach*). Mag-7 cluster = **93.3%** of NLV (warn 60% — §7). Single names: GOOGL 26.1%, MSFT 24.7%, AMZN 19.7%, AAPL 15.2%.
2. **Net-long beta into a bearish macro regime.** β-weighted delta ≈ **+242** (~2.7× NLV in SPY-equivalent), while the portfolio macro regime reads bearish.
3. **Capital-inefficient longs.** The LEAPs tie up the capital-at-risk but earn almost no premium: efficiency MSFT 0.54, AAPL 0.41, AMZN 0.29, GOOGL 0.25 — versus the PCS engine at 7–212. ~$76k of capital is sitting in directional longs generating little theta.
4. **Under-sized tail hedge.** SPY hedge net value ≈ **$2.9k** vs the §2.D **$20–30k** target (4.4% of NLV). When tech fell, there was almost no offset.
5. **A position never cut.** OST went $4,545 → $75 and was carried to a near-total loss.

---

## 2. Revised strategy — recover *through* the engine

**Principle:** you don't climb out of a concentration-driven hole by adding more of the same beta. You climb out by (a) stopping the bleed — diversify and re-hedge, (b) turning the dead long capital into a theta machine, and (c) running the income engine on uncorrelated names with a real volatility edge. Keep enough upside delta to benefit if tech recovers — you already own that via the LEAPs.

### Pillar 1 — Stop the concentration bleed (glide, don't dump)
- **Cluster glide path: 93% → ≤60% over ~6–8 weeks** (§7 `cluster_concentration_warn_pct`). Use rallies to trim; never sell the lows in size.
- **GOOGL (26.1%) and MSFT (24.7%) are the two oversized names.** On bounces, trim one LEAP tranche each toward **≤20% near-term, ≤15% eventually**. Rolling a LEAP down-and-in (e.g. to a higher-delta, lower-strike, shorter-dated long) also cuts capital-at-risk without fully exiting the recovery thesis.
- **Cut OST Monday.** It's $75 of residual value and a dead line. NL Box 3 means no tax-loss benefit, so there's nothing to wait for — close it and free the slot and the attention.

### Pillar 2 — Convert dead LEAP capital into income (disciplined PMCC)
- Every LEAP carries a **systematic short call** (you've already PMCC'd AMZN/NVDA/AAPL/GOOGL/MSFT — make it a rule, not ad hoc).
- Mechanics: short call **~30–45 DTE, ~0.30 delta**, respecting the **breakeven guardrail** (§4a — never short below long breakeven) and the **earnings rule** (§4c — close shorts before the print). Manage at **50% profit or 21 DTE** (§1, §2).
- This is the **core recovery engine**: ~$1–2k/month of theta harvested against calls you already own, grinding the LEAP drawdown back with positive expectancy. On a tech bounce, roll the shorts up so the LEAPs participate.

### Pillar 3 — Diversify the income engine OUT of tech
- **New PCS / iron condors go on non-tech, high-VRP names.** From today's scanner: **ELV** (healthcare), **GE** (industrial), **MAR** (travel), **LLY** (healthcare), **VST** (power/utility). MSTR shows prime IV-crush but is a high-beta crypto proxy — size tiny if at all.
- **Gate every entry** (§3): VRP (IV − HV20) ≥ **3–5pp**, IVR ≥ **25**, liquidity grade ≥ B, and the **catalyst gate** (defer new premium 2 days around NFP/CPI/FOMC).
- Each new name ≤ **5% capital-at-risk**; keep sector ≤40%, cluster ≤60%.

### Pillar 4 — Right-size the tail hedge (catalyst-timed put spread)
- Rebuild the SPY hedge toward the **$20k floor** as a **put spread** (§5), timed to the **NFP catalyst (Jul 2)** — add *before* the event, not after. The bigger you keep the long-tech book, the bigger the hedge must be; as Pillar 1 trims the longs, the required hedge shrinks.
- **Missing dial:** β-weighted vega (§6, B1) isn't built yet — you're ~**−374 vega**, so a *volatility spike* is your worst day, not just a price drop. Until B1 ships, treat the funded SPY put spread as your vega proxy and keep it at the floor.

### Pillar 5 — Loss-psychology guardrails
- **No averaging down to "get even" on a single name.** Recovery is a portfolio-expectancy outcome, not a MSFT round-trip.
- Honor stop-loss verdicts (delta / 200-SMA), manage winners at 50%, roll at 21 DTE.
- Log every close to the trade-outcomes store so `journal_analytics.py` can prove which buckets (IVR/DTE/delta) actually pay — the store is currently too sparse (4 records) to trust.

---

## 3. Monday (2026-06-29) action plan — sequenced

Pacing resets Monday (was 5/5). NFP-defer gate arms ~Jun 30, so Monday is clear for entries and the hedge.

1. **Close OST** (44 sh @ ~$1.70). Free the line. Log the outcome.
2. **Re-fund the SPY hedge** toward the $20k floor — add to the Aug21 710/665 put spread (or open a fresh SPY/QQQ put spread), ahead of NFP. Defined cost.
3. **One non-tech income starter** — a single PCS or IC on **ELV / GE / MAR** (VRP-positive, earnings-clear, ≤5% CAR), short strike **below charted support**.
4. **On any tech bounce** — trim one GOOGL *or* MSFT LEAP tranche toward 20%; roll the matching short call up so the LEAP can run.
5. **Keep the existing engine running** — MU / ARM / V / AMD PCS; harvest each at 50%.

**Success metric for the recovery:** cluster % falling toward 60, hedge at floor, and a rising realized-premium line in the trade-outcomes store — not a single-name price target.

---

## 4. Chart levels (TradingView MCP — now connected 2026-06-26)

**TradingView MCP is live** (`tradingview` server in `claude_desktop_config.json`; reads the **"Clean"** layout with TN Alerts v17 / Clean Decision Chart v3.2 / LuxAlgo "Support and Resistance Levels with Breaks"). Levels below pulled via `data_get_study_values` (daily, post-close 6/26). **Caveats:** read settles ~1 turn after a symbol switch (first read returns only TN Alerts — re-read for all 3 studies); the TN "Plot" field can race mid-switch (cross-check price with `quote_get`, which returns the *current chart symbol* regardless of its argument); LuxAlgo pivots go stale on strongly-trending names (use SMAs there).

**Tech LEAP names — trim-into-resistance / SMA map:**

| Name | Price | 50 SMA | 200 SMA | LuxAlgo S / R | TN signal | Action level |
|---|---|---|---|---|---|---|
| **MSFT** | ~373 | 411 | 448 | 356 / 466 | neutral | Below both SMAs (broken) → **trim into 405–411** |
| **GOOGL** | ~337 | 369 | 314 | 272 / 409 | **Re-entry SHORT** | Below 50SMA → trim into **367–369**; supp 314 |
| **AMZN** | ~231 | 251 | 232 | 199 / 278 | neutral | On 200SMA; short 250C at 50SMA/resist ✓ |
| **NVDA** | ~192 | 210 | **190.6** | **164** / 236 | **Re-entry SHORT** | **On 200SMA** — pivotal; add-back 164; short 220C ✓ |
| **AAPL** | ~281 | 291 | 269 | 245 / **281** | neutral | At LuxAlgo resist 281, below 50SMA; short 305C ✓ |

Trim priority unchanged: **MSFT** (only name below both SMAs). **GOOGL weakened** (re-entry SHORT, below 50SMA) — no longer the safe "keep" anchor; trim into 367–369. AMZN/NVDA/AAPL = keep, short calls correctly placed above resistance.

**Indices (hedge / regime):** SPY ~729 just **below** its 50SMA (734), 200SMA 690 — soft/pivoting; the hedge works hard if SPY loses **690**. QQQ ~706 just **above** its 50SMA (703), 200SMA 632 — marginally firmer. Both above 200SMA = not breaking down; hedge is insurance, rebuild to §2.D floor before NFP.

**Non-tech PCS candidates — short-put placement (below charted support):**

| Name | Price | 50 SMA | 200 SMA | LuxAlgo S / R | Earnings | PCS short-put zone |
|---|---|---|---|---|---|---|
| **MAR** | ~377 | 373 | 322 | **345** / 380 | ~38d ✓ | **~345**, e.g. 345/335 — **top pick** |
| **VST** | ~164 | 155 | **170** | 133 / 168 | ~40d ✓ | **~150**, e.g. 150/145 — small size (below 200SMA, resist 168–170) |
| **LLY** | ~1190 | 1031 | 976 | 850 / 1114 | ~39d ✓ | **~1100**, e.g. 1100/1075 — 1 lot (big notional) |
| **ELV** | ~393 | 382 | 343 | 275 / 383 | ~19d ⚠ | **HOLD** — print mid-July (§4c) |
| **GE** | ~368 | 313 | 307 | 269 / 319* | ~19d ⚠ | **HOLD** — print mid-July (§4c) |

*GE LuxAlgo pivots stale below price (extended uptrend) — use 50SMA 313 as support.

**Monday execution:** lead with **MAR** PCS (earnings-clear, clean support at 345); VST small second; LLY if sizing allows. These are *strike-placement* levels from the charts — exact short strikes/delta/IV/credit need the live option chain (re-sync IBKR → pull MAR ~345 chain → short ~0.20–0.25Δ below 345, liquidity-checked).
