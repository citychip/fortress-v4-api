"""
Journal endpoints — Phase 2 write capability.
GET  /api/journal          — list all entries + 30d metrics (existing)
POST /api/journal          — log a new trade entry
DELETE /api/journal/{id}   — remove an entry (correction flow)
POST /api/journal/close/{id} — link close→open entry (K-04, Sprint v8.8)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator

from app.services import state

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

# Canonical action vocabulary + tolerant aliases. The MCP add_journal_entry tool
# historically sent lowercase verbs (e.g. 'observe', 'adjust') and the Parapet
# note box sends no action at all — both used to 422 against the old uppercase
# regex (Sprint 20.1). We now normalize instead of reject.
_CANON_ACTIONS = {"OPEN", "CLOSE", "ROLL", "TRIM", "ADD", "NOTE", "ADJUST", "OBSERVE"}
_ACTION_ALIASES = {"OBSERVE": "OBSERVE", "ADJUST": "ADJUST", "NOTES": "NOTE", "": "NOTE"}
# Sentinel ticker for free-text / non-position journal notes (no symbol attached).
_GENERAL_TICKER = "GENERAL"
# Actions that are pure commentary — exempt from the outside-universe gate.
_NOTE_ACTIONS = {"NOTE", "OBSERVE"}


class JournalEntryCreate(BaseModel):
    # extra='ignore' (Pydantic default) — unknown keys are dropped, never 422.
    ticker: str = Field(_GENERAL_TICKER, max_length=10)
    action: str = Field("NOTE")
    strategy: Optional[str] = Field(None, max_length=30)
    description: str = Field(..., min_length=1, max_length=2000,
                              description="Human-readable description. Coalesced from note/entry/text for free-form UI posts.")
    realized_pnl: Optional[float] = Field(None, description="Realised P&L in USD (CLOSE/TRIM actions)")
    debit_credit: Optional[float] = Field(None, description="Net debit (negative) or credit (positive) in USD")
    outside_universe: bool = Field(False, description="True if ticker is not in ticker_universe.json")
    outside_universe_justification: Optional[str] = Field(
        None, max_length=500,
        description="Required when outside_universe=True per Strategy §3.4.4"
    )
    notes: Optional[str] = Field(None, max_length=2000)
    # ── Qualitative / prose fields (Sprint 20.1) — the feedback loop these feed ──
    reasoning: Optional[str] = Field(None, max_length=4000,
                                     description="Detailed reasoning referencing the strategy framework.")
    framework_rules: Optional[list[str]] = Field(None,
                                     description="Strategy section refs cited, e.g. ['§3.3','§6.2'].")
    outcome: Optional[str] = Field(None, max_length=2000,
                                   description="Outcome description for post-trade entries.")
    tags: Optional[list[str]] = Field(None, description="Free-form tags, e.g. ['earnings','roll'].")

    @model_validator(mode="before")
    @classmethod
    def _coalesce_aliases(cls, data):
        """Accept the MCP body, the Parapet {note,entry} body, and the native
        body interchangeably — derive the required fields before validation."""
        if not isinstance(data, dict):
            return data
        d = dict(data)
        free = d.get("note") or d.get("entry") or d.get("text") or d.get("content")
        if not d.get("description"):
            d["description"] = free or d.get("reasoning")
        if not d.get("notes") and free:
            d["notes"] = free
        if not d.get("action"):
            d["action"] = "NOTE"
        if not d.get("ticker"):
            d["ticker"] = _GENERAL_TICKER
        return d

    @field_validator("action", mode="before")
    @classmethod
    def _normalize_action(cls, v):
        if v is None:
            return "NOTE"
        s = str(v).strip().upper()
        s = _ACTION_ALIASES.get(s, s)
        return s if s in _CANON_ACTIONS else "NOTE"

    @field_validator("ticker", mode="before")
    @classmethod
    def _normalize_ticker(cls, v):
        if not v:
            return _GENERAL_TICKER
        return str(v).strip().upper()[:10] or _GENERAL_TICKER


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

    # Check if ticker is in universe (informational — we trust the client flag but also verify).
    # Pure commentary (NOTE/OBSERVE) and the GENERAL sentinel carry no position, so they
    # bypass the §3.4.4 universe gate — otherwise free-text journal notes would 422.
    if body.action not in _NOTE_ACTIONS and body.ticker != _GENERAL_TICKER:
        try:
            universe_data = state.get_ticker_universe()
            all_tickers = set()
            for tier_tickers in universe_data.values():
                if isinstance(tier_tickers, list):
                    for t in tier_tickers:
                        if isinstance(t, str):
                            all_tickers.add(t.upper())
                        elif isinstance(t, dict) and t.get("ticker"):
                            all_tickers.add(t["ticker"].upper())
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
        # Prose / qualitative fields (Sprint 20.1) — persisted so the journal
        # feedback loop and analytics actually accrue narrative context.
        "reasoning": body.reasoning,
        "framework_rules": body.framework_rules,
        "outcome": body.outcome,
        "tags": body.tags,
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


# ---------------------------------------------------------------------------
# Sprint v8.8 — Journal Close Linkage (K-04)
# ---------------------------------------------------------------------------

class JournalCloseLink(BaseModel):
    open_entry_id: str = Field(..., description="ID of the OPEN journal entry this close trade is linked to")
    iv_crush_realized: Optional[float] = Field(
        None, description="IV crush realised at close (e.g. 0.42 means IV dropped 42 points)"
    )
    dte_at_close: Optional[int] = Field(
        None, ge=0, description="Days-to-expiry of the option leg when the position was closed"
    )


@router.post("/journal/close/{close_entry_id}", status_code=200)
def link_journal_close(close_entry_id: str, body: JournalCloseLink):
    """
    Link a closing journal entry to its opening entry (K-04 fix).

    - Stamps the close entry with open_entry_id, iv_crush_realized, dte_at_close.
    - Stamps the open entry with close_entry_id (back-link).
    Both entries are written atomically to journal.json.
    """
    try:
        data = state.get_journal()
    except state.StateError as e:
        raise HTTPException(status_code=500, detail=str(e))

    entries = data.get("entries", [])

    # Resolve both entries
    close_idx, close_entry = _find_entry(entries, close_entry_id)

    if body.open_entry_id == close_entry_id:
        raise HTTPException(
            status_code=422,
            detail="open_entry_id and close_entry_id must be different entries."
        )

    open_idx, open_entry = _find_entry(entries, body.open_entry_id)

    # Warn (but don't block) if action types look wrong
    if close_entry.get("action") not in ("CLOSE", "TRIM", "ROLL"):
        raise HTTPException(
            status_code=422,
            detail=(
                f"Entry '{close_entry_id}' has action '{close_entry.get('action')}'. "
                "Expected CLOSE, TRIM, or ROLL for the closing entry."
            )
        )
    if open_entry.get("action") not in ("OPEN", "ADD", "ROLL"):
        raise HTTPException(
            status_code=422,
            detail=(
                f"Entry '{body.open_entry_id}' has action '{open_entry.get('action')}'. "
                "Expected OPEN, ADD, or ROLL for the opening entry."
            )
        )

    # Stamp the close entry
    entries[close_idx] = {
        **close_entry,
        "open_entry_id": body.open_entry_id,
        "iv_crush_realized": body.iv_crush_realized,
        "dte_at_close": body.dte_at_close,
        "_linked_at": datetime.now(timezone.utc).isoformat(),
    }

    # Back-link on the open entry
    entries[open_idx] = {
        **open_entry,
        "close_entry_id": close_entry_id,
    }

    data["entries"] = entries
    data["_last_updated"] = datetime.now(timezone.utc).isoformat()

    try:
        state.save_journal(data)
    except state.StateError as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "status": "linked",
        "close_entry": entries[close_idx],
        "open_entry": entries[open_idx],
    }
