"""
Calendar endpoints — Phase 2 CRUD.
GET    /api/calendar                    — list all tickers with computed DTE + status (existing)
PUT    /api/calendar/{ticker}           — update or create a ticker's earnings entry
DELETE /api/calendar/{ticker}           — remove a ticker from the calendar
POST   /api/calendar/{ticker}/confirm   — mark a date as confirmed
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services import state

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class EarningsUpdate(BaseModel):
    next_earnings: str = Field(..., description="YYYY-MM-DD expected earnings date")
    confirmed: bool = Field(False, description="True once date is confirmed by the company IR")
    notes: Optional[str] = Field(None, max_length=300)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _enrich_ticker(ticker: str, entry: dict, calendar: dict) -> dict:
    days = state.days_to_earnings(ticker, calendar)
    if days is None:
        status = "no_earnings"
    elif days < 0:
        status = "past"
    elif days <= 10:
        status = "blackout"
    elif days <= 30:
        status = "approaching"
    else:
        status = "clear"
    return {**entry, "days_to_earnings": days, "status": status}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/calendar")
def get_calendar():
    try:
        calendar = state.get_earnings_blocklist()
    except state.StateError as e:
        raise HTTPException(status_code=500, detail=str(e))

    enriched = {}
    for ticker, entry in calendar.get("tickers", {}).items():
        enriched[ticker] = _enrich_ticker(ticker, entry, calendar)

    return {
        "as_of": calendar.get("_last_updated"),
        "tickers": enriched,
    }


@router.put("/calendar/{ticker}", status_code=200)
def upsert_calendar_entry(ticker: str, body: EarningsUpdate):
    ticker = ticker.upper()

    # Validate date format
    try:
        datetime.strptime(body.next_earnings, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"next_earnings must be YYYY-MM-DD, got: {body.next_earnings!r}"
        )

    try:
        data = state.get_earnings_blocklist()
    except state.StateError as e:
        raise HTTPException(status_code=500, detail=str(e))

    tickers = data.get("tickers", {})
    tickers[ticker] = {
        "next_earnings": body.next_earnings,
        "confirmed": body.confirmed,
        "notes": body.notes or "",
        "_updated_at": datetime.now(timezone.utc).isoformat(),
    }
    data["tickers"] = tickers
    data["_last_updated"] = datetime.now(timezone.utc).date().isoformat()

    try:
        state.save_earnings_blocklist(data)
    except state.StateError as e:
        raise HTTPException(status_code=500, detail=str(e))

    return _enrich_ticker(ticker, tickers[ticker], data)


@router.post("/calendar/{ticker}/confirm", status_code=200)
def confirm_earnings_date(ticker: str):
    ticker = ticker.upper()

    try:
        data = state.get_earnings_blocklist()
    except state.StateError as e:
        raise HTTPException(status_code=500, detail=str(e))

    tickers = data.get("tickers", {})
    if ticker not in tickers:
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' not in earnings calendar.")

    tickers[ticker]["confirmed"] = True
    tickers[ticker]["_confirmed_at"] = datetime.now(timezone.utc).isoformat()
    data["tickers"] = tickers
    data["_last_updated"] = datetime.now(timezone.utc).date().isoformat()

    try:
        state.save_earnings_blocklist(data)
    except state.StateError as e:
        raise HTTPException(status_code=500, detail=str(e))

    return _enrich_ticker(ticker, tickers[ticker], data)


@router.delete("/calendar/{ticker}", status_code=204)
def delete_calendar_entry(ticker: str):
    ticker = ticker.upper()

    try:
        data = state.get_earnings_blocklist()
    except state.StateError as e:
        raise HTTPException(status_code=500, detail=str(e))

    tickers = data.get("tickers", {})
    if ticker not in tickers:
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' not in earnings calendar.")

    del tickers[ticker]
    data["tickers"] = tickers
    data["_last_updated"] = datetime.now(timezone.utc).date().isoformat()

    try:
        state.save_earnings_blocklist(data)
    except state.StateError as e:
        raise HTTPException(status_code=500, detail=str(e))
