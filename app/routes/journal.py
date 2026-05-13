"""
Journal endpoints — Phase 2 write capability.
GET  /api/journal          — list all entries + 30d metrics (existing)
POST /api/journal          — log a new trade entry
DELETE /api/journal/{id}   — remove an entry (correction flow)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services import state

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class JournalEntryCreate(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=10)
    action: str = Field(..., pattern="^(OPEN|CLOSE|ROLL|TRIM|ADD|NOTE)$")
    strategy: Optional[str] = Field(None, max_length=30)
    description: str = Field(..., min_length=1, max_length=500,
                              description="Human-readable trade description, e.g. 'Opened MSFT PMCC Jan28 310C / Dec26 480C'")
    realized_pnl: Optional[float] = Field(None, description="Realised P&L in USD (CLOSE/TRIM actions)")
    debit_credit: Optional[float] = Field(None, description="Net debit (negative) or credit (positive) in USD")
    outside_universe: bool = Field(False, description="True if ticker is not in ticker_universe.json")
    outside_universe_justification: Optional[str] = Field(
        None, max_length=500,
        description="Required when outside_universe=True per Strategy §3.4.4"
    )
    notes: Optional[str] = Field(None, max_length=1000)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def compute_metrics(entries: list[dict]) -> dict:
    """30-day outcome metrics per Build Spec §6.5."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    closes = []
    for e in entries:
        if e.get("action") != "CLOSE":
            continue
        ts = e.get("closed_timestamp") or e.get("timestamp", "")
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if dt >= cutoff and e.get("realized_pnl") is not None:
                closes.append(e)
        except ValueError:
            continue
    total_realized = sum(e.get("realized_pnl", 0) for e in closes)
    pcs_closes = [e for e in closes if "PCS" in e.get("description", "")]
    pcs_winners = [e for e in pcs_closes if e.get("realized_pnl", 0) > 0]
    pcs_hit_rate = (
        round(100 * len(pcs_winners) / len(pcs_closes)) if pcs_closes else None
    )
    violations = sum(
        1 for e in entries
        if e.get("outside_universe") and not e.get("outside_universe_justification")
    )
    return {
        "total_realized_30d": round(total_realized, 2),
        "closed_positions_30d": len(closes),
        "pcs_hit_rate_pct": pcs_hit_rate,
        "framework_violations_30d": violations,
    }


def _find_entry(entries: list[dict], entry_id: str) -> tuple[int, dict]:
    for i, e in enumerate(entries):
        if e.get("id") == entry_id:
            return i, e
    raise HTTPException(status_code=404, detail=f"Journal entry '{entry_id}' not found.")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/journal")
def get_journal():
    try:
        data = state.get_journal()
    except state.StateError as e:
        raise HTTPException(status_code=500, detail=str(e))
    entries = sorted(
        data.get("entries", []),
        key=lambda e: e.get("timestamp", ""),
        reverse=True
    )
    return {
        "as_of": data.get("_last_updated"),
        "entries": entries,
        "metrics": compute_metrics(entries),
    }


@router.post("/journal", status_code=201)
def create_journal_entry(body: JournalEntryCreate):
    # Strategy §3.4.4 — outside-universe trades require justification
    if body.outside_universe and not body.outside_universe_justification:
        raise HTTPException(
            status_code=422,
            detail=(
                "Strategy §3.4.4 requires an explicit justification for trades on tickers "
                "outside the universe. Provide outside_universe_justification."
            ),
        )

    # Check if ticker is in universe (informational — we trust the client flag but also verify)
    try:
        universe_data = state.get_ticker_universe()
        all_tickers = set()
        for tier_tickers in universe_data.values():
            if isinstance(tier_tickers, list):
                all_tickers.update(t.upper() for t in tier_tickers)
        ticker_upper = body.ticker.upper()
        is_outside = ticker_upper not in all_tickers
        if is_outside and not body.outside_universe and not body.outside_universe_justification:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Ticker '{ticker_upper}' is not in ticker_universe.json. "
                    "Set outside_universe=true and provide outside_universe_justification per Strategy §3.4.4."
                ),
            )
    except state.StateError:
        pass  # Universe file missing — skip check

    try:
        data = state.get_journal()
    except state.StateError as e:
        raise HTTPException(status_code=500, detail=str(e))

    entries = data.get("entries", [])
    new_entry = {
        "id": str(uuid.uuid4())[:8],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ticker": body.ticker.upper(),
        "action": body.action,
        "strategy": body.strategy,
        "description": body.description,
        "realized_pnl": body.realized_pnl,
        "debit_credit": body.debit_credit,
        "outside_universe": body.outside_universe,
        "outside_universe_justification": body.outside_universe_justification,
        "notes": body.notes,
    }
    entries.append(new_entry)
    data["entries"] = entries
    data["_last_updated"] = datetime.now(timezone.utc).isoformat()

    try:
        state.save_journal(data)
    except state.StateError as e:
        raise HTTPException(status_code=500, detail=str(e))

    return new_entry


@router.get("/journal/suggest")
def suggest_journal_entry():
    """
    Auto-suggest journal entry fields from the most recent IBKR sync diff.
    Returns the last position change detected (item G).
    """
    try:
        positions_data = state.get_active_positions()
    except state.StateError as e:
        raise HTTPException(status_code=500, detail=str(e))

    positions = positions_data.get("positions", [])
    last_sync = positions_data.get("ibkr_last_sync") or positions_data.get("_last_updated")

    # Find the most recently changed position (highest timestamp or last in list)
    # IBKR sync writes positions in order — the last one is typically the most recent change
    # We also look for positions with a "new" or "changed" flag if present
    candidate = None
    for p in reversed(positions):
        if p.get("_new") or p.get("_changed"):
            candidate = p
            break

    if not candidate and positions:
        # Fall back to last position in list
        candidate = positions[-1]

    if not candidate:
        return {
            "suggestion": None,
            "message": "No positions found — sync from IBKR first.",
        }

    ticker = (candidate.get("ticker") or "").upper()
    strategy = candidate.get("strategy") or ""
    action = "OPEN"  # default

    # Infer action from position state
    qty = candidate.get("qty") or candidate.get("position") or 0
    if isinstance(qty, (int, float)):
        if qty < 0:
            action = "OPEN"   # short position opened
        elif qty > 0:
            action = "OPEN"   # long position opened

    return {
        "suggestion": {
            "ticker": ticker,
            "strategy": strategy,
            "action": action,
            "description": f"{action} {ticker} {strategy}".strip(),
        },
        "last_sync": last_sync,
        "message": f"Suggested from last IBKR sync ({last_sync})",
    }


@router.delete("/journal/{entry_id}", status_code=204)
def delete_journal_entry(entry_id: str):
    try:
        data = state.get_journal()
    except state.StateError as e:
        raise HTTPException(status_code=500, detail=str(e))

    entries = data.get("entries", [])
    idx, _ = _find_entry(entries, entry_id)

    entries.pop(idx)
    data["entries"] = entries
    data["_last_updated"] = datetime.now(timezone.utc).isoformat()

    try:
        state.save_journal(data)
    except state.StateError as e:
        raise HTTPException(status_code=500, detail=str(e))
