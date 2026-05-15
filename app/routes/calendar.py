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


# ---------------------------------------------------------------------------
# Earnings history endpoint — returns past + upcoming earnings dates from yfinance
# ---------------------------------------------------------------------------

@router.get("/calendar/{ticker}/history", status_code=200)
def get_earnings_history(ticker: str, limit: int = 12):
    """
    Return up to `limit` historical and upcoming earnings dates for a ticker.
    Uses yfinance.Ticker.earnings_dates which requires lxml.
    
    Response shape:
    {
      "ticker": "MSFT",
      "dates": [
        {
          "date": "2026-07-29",
          "type": "upcoming",        // "past" | "upcoming"
          "eps_estimate": 4.25,
          "reported_eps": null,
          "surprise_pct": null
        },
        ...
      ]
    }
    """
    import yfinance as yf
    from datetime import date

    ticker = ticker.upper()
    try:
        t = yf.Ticker(ticker)
        df = t.earnings_dates
        if df is None or df.empty:
            return {"ticker": ticker, "dates": []}
        
        # Limit to most recent N entries (yfinance returns newest first)
        df = df.head(limit)
        
        today = date.today()
        results = []
        for ts, row in df.iterrows():
            try:
                dt = ts.date()
                date_str = dt.isoformat()
                entry_type = "upcoming" if dt >= today else "past"
                
                eps_est = row.get("EPS Estimate")
                reported = row.get("Reported EPS")
                surprise = row.get("Surprise(%)")
                
                results.append({
                    "date": date_str,
                    "type": entry_type,
                    "eps_estimate": None if (eps_est is None or (hasattr(eps_est, "__class__") and str(eps_est) == "nan")) else float(eps_est),
                    "reported_eps": None if (reported is None or (hasattr(reported, "__class__") and str(reported) == "nan")) else float(reported),
                    "surprise_pct": None if (surprise is None or (hasattr(surprise, "__class__") and str(surprise) == "nan")) else float(surprise),
                })
            except Exception:
                continue
        
        return {"ticker": ticker, "dates": results}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch earnings history for {ticker}: {str(e)}")
