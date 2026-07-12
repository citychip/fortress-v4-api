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
