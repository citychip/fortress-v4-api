# Strategy Amendment Proposal — Two-Bucket Architecture (v3.9 → candidate v3.11)
**Status: ADOPTED 2026-07-07 (all decisions taken same day: VWCE only · seed half now/half post-CPI · 20% target · HYBRID income book). Pending: B-2 hedge formula + fold-in to `01_Portfolio_Strategy` as v3.11. Not financial advice.**

---

## 1. The problem this solves

The 2026 drawdown diagnosis (`REVISED_RECOVERY_STRATEGY_2026-06-26.md`) is unambiguous: **−$21k came from concentrated long mega-cap tech LEAPs + dead OST; the income engine is green.** Yet the current architecture forces every recovery decision through the options account:

- De-concentration happens trade-by-trade (trims, ladders, alerts) and the freed capital sits in USD cash waiting to be redeployed *into the same account* — so cluster % falls slowly and re-risks easily.
- The premium engine carries gates whose only purpose is managing single-name event risk: earnings blackout, ex-div assignment, news-spike cooldown, per-name concentration caps — plus a scanner earnings-null bug that has now twice mislabeled blackout names as PRIME.
- The SPY hedge floor ($20–30k) is sized against the leveraged tech-LEAP book. Hedges are pure drag; the bigger the beta book, the more drag we must carry.
- Reliability risk concentrates in one venue: one IBKR session, one gateway, one toolchain.

## 2. The proposal in one line

**Split the portfolio into a boring EUR core that needs no management (Bucket A) and a smaller, purely-US options income engine (Bucket B) — and shift Bucket B's default income vehicle toward cash-settled index spreads.**

---

## 3. Bucket A — EUR core (reliability)

**Vehicle:** accumulating UCITS ETF, bought on Euronext **inside the same IBKR account** (no cash withdrawal needed; convert USD→EUR in-account).

- ✅ **A-1 DECIDED 07-07: VWCE only** (Vanguard FTSE All-World, acc.) — one line, ~3,600 holdings, includes the US so it does NOT bet against the mega-caps, it just un-levers and diversifies them. (Watchlist names QDVE/CNDX/VVSM are *sector* ETFs (US tech/semis) — they would INCREASE cluster overlap; not for Bucket A.)
- **Why UCITS:** PRIIPs means US-domiciled ETFs are inaccessible to you anyway; accumulating share class is clean under Box 3 (deemed-return regime — no tax penalty vs distributing; watch the actual-return reform).
- **Properties:** no gamma, no expiry, no assignment, no gateway, no session-conflict, no scanner. Zero workflow.

**Sizing & glide path (proposal):**

| Rung | Trigger | Action |
|---|---|---|
| Seed 1 | ✅ **A-2 DECIDED 07-07:** on adoption | move ~**$5.5k** (half the GOOGL-trim proceeds) → EUR → VWCE |
| Seed 2 | After CPI Jul 14 + bank earnings clear | second ~**$5.5k** → VWCE (→ ~16% of NLV) |
| Rung 3 | MSFT ladder fires (382/375 break or 395 strength) | **portion of trim proceeds** tops Bucket A up to target |
| Target | ✅ **A-3 DECIDED 07-07:** | Bucket A = **20% of NLV (~$14k)**; revisit at Q4 (long-run 30%+ still on the table). NB at 20%, cluster ≤60% still needs engine-side trims (MSFT ladder) — removal alone won't get there. |

**Effect on the cluster KPI:** de-concentration by *removal*. Every dollar that leaves for Bucket A cuts the Mag-7 cluster denominator-and-numerator permanently instead of waiting in cash to be re-risked. Cluster 82% → ≤60% becomes arithmetic, not discipline.

## 4. Bucket B — US options engine (profitability)

Fortress as-is, but smaller and cleaner. Existing floors unchanged: avail ≥ $17k, excess liq ≥ $25k, pacing 5/wk, Δ target +0.25–0.35 (Bucket B scope only).

**4a. Income mix shift — index spreads as the default:**

- ✅ **B-1 DECIDED 07-07: HYBRID.** Base book = **XSP** (1/10th SPX) put credit spreads / iron condors, 2–3 laddered expirations: European-style, cash-settled → **no early assignment, no ex-div gate, no earnings blackout, no single-name gap risk**. Three gate categories deleted from the daily workflow. QuantData/GEX/DP toolchain fully supports SPX-complex data.
- Single-name sleeve retained for edge: **max 2 concurrent names**, **post-earnings IV-crush entries only** (JPM Jul 14 pattern — enter after the binary event), rotation-sleeve (tier2 non-Mag-7) preferred. Rationale (scenario analysis 07-07): pure single-name earns ~1.4x gross credit but one MU-type gap (−20% through both strikes, ~$1.7k max loss) erases 6–8 index wins; the hybrid keeps the crush edge and deletes the tail. Pre-earnings single-name premium selling is DISCONTINUED.
- PMCC short-call writing against the remaining LEAPs continues unchanged (that's harvesting, not new risk).

**4b. Hedge floor scales with the beta book:**

- Current §2.D floor ($20–30k notional-protection) was sized for the ~97%-cluster leveraged LEAP book. Propose: ⬜ **B-2:** hedge floor becomes a **function of Bucket B beta-notional** (e.g. protect a −20% SPY move on Bucket B's net long delta-dollars), reviewed at each glide rung. As LEAP trims fund Bucket A, required hedge shrinks → less permanent drag. (Bucket A is unhedged by design — it's the thing we're comfortable holding through a drawdown.)

**4c. What gets simpler / more reliable:**

| Today | After |
|---|---|
| Earnings gate + ex-div gate + news cooldown on every entry | Only on the ≤2-name single-name sleeve |
| Scanner earnings-null bug is a trading risk | Bug only affects the small sleeve (still fix it) |
| Hedge $20–30k against the whole book | Hedge sized to Bucket B only |
| Cluster target fought trade-by-trade | Cluster falls structurally with each glide rung |
| Assignment risk on short legs | None on index spreads (cash-settled) |

## 5. Risks / honest counterpoints

- **Opportunity cost:** if mega-cap tech rips, Bucket A (market weight) lags the current leveraged LEAP book. That is the point — but name it.
- **XSP liquidity** is good but spreads are wider than SPY's penny markets; work mids patiently. SPY remains the fallback (accepting assignment mechanics).
- **FX:** VWCE's listing currency is EUR but ~60% of its exposure is USD underneath — Bucket A reduces *account* FX noise, not economic USD exposure. Don't double-count.
- **Box 3 reform** (actual-return taxation) could change the calculus for high-turnover vs buy-and-hold around 2028 — revisit then.
- **Sample-size humility:** the outcomes store is n=6; "the engine is green" rests partly on the journal, not statistics. The XSP shift also makes future stats cleaner (one underlying, comparable trades).

## 6. Implementation checklist (if adopted)

1. ✅ Decisions taken 07-07: **A-1 VWCE only · A-2 seed half now (~$5.5k) + half post-CPI · A-3 target 20% of NLV (~$14k, revisit Q4) · B-1 HYBRID (XSP base + ≤2-name post-earnings sleeve)**. ⬜ Only B-2 (hedge-floor formula) still open — settle during the v3.11 fold-in.
2. Convert seed USD→EUR in IBKR, buy the ETF on Euronext (manual, TWS — Bucket A never touches the staging pipeline).
3. Settings: add `strategy.bucket_a_target_pct`, glide-rung rule to the trim playbook; re-derive `spy_hedge_min/max_usd` per B-2.
4. Universe: add XSP to `macro`; keep tier2 rotation sleeve as the single-name pool.
5. Docs: fold into `01_Portfolio_Strategy` as **v3.11 §2-bis (Two-Bucket Architecture)**; update WORKFLOW §5 entry flow (index-first); backlog item for the scanner earnings-null fix stays.
6. KPIs on the recovery dashboard: Bucket A % of NLV (glide line), cluster % (existing), hedge-drag $ per month (new).

---

*Prepared 2026-07-07. Grounded in: live book (NLV $70.1k, cluster 82.1%, USD cash $13.1k), REVISED_RECOVERY_STRATEGY_2026-06-26, OptionsPlay 07-06 rotation research, EU/US valuation data (Morningstar, GS, Cambridge Assoc., Schiller — links in SESSION_LOG 07-07).*
