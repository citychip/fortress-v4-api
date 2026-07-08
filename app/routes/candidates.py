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

    # Scanner-null fix (2026-07-08): unknown earnings date must NEVER render
    # "clear" — the 07-06 trap flagged JPM/JNJ/CSX 🔥PRIME while they reported
    # Jul 14/15/22. Canonical derivation lives in state.earnings_state_from_days
    # (None → "unverified": advisory, non-blocking, but visibly needs a manual
    # get_earnings_history check before sizing).
    earnings_state = state.earnings_state_from_days(days)

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
        # Advisory companion to "unverified" — consumers must verify per name.
        "earnings_note": (
            "⚠ earnings date UNKNOWN — verify with get_earnings_history before sizing"
            if earnings_state == "unverified" else None
        ),
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
