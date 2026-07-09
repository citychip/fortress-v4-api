# Fortress — Multi-Timeframe Technical Integration Procedure

**Version:** 1.1
**Date:** 2026-07-03
**Applies to:** Fortress PMCC/PCS book on IBKR (account U7453366), Strategy v3.9.0
**Status:** Active. Sprint 22 shipped the backend that this procedure assumed was manual: the **`get_technical_gate` MCP tool** (per-name weekly-200 "Thesis Stop" state + daily trend/key-level, one call) and **`get_chart_data` `1mo`/`4h` intervals** — so the headless run no longer depends on TradingView for Monthly/4h. Sections updated for that below (v1.1 deltas marked **[22.x]**).

---

## 1. Purpose & scope

This procedure integrates **TradingView multi-timeframe charts** (Monthly / Weekly / Daily / 4-hour) into the existing Fortress workflow, while keeping **IBKR/Fortress as the authoritative source for all book and risk data**. It defines: which data source owns which decision, how the timeframes divide labor, the precedence rules when they disagree, and exactly where technical checks slot into the daily briefing.

Guiding rule of thumb:

> **Monthly/Weekly decide *whether* and *how much*. Daily decides *when* and *where*. 4-hour decides the *exact fill*. IBKR/Fortress decides the *hard limits and sizing* — and is never overridden by a chart.**

---

## 2. Source-of-truth split

Four data sources, each with a non-overlapping mandate. When two sources could answer the same question, the "owner" column wins.

| Domain | Owner | Notes |
|---|---|---|
| Positions, greeks, β-weighted delta | **IBKR / Fortress** | `get_positions`, `get_portfolio_beta`, `get_briefing` |
| Liquidity vs floors, P&L, pacing | **IBKR / Fortress** | Hard limits — never chart-overridden |
| IV rank, roll/stop signals, hedge coverage | **IBKR / Fortress** | `get_roll_all`, `get_stop_loss_all`, `get_spy_hedge_coverage` |
| Options chain, strikes, greeks per leg | **IBKR (live) / QuantData / Massive** | Massive/QuantData as backup |
| Secular thesis, structural levels | **TradingView (Monthly/Weekly)** | 200-wk "Thesis Stop", TN framework |
| Execution timing, strike selection | **TradingView (Daily/4h)** | Entry/roll/hedge fills |
| **Headless technical read** | **Fortress `get_technical_gate` + `get_chart_data`** | **[22.1/22.5]** `get_technical_gate` gives the per-name weekly-200 Thesis-Stop state + daily trend/key-level in one call; `get_chart_data` serves candles at **1d / 1wk / 1mo / 4h** (4h resampled from 1h) for the fuller MTF view — no TradingView dependency |

**Why the headless layer matters:** the automated post-open briefing runs unattended, and TradingView Desktop with the debug port may not be up. **[22.1]** `get_technical_gate` delivers the weekly Thesis-Stop + daily trend read for SPY + every open-position name with no TV dependency, and **[22.5]** `get_chart_data` now also serves Monthly (`1mo`) and 4-hour (`4h`) candles — so the automated run always has the full multi-timeframe read. TradingView (with the TN custom indicators — Buy/Sell/Re-entry signals, WMA62, Thesis-Stop labels) remains the richer **interactive** layer for live sessions; its edge is the TN framework, not the timeframes themselves anymore.

**Data-source availability rule (must-follow):**

- **Interactive Claude Cowork session:** *always tell the user immediately, before presenting analysis,* if any data source is unavailable or serving fallback/stale data — IBKR `web_api` down or on `bs_yfinance`, TradingView not attached, QuantData/Massive empty, etc. Never silently analyze on degraded data in a live session.
- **Scheduled / automated tasks:** may proceed on documented fallback sources (e.g. `bs_yfinance`, `get_chart_data` instead of TradingView), but **must label the fallback in the output** so the reader knows the read is degraded.

---

## 3. Timeframe roles (full stack)

| Timeframe | Question it answers | Primary use | Key reads |
|---|---|---|---|
| **Monthly** | Is the multi-year secular thesis for this LEAP intact? | LEAP hold-vs-harvest; position sizing | Higher-high/higher-low structure; 10/20-mo EMA; major breakouts |
| **Weekly** | What is the primary bias, and is the thesis stop threatened? | De-risk triggers; cluster-glide decisions | **200-wk SMA = "Thesis Stop"**, 50-wk SMA, WMA62, TN weekly signals |
| **Daily** | When and where do I execute? | Roll timing, short-strike selection, trim/entry zones | 50/200-day SMA, WMA62, TN Buy/Sell/Re-entry, S/R levels, GEX |
| **4-hour** | What is the precise fill level right now? | Catalyst-window entries (NFP/CPI/FOMC), hedge/roll fills | Intraday S/R, momentum, VWAP behavior |

**Availability by mode:**

- Automated briefing (headless): **[22.1/22.5]** **Weekly + Daily** via `get_technical_gate`; **Monthly + 4h** candles available via `get_chart_data` (`interval=1mo`/`4h`) when a deeper read is needed. TN signal flags remain TV-only.
- Interactive session (TV attached): **Monthly + Weekly + Daily + 4h** via TradingView with the full TN framework (the signal flags + WMA/Thesis-Stop labels the headless SMAs don't carry).

---

## 4. Precedence & conflict rules

1. **Hard risk limits are absolute.** A liquidity-floor breach, a delta-critical stop, or a catalyst-gate defer is executed regardless of what any chart shows. Charts shape the *response*, not *whether* to respond.
2. **Higher timeframe sets direction; lower timeframe sets timing.** If Weekly bias is down but Daily is bouncing, you may still *time* a trim into the daily bounce — but you do not flip the thesis on the daily.
3. **Thesis change requires the Weekly (confirmed on close).** Intraday/daily wicks through a structural level do not change the thesis; a **weekly close** beyond it does.
4. **When Weekly and Monthly disagree**, reduce size and wait — do not add. Monthly is the tie-breaker for LEAP hold/harvest.
5. **IBKR price is the execution reference; TradingView is the structure reference.** If they diverge materially, trust IBKR for fills and re-check the feed.

---

## 5. Decision matrix

Each action starts from an IBKR/Fortress trigger, then the technical layers modify *how* it's executed.

| Action | IBKR/Fortress trigger | Monthly / Weekly modifier | Daily / 4h modifier |
|---|---|---|---|
| **Roll short call** | delta ≥ 0.40 or DTE ≤ 5 | Weekly trend: roll *up* more aggressively if weekly bias down (keep protection) | Pick new strike vs daily resistance, target ~0.30Δ; time fill on 4h |
| **Stop-loss** | stop signal fires | Weekly close beyond thesis stop = honor in full | Daily/4h wick alone = may defer to close; do not defer a confirmed signal |
| **LEAP trim (cluster glide)** | cluster > 60% | Weekly/Monthly thesis intact = trim into *strength only*; thesis broken = accelerate | Trim into daily resistance zone; 4h to place the limit |
| **Hedge re-fund** | coverage < $20k | Weekly down-trend = size to upper band ($30k) | Time around catalysts; 4h fill after event IV crush |
| **New premium entry** | pacing OK + IV rank + catalyst gate clear | Weekly trend must agree with the position's direction | Not at a daily S/R extreme; 4h confirm |
| **Add / size up** | within limits | Monthly + Weekly aligned (both up for longs) | Daily pullback to support = better entry |

### Name-specific rules (live examples, refresh each review)

- **MSFT (structurally broken name):** Weekly 200-SMA "Thesis Stop" ≈ **$388**; price ≈ $391 (sitting on it). **A weekly *close* below ~$388 = accelerate the LEAP de-risk.** Daily $395–410 (weekly WMA62 resistance ≈ $438 above) = trim into strength. Do not trim at the lows.
- **NVDA:** Daily 200-SMA (~$191) looks like a knife-edge, but Weekly 200-SMA thesis stop is ~**$105** — secular thesis intact. Treat current action as a 50-week test (~$188), **not** a thesis break. Only escalate if weekly structure breaks.
- **GOOGL / AMZN / AAPL / SPY:** Weekly above the 200-wk line = theses intact. Daily softness (below 50-day) is a pullback, not a signal to exit cores. Manage short calls normally.

---

## 6. Updated daily post-open briefing workflow

Insert a **Technical Gate** as a new step. Additions to the current procedure are marked **[NEW]**.

1. **Data backbone (staleness guard).** `trigger_ibkr_sync` → `get_ibkr_status` (confirm `web_api` + authenticated; warn loudly if `bs_yfinance`/frozen).
2. **Briefing core.** `refresh_iv_data` → `get_briefing` + `get_portfolio_beta`: Net Liq, liquidity vs floors, β-weighted delta, Θ/VEGA (flag vega sign flips), pacing, regime, VIX, top-5 concentration + Mag-7 cluster vs 60%.
3. **[22.1] Technical Gate (headless — now one call).** Call **`get_technical_gate`** (SPY + every open-position name by default). It returns, per name: the weekly-200 Thesis-Stop state (`hold` / `watch` = within 3% above / `act` = below the weekly 200-SMA / `unknown`), plus a `daily{}` block (daily 50/200-SMA, `trend` up/down/mixed, nearest `key_level`). Flag every `act` (the Sprint 21.4 entry gate already de-ranks bullish premium-sells there) and `watch`. For a deeper look on a flagged name, pull `get_chart_data` at `1mo`/`4h`. Output one line per name: `TICKER  Wk: [hold/watch/act]  D: [trend, key level]  → [disposition]`.
4. **[NEW] Technical overlay on actions.** For every roll/stop/trim the briefing raises, annotate with the matrix modifier (e.g. "MSFT roll — weekly still on 388 line, daily resistance 402; trim zone 395–410").
5. Hedge coverage, macro/catalyst gate, VIX term (unchanged).
6. Stop-loss + roll scan: `get_stop_loss_all`, `get_roll_all` — now cross-referenced with the Technical Gate (step 3) before recommending strikes.
7. **Position watch** (MSFT de-risk, NVDA weekly-stop watch, short-leg delta breaches).
8. **Output:** prioritized action list; account header; regime + catalyst line; cluster-glide + hedge line; **[NEW] one-line multi-timeframe technical summary**; watch items.

**Interactive deep-dive (when at the desk, TV attached):** after the automated briefing, use TradingView for Monthly (LEAP thesis) and 4h (fill timing) on any name flagged `watch`/`act`.

---

## 7. TradingView operating procedure

### 7.1 Launch with remote debugging (required for MCP control)

Fully close any running TradingView first, then:

```
"C:\Users\cityc.000\Downloads\TradingView\TradingView.exe" --remote-debugging-port=9222
```

Verify: browse to `http://localhost:9222/json/version` — a JSON response = debug live. Or run `tv_health_check`.

Optional: make a desktop shortcut with that exact target so every launch enables the port.

### 7.2 Watchlist (core book)

**Watchlist definition:** every ticker with an **open position (any leg)** in the portfolio, **plus** any ticker the user adds during a Claude session or in Fortress (e.g. via `add_universe_ticker`). The current core set is `SPY, MSFT, GOOGL, AMZN, AAPL, NVDA`; names with open short spreads (ARM, MU, AMD) or newly added tickers are included automatically whenever a position exists. The watchlist is dynamic — it is derived from positions + user additions, not a fixed list.

### 7.3 What to read (per name, per timeframe)

- **Clean Decision Chart v3.2:** 50 SMA, 200 SMA, "Thesis Stop (200 SMA)" label, 52W High.
- **TN Alerts v17:** WMA 4 (fast), WMA 62 (trend), Trading Stop, and the signal flags — Buy / Sell / Stoploss Long / Stoploss Short / Re-entry Long / Re-entry Short (1.0 = active).
- **TN Options v10:** expiration markers and strike-level shapes (useful for short-strike placement).
- **Support and Resistance Levels with Breaks:** current Resistance, Support, Break flag.

### 7.4 TN signal glossary (as used above)

| Field | Meaning | Action relevance |
|---|---|---|
| Buy / Sell Signal | Primary entry/exit trigger | Confirms direction for new entries |
| Re-entry Long / Short | Trend-resumption trigger | Add/hold long cores; caution on short calls if Long re-entry fires |
| Stoploss Long / Short | System stop hit | Cross-check against Fortress stop-loss |
| WMA 4 / WMA 62 | Fast / trend weighted MAs | WMA62 = dynamic resistance/support; strike anchor |
| Thesis Stop (200 SMA) | Structural invalidation line | **Weekly close beyond = thesis change** |

### 7.5 Fallback

**[22.1/22.5]** If TradingView is not attached (or in an automated run): use **`get_technical_gate`** for the per-name weekly Thesis-Stop + daily trend read, and **`get_chart_data`** for candles at **1d / 1wk / 1mo / 4h** (4h resampled from 1h; intraday lookback is clamped to yfinance's cap). Monthly and 4h are **no longer TradingView-only** — only the TN *signal flags* (Buy/Sell/Re-entry, WMA62 label) require TradingView, so defer only those signal-dependent reads to the next interactive session.

### 7.6 Etiquette

The MCP switches symbols/timeframes on the live chart. Restore the working symbol/timeframe when done (record it before starting). Avoid adding/removing the user's custom studies.

---

## 8. Current-state application (worked example, 2026-07-02)

| Name | Price | Weekly 200-SMA (Thesis Stop) | Weekly read | Daily read | Disposition |
|---|---|---|---|---|---|
| SPY | $741.9 | $540 | Secular bull intact | On 50-day/WMA cluster, <760 res | Normal |
| AAPL | $307.7 | $208 | Strong; Re-entry Long (daily) | Above all averages, near 52W high | Hold; watch Dec 320 short if it runs |
| GOOGL | $357.7 | $182 | Strong uptrend | Below 50-day (pullback) | Hold; Nov 390 short comfortable |
| AMZN | $244.5 | $177 | Healthy; on WMA62 support | Below 50-day (pullback) | Hold; Oct 280 short comfortable |
| NVDA | $192.8 | $105 | Uptrend intact; testing 50-wk | On daily 200-SMA (191) | Hold core; **watch weekly 50-wk** |
| MSFT | $390.8 | **$388** | **On the structural line** | Below 50/200-day (broken) | **De-risk name; weekly close <388 = accelerate; trim 395–410 into strength** |

---

## 9. Governance

- **Automated (headless, every scheduled run):** IBKR/Fortress full briefing + Technical Gate — **[22.1]** via `get_technical_gate` (weekly Thesis-Stop + daily trend), now a wired step in the `daily-post-open-briefing` task; Monthly/4h candles via `get_chart_data` on demand.
- **Interactive (at the desk):** add Monthly (LEAP thesis) + 4h (fills) via TradingView on flagged names.
- **Never automated:** trade execution (advisory only), thesis changes (require weekly close + human sign-off).
- **Review cadence:** refresh the name-specific rules (§5) and current-state table (§8) weekly, ideally on the Friday weekly close.
- **Versioning:** bump the version and date on any change to precedence rules or the decision matrix.

---

## 10. Open items to refine (your input)

- Confirm the **Monthly thesis definition** (structure-based vs a specific MA, e.g. 10-month EMA).
- Confirm **4h usage** — only around high-impact catalysts, or every roll/hedge fill?
- Decide whether the **Technical Gate output** should be a fixed one-liner per name or a fuller block.
- Confirm the **weekly-close review** day/time and who signs off thesis changes.
- Any names to add to the watchlist beyond the six cores (e.g. ARM/MU/AMD when positions are open).

*Draft — not investment advice. For account-holder decision support only.*
