# Portfolio Management Strategy
**Version 3.9.0 — June 8, 2026**

> ⭐ **v3.11 IN FORCE (2026-07-07): `STRATEGY_v3_11_UPDATE_2026-07-07.md` is the canonical DELTA against this document — where they conflict, v3.11 wins.** Headlines: two-bucket architecture (VWCE core 20% + engine) · HYBRID income book (XSP base ≥45–60 DTE + ≤2-name post-earnings sleeve; pre-earnings single-name selling discontinued) · per-ticker β-dollar-delta caps 30% (replaces MV/NLV as control metric) · hedge sized 25–33% of Bucket-B β-DD by MAX PAYOUT (fixed $20–30k MV floor retired) · roll doctrine v2 (same-strike out-rolls forbidden on keep-names; matched verticals exempt from flags) · weekly-close de-risk rules · dynamic pacing by VIX band · compliance-score measurement until n≥30. This v3.9 text remains the base spec for everything not superseded.

v3.9.0 introduces: multi-strategy selection framework with regime gates + yield comparison (§2.5); CSP, Iron Condor, and Covered Call added as fully formalized strategies (§2.F–H); bid-ask 5% advisory threshold formalized in §4 alongside the existing 10% hard block; `get_strategy_metrics()` and `check_liquidity()` MCP tools; yfinance GEX/vol-skew backend (`get_gex()`, `get_vol_skew()`) deployed and confirmed; Parapet Candidates tab now shows recommended strategy per ticker; fortress_mcp bumped to v4.4.0 (67 tools). Trading rules otherwise unchanged from v3.8.0.

---

## 1. Governance

The decision-maker is you, the trader. **This is an advisory system, not an automated one.** All thresholds, signals, and tool outputs are inputs to your judgment — not triggers for automatic action. When a parameter is breached, the correct response is to review the position and decide consciously, not to act mechanically.

AI tools are analytical inputs, not decision sources. When another AI recommends a trade, flag it before executing so it can be evaluated against the active strategy. Before every execution, verify ticker, earnings date, strike direction, and limit price. The framework is flexible — open to any strategy or rotation as long as the trade is profitable and fits the rules below.

---

## 2. Active Strategies

### A. Poor Man's Covered Call (PMCC) — primary

The primary income strategy. The long leg uses LEAPS approximately 640 DTE (Jan 2028 cycle), 25–30% ITM, targeting delta 0.78–0.85. The short leg uses monthly calls 30–45 DTE, delta 0.25–0.30 at entry, 7–10% OTM. Coverage is strict 1:1 short-to-LEAP ratio — never hold an uncovered LEAP.

### B. Diagonal Spreads — tactical

Structure: long call 30–90 DTE plus short call at shorter DTE. Used for directional tactical plays, not income generation. Decay profile differs from PMCC and requires shorter-horizon monitoring.

#### Post-Earnings Diagonal Playbook (primary use case for Strategy B)

Entry trigger: morning after earnings, when IV crush ≥ 25% AND stock gap within ±8%. Entry timing: place order between 10:00–11:00 AM ET on the day after earnings. Long leg: 30–90 DTE call, delta 0.55–0.70, at or near current price (ATM or slightly ITM). Short leg: 14–21 DTE call, delta 0.25–0.30, at first resistance level above current price. Target net debit: ≤ 50% of the long leg's value. Exit: close the entire diagonal at 50% of max profit, or roll the short leg when it reaches 80% profit. Never enter a new diagonal within 10 days of the next earnings date for that ticker.

### C. Put Credit Spreads — income

Structure: sell OTM put + buy further-OTM put as protection. Short strike: delta 0.15–0.20 (80–85% probability of expiring worthless), anchored below the nearest DP floor or GEX put wall when one falls within 12% of the delta-computed strike. This ensures the short put is sold below structural support — if price holds above the floor, the spread expires worthless. DTE: 30–45 days at entry.

### F. Cash-Secured Put (CSP) — income, lower-leverage

Structure: sell OTM put, fully cash-secured (no margin). Strike delta 0.20–0.30, DTE 30–45. Use for names where a PMCC LEAP would be disproportionately capital-intensive or where the directional thesis is mildly bullish. CSP is simpler than PMCC — less monitoring required, no LEAP management overhead, but lower capital efficiency (full cash reserve vs. LEAP margin). Wheel exit: if assigned, sell covered calls until cost basis is recovered.

### G. Iron Condor (IC) — neutral/range-bound income

Structure: OTM call spread + OTM put spread, same expiration. Short strikes at delta 0.15–0.20 on each side; wing width 2–5 strikes. DTE 30–45. Preferred in neutral or low-trend regimes when IV is elevated. Max profit = net credit; max loss = wing width − credit. Close at 50% profit or 21 DTE, whichever comes first. Never hold through earnings. IC is blocked in strong trend regimes — structure dies quickly when the underlying moves directionally.

### H. Covered Call (CC) — stock position income

Structure: sell OTM call against 100 shares of stock. Strike delta 0.25–0.30, DTE 30–45. Use only when stock is already held (e.g., from a CSP assignment wheel). Not a primary entry — CC is the wheel exit, not a standalone income trade. Do not buy stock specifically to sell covered calls; use PMCC instead for synthetic coverage.

### D. SPY Hedge — protective

Maintain SPY put hedge with market value $20,000–$30,000 USD at all times when total portfolio Net Liq exceeds $50,000. Dashboard enforces this gate: if hedge MV falls below $20,000, new PMCC entries are blocked until the hedge is restored. Hedge MV tracked live from IBKR via CP Gateway.

### E. Jade Lizard — consolidation income

Structure: short OTM call + short OTM put spread (no upside risk, defined downside risk). Use when the underlying is in a consolidation range and IV is elevated. Credit gate enforced by dashboard: total credit received must exceed the width of the put spread. Dashboard validator rejects the structure if this condition is not met.

### 2.5 Strategy Selection Framework (v3.9.0)

**Step 1 — Regime gate (hard filter):** The current macro regime narrows the allowed strategy set:

| Regime | Allowed strategies |
|---|---|
| Bullish | PMCC, CSP, PCS, Diagonal, Jade Lizard |
| Neutral | IC, PCS, CSP (far-OTM) |
| Bearish | IC, CSP (far-OTM, delta ≤ 0.15) |

Strategies outside the regime-allowed set are not considered, regardless of yield. This filter runs first.

**Step 2 — Yield comparison (within allowed set):** Among regime-allowed strategies, select the one with the highest annualized yield estimate that also passes all quality filters (§4). Use `get_strategy_metrics(ticker)` [fortress MCP] to get the full comparison — it returns annualized yield, regime score, capital required, and a `recommended=True` flag on the top-scoring strategy. The Parapet Candidates tab shows the recommended strategy badge directly.

**Decision rule:** Regime gates first, yield comparison second. Do not override a regime gate for yield alone.

### 2.6 Source-of-Truth Hierarchy

When sources conflict, the hierarchy is: **this strategy document > tool behavior > memory**. If a tool produces a recommendation that contradicts a rule here, the rule wins. If memory contains a rule that contradicts this document, this document wins. Tools may add safety beyond what this document requires; they may not subtract safety.

---

## 3. Name Universe

### 3.1 Core Holdings (standing instruction)

MSFT is a high-conviction core holding. Concentration above 20% Net Liq is acceptable for MSFT specifically, subject to the High-Concentration Entry Override in §7 and the MSFT De-Risking Plan in §7. All other names follow standard concentration limits.

### 3.2 Approved for New Entries

> **Live source of truth: fortress `get_universe()` / `ticker_universe.json`.** The list below is a snapshot (updated 2026-06-15); if it disagrees with `get_universe()`, trust the tool.

**Tier 1 — primary candidates (23 tickers, as of 2026-06-09):** MSFT, AVGO, NFLX, VST, GOOGL, AMZN, AMD, MSTR, UNH, APP, LLY, TSM, V, MU, GEV, META, AAPL, ELV, GE, PNC, CSX, MAR, NVDA.

**Tier 2 — secondary candidates:** (none — META/AAPL/NVDA promoted to Tier 1).

**Macro / Index — benchmark and hedge instruments:** SPX, SPY, VIX.

Non-tech candidates for future consideration: Healthcare (UNH, LLY), Financials (MS, GS, JPM), Energy (XOM, OXY).

### 3.3 Excluded

Hard exclusions enforced by the dashboard via `ticker_universe.json` `excluded` array:

- **Regulatory risk:** COIN, HOOD, SMCI — until legal clouds clear.
- **PMCC-incompatible:** Small-caps with thin option chains (e.g., LKFN).
- **Ignored entirely:** OST. Display in book if held; never recommend.

### 3.4 Universe as Signal, Not Law

Outside-universe names are explorable when a setup demonstrably exceeds universe candidates. Documentation in the journal is required. All quality filters in §4 still apply. All hard exclusions in §3.3 remain blocked regardless.

---

## 4. Entry Rules

### Timing

Execute after 10:00 AM ET / 16:00 Amsterdam — avoid opening volatility. On Opex Fridays, trade cautiously and expect wider spreads. Wait 3–5 days for IV normalisation after news-driven spikes. Use limit orders at mid, walk up/down patiently. Do not pay ask or chase fills.

### Earnings Discipline

Verify earnings date before every new entry — non-negotiable. No new LEAP entries within 2 weeks of ticker earnings. No new put spreads within 10 days of ticker earnings. Post-earnings IV crush morning (next day) is the preferred LEAP entry window. Entry trigger for post-earnings: IV crush ≥ 25% AND stock gap within ±8%. Hold existing positions through earnings — PMCC is designed for this.

### Quality Filters

**Bid-ask spread (v3.9.0 — two-tier):**
- ≥ 10% of mid: **hard block** — do not trade
- 5–10% of mid: **advisory** — flag and document in journal before trading; acceptable if all other filters pass
- < 5% of mid: **good** — no restriction

Use `check_liquidity(ticker)` [fortress MCP] for a pre-trade spread check. The liquidity grade (A/B/C/D) reflects the fraction of strikes within ±15% of spot with spread < 5%. ATM advisory fires automatically in the Candidates tab when ATM spread ≥ 5%.

Open interest > 100 per leg. Underlying daily option volume: > 1K contracts (credit spreads), > 10K (LEAPS preferred).

**IV Rank — dual confirmation (v3.8.0):** Before entering any premium-selling position, confirm IVR > 25 from both sources:
1. `get_candidates()` / `refresh_iv_data()` [fortress] — yfinance-based, fast full-universe scan
2. `qd_get_iv_rank(ticker)` [quantdata] — live QuantData per-ticker IV rank

If sources diverge materially (>15pp difference), investigate before entering — a divergence often signals a yfinance data artifact or a very recent IV move not yet captured in the batch scan. Do not enter if only one source confirms.

---

## 5. Short Call Management (PMCC)

### Strike Selection

**Primary anchor — live GEX call wall (v3.8.0):** Use `qd_get_exposure_by_strike(ticker)` [quantdata] to identify the nearest GEX call wall above current price. Prefer a short strike just below this wall — price tends to pin at GEX call walls, maximising probability of the short expiring worthless. This replaces the daily-report GEX as the primary anchor during market hours.

**Secondary anchor — delta:** Target 0.25–0.30 delta at entry. If the GEX wall and delta anchor diverge by more than 2 strikes, prefer the GEX wall and note the deviation.

**DP floor / GEX override (short puts):** For PCS/CSP, anchor strike $5 below the nearest DP floor or GEX put wall within 12% of the delta strike. The dashboard Trade Builder auto-suggests this level with an ⚓ indicator.

**Chart override:** If a strike within the target delta range sits at or just above a well-defined chart resistance level, prefer the chart-aligned strike.

**Outside market hours:** `qd_get_exposure_by_strike` returns empty data outside market hours. Fall back to `get_dp_floors_and_gex(ticker)` [fortress] (daily report, ~12h old — structural levels are stable intraday).

### Vol Skew Gate (v3.8.0)

Before any new call-side entry (PMCC short call, IC call spread), check `qd_get_volatility_skew(ticker)` [quantdata]. If put skew is unusually steep — significantly elevated put IV relative to call IV across strikes — treat this as a caution signal: the market is pricing in elevated downside risk. This does not block the trade, but requires conscious acknowledgement. Flat or normal skew = proceed. Steep put skew = document the override reason in the journal.

### Management Rules

Take profit at 80%: close short call when value decays to approximately 20% of credit received. Time-based roll rule: if the short call has not reached 80% profit by 14–21 DTE, close it anyway and re-sell a fresh short at 30–45 DTE. Roll up-and-out if the short becomes ITM, targeting net credit. Never roll winners. Never roll losers into earnings. Never roll on strong-underlying days.

### DTE Discipline

Short calls 30–45 DTE at entry. 90+ DTE shorts capture 3–5× less total premium over the holding period. 7–10% OTM for low-IV names. Before selling any short call > 60 DTE: explicitly state the reason and acknowledge theta inefficiency.

### Delta Drift Monitoring

Short call delta drifts upward as the underlying rallies. Monitoring delta after entry is part of active position management.

**Delta thresholds (v3.8.0) — entry target codified:**

| Delta range | Status | Action |
|---|---|---|
| 0.25–0.30 | Entry target | Preferred zone for new short calls |
| ≤ 0.30 | Normal | No special action required |
| 0.30–0.35 | Watch zone | Monitor closely; consider rolling on next strong-down day or at 80% profit |
| > 0.35 | Roll trigger | Roll up-and-out within the current trading week, or close if rolling for credit is not achievable |

The dashboard reads the roll trigger from `cfg("strategy.delta_critical_threshold")` — tunable in Settings without a code deploy. The threshold was tightened from 0.40 to 0.35 in v3.6. It remains at 0.35 in v3.8.0 — tightening further to 0.30 would collapse the entry/management gap and increase roll frequency without proportionate risk reduction.

**Interaction with existing rules:** if 14–21 DTE approaches and delta is > 0.30, prioritise rolling. If delta is > 0.35 AND today is a strong-up day, wait one session then roll. If delta is > 0.35 AND earnings is within 10 days, close instead of roll.

---

## 6. Exit Rules

### Put Credit Spreads

Close at 50% profit. If the spread reaches 21 DTE without hitting the profit target, close it regardless. Never hold a put spread through earnings.

### Jade Lizard

Close the entire structure at 50% of max credit. If the short call is threatened (delta > 0.30), close the call leg first and evaluate the put spread independently.

### LEAPS Profit-Taking

No mechanical profit target on LEAPS — these are long-term positions. Evaluate exit only when: (a) the thesis has changed materially, (b) the underlying has broken the 200-day SMA on strong volume, or (c) concentration has grown to a level that requires trimming per §7.

### LEAPS Stop-Loss / Thesis Break

The 200-day SMA breach is the primary stop-loss signal for LEAPS. A breach is confirmed when: (1) the underlying closes below the 200 SMA on above-average volume, AND (2) the breach is not immediately recovered within 1–2 sessions. On confirmation, close the LEAP. Do not average down into a broken thesis.

---

## 7. Risk Management

### Position Sizing (USD)

Maximum new LEAP cost: $5,000 per position. Maximum total exposure per ticker: 20% of Net Liq (exception: MSFT per §3.1). Maximum sector exposure: 40% of Net Liq.

### Concentration

| Concentration | Status | Action |
|---|---|---|
| < 20% Net Liq | Normal | No restriction |
| 20–50% Net Liq | Elevated | New entries require explicit override |
| > 50% Net Liq | Critical | No new entries; consider trimming |

MSFT exception: concentration above 20% is acceptable given high-conviction thesis, subject to active SPY hedge per §2.D and the MSFT De-Risking Plan below.

### MSFT De-Risking Plan (v3.8.0)

Current MSFT concentration: ~99% Net Liq. This is acknowledged and managed, not ignored. Formal de-risking target: reduce to below 50% Net Liq over the next 6 months (by December 2026).

De-risking approach:
- At each short call roll, evaluate whether to re-sell fewer contracts than currently held (e.g. 3 instead of 4)
- When LEAP value grows materially, consider selling one LEAP contract and not replacing it
- Do not add new MSFT LEAP positions until concentration is below 50%
- Track progress quarterly via `get_sector_exposure()` and `get_capital_efficiency()`

Trigger for accelerated de-risking: if MSFT breaks the 200-day SMA on above-average volume, treat this as a mandatory review — close one LEAP within 5 trading days regardless of plan cadence.

### High-Concentration Entry Override

When a ticker is above 20% Net Liq, a new entry requires: (1) explicit acknowledgement of concentration, (2) confirmation that the SPY hedge is in place, (3) confirmation that the new entry does not push the ticker above 50% Net Liq.

### Pacing (Cooling-Off Target)

No more than 5 new positions per week under normal conditions. After a stop-loss event, observe a 3-day cooling-off period before the next new entry.

### Market Regime Filters

The dashboard synthesises a Macro Regime Score from -5 to +5 using SPY GEX walls, dark pool floors, and net drift data from QuantData. New entries are gated when the regime score is ≤ 0 (neutral or bearish). The threshold is configurable via Settings (`regime_entry_threshold`).

| Regime Score | Status | Entry Gate |
|---|---|---|
| > 0 | Bullish / Neutral | Entries permitted |
| 0 | Neutral | No new entries |
| < 0 | Bearish | No new entries |

All regime gates are advisory. A bearish regime score is a caution signal, not an automatic block. Document any override in the journal.

### Margin Discipline (USD)

Minimum Excess Liquidity: $17,000 USD at all times. Minimum Available Funds: $25,000 USD before any new position. These floors are configurable via Settings (`excess_liq_min_usd`, `available_funds_min_usd`). The dashboard reads live values from IBKR via CP Gateway and flags breaches.

### Prohibited Actions

Never hold uncovered LEAPS. Never sell naked puts (credit spreads only — exception: Jade Lizard short put per §2.E). Never use SPY shares for hedging (options only). Never sell puts on names in clear downtrend. Never enter LEAP or put-spread positions on names with active DOJ/SEC investigations.

---

## 8. Workflow

### Before Every New Trade

1. Open the Fortress V4 dashboard → Trade page → Morning Brief for the prioritised action list.
2. Review Candidates: `get_candidates()` [fortress] for full-universe IV crush ranking. Pick top 2–3 by IVR and spread.
3. Per-candidate deep dive: `qd_get_iv_rank(ticker)` [quantdata] to confirm IV rank. `get_strategy_metrics(ticker)` [fortress] for regime-gated strategy recommendation (PMCC/CSP/IC/PCS/Diagonal) — the Candidates tab shows this as the "Rec" badge. `check_liquidity(ticker)` [fortress] for bid-ask quality grade. `get_gex(ticker)` [fortress] for live GEX walls (yfinance-based, works outside market hours). `get_vol_skew(ticker)` [fortress] for skew direction and term structure.
4. Pull the Market Intelligence page for the target ticker: review regime score, GEX Call/Put Wall, Dark Pool Floor/Ceiling, Net Drift, and Directional Bias score.
5. Pull the live option chain from IBKR (CP Gateway snapshot).
6. Verify earnings date — non-negotiable.
7. Select strikes using GEX call wall as primary anchor, delta as secondary check, chart structure as tie-breaker.
8. Confirm structure matches intended strategy and all quality filters in §4 are met.
9. Verify limit price direction and magnitude relative to bid/mid/ask.
10. Submit as limit order; work patiently.

### Daily Routine

Morning: `get_briefing()` — Net Liq, regime, concentration, pacing, staleness. `refresh_iv_data()` + `run_script("max_pain")` — fresh IV scan and max pain for full universe. `get_stop_loss_all()` + `get_roll_all()` — sweep for required actions. Place orders after 10:00 AM ET. End of day: `trigger_ibkr_sync()` if data is stale; `add_journal_entry()` for any trades.

### Weekly Routine

Sunday or Monday morning: review Clean Decision Charts (TradingView) for each active LEAP. Flag any 200-day MA breaks — stop-loss signal per §6. Identify positions approaching roll windows (14–21 DTE) via DTE triage badges. Review Market Intelligence for regime shifts across the full universe. Review MSFT de-risking progress.

---

## 9. Chart Setup & Review (TradingView Workflow)

Unchanged from v3.5. Clean Decision Chart for strategic decisions; Signal/Timing Chart retained for tactical use. The Analysis page in the Fortress V4 dashboard overlays open positions directly onto the price chart — short call/put strikes, LEAP entry level, GEX walls, and earnings markers are all visible without leaving the dashboard.

---

## 10. Post-Earnings Entry Playbook

Unchanged from v3.5. Gap × IV crush matrix:

| Gap range | Rule | Verdict |
|---|---|---|
| Gap up > 5% | Missed move, IV will be low | PASS |
| +2 to +5% | Buy if IV crush > 30% | CONDITIONAL |
| Flat ±2% | Buy if IV crush > 25% | CONDITIONAL |
| −3 to −8% | PRIME ENTRY zone (assuming thesis intact) | PRIME ENTRY |
| −8 to −15% | Evaluate fundamentals before entry | EVALUATE |
| Gap down > 15% | Thesis likely broken | PASS |
| IV crush < 20% (any gap) | Premium not crushing — no edge | PASS (override) |

High-concentration filter, execution timing, and put-credit-spread post-earnings rules unchanged.

---

## 11. Current Book Snapshot

Live state in `active_positions.json`. Refreshed via CP Gateway Web API sync (preferred) or OCR upload fallback. The Portfolio page in the Fortress V4 dashboard shows all open legs with live Greeks, alerts, and concentration metrics.

---

## 12. Open Items & Pipeline

- **MSFT de-risking:** Begin systematic reduction — target below 50% NLQ by December 2026. See §7.
- **QuantData tools — market hours test pending:** `qd_get_volatility_skew` and `qd_get_exposure_by_strike` confirmed unavailable outside market hours; retest tomorrow during market hours to confirm per-ticker functionality. If confirmed, update §5 strike selection workflow.
- **QuantData tools — widget-locked:** `qd_get_dark_pool_levels` and `qd_get_order_flow` currently return SPX data only (widget locked to SPX). Per-ticker dark pool and order flow unavailable until resolved upstream in quantdata-mcp.
- **SPY hedge:** Currently missing. Required when Net Liq > $50K per §2.D. Add before next new entry.
- **Dashboard settings alignment:** Settings persona, strategies, roll DTE trigger, and profit target have been updated to match this strategy document (v3.8.0). Verify via `get_settings_narrative()`.
- **Earnings blocklist:** Maintain `earnings_blocklist.json` — auto-fetcher available via the Earnings page.
- **ibind OAuth:** Configured, pending IBKR activation — would eliminate daily CP Gateway browser login.
- **Catalyst gate (NEW 2026-06-16):** The §4 binary-event timing rule is now codified and displayed — backend `get_macro_events()` / `set_macro_events()` (advisory `defer_advisory` when a high-impact FOMC/CPI/PPI/NFP/PCE event is within the defer window), surfaced on the Parapet Briefing event-horizon row + amber defer banner. Implements the prior Sprint 14 `intel.events` backlog item via a Claude-curated store (Claude has FRED/FMP; the backend does not). Advisory only (§15.1). Follow-ups: settings-promote `defer_days` and `news_spike_cooldown_days`; wire the advisory into `pretrade_check`; add a per-ticker news scan (`qd_get_news_articles` / FMP `news`). Full design: `docs/CATALYST_GATE_PROPOSAL.md`.
- **Vol-regime + feedback tools (NEW 2026-06-16):** `get_vix_term()` adds a VIX-vs-VIX3M term-structure read (contango favors premium selling; backwardation = tighten/defer) as a complement to the regime score. `journal_analytics.py` computes expectancy/win-rate by strategy and by IV-rank/DTE/short-delta at entry, reading the new **trade-outcomes store** (`log_trade_outcome()` / `get_trade_outcomes()`, MCP v4.8.0) — a structured closed-trade sidecar that captures the entry conditions the prose journal omits. Log a record at each close. (Design: `docs/JOURNAL_FEEDBACK_LOOP.md`.) Ex-dividend assignment-risk check added to the workflow (FMP `dividends-calendar`, verified on-tier) for ITM short calls near ex-div. All advisory (§15.1).

---

## 13. Calendar Events (Next 30 Days)

Live calendar maintained in `earnings_blocklist.json` and visible in the dashboard Earnings page.

---

## 14. Change Log

- **v3.11 (July 7, 2026):** Consolidated rules update — see **`STRATEGY_v3_11_UPDATE_2026-07-07.md`** (canonical delta; supersedes conflicting sections here). Two-bucket architecture (§2-bis), hybrid XSP-base income book (replaces parts of §2/§4), β-DD concentration caps (replaces §7 control metric), B-2 hedge formula (replaces §2.D fixed floor), roll doctrine v2 (§5), weekly-close de-risk rules (§6/§7), LEAP salvage doctrine (new), dynamic pacing (§4), compliance-score measurement (§15). Executed same day: GOOGL LEAP trim, MSFT salvage (310/450 vertical + 340C-unit exit), hedge tranche 2, tranche 3 cancelled — cluster 97.3%→69.5%. (v3.10 designation was consumed by the Sprint 19 enhancement spec `STRATEGY_ENHANCEMENTS_v3_10.md`.)
- **v3.9.0 (June 8, 2026):** §2.F–H CSP, Iron Condor, Covered Call formally added as strategies. §2.5 Strategy Selection Framework: regime gate (bullish→PMCC/CSP, neutral→IC, bearish→IC/CSP-far-OTM) applied before yield comparison within allowed set. §4 bid-ask two-tier threshold: 5% advisory (new), 10% hard block (unchanged). `get_strategy_metrics()` and `check_liquidity()` MCP tools added (fortress_mcp v4.4.0, 67 tools). yfinance GEX/vol-skew backend (`get_gex()`, `get_vol_skew()`) deployed on VPS and confirmed working. Parapet Candidates tab shows "Rec" strategy badge for tradeable rows. §8 workflow step 3 updated to reference new MCP tools. §15.6 updated: fortress_mcp v4.4.0; three new `/api/options/` endpoints; QuantData qd_get_volatility_skew and qd_get_exposure_by_strike status updated.
- **v3.8.0 (June 1, 2026):** §1 advisory-system framing added. §4 dual IV rank confirmation gate (yfinance + QuantData). §5 live GEX-by-strike as primary short-strike anchor; vol skew gate added; delta entry target (0.25–0.30) codified separately from roll trigger (0.35). §7 MSFT formal de-risking plan added (target: below 50% NLQ by Dec 2026). §8 workflow updated for new tools. §12 open items updated: QD-01 partially resolved (iv_rank confirmed per-ticker; dark pool/order flow still SPX-locked; vol skew and GEX pending market-hours confirmation). §15.6 tool stack updated for fortress_mcp v4.2.0, standalone quantdata-mcp.
- **v3.7.3 (May 31, 2026):** §2C and §5 strike selection updated — short put strikes now anchored $5 below nearest DP floor or GEX put wall. Trade Builder auto-suggests anchored strikes with ⚓. §8 Trade Builder workflow updated.
- **v3.7.2 (May 29, 2026):** §15.6 tool stack updated — V4 WSL local deployment; yfinance ATM options IV replaces QuantData per-ticker IVR.
- **v3.7 (May 18, 2026):** §15.6 QuantData MCP integration. §8 workflow updated. §7 Market Regime Filters table added.
- **v3.6 (May 5, 2026):** §5 Critical Gamma threshold tightened from 0.40 to 0.35. §7 margin floors normalised to USD.
- **v3.5 (May 4, 2026):** §2.D SPY hedge enforcement; §2.E Jade Lizard credit gate.
- (Earlier) v3.4–v3.0: Delta monitoring, concentration override, source-of-truth hierarchy, post-earnings playbook.

---

## 15. How the Framework is Enforced

### 15.1 Signaling vs. Blocking

**This is an advisory system.** No tool blocks a trade. Tools warn; humans decide. Discipline is a human responsibility, not a software-enforced state. Every button in the dashboard is technically clickable; every script can be overridden; every alert can be dismissed.

All thresholds in this document — delta, IVR, concentration, regime score, DTE — are signals for conscious review, not automatic triggers. When a threshold is breached, the correct response is to evaluate the position deliberately and decide. Acting mechanically on thresholds without judgment defeats the purpose of the framework.

**What tools do:** surface relevant data (IV/HV spread, GEX walls, dark pool floors, earnings dates, concentration percentages); flag rule conflicts visually — amber for warnings, red for critical conditions; pre-fill recommended actions for human review; log decisions and outcomes.

**What tools do not do:** disable trade-execution paths in IBKR; block the user from clicking past a warning; auto-correct the book; override your judgment when judgment differs from the framework.

**Visual conventions:** Green = position or candidate is within all framework parameters. Amber = parameter approaching a threshold (e.g., delta 0.30–0.35, position 30–50% concentration, VIX above 25). Red = parameter has crossed a critical threshold (e.g., delta > 0.35, position > 50% concentration, dark pool floor broken).

### 15.2 Enforcement Layers

| Layer | How rules are applied |
|---|---|
| Manual checklist | Pre-trade workflow in §8. Each step verified by the trader. |
| Code-enforced gates | Dashboard pre-trade gate (§3.3 exclusion, §4 earnings, §7 concentration, §7 VIX). `workflow_02_entry_scoring.py` rejects within 10-day blackout. Jade Lizard validator rejects if credit ≤ width. |
| Surfacing & alerts | Daily QuantData Summary, IV Crush Report, Dark Pool Alert. Profit-take alerts. Dashboard surfaces all of the above. |
| Decision logic helpers | Stop-loss aggregator (§6 multi-signal), roll evaluator (§5), post-earnings playbook (§10), Jade Lizard validator (§2.E), SPY hedge coverage (§2.D). |

### 15.3 Authority Hierarchy When Sources Conflict

**Strategy document > Tool behavior > Memory.** If a tool produces a recommendation that contradicts a rule in this document, the rule wins. If memory contains a rule that contradicts this document, this document wins.

### 15.4 What This Means for Tool Development

Tools may add safety beyond what this document requires. They may not subtract safety. Tools may surface information faster than manual review. They may not bypass review entirely. If a tool's behavior diverges from the strategy document, the tool is wrong and gets corrected.

### 15.5 Review Cadence

Strategy document: review quarterly or after significant outcome events. Tool stack: review monthly — tools should evolve faster than strategy. Memory: review weekly.

### 15.6 Tool Stack Inventory (v4.4.0, June 2026)

**Frontend — Fortress V4 Dashboard (React/Vite)**

React 19 + TypeScript + Tailwind CSS SPA. Runs locally on WSL, served via nginx at `http://localhost`. Key pages:

| Page | Function |
|---|---|
| Dashboard / Briefing | Macro Regime Score, Net Liq, Daily P&L, Morning Brief, Priority Orders |
| Trade → Candidates | IV Rank screener — yfinance-based IVR, full universe |
| Trade → Market Intelligence | Per-ticker GEX walls, dark pool levels, net drift, directional bias |
| Analysis | Price chart with position overlays, Greeks summary, vol analytics |
| Portfolio | Per-leg Greeks, DTE triage, concentration alerts, roll prompts, journal |
| System → Settings | Strategy parameters, ticker universe, IBKR auth mode, QuantData login |

**Backend — Python/FastAPI (WSL)**

REST API at `http://localhost:8081/api/`. Running as `fortress-dashboard-v4.service` (systemd). Key endpoints: `/api/briefing`, `/api/candidates`, `/api/market-intelligence`, `/api/positions`, `/api/manage/roll_all`, `/api/manage/stop_loss_all`.

**MCP Servers (Claude Desktop)**

Two MCP servers registered in `claude_desktop_config.json`:

| Server | Tools | Notes |
|---|---|---|
| `fortress-dashboard` | 67 tools (v4.4.0) | Portfolio, orders, journal, IBKR sync, market intel, GEX, skew, liquidity, strategy |
| `quantdata` | 26 widget tools | Live QuantData data via standalone quantdata-mcp |

**New fortress MCP tools (v4.4.0):**

| Tool | Endpoint | Notes |
|---|---|---|
| `get_gex(ticker)` | `GET /api/options/gex/{ticker}` | yfinance + BS gamma; works outside market hours |
| `get_vol_skew(ticker)` | `GET /api/options/vol-skew/{ticker}` | IV skew, term structure, skew_25d/10d |
| `get_strategy_metrics(ticker)` | `GET /api/options/strategy_metrics` | PMCC/CSP/IC/PCS/Diagonal comparison; regime-scored |
| `check_liquidity(ticker)` | `GET /api/options/liquidity/{ticker}` | Bid-ask spread quality grade A–D |

**QuantData MCP — per-ticker status (tested 2026-06-08):**

| Tool | Status |
|---|---|
| `qd_get_iv_rank(ticker)` | ✓ confirmed per-ticker |
| `qd_get_volatility_skew(ticker)` | ✗ broken — use `get_vol_skew()` [fortress] instead |
| `qd_get_exposure_by_strike(ticker)` | ✗ broken — use `get_gex()` [fortress] instead |
| `qd_get_dark_pool_levels` | ✗ widget locked to SPX |
| `qd_get_order_flow` | ✗ widget locked to SPX |

Credentials at `~/.quantdata-mcp/config.json`. Refresh via `quantdata-mcp setup --auth-token "..." --instance-id "..."` when token expires (~30 days). After refresh, restart Claude Desktop.

**IVR / IV Source**

workflow_01 and workflow_05 use yfinance ATM options chain IV + 52-week rolling HV. `qd_get_iv_rank(ticker)` [quantdata] used as live cross-check before entry. Max pain (workflow_08) uses yfinance options chain.

**Broker Integration — IBKR**

- **CP Gateway** (active, requires daily browser login): `https://localhost:5000`
- **ibind OAuth 1.0a** (configured, pending IBKR activation): fully headless
- Greeks backend: `web_api` (CP Gateway + OPRA, preferred) → `bs_yfinance` (fallback)

**Workflow Scripts**

`workflow_01` through `workflow_08` in `~/fortress-v4-api/quant/`. Run via dashboard Scripts page, MCP `run_script()`, or APScheduler (automated).

**State Files**

All in `~/fortress-v4-api/quant/`: `active_positions.json`, `earnings_blocklist.json`, `ticker_universe.json`, `alerts.json`, `journal.json`, `fortress_config.json`.

— End of document —
