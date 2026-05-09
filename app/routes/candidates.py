"""
Candidates endpoint: latest IV Crush report with earnings + concentration cross-checks.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.services import state

router = APIRouter()


def enrich_row(row: dict, calendar: dict, concentration: dict, excluded_map: dict) -> dict:
    """Add cross-check fields per Build Spec §5.2 + Strategy §3.3 exclusion."""
    ticker = row.get("ticker", "")
    days = row.get("days_to_earnings")
    if days is None:
        days = state.days_to_earnings(ticker, calendar)

    if days is not None and 0 <= days <= 10:
        earnings_state = "blackout"
    elif days is not None and 0 <= days <= 30:
        earnings_state = "approaching"
    else:
        earnings_state = "clear"

    conc_pct = concentration.get(ticker, 0)
    if conc_pct >= 50:
        concentration_state = "high"
    elif conc_pct >= 30:
        concentration_state = "moderate"
    else:
        concentration_state = "low"

    excluded_entry = excluded_map.get(ticker.upper())
    is_excluded = excluded_entry is not None
    exclusion_reason = excluded_entry.get("reason") if excluded_entry else None

    can_trade = (
        (not is_excluded)
        and (earnings_state != "blackout")
        and (concentration_state != "high")
    )

    return {
        **row,
        "days_to_earnings": days,
        "concentration_pct": conc_pct,
        "earnings_state": earnings_state,
        "concentration_state": concentration_state,
        "excluded": is_excluded,
        "exclusion_reason": exclusion_reason,
        "can_trade": can_trade,
    }


@router.get("/candidates")
def get_candidates():
    """Latest IV Crush report rows enriched with strategy cross-checks."""
    try:
        report = state.get_iv_crush_report()
        calendar = state.get_earnings_blocklist()
        positions = state.get_active_positions()
    except state.StateError as e:
        raise HTTPException(status_code=500, detail=str(e))

    concentration = state.compute_concentration(positions)
    rows = report.get("rows", []) or []
    universe = state.get_ticker_universe()
    excluded_map = {e["ticker"].upper(): e for e in (universe.get("excluded") or []) if isinstance(e, dict) and e.get("ticker")}
    enriched = [enrich_row(row, calendar, concentration, excluded_map) for row in rows]

    return {
        "as_of": report.get("_last_updated"),
        "source": report.get("_source"),
        "rows": enriched,
    }
