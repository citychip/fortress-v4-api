"""
Household endpoint — v4.0 Phase 2 (backlog O-10), read-only.

Promotes the Combined_Portfolio.xlsx / lib/household.ts client-side aggregation
to a live BACKEND view so it is exposed to the MCP (get_household_overview /
get_household_concentration) and the Parapet Household page can swap its seed for
/api/household unchanged.

Two-leaf household = Leaf B (IBKR, computed LIVE from get_active_positions) +
Leaf A (eToro, a STORED SNAPSHOT in household_state.json — eToro has no API).
Leaf A is self-hedged by the copied trader, so household *delta* is Leaf B only.

READ-ONLY. Never places or blocks a trade. Engine (v3.11) untouched — this is a
thin aggregation over existing computations (state.compute_concentration + fx),
mirroring fortress-parapet/src/lib/household.ts line-for-line so the two never drift.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter

from app.services import state

try:  # fx lives beside state; guard so the route degrades to seed if unavailable
    from app.services import fx as _fx
except Exception:  # pragma: no cover
    _fx = None

router = APIRouter()

_STORE_NAME = "household_state.json"

# Last-resort seed if household_state.json is missing/unreadable entirely (so the
# route degrades gracefully instead of 500ing). Mirrors the JSON store's "seed".
_EMERGENCY_SEED = {
    "as_of": "2026-07-09", "household_eur": 85400,
    "leaf_ibkr_pct": 71, "leaf_etoro_pct": 29,
    "ai_tech_chips_pct": 57.0, "semis_pct": 15.3,
    "single_name_cap": 15, "sector_cap": 25, "group_cap": 35,
    "names": [
        {"ticker": "AAPL", "pct": 15.5}, {"ticker": "GOOGL", "pct": 9.0},
        {"ticker": "AMZN", "pct": 8.4}, {"ticker": "NVDA", "pct": 7.5},
        {"ticker": "MSFT", "pct": 7.2}, {"ticker": "MU", "pct": 3.2},
        {"ticker": "TSM", "pct": 2.8},
    ],
    "sectors": [
        {"sector": "Technology", "pct": 23.5}, {"sector": "Semis", "pct": 15.3},
        {"sector": "Comm services", "pct": 9.6}, {"sector": "Cons cyclical", "pct": 8.8},
        {"sector": "Defensives", "pct": 7.8},
    ],
    "source": "seed",
}


def _load_store() -> dict:
    """Load the eToro snapshot + caps/meta store from BASE_DIR (= FORTRESS_DATA_DIR,
    i.e. the repo's quant/ dir at runtime — NOT the repo root)."""
    path = state.BASE_DIR / _STORE_NAME
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _fx_rate(store: dict) -> float:
    """EUR/USD rate — live if fx service is up, else the store fallback."""
    if _fx is not None:
        try:
            rate = _fx.get_eur_usd_rate()
            if rate:
                return float(rate)
        except Exception:
            pass
    return float(store.get("fx_fallback", 1.1435))


def _compute_household() -> dict:
    """
    Netted two-leaf household exposure. Mirrors lib/household.ts::getHousehold().

    Returns the full HouseholdData shape (source='live'), or the stored seed
    (source='seed') if the briefing/positions read is unavailable — exactly the
    frontend's try/catch fallback, so the Parapet page behaves identically.
    """
    try:
        store = _load_store()
    except Exception:
        # Store missing/unreadable — never 500 the dashboard.
        return dict(_EMERGENCY_SEED)
    caps = store.get("caps", {})
    etoro = store.get("etoro", {})
    meta = store.get("ibkr_meta", {})
    exclude = set(store.get("ibkr_exclude", ["SPY", "OST"]))
    sector_order = store.get("sector_order", [])
    default_sector = store.get("default_sector", "Defensives")

    try:
        positions = state.get_active_positions()
        nlv_usd = positions.get("net_liq")
        if not nlv_usd:
            return {**store["seed"]}

        fx = _fx_rate(store)
        ibkr_eur = float(nlv_usd) / fx
        etoro_eur = float(etoro.get("total_eur", 0) or 0)
        household = ibkr_eur + etoro_eur
        if household <= 0:
            return {**store["seed"]}

        # Leaf B per-name EUR from canonical concentration (% of NetLiq), ex SPY/OST.
        conc = state.compute_concentration(positions) or {}
        ibkr_name_eur: dict[str, float] = {}
        for tk, pct in conc.items():
            if tk in exclude:
                continue
            ibkr_name_eur[tk] = (float(pct) / 100.0) * ibkr_eur

        # Netted single-name across both leaves.
        name_eur: dict[str, float] = dict(ibkr_name_eur)
        for tk, eur in (etoro.get("by_name") or {}).items():
            name_eur[tk] = name_eur.get(tk, 0.0) + float(eur)
        names = sorted(
            ({"ticker": tk, "pct": round(eur / household * 100, 2)} for tk, eur in name_eur.items()),
            key=lambda r: r["pct"],
            reverse=True,
        )[:7]

        # Netted sector across both leaves (Leaf A sectors seed the map).
        sec_eur: dict[str, float] = dict((etoro.get("by_sector") or {}))
        for tk, eur in ibkr_name_eur.items():
            sec = (meta.get(tk) or {}).get("sector", default_sector)
            sec_eur[sec] = sec_eur.get(sec, 0.0) + eur
        sectors = [
            {"sector": s, "pct": round(sec_eur[s] / household * 100, 2)}
            for s in sector_order if sec_eur.get(s)
        ]

        # AI/tech/chips group % (Leaf A precomputed + Leaf B flagged names).
        ai_eur = float(etoro.get("ai_tech_chips_eur", 0) or 0)
        for tk, eur in ibkr_name_eur.items():
            if (meta.get(tk) or {}).get("ai"):
                ai_eur += eur

        return {
            "as_of": datetime.now(timezone.utc).date().isoformat(),
            "household_eur": round(household),
            "leaf_ibkr_pct": round(ibkr_eur / household * 100),
            "leaf_etoro_pct": round(etoro_eur / household * 100),
            "ai_tech_chips_pct": round(ai_eur / household * 100, 1),
            "semis_pct": round((sec_eur.get("Semis", 0.0)) / household * 100, 1),
            "single_name_cap": caps.get("single_name", 15),
            "sector_cap": caps.get("sector", 25),
            "group_cap": caps.get("group", 35),
            "names": names,
            "sectors": sectors,
            "etoro_as_of": store.get("as_of"),
            "fx_rate_eur_usd": round(fx, 4),
            "source": "live",
        }
    except Exception:
        # Same posture as the frontend catch: never 500 the dashboard — fall
        # back to the last known-good seed so the page always renders.
        return {**store["seed"], "etoro_as_of": store.get("as_of")}


@router.get("/household")
def get_household():
    """Full netted two-leaf household exposure (HouseholdData shape)."""
    return _compute_household()


@router.get("/household/overview")
def get_household_overview():
    """Panel 1 — combined NLV, leaf split (A/B %), caps, snapshot freshness."""
    h = _compute_household()
    return {
        "as_of": h.get("as_of"),
        "household_eur": h.get("household_eur"),
        "leaf_ibkr_pct": h.get("leaf_ibkr_pct"),
        "leaf_etoro_pct": h.get("leaf_etoro_pct"),
        "single_name_cap": h.get("single_name_cap"),
        "sector_cap": h.get("sector_cap"),
        "group_cap": h.get("group_cap"),
        "etoro_as_of": h.get("etoro_as_of"),
        "fx_rate_eur_usd": h.get("fx_rate_eur_usd"),
        "source": h.get("source"),
    }


@router.get("/household/concentration")
def get_household_concentration():
    """Panel 2 — single-name / sector / AI-tech-chips % vs the v4.0 caps."""
    h = _compute_household()
    return {
        "as_of": h.get("as_of"),
        "names": h.get("names"),
        "sectors": h.get("sectors"),
        "ai_tech_chips_pct": h.get("ai_tech_chips_pct"),
        "semis_pct": h.get("semis_pct"),
        "single_name_cap": h.get("single_name_cap"),
        "sector_cap": h.get("sector_cap"),
        "group_cap": h.get("group_cap"),
        "source": h.get("source"),
    }


# ---------------------------------------------------------------------------
# v4.0 Phase 3 (O-13) — staged-uncap tracker + tail-hedge monitor. Read-only.
# Mirrors the client UncapTracker.tsx but derives the ACTUAL stage from live
# coverage (short calls / long LEAP calls per name) instead of a store, and adds
# the tail-hedge monitor that replaces the B-2 widget for the household view.
# ---------------------------------------------------------------------------

_SINGLE_NAME_CAP = 15.0
_UNCAP_EXCLUDE = {"SPY", "OST"}


def _dte(expiry: str | None) -> int | None:
    """Days-to-expiry from an 'YYYYMMDD' or 'YYYY-MM-DD' string."""
    if not expiry:
        return None
    s = str(expiry).replace("-", "")
    try:
        exp = datetime.strptime(s[:8], "%Y%m%d").date()
        return (exp - datetime.now(timezone.utc).date()).days
    except (ValueError, TypeError):
        return None


def _stage_from_coverage(coverage: float | None) -> int | None:
    """v4.0 §3.1 ladder: 100%→S0, 50%→S1, 25%→S2, uncapped→S3.
    Derived from live short-call:long-LEAP coverage ratio (midpoint bands)."""
    if coverage is None:
        return None
    if coverage >= 0.75:
        return 0
    if coverage >= 0.375:
        return 1
    if coverage >= 0.125:
        return 2
    return 3


def _briefing_context() -> dict:
    """Regime + cash-floor gate from the canonical briefing (lazy import to
    avoid a route↔route circular). Degrades to None gates if unavailable."""
    try:
        from app.routes import briefing  # lazy
        b = briefing.get_briefing()
        regime = ((b.get("macro_regime") or {}).get("regime") or "").lower()
        thr = (b.get("account") or {}).get("thresholds") or {}
        cash_ok = bool(thr.get("available_funds_ok") and thr.get("excess_liq_ok"))
        return {
            "regime": regime or None,
            "regime_ok": (regime != "bearish") if regime else None,
            "cash_ok": cash_ok,
            "net_liq": (b.get("account") or {}).get("net_liq"),
            "avail_floor": thr.get("available_funds_floor_usd"),
            "excess_floor": thr.get("excess_liq_floor_usd"),
        }
    except Exception:
        return {"regime": None, "regime_ok": None, "cash_ok": None, "net_liq": None}


def _trend_above_200w(ticker: str) -> bool | None:
    """v3.11 §8 weekly-200-SMA gate, reused as the v4.0 trend gate (lazy import)."""
    try:
        from app.routes.options_analytics import weekly_trend_state  # lazy
        return weekly_trend_state(ticker).get("above_200w")
    except Exception:
        return None


@router.get("/household/uncap_stages")
def get_uncap_stages():
    """Panel 3 — per Leaf-B LEAP: current stage (0–3, from live coverage) + the
    four v4.0 §3.1 gates (name<15% household · cash floors · regime not bearish ·
    >weekly-200-SMA) + a verdict (advance/hold/de-stage). Read-only."""
    ctx = _briefing_context()
    hh = _compute_household()
    hh_pct = {n["ticker"]: n["pct"] for n in (hh.get("names") or [])}

    try:
        positions = state.get_active_positions()
        legs = positions.get("positions", []) or []
    except Exception:
        return {"as_of": datetime.now(timezone.utc).date().isoformat(),
                "rows": [], "regime": ctx.get("regime"), "cash_ok": ctx.get("cash_ok"),
                "source": "unavailable"}

    # Per-name long-LEAP-call and short-call contract counts.
    longs: dict[str, float] = {}
    shorts: dict[str, float] = {}
    for p in legs:
        t = (p.get("ticker") or "").upper()
        if t in _UNCAP_EXCLUDE or not t:
            continue
        if (p.get("right") or "").upper() != "C":
            continue
        q = p.get("qty") or 0
        if q > 0:
            longs[t] = longs.get(t, 0.0) + q
        elif q < 0:
            shorts[t] = shorts.get(t, 0.0) + abs(q)

    rows = []
    for t, long_ct in longs.items():
        if long_ct <= 0:
            continue  # not a LEAP holder
        short_ct = shorts.get(t, 0.0)
        coverage = short_ct / long_ct if long_ct else None
        stage = _stage_from_coverage(coverage)
        conc_pct = hh_pct.get(t)
        gate_conc = (conc_pct < _SINGLE_NAME_CAP) if conc_pct is not None else None
        gate_cash = ctx.get("cash_ok")
        gate_regime = ctx.get("regime_ok")
        gate_trend = _trend_above_200w(t)

        gates = {"name_lt_15": gate_conc, "cash_floor": gate_cash,
                 "regime_ok": gate_regime, "above_200w": gate_trend}
        # Verdict: de-stage overrides (regime bearish or below trend); else all-green
        # advances one stage; else hold.
        if gate_regime is False or gate_trend is False:
            verdict = "de-stage / add cover"
        elif stage is not None and stage >= 3:
            verdict = "uncapped (Stage 3)"
        elif all(g is True for g in (gate_conc, gate_cash, gate_regime, gate_trend)):
            verdict = "eligible to uncap +1"
        else:
            verdict = "hold"

        rows.append({
            "ticker": t,
            "stage": stage,
            "coverage_ratio": round(coverage, 3) if coverage is not None else None,
            "long_leap_calls": int(long_ct),
            "short_calls": int(short_ct),
            "household_pct": round(conc_pct, 2) if conc_pct is not None else None,
            "gates": gates,
            "verdict": verdict,
        })
    rows.sort(key=lambda r: (r["household_pct"] or 0), reverse=True)

    return {
        "as_of": datetime.now(timezone.utc).date().isoformat(),
        "regime": ctx.get("regime"),
        "cash_ok": ctx.get("cash_ok"),
        "single_name_cap": _SINGLE_NAME_CAP,
        "ladder": "100% → 50% → 25% → uncapped (S0→S3); all 4 gates green = advance +1; regime bearish or <200-SMA = de-stage",
        "rows": rows,
        "source": hh.get("source"),
    }


@router.get("/household/tail_hedge")
def get_tail_hedge():
    """Panel 4 — v4.0 §5 tail-hedge monitor (replaces the B-2 widget for the
    household view). Far-OTM SPY/SPX crash puts (~15–25% OTM, 3–6mo, rolled
    quarterly); quarterly budget ≈ 0.75% of net liq. Read-only."""
    ctx = _briefing_context()
    try:
        positions = state.get_active_positions()
        legs = positions.get("positions", []) or []
        nlv = ctx.get("net_liq") or positions.get("net_liq")
    except Exception:
        return {"as_of": datetime.now(timezone.utc).date().isoformat(),
                "tail_puts": [], "source": "unavailable"}

    # SPY spot from any SPY leg's BS input.
    spot = None
    for p in legs:
        if (p.get("ticker") or "").upper() == "SPY":
            sp = (p.get("bs_inputs") or {}).get("spot")
            if sp:
                spot = float(sp)
                break

    tail_puts = []
    total_est_cost = 0.0
    have_cost = False
    for p in legs:
        if (p.get("ticker") or "").upper() != "SPY" or (p.get("right") or "").upper() != "P":
            continue
        q = p.get("qty") or 0
        if q <= 0:  # long puts only = the crash hedge (skip the short leg of any spread)
            continue
        strike = float(p.get("strike") or 0)
        otm_pct = round((spot - strike) / spot * 100, 1) if spot and strike else None
        # Tail = deep OTM (≥15%); shallower long puts are B-2 spread legs, not tail.
        if otm_pct is None or otm_pct < 15:
            continue
        mv = p.get("market_value")
        if mv is not None:
            try:
                total_est_cost += abs(float(mv))
                have_cost = True
            except (TypeError, ValueError):
                pass
        tail_puts.append({
            "strike": strike, "qty": int(q), "expiry": p.get("expiry"),
            "dte": _dte(p.get("expiry")), "otm_pct": otm_pct,
            "market_value": round(float(mv), 2) if mv is not None else None,
        })
    tail_puts.sort(key=lambda r: (r["dte"] is None, r["dte"]))

    q_budget = round(0.0075 * float(nlv), 0) if nlv else None
    dtes = [r["dte"] for r in tail_puts if r["dte"] is not None]
    nearest_dte = min(dtes) if dtes else None
    util = (round(total_est_cost / q_budget * 100, 1)
            if (have_cost and q_budget) else None)

    return {
        "as_of": datetime.now(timezone.utc).date().isoformat(),
        "net_liq": round(float(nlv), 0) if nlv else None,
        "spy_spot": spot,
        "quarterly_budget_usd": q_budget,
        "budget_basis": "0.75% of net liq / quarter (v4.0 §5)",
        "tail_put_count": len(tail_puts),
        "tail_puts": tail_puts,
        "current_hedge_cost_est": round(total_est_cost, 0) if have_cost else None,
        "budget_utilization_pct": util,
        "nearest_roll_dte": nearest_dte,
        "roll_flag": (nearest_dte is not None and nearest_dte < 90),
        "note": "Tail-hedge-only for Leaf B — this RETIRES the v3.11 B-2 spread overlay. "
                "Roll quarterly; target 15–25% OTM, 3–6mo. Shallow (<15% OTM) SPY puts "
                "are treated as B-2 spread legs and excluded here.",
        "source": ctx.get("regime") is not None and "live" or "partial",
    }
