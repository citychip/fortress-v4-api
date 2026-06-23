# Data Sources Optimization Proposal — IBKR-first for time-sensitive data
**v1.0 · 2026-06-10 · companion to docs/DATA_SOURCES.md v1.0**

---

## Premise

The backend already has a working IBKR CP Gateway market-data pipeline (`app/services/ibkr_chain.py`: conid search → strikes → opt conid → `snapshot()` with fields `84` bid, `86` ask, `7633` strike IV, `31` mark, with silent yfinance fallback and sane caching) — **but it is only wired into the roll-candidates engine.** Every analytics route (`options_analytics.py`) and the conditional-alert spot check (`chain.get_spot`) still run on yfinance.

IBKR data is paid-for, real-time (OPRA — per-leg greeks already stream live on positions), and authoritative. yfinance is ~15-min delayed, zeroes bid/ask intermittently intraday, and its IV column is junk on delayed-feed days. The fix is not new infrastructure — it's wiring existing infrastructure into more consumers.

**Decision rule going forward:**

| Data shape | Source |
|---|---|
| Real-time, per-contract, small N (spot, ATM IV, bid/ask on ≤~40 contracts) | **IBKR** (yfinance fallback) |
| Bulk chains, daily history, 22-ticker universe sweeps | **yfinance** |
| Flow, dark pool, max pain, OI/net flow | **QuantData** |
| Independent verification | **Massive** |

---

## Migration candidates (priority order)

### P1 — Conditional alert spot evaluation · `chain.get_spot()`
**Now:** yfinance `fast_info`, **module cache 300s, on ~15-min delayed data** → the MSFT $385 "sell immediately, no debate" critical trigger can fire up to ~20 minutes late.
**Proposed:** IBKR snapshot field `31` on the underlying conid (conid cache already exists, 1h TTL). Cache 30–60s. Silent yfinance fallback (pattern already in `ibkr_chain.py`).
**Impact:** execution triggers evaluated on live prices. Trivial load — one snapshot per alert ticker per `alert_eval` run.

### P2 — Liquidity grades · `/api/options/liquidity/{t}`
**Now:** yfinance bid/ask — reliability ledger: "⚠ intermittently zeroed intraday — liquidity grades flap." The §4 two-tier gate (5% advisory / 10% hard block) is unreliable exactly when it matters (intraday, pre-entry).
**Proposed:** reuse `_snapshot_contracts()` (fields 84/86) for the ATM ±15% window (~20–40 contracts). Add `"source": "ibkr"|"yfinance"` to the payload so Parapet/Claude can see which fed the grade.
**Impact:** stable grades during RTH; hard block becomes trustworthy.

### P3 — ATM IV → IV rank · `/api/options/iv-rank/{t}`
**Now:** BS-inversion from yfinance lastPrice. Works (verified Jun 10) but degraded on Yahoo delayed-feed days, and the `iv_snapshots` history being built toward true IV rank (~Sep 2026) inherits that noise.
**Proposed:** IBKR field `7633` (strike IV, IBKR-computed, real-time) for the ATM straddle — no inversion needed. Keep BS-inversion as fallback; tag each `iv_history.json` entry with its source so the rank series stays interpretable.
**Impact:** cleaner snapshot history = better true IV rank sooner; removes the delayed-feed caveat.

### P4 — Vol skew + term structure · `/api/options/vol-skew/{t}`
**Now:** reads Yahoo's IV column — "❌ never trust." Sprint 14 plans a BS-inversion fix.
**Proposed:** skip the BS-inversion work entirely. Skew needs only ~12–20 contracts per ticker (ATM / 25Δ / 10Δ per expiry) — fetch IV via IBKR `7633`. Less code than inverting, better data.
**Impact:** supersedes the Sprint 14 backlog item; pre-PPI-style IV-crush checks become real-time.

### P5 — GEX · `/api/options/gex/{t}` (hybrid, optional)
**Now:** full yfinance chain, BS gamma from Yahoo IV column (junk on delayed days).
**Proposed hybrid:** keep yfinance for strikes + OI (OI updates daily — delay is irrelevant; full-chain IBKR snapshots across 22 tickers are rate-prohibitive). Compute gamma via BS using **IBKR ATM IV per expiry** (from P3, already fetched) instead of per-row Yahoo IV.
**Impact:** wall/flip levels stop drifting on delayed-feed days at near-zero extra IBKR load.

---

## Explicitly NOT migrating

| Data | Stays on | Why |
|---|---|---|
| SMA200 / price history (stop-loss floors) | yfinance | Daily closes; delay irrelevant |
| HV20, IV–HV spread | yfinance | Daily history |
| Earnings dates/history, implied move | yfinance backend fetch | Works (✅ ledger) |
| Universe IV sweep (`snapshot_iv.sh`, 22 tickers) | yfinance | Bulk scan — IBKR rate limits make this the wrong tool; P3 source-tagging keeps history honest |
| VIX | yfinance/IBKR as-is | Regime input, not execution-sensitive |
| Dark pool, order flow, max pain, net flow | QuantData | Only source; works |
| Macro calendar | FRED/FMP via Claude | Unchanged |

---

## Implementation plan

**Phase 1 (one session):** `ibkr_spot(ticker)` helper in `ibkr_chain.py` (underlying conid → snapshot field 31, 30–60s cache, yfinance fallback). Wire into `chain.get_spot()`. Conditional alerts immediately evaluate on live data. Smallest change, biggest risk reduction.

**Phase 2:** liquidity route → `_snapshot_contracts()` bid/ask; add `source` field to response.

**Phase 3:** iv-rank + vol-skew → field `7633` with BS-inversion fallback; source-tag `iv_history.json` entries.

**Phase 4 (optional):** GEX hybrid (IBKR ATM IV per expiry into the BS gamma calc).

Each phase: deploy backend (`sudo systemctl restart fortress-dashboard-v4`), verify route returns `"source": "ibkr"` during RTH, verify fallback by stopping cp-gateway. Update `docs/DATA_SOURCES.md` reliability ledger after each phase.

---

## Risks & constraints

- **Gateway downtime is the new failure mode.** iBeam drops → every migrated consumer must fall back silently to yfinance (pattern exists; enforce per phase). Reliability inverts: today yfinance flakiness is the risk; after, it's gateway uptime — with the old path as the net.
- **Rate limits:** CP Gateway ~10 req/s global. P1–P4 stay under ~50 snapshot conids per ticker on demand. Do NOT point universe-wide sweeps at IBKR.
- **Entitlements:** positions stream live greeks, so OPRA is subscribed — but verify snapshot on a *non-held* contract returns live (not delayed) quotes during Phase 2. If delayed, P2/P3 degrade gracefully to current behavior.
- **Snapshot warm-up quirk:** first CP snapshot call can return partial rows (needs re-request). `ibkr_chain.py` already lives with this — reuse its handling, don't reimplement.
- **Mark vs last (field 31):** mark price near close/after hours can differ from last trade; for trigger evaluation during RTH this is acceptable (and better than 15-min-old last).

---

## Expected outcome

| Reliability ledger line | Before | After |
|---|---|---|
| Conditional alert spot | yfinance delayed + 300s cache | ✅ live (IBKR), fallback yfinance |
| yfinance bid/ask flapping | ⚠ | ✅ IBKR primary during RTH |
| yfinance IV column | ❌ never trust | bypassed everywhere (7633 or BS-inversion fallback) |
| GEX/skew on delayed-feed days | ⚠ degraded | ✅ (skew), improved (GEX) |
| Sprint 14 "BS-inversion for GEX/skew" | open | **superseded by P4/P3** |
