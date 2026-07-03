# Sprint 21 — Backend Change-List ("Monetize & gate")

**Version:** 1.0 (for review) · **Date:** 2026-07-02 · **Source:** Enhancement Proposal v1 + decisions (adaptive delta; trend gate = warn; fallback = warn).
**Scope:** `options.py`, `config_store.py`, `market_intelligence.py`, `manage.py`, `settings.py`. Grounded in a read of the live code. *Not investment advice; code proposal for the account holder's own system.*

---

## 21.1 — Root-cause bug + adaptive short-call delta

### 21.1a — THE BUG (confirmed in code)
`options.py :: get_strategy_metrics :: target_strike_by_delta()` (~L819–842) has an **inverted bisection direction for calls.**

- For a **call**, |delta| *decreases* as strike rises. The branch does `if abs(d) < delta_target: lo = mid` — which pushes the search to **higher** strikes when delta is already too low, so it converges to the upper bound `spot*2.0`. That is exactly the observed **MSFT $780C / GOOGL $715C / SPY $1485C, `estimated_credit = 0`**.
- For a **put**, |delta| *increases* with strike, so the same branch happens to be correct — which is why **PCS/CSP returned sane ~0.20Δ strikes with real credit** and only the call-based **PMCC/Diagonal** broke.

**Fix — direction-aware bisection:**
```python
def target_strike_by_delta(delta_target, right="C"):
    t = target_dte / 365.0
    if t <= 0 or iv <= 0:
        return spot
    lo, hi = spot * 0.5, spot * 2.0
    mid = spot
    for _ in range(60):
        mid = (lo + hi) / 2
        d1 = (_math.log(spot / mid) + (_RISK_FREE + 0.5 * iv**2) * t) / (iv * _math.sqrt(t))
        d = norm_cdf(d1) if right.upper() == "C" else norm_cdf(d1) - 1.0
        ad = abs(d)
        if right.upper() == "C":
            # |delta| falls as strike rises
            if ad > delta_target: lo = mid      # too much delta → go higher
            else:                 hi = mid      # too little  → go lower
        else:
            # |delta| rises as strike rises
            if ad > delta_target: hi = mid      # too much delta → go lower
            else:                 lo = mid      # too little  → go higher
        if abs(ad - delta_target) < 0.001:
            break
    return round(mid / 5) * 5
```

### 21.1b — Adaptive short-call delta
Add `pick_short_call_delta(ticker, ctx) -> (target_delta, rationale)` and use it for the **PMCC short call (L931)**, **Diagonal short call (L997)**, and any covered-call income leg (replace the hard-coded `0.20`).

```python
def pick_short_call_delta(ivr, regime, weekly_below_200, days_to_earnings, conc_pct):
    base = cfg("strategy.short_call_base_delta")          # 0.30
    lo   = cfg("strategy.short_call_delta_min")           # 0.20
    hi   = cfg("strategy.short_call_delta_max")           # 0.40
    d, why = base, []
    # rich premium → sell further OTM (lower delta), keep upside
    if ivr >= 70:  d -= 0.05 * cfg("strategy.delta_ivr_weight");  why.append(f"IVR {ivr:.0f} high → −Δ")
    elif ivr <= 35: d += 0.05 * cfg("strategy.delta_ivr_weight"); why.append(f"IVR {ivr:.0f} low → +Δ")
    # broken weekly trend → closer strike (more premium + downside cushion)
    if weekly_below_200: d += 0.05 * cfg("strategy.delta_trend_weight"); why.append("below wk200 → +Δ")
    # catalyst window → further OTM to cut gap risk
    if days_to_earnings <= 10: d -= 0.05 * cfg("strategy.delta_catalyst_weight"); why.append("earnings ≤10d → −Δ")
    # over-concentrated name → closer strike doubles as de-risk
    if conc_pct and conc_pct > 20: d += 0.03 * cfg("strategy.delta_concentration_weight"); why.append(f"conc {conc_pct:.0f}% → +Δ")
    d = max(lo, min(hi, d))
    return round(d, 2), why
```
- **Resistance anchor (optional refinement):** after computing the delta strike, snap the short strike to sit at/above the nearest of {weekly WMA62, 52-wk high, GEX call wall} when that level is within ~1 strike, so the cap sits on structure rather than mid-air.
- **Sanity guard:** after building any income structure, `if estimated_credit == 0 → raise/flag` (never emit a $0-credit "income" leg).
- Emit `target_delta` and `delta_rationale[]` on the PMCC/Diagonal dicts.

**Config (add to `config_store.py` `strategy`):**
```
short_call_base_delta: 0.30, short_call_delta_min: 0.20, short_call_delta_max: 0.40,
delta_ivr_weight: 1.0, delta_trend_weight: 1.0, delta_catalyst_weight: 1.0, delta_concentration_weight: 1.0
```
> Note: the existing `strategy.target_delta_low` (0.20) / `target_delta_high` (0.25) are **not currently read** by `get_strategy_metrics` (it hard-codes 0.20). The adaptive engine supersedes them; keep them for the roll logic or deprecate.

---

## 21.2 — Singular `recommended`
`options.py` L1030–1034 currently flags **every** strategy whose `regime_score == best_score` (so PCS/CSP/PMCC/Diagonal are all `recommended=True`).

**Fix:**
1. Add an `annualized_yield` field per strategy: `round(estimated_credit / max(capital_required, 1) * (365 / target_dte), 3)` (the docstring already promises this field; it's currently absent).
2. Rank by `(regime_score desc, annualized_yield desc)`; set `recommended=True` on **exactly one** best that also passes gates (earnings_safe + trend gate 21.4 + concentration 21.5).
3. Set `eligible=True` on the others that pass gates; everything else `eligible=False` with a `gate_reason`.

---

## 21.3 — Unify the regime signal
Today `get_strategy_metrics.regime` = `market_intelligence.overall` (per-name), while `get_briefing.macro_regime` is a separate top-level read — they can disagree (per-name **bullish** vs briefing **bearish** vs SPY GEX **negative**), with no single labeled gate.

**Fix (`market_intelligence.py :: _synthesize_regime`):** return a single `regime_gate` object and have **both** `get_briefing` and `get_strategy_metrics` read it:
```json
"regime_gate": {
  "label": "bullish|neutral|bearish",
  "source": "synthesized",
  "inputs": [
    {"source": "gex",      "label": "positive", "score": +1},
    {"source": "macro",    "label": "bearish",  "score": -1},
    {"source": "vix_term", "label": "contango", "score": +1},
    {"source": "net_drift","label": "…",        "score": …}
  ]
}
```
Precedence already exists via the 15.3/16.6 score sum; this just **exposes the inputs** and makes the gate a single canonical field so the two endpoints can't diverge.

---

## 21.4 — Trend-filter entry gate (mode = **warn**)
Add `weekly_trend_state(ticker)` → reads the weekly 200-SMA (via `get_chart_data(interval="1wk")` or a cached SMA) and returns `{above_200w: bool, sma_200w, spot}`.

- In `get_strategy_metrics`: add a top-level `trend_gate` field and, when `spot < sma_200w`, apply a `regime_score` penalty (−2) **and** set `eligible=False` on bullish premium-sells — but **do not remove them** (warn, not block).
- In `manage.py :: pre_trade_check` advisories (Sprint 16.1 pattern): add a `trend` sub-flag → amber `caution` when below wk-200, never flips PROCEED/BLOCKED.
- **Config:** `strategy.trend_gate_enabled: true`, `strategy.trend_gate_mode: "warn"`, `strategy.trend_gate_sma_tf: "1wk"`, `strategy.trend_gate_sma_len: 200`.
- **Live validation set (2026-07-02):** JPM/JNJ above wk-200 (pass); CVX/COST/WMT below (warn); XOM marginal. Use these as the fixture.

---

## 21.5 — Concentration hard-gate (mode = **warn**, hardenable)
`manage.py :: pre_trade_check` / candidates: add a `concentration` advisory that reads `get_briefing.concentration` (canonical MV/NLV basis, Sprint 20.4) and raises `caution` when the candidate name would exceed **20%** or the Mag-7 cluster would exceed **60%**.
- **Config:** `strategy.single_name_cap_pct: 20`, `strategy.cluster_cap_pct: 60`, `strategy.concentration_gate_mode: "warn"` (flip to `block` later if desired).

---

## 21.6 — Persona re-baseline
`settings.py` / `config_store`:
- `trader_type`: `strategic_speculator` → **`hedged_premium_seller`**.
- `active_strategies`: add `COVERED_CALL, PMCC, PUT_CREDIT_SPREAD, CASH_SECURED_PUT, COLLAR` (the real book); keep the directional set only if still used.
- Turn the **hedge module on** for this persona (settings narrative currently says "no hedge configured" while a live SPY hedge exists).
- Enforce the 20% single-name cap in the settings schema so it's not just a report metric.
- Collar keys already exist (`strategy.collar_put_delta_target 0.25`, `collar_call_delta_target 0.25`) — reuse for Sprint 23.2.

---

## Deploy / test

- **Unit tests:** (21.1) `target_strike_by_delta(0.30,"C")` returns a strike **above** spot with |delta|≈0.30 and non-zero BS credit on MSFT/GOOGL/SPY fixtures; puts unchanged. (21.1b) `pick_short_call_delta` moves the right direction on each nudge and clamps to [0.20,0.40]. (21.2) exactly one `recommended=True` per name. (21.4) below-wk200 fixture flips `eligible=False` + `caution`, not BLOCKED.
- **Wiring:** add any newly-touched out-of-mount files to `deploy_data_sources.sh` `ROUTE_FILES` + `sync_check.sh` `MAP` (Sprint 0 pattern); compile-check + rollback.
- **Live verify (writes-enabled MCP relaunch):** `get_strategy_metrics("MSFT")` PMCC now shows a **non-zero credit** at its adaptive delta with a `delta_rationale`; one `recommended`; `regime_gate` present; `trend_gate` present.

## Sequencing
21.1a (bug) → 21.1b (adaptive) → 21.2 (singular) → 21.6 (persona/caps, low-risk) → 21.3 (regime) → 21.4/21.5 (gates, depend on the weekly-SMA ingest from 22.1). 21.1a alone restores real premium capture and is the single highest-value change.
