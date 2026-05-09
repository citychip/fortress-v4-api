"""
Universe endpoint — ticker_universe.json CRUD.

GET  /api/universe                  — full universe
POST /api/universe/add              — add ticker to a tier
DELETE /api/universe/{tier}/{ticker} — remove ticker from a tier
POST /api/universe/move             — move ticker between tiers
POST /api/universe/exclude          — add to excluded list
DELETE /api/universe/exclude/{ticker} — remove from excluded list
"""
from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from app.services import state

router = APIRouter()

VALID_TIERS = {"tier1", "tier2", "macro"}


# ── Models ────────────────────────────────────────────────────────────────────

class AddTickerRequest(BaseModel):
    ticker: str
    tier: Literal["tier1", "tier2", "macro"] = "tier1"

    @field_validator("ticker")
    @classmethod
    def upper_and_clean(cls, v: str) -> str:
        v = v.strip().upper()
        if not v or not v.replace(".", "").replace("-", "").isalnum():
            raise ValueError("Invalid ticker symbol")
        if len(v) > 10:
            raise ValueError("Ticker too long")
        return v


class MoveTickerRequest(BaseModel):
    ticker: str
    from_tier: Literal["tier1", "tier2", "macro"]
    to_tier: Literal["tier1", "tier2", "macro"]

    @field_validator("ticker")
    @classmethod
    def upper(cls, v: str) -> str:
        return v.strip().upper()


class ExcludeTickerRequest(BaseModel):
    ticker: str
    reason: str = "manual"
    note: str = ""
    until_cleared: bool = True

    @field_validator("ticker")
    @classmethod
    def upper(cls, v: str) -> str:
        return v.strip().upper()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load() -> dict:
    return state.get_ticker_universe()


def _save(data: dict) -> None:
    data["_last_updated"] = str(date.today())
    state.save_universe(data)


def _all_active_tickers(data: dict) -> list[str]:
    """Return all tickers across tier1, tier2, macro."""
    result = []
    for tier in VALID_TIERS:
        result.extend(data.get(tier, []))
    return result


def _excluded_tickers(data: dict) -> list[str]:
    return [e["ticker"] for e in data.get("excluded", [])]


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/universe")
def get_universe():
    try:
        return state.get_ticker_universe()
    except state.StateError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/universe/add")
def add_ticker(req: AddTickerRequest):
    """Add a ticker to the specified tier. Prevents duplicates across all tiers."""
    data = _load()
    ticker = req.ticker
    tier = req.tier

    # Check not already in an active tier
    all_active = _all_active_tickers(data)
    if ticker in all_active:
        # Find which tier it's in
        for t in VALID_TIERS:
            if ticker in data.get(t, []):
                raise HTTPException(
                    status_code=409,
                    detail=f"{ticker} is already in {t}. Use /universe/move to change tier."
                )

    # Check not in excluded list
    if ticker in _excluded_tickers(data):
        raise HTTPException(
            status_code=409,
            detail=f"{ticker} is on the excluded list. Remove it from excluded first."
        )

    if tier not in data:
        data[tier] = []
    data[tier].append(ticker)
    _save(data)
    return {"status": "added", "ticker": ticker, "tier": tier, "universe": data}


@router.delete("/universe/{tier}/{ticker}")
def remove_ticker(tier: str, ticker: str):
    """Remove a ticker from the specified tier."""
    ticker = ticker.strip().upper()
    if tier not in VALID_TIERS:
        raise HTTPException(status_code=400, detail=f"Invalid tier '{tier}'. Must be one of: {sorted(VALID_TIERS)}")

    data = _load()
    tier_list: list = data.get(tier, [])

    if ticker not in tier_list:
        raise HTTPException(status_code=404, detail=f"{ticker} not found in {tier}")

    tier_list.remove(ticker)
    data[tier] = tier_list
    _save(data)
    return {"status": "removed", "ticker": ticker, "tier": tier, "universe": data}


@router.post("/universe/move")
def move_ticker(req: MoveTickerRequest):
    """Move a ticker from one tier to another."""
    data = _load()
    ticker = req.ticker
    from_tier = req.from_tier
    to_tier = req.to_tier

    if from_tier == to_tier:
        raise HTTPException(status_code=400, detail="from_tier and to_tier are the same")

    from_list: list = data.get(from_tier, [])
    if ticker not in from_list:
        raise HTTPException(status_code=404, detail=f"{ticker} not found in {from_tier}")

    from_list.remove(ticker)
    data[from_tier] = from_list

    if to_tier not in data:
        data[to_tier] = []
    data[to_tier].append(ticker)

    _save(data)
    return {"status": "moved", "ticker": ticker, "from": from_tier, "to": to_tier, "universe": data}


@router.post("/universe/exclude")
def exclude_ticker(req: ExcludeTickerRequest):
    """Add a ticker to the excluded list (and remove from active tiers if present)."""
    data = _load()
    ticker = req.ticker

    # Remove from active tiers if present
    for tier in VALID_TIERS:
        if ticker in data.get(tier, []):
            data[tier].remove(ticker)

    # Check not already excluded
    if ticker in _excluded_tickers(data):
        raise HTTPException(status_code=409, detail=f"{ticker} is already excluded")

    excluded_entry = {
        "ticker": ticker,
        "reason": req.reason,
        "until_cleared": req.until_cleared,
    }
    if req.note:
        excluded_entry["note"] = req.note

    if "excluded" not in data:
        data["excluded"] = []
    data["excluded"].append(excluded_entry)
    _save(data)
    return {"status": "excluded", "ticker": ticker, "universe": data}


@router.delete("/universe/exclude/{ticker}")
def unexclude_ticker(ticker: str):
    """Remove a ticker from the excluded list (does not add it back to any tier)."""
    ticker = ticker.strip().upper()
    data = _load()
    excluded: list = data.get("excluded", [])
    original_len = len(excluded)
    data["excluded"] = [e for e in excluded if e.get("ticker") != ticker]

    if len(data["excluded"]) == original_len:
        raise HTTPException(status_code=404, detail=f"{ticker} not found in excluded list")

    _save(data)
    return {"status": "unexcluded", "ticker": ticker, "universe": data}
