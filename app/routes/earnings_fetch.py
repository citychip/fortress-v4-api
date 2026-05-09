"""
Earnings auto-fetch endpoint.

POST /api/calendar/fetch-earnings
  - Reads the ticker universe (tier1 + tier2 + macro)
  - Queries yfinance for the next earnings date for each ticker
  - Merges results into earnings_blocklist.json
  - Returns a diff of what changed

Existing confirmed dates are preserved unless overridden explicitly.
Tickers with no yfinance data are skipped (not deleted).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException

from app.services import state

logger = logging.getLogger("fortress.earnings_fetch")
router = APIRouter()


def _fetch_earnings_date(ticker: str) -> Optional[str]:
    """
    Query yfinance for the next earnings date for a single ticker.
    Returns ISO date string (YYYY-MM-DD) or None if unavailable.
    """
    try:
        import yfinance as yf
        cal = yf.Ticker(ticker).calendar
        dates = cal.get("Earnings Date")
        if dates and len(dates) > 0:
            d = dates[0]
            # yfinance returns datetime.date objects
            if hasattr(d, "isoformat"):
                return d.isoformat()
            return str(d)
    except Exception as e:
        logger.warning(f"yfinance earnings fetch failed for {ticker}: {e}")
    return None


@router.post("/calendar/fetch-earnings", status_code=200)
def fetch_earnings_dates():
    """
    Auto-fetch earnings dates from yfinance for all universe tickers and
    merge into earnings_blocklist.json. Returns a summary of changes.
    """
    try:
        universe = state.get_ticker_universe()
        calendar_data = state.get_earnings_blocklist()
    except state.StateError as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Collect all tickers from universe
    tickers = set()
    for tier in ("tier1", "tier2", "macro"):
        tier_entries = universe.get(tier, [])
        for entry in tier_entries:
            # Universe tiers contain plain strings (e.g. "MSFT")
            if isinstance(entry, dict):
                t = entry.get("ticker", "")
            else:
                t = str(entry)
            if t:
                tickers.add(t.upper())

    if not tickers:
        raise HTTPException(status_code=422, detail="No tickers found in universe.")

    existing = calendar_data.get("tickers", {})
    now_iso = datetime.now(timezone.utc).isoformat()
    today = datetime.now(timezone.utc).date().isoformat()

    added = []
    updated = []
    skipped = []
    unchanged = []

    for ticker in sorted(tickers):
        fetched_date = _fetch_earnings_date(ticker)

        if fetched_date is None:
            skipped.append(ticker)
            continue

        existing_entry = existing.get(ticker, {})
        existing_date = existing_entry.get("next_earnings")
        is_confirmed = existing_entry.get("confirmed", False)

        if existing_date == fetched_date:
            unchanged.append(ticker)
            continue

        # If the existing date is confirmed by the user, do not overwrite it
        # unless the fetched date is different AND the existing date is in the past
        if is_confirmed and existing_date:
            try:
                existing_dt = datetime.strptime(existing_date, "%Y-%m-%d").date()
                today_dt = datetime.strptime(today, "%Y-%m-%d").date()
                if existing_dt >= today_dt:
                    # Confirmed future date — preserve it, just note the discrepancy
                    skipped.append(f"{ticker} (confirmed date preserved)")
                    continue
            except ValueError:
                pass

        action = "added" if ticker not in existing else "updated"
        existing[ticker] = {
            "next_earnings": fetched_date,
            "confirmed": False,
            "notes": existing_entry.get("notes", ""),
            "_updated_at": now_iso,
            "_source": "yfinance_auto",
        }

        if action == "added":
            added.append({"ticker": ticker, "date": fetched_date})
        else:
            updated.append({
                "ticker": ticker,
                "old_date": existing_date,
                "new_date": fetched_date,
            })

    # Persist
    calendar_data["tickers"] = existing
    calendar_data["_last_updated"] = today
    calendar_data["_last_auto_fetch"] = now_iso

    try:
        state.save_earnings_blocklist(calendar_data)
    except state.StateError as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "as_of": now_iso,
        "tickers_checked": len(tickers),
        "added": added,
        "updated": updated,
        "unchanged_count": len(unchanged),
        "skipped": skipped,
        "message": (
            f"Fetched earnings dates for {len(tickers)} tickers. "
            f"{len(added)} added, {len(updated)} updated, "
            f"{len(unchanged)} unchanged, {len(skipped)} skipped."
        ),
    }
