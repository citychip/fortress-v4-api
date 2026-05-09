"""
Playbook endpoint — Phase 4 §8.3.

POST /api/playbook/post_earnings
Body: {ticker, gap_pct, iv_crush_pct, thesis?: {revenue_beat, guidance_maintained, ...}}
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services import state
from app.services.playbook import ThesisCheck, evaluate_post_earnings

router = APIRouter()


class ThesisPayload(BaseModel):
    revenue_beat: bool = False
    guidance_maintained: bool = False
    no_leadership_or_regulatory_event: bool = False
    sector_context_normal: bool = False


class PostEarningsRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=8)
    gap_pct: float = Field(..., description="Signed gap %, e.g. -5.2 for −5.2%")
    iv_crush_pct: float = Field(..., ge=0, description="IV crush as positive % drop, e.g. 28")
    concentration_pct: float | None = Field(
        None,
        description="Optional override; if omitted, looked up from active_positions.json"
    )
    thesis: ThesisPayload | None = None


@router.post("/playbook/post_earnings")
def post_earnings(req: PostEarningsRequest):
    ticker = req.ticker.upper().strip()
    if not ticker.isalpha():
        raise HTTPException(status_code=400, detail=f"Invalid ticker: {req.ticker!r}")

    # Concentration: if not provided, look it up from active_positions.json
    concentration = req.concentration_pct
    if concentration is None:
        try:
            positions = state.get_active_positions()
            conc_map = state.compute_concentration(positions)
            concentration = float(conc_map.get(ticker, 0.0))
        except Exception:
            concentration = None

    thesis = None
    if req.thesis is not None:
        thesis = ThesisCheck(
            revenue_beat=req.thesis.revenue_beat,
            guidance_maintained=req.thesis.guidance_maintained,
            no_leadership_or_regulatory_event=req.thesis.no_leadership_or_regulatory_event,
            sector_context_normal=req.thesis.sector_context_normal,
        )

    return evaluate_post_earnings(
        ticker=ticker,
        gap_pct=req.gap_pct,
        iv_crush_pct=req.iv_crush_pct,
        concentration_pct=concentration,
        thesis=thesis,
    )
