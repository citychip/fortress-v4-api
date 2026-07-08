# Portfolio Management Strategy
**Version 3.11 — consolidated edition, July 8, 2026**

> **This is the SINGLE canonical strategy spec.** It consolidates `01_Portfolio_Strategy_v3_9.md` (base), `STRATEGY_ENHANCEMENTS_v3_10.md` (research addendum), and `STRATEGY_v3_11_UPDATE_2026-07-07.md` (adopted delta) into one document — those three are superseded and archived (the v3.11 UPDATE stays available unedited as the external-review adoption record until Manus v6 lands). Where an old doc conflicts with this one, this one wins. Statuses reflect the 2026-07-08 backend state (Sprint 27: β-DD block, dynamic pacing, matched-vertical exemption, weekly-close alerts all LIVE).

---

## 1. Governance

The decision-maker is you, the trader. **This is an advisory system, not an automated one.** All thresholds, signals, and tool outputs are inputs to your judgment — not triggers for automatic action. When a parameter is breached, the correct response is to review the position and decide consciously, not to act mechanically.

AI tools are analytical inputs, not decision sources. When another AI recommends a trade, flag it before executing so it can be evaluated against the active strategy — and **cross-check external-AI claims against live data before acting** (the 07-07 review loop caught five material errors, including a naked-upside trade construction and phantom fills). Before every execution, verify ticker, earnings date, strike direction, and limit price.

**Source-of-truth hierarchy:** this strategy document > tool behavior > memory. Tools may add safety beyond this document; they may not subtract it.

---

## 2. Architecture — Two-Bucket Portfolio (v3.11)

| Bucket | Contents | Target | Management |
|---|---|---|---|
| **A — Core** | VWCE (accumulating UCITS all-world), bought on Euronext inside the IBKR account | **20% of NLV (~$14k)**, revisit Q4'26 | None. Never touched by the options workflow. |
| **B — Engine** | Everything else: LEAPs/verticals, PMCC shorts, income spreads, SPY hedge | remainder | Full Fortress workflow |

Funding glide: seed 1 ~$5.5k (⏳ pending Euronext order) · seed 2 ~$5.5k post-CPI Jul 14 · thereafter topped up from trim/salvage proceeds until target. Rationale: de-concentration by removal; bucket A has no gamma, expiry, venue, or session risk; fits the 2–3 sessions/week operator cadence (§12).

---

## 3. Active Strategies (Bucket B)

### 3.1 Income book — HYBRID (v3.11; replaces the old single-name-first income flow)

1. **Base book = XSP** (mini-SPX, cash-settled European) put credit spreads / iron condors, 2–3 laddered expiries, **minimum 45–60 DTE**. No assignment, no ex-div, no earnings gates apply.
2. **Single-name sleeve: max 2 concurrent names, POST-earnings IV-crush entries only.** Pre-earnings single-name premium selling is **DISCONTINUED**. Prefer non-Mag-7 (tier2 rotation sleeve).
3. **XSP entry gates:** open the book when **(index IVR ≥ 25 OR VIX ≥ 18)** AND **VRP (IV − HV20) ≥ 3.5 vol-points** AND **VIX/VIX3M < 0.95 (contango)**.
4. **Stored ladder blueprint** (execute when the gate opens; ~$21k income allocation): Tranche 1 — XSP PCS, 45 DTE, short Δ0.15, 10-wide, ×10 (~$10k margin) · Tranche 2 — same at 60 DTE. Work combos at the mid; re-check gates per tranche.

Rationale: one single-name gap through both strikes (MU-type, −20%) erases 6–8 index wins; the hybrid keeps the documented post-crush edge and deletes the tail.

### 3.2 Strategy definitions

**A. PMCC (Poor Man's Covered Call)** — long LEAP ~640 DTE, 25–30% ITM, Δ0.78–0.85; short monthly call 30–45 DTE (written 60+ days out under the operator cadence), Δ0.25–0.30 at entry. Strict 1:1 coverage — never hold an uncovered LEAP.

**B. Diagonal** — long call 30–90 DTE + shorter-DTE short call; tactical/post-earnings, not core income. Post-earnings playbook: enter morning after earnings when IV crush ≥ 25% AND gap within ±8%, 10:00–11:00 ET; long Δ0.55–0.70, short 14–21 DTE Δ0.25–0.30 at first resistance; net debit ≤ 50% of long value; exit at 50% max profit; never within 10 days of next earnings.

**C. Put Credit Spread** — short put Δ0.15–0.20 anchored below the nearest DP floor / GEX put wall (within 12% of the delta strike); 30–45 DTE single-name (post-earnings only), 45–60+ DTE on XSP.

**D. SPY Hedge** — see §7 (B-2 formula; the old fixed $20–30k MV floor is RETIRED).

**E. Jade Lizard** — short OTM call + short OTM put spread; consolidation + elevated IV only. Credit must exceed put-spread width (validator-enforced).

**F. CSP** — Δ0.20–0.30, 30–45 DTE, fully cash-secured; wheel exit via covered calls if assigned.

**G. Iron Condor** — short strikes Δ0.15–0.20 both sides, wings 2–5 strikes, 30–45 DTE; neutral/range regimes with elevated IV; close at profit target or 21 DTE; never through earnings; blocked in strong trends.

**H. Covered Call** — Δ0.25–0.30, 30–45 DTE against held stock only (wheel exit). Never buy stock to write calls — use PMCC.

**LEAP call-writing / collar overlay (v3.10 §8, now tool-surfaced):** under-written LEAP cores are auto-flagged by `get_covered_call_candidates` (adaptive ~0.30Δ 30–45 DTE call + DTE-matched ~0.25Δ protective put + `collar_net`) and by the Recovery page ⚠ MONETIZE flag (which since 07-08 only fires on genuinely under-written cores). Honor the PMCC guardrails in §6.

### 3.3 Strategy Selection Framework

**Step 1 — regime gate (hard filter):** bullish → PMCC/CSP/PCS/Diagonal/Jade Lizard · neutral → IC/PCS/CSP(far-OTM) · bearish → IC/CSP(far-OTM, Δ≤0.15). **Step 2 — yield comparison** within the allowed set via `get_strategy_metrics(ticker)` (annualized yield, regime score, `recommended` flag). Regime gates first; never override a gate for yield alone.

---

## 4. Name Universe

- **Live source of truth: `get_universe()` / `ticker_universe.json`** — the tool wins over any snapshot.
- Tier 1 core candidates + **tier2 rotation sleeve (added 07-07, 14 names):** RMD PYPL HCA CBRE GILD MSI RJF MA CVX XOM PG WMT COST TROW — preference rule: on an IVR/VRP tie take the non-Mag-7 name while the cluster is being glided down. **Macro/index:** XSP (base book), SPX/SPY/VIX (reference/hedge).
- **Excluded (hard, dashboard-enforced):** regulatory-risk names (COIN/HOOD/SMCI), thin-chain small-caps, OST (display only, never recommend). Names with active DOJ/SEC investigations are never entered.
- Outside-universe names are explorable when a setup demonstrably beats universe candidates — journal it; all §5 filters and hard exclusions still apply.

---

## 5. Entry Rules

**Timing:** execute after 10:00 ET; avoid opening volatility; cautious on Opex Fridays; wait 3–5 days after news-driven IV spikes; always limit orders worked at the mid.

**Earnings discipline:** verify the earnings date before EVERY new entry — non-negotiable, and **do not trust a blank scanner field**: `earnings_state: "unverified"` (unknown date) requires a manual `get_earnings_history` check before sizing. No new LEAPs within 2 weeks, no new put spreads within 10 days of earnings. Post-earnings IV-crush morning is the preferred entry window (gap × crush matrix in §11). Hold existing PMCC through earnings — that's what it's built for.

**Quality filters:**
- Bid-ask: ≥10% of mid hard block · 5–10% advisory (journal it) · <5% good. Use `check_liquidity` — since 06-20 it grades the **OTM short-leg zone** (|Δ|≤0.35): read `short_leg`/`tradeable_spread_pct`, not just ATM. If `get_contract_price` returns no quote on the candidate's strikes, the trade is dead (MAR pattern).
- OI > 100/leg; daily option volume > 1K (spreads) / > 10K (LEAPs preferred).
- **IVR ≥ 25** from fortress `get_iv_rank(ticker)` (IBKR-first). ⚠ The old dual-confirm with `qd_get_iv_rank` is DEAD — that tool is broken upstream (ticker ignored). Independent cross-check when a number looks off: `massive` chain IV.
- **VRP gate (v3.10):** IV − HV20 ≥ 3 pp advisory floor (`vrp_min_entry_pp`); scanner signals GOOD ≥ 5 pp. IVR without VRP is not an edge.
- **Catalyst gate:** `get_macro_events()` defer-advisory when a high-impact event is inside the window (default 2d) — hold new premium through binary prints. **VIX term structure** (`get_vix_term`): contango favors selling; backwardation/flat = tighten or defer.
- **Trend gate (Sprint 21.4/22.1):** bullish premium-sells below the weekly-200 SMA are flagged (`below_wk200`) — the losing setup. Check `get_technical_gate` per name.

**Pacing — dynamic (v3.11, briefing-computed since 07-08):** VIX < 18 → **2** new entries/week · 18–25 → **3** · > 25 → **5**. Rolls, closes, and hedge maintenance don't count (⚠ the exclusion keys on journal `framework_rules` — tag hedge/roll journals). `strategy.entries_per_week_max` remains the absolute ceiling. After a stop-loss event: 3-day cooling-off.

---

## 6. Position Management

### Short call strike selection
Primary anchor: GEX call wall (`get_dp_floors_and_gex` / quantdata exposure when live) with Δ0.25–0.30 as the secondary check; chart resistance as tie-breaker. Short puts: $5 below the nearest DP floor / GEX put wall within 12% of the delta strike. The 21.1b **adaptive delta engine** (base 0.30, clamp 0.20–0.40, IVR/trend/catalyst/concentration nudges + `delta_rationale`) drives tool recommendations.

### Delta thresholds (short legs)
| Delta | Status | Action |
|---|---|---|
| 0.25–0.30 | Entry target | preferred zone |
| 0.30–0.35 | Watch | monitor; consider roll on next weak day or at profit target |
| > 0.35–0.40 | Roll doctrine v2 | see below |

### Roll doctrine v2 (v3.11 — replaces all earlier roll rules)
- **KEEP-names** tested (Δ > 0.40): roll **out-and-up for a small debit** (delta relief) or close the spread. **Same-strike out-rolls are FORBIDDEN on keep-names** (they raise delta and trap you short).
- **EXIT-names:** the tight cap IS the hedge on the way out — same-strike credit rolls allowed, but the position must carry an active exit rule (§8).
- **Expiry-matched verticals are EXEMPT from roll/stop/gamma flags** — defined-risk packages managed at the package level (weekly-close rules), never leg-rolled. ✅ Backend-enforced since 07-08 (`vertical_exempt: true`; if a vertical still flags, the coverage detection broke — investigate).
- Roll leg direction: BUY-to-close the front short + SELL-to-open the back leg. Always combos. Never sell a new short before closing the existing one (the naked-upside trap — TWS Roll Builder pre-fills qty and ask; verify both).
- Never roll winners; never roll losers into earnings; never roll on strong-up days (wait one session).

### Profit + time discipline (v3.10, tool-live)
Defined-risk credit spreads: research default = manage at **50% of max profit** (config currently user-set at 80 — decision O-4); ALWAYS manage at **≤ 21 DTE** regardless of P&L (gamma outweighs remaining theta). `get_profit_targets` scans both triggers on every open short leg.

### PMCC guardrails (v3.10)
(a) Never sell a PMCC short below the long-leg breakeven (guaranteed loss — tool-blocked advisory). (b) Roll the long LEAP early: Δ ≤ 0.70 or ≤ 120 DTE → new 12–18-month LEAP (`get_leap_roll_all` flags). (c) Close the short before the underlying's earnings.

### LEAP salvage doctrine (v3.11 §G — from the 07-07 MSFT/AMZN executions)
For each underwater LEAP unit (LEAP + its short), classify then act:
- **Healthy leg** (recovery odds ≥ ~40%, technicals hold): **convert to an expiry-matched vertical** — BTC the mismatched short, STO a same-expiry higher strike for net credit (lower breakeven, duration match, credit). Precedent: MSFT → Jan'28 310/450 @ +$21.35 cr; AMZN → Jan'28 200/280 + 200/300, ~$6.9k harvested, β-DD 45→19%.
- **Weak leg** (odds ≤ ~35%, technicals broken): **accelerated exit** — sell the LEAP + BTC its short as a combo. Sunk cost is irrelevant.
- Watch item: any remaining calendar-mismatch (currently AAPL Jan'27 shorts vs Jan'28 LEAPs) gets the same conversion playbook if the short pushes Δ > 0.40.

---

## 7. Risk Management

### Concentration — β-Dollar-Delta caps (v3.11; MV/NLV is reporting-only)
- **Metric: per-ticker β-DD = Σ(qty × delta × 100 × spot)** per underlying, as % of NLV. ✅ Live in the briefing since 07-08: `beta_dd` block + `frozen[]` list (SPY hedge/OST gate-exempt).
- **Soft gate 30% NLV:** name FROZEN — no new long entries, no duration adds, no size-ups, no spread-widening. Reduction only via strength-trims, salvage (§6), or weekly rules (§8).
- **Hard backstop 40% NLV at a weekly (Friday) close:** mandatory salvage analysis within one session; execution stays an operator decision.
- Mag-7 cluster glide target ≤ 60% NLV (MV basis, legacy KPI) retained until re-based on β-DD.

### Hedging — B-2 formula (v3.11; fixed $20–30k MV floor RETIRED)
- **Engine β-DD** (what the hedge covers) = Σ long LEAP deltas NET of short calls + net delta of open verticals, β-weighted to SPY; EXCLUDE the hedge itself, cash, Bucket A, inert lines.
- **SPY bear-put-spread MAX PAYOUT (qty × width × 100) must span 25–33% of Engine β-DD.** Premium MV measures cost, not protection. Budget ≤ 5% NLV/yr in net hedge debits.
- **Re-run the formula at every hedge-leg expiry** (next: Aug 21 — Aug legs = ~$22.5k of payout lapse; recompute Engine β-DD live that week before replacing anything). Ignore the backend's legacy `coverage_ok` until re-based.

### Sizing & floors
Max new LEAP cost $5k/position · max sector 40% NLV · Excess Liq ≥ $25k and Available Funds ≥ $17k before any new position (IBKR-live, flagged).

### Prohibited
Uncovered LEAPs · naked puts (spreads only; Jade Lizard's short put is the codified exception) · SPY shares as hedge · selling puts into clear downtrends · entering names under active DOJ/SEC investigation.

---

## 8. De-risk rules — weekly close protocol (v3.11)

- **Authoritative close = the TradingView weekly bar close on the primary exchange feed at Friday's NY close** (yfinance is dividend-adjusted — the source of the ~$5 MSFT wk-200 divergence).
- **Break rule:** Friday weekly close < the active weekly-200 SMA → reduce the position 50%, routed **the following Monday 09:30–10:00 ET** (rule deliberately written in ET — DST-proof).
- **Catastrophic-gap exception:** weekend gap > 5% beyond the SMA → do NOT market the open; defer to the next Phase-1 pricing pass, work limits once early IV expansion cools.
- **Strength rule (never delete):** trim-into-bounce — e.g. MSFT close ≥ 395 (`baa3bc98`) → trim a LEAP/vertical tranche.
- **Implementation:** use `weekly_close_below` / `weekly_close_above` conditional alerts (live since 07-08 — EOD pass, Friday bar only, wick-immune). In force for MSFT: Fri close < ~383 → cut the 310/450 vertical 50% Monday.
- LEAPs generally: the weekly/200-day SMA break on volume, unrecovered in 1–2 sessions, is the thesis stop. Do not average down into a broken thesis.

---

## 9. Exit Rules (income legs)

- PCS/defined-risk: profit target per §6 discipline; close at 21 DTE regardless; never through earnings.
- Jade Lizard: close the package at 50% of max credit; if the short call is threatened (Δ > 0.30), close the call leg first.
- LEAPs: no mechanical target; exit on thesis change, §8 break rules, or β-DD cap pressure (§7). Log EVERY close same-session (`log_trade_outcome` + journal) — §10 depends on it.

---

## 10. Measurement — compliance over P&L until n ≥ 30 (v3.11)

The trade-outcomes store carries a documented bias (unrecorded early wins, journal `e7e737c8`) — it **must not drive rule changes**. Until **n ≥ 30 fully-logged trades**: assume published base rates (0.15–0.20Δ PCS ≈ 70–80% win rate); score each trade on **entry-gate compliance** (all gates passed at entry = success, regardless of P&L); `cap_pacing` checks the XSP margin ceiling (≤$30k) for index entries and the 30% β-DD soft gate for single-name entries. No strategy changes justified by short-term P&L in the interim.

---

## 11. Post-Earnings Entry Playbook

Gap × IV-crush matrix (unchanged):

| Gap | Rule | Verdict |
|---|---|---|
| > +5% | missed move, IV low | PASS |
| +2 to +5% | buy if crush > 30% | CONDITIONAL |
| ±2% | buy if crush > 25% | CONDITIONAL |
| −3 to −8% | thesis intact | **PRIME ENTRY** |
| −8 to −15% | check fundamentals first | EVALUATE |
| < −15% | thesis likely broken | PASS |
| crush < 20% (any gap) | no edge | PASS |

Entry 10:00–11:00 ET the morning after. This playbook is now the ONLY single-name entry path (§3.1).

---

## 12. Operator cadence — 2–3 sessions/week (v3.11 constraint)

Session types: **management** (OPEN checklist, risk sweeps, doctrine-v2 rolls) · **trade** (full WORKFLOW §Trade Session Procedure whenever orders are placed — analyze with gateway up → exact-orders deliverable → manual TWS execution → verify/log) · **Friday close check** (now largely automated via weekly_close alerts). Standing consequences: base book ≥ 45–60 DTE; PMCC shorts written 60+ days out; de-risk keyed to weekly closes; all price rules close-confirmed (wick-immune).

Daily/weekly tool routine, data-source canon, and troubleshooting live in **`WORKFLOW.md`** and **`DATA_SOURCES.md`** (not duplicated here). System/deploy in **`SYSTEM.md`**.

---

## 13. Enforcement Model

**Signaling, not blocking.** No tool blocks a trade; tools warn, humans decide. Green = within parameters · amber = approaching a threshold · red = crossed. Layers: manual pre-trade checklist (WORKFLOW) → code-enforced gates (exclusions, earnings blackout, concentration, validators) → surfacing/alerts (briefing actions, conditional alerts, scheduled tasks) → decision helpers (stop-loss aggregator, roll evaluator, salvage math, hedge coverage). Tools that diverge from this document are wrong and get corrected. Review cadence: strategy quarterly or after significant outcomes; tool stack monthly; memory weekly.

---

## 14. Change Log

- **v3.11 consolidated edition (Jul 8, 2026):** merged v3.9 base + v3.10 addendum + v3.11 delta into this single spec; statuses updated for Sprint 26/27 (β-DD block, dynamic pacing, matched-vertical exemption, weekly-close alerts, profit-targets scan all LIVE). Superseded docs archived; `STRATEGY_v3_11_UPDATE_2026-07-07.md` retained unedited as the external-review adoption record.
- **v3.11 (Jul 7, 2026):** two-bucket architecture · hybrid XSP income · β-DD caps 30/40 · B-2 hedge formula · roll doctrine v2 · weekly-close protocol · LEAP salvage doctrine · dynamic pacing · compliance-score measurement. Executed same day: GOOGL trim, MSFT + AMZN salvages, hedge tranche 2, tranche 3 cancelled; cluster 97.3% → 59.6%.
- **v3.10 (Jun 22, 2026):** research-codified: 50%-take + 21-DTE discipline, VRP gate, PMCC guardrails, β-vega dial, cluster concentration, LEAP call-writing/collar (§8).
- **v3.9 (Jun 8, 2026):** CSP/IC/CC formalized; strategy-selection framework; two-tier bid-ask; strategy_metrics/check_liquidity tools.
- **v3.8 → v3.0:** advisory framing, GEX anchoring, delta thresholds, hedge enforcement, Jade Lizard gate, post-earnings playbook, source-of-truth hierarchy. Full history in the archived v3.9 doc.

— End of document —
