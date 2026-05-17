"""
Options math endpoints.

POST /api/options/greeks   — Black-Scholes Greeks for any arbitrary strike
GET  /api/options/chain    — yfinance option chain for a ticker + expiry
"""
from __future__ import annotations

import math
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.bs_fallback import (
    _bs_d1d2, _norm_cdf, _norm_pdf,
    bs_theta, bs_vega, bs_gamma,
    _RISK_FREE,
)

router = APIRouter()


# ── Pydantic models ────────────────────────────────────────────────────────────

class GreeksRequest(BaseModel):
    spot:   float  = Field(..., gt=0, description="Current underlying price")
    strike: float  = Field(..., gt=0, description="Option strike price")
    dte:    int    = Field(..., ge=0, description="Calendar days to expiration")
    iv:     float  = Field(..., gt=0, description="Implied volatility as decimal, e.g. 0.35")
    right:  str    = Field(..., pattern="^[CP]$", description="'C' for call, 'P' for put")
    rate:   float  = Field(_RISK_FREE, description="Risk-free rate, default 4.5%")
    qty:    Optional[int] = Field(None, description="Signed quantity — used for position-level Greeks")


class GreeksResponse(BaseModel):
    delta:    float
    theta:    float          # per calendar day per share
    gamma:    float
    vega:     float          # per 1% IV move per share
    pop:      float          # log-normal PoP (for short option)
    intrinsic: float
    extrinsic: float
    itm:      bool
    # Position-level (populated if qty is supplied)
    pos_delta: Optional[float] = None
    pos_theta: Optional[float] = None
    pos_vega:  Optional[float] = None


# ── Route ─────────────────────────────────────────────────────────────────────

@router.post("/options/greeks", response_model=GreeksResponse)
def calculate_greeks(req: GreeksRequest):
    """
    Compute full Black-Scholes Greeks for an option.
    Returns per-share values; position-level values if qty is provided.
    """
    t = max(req.dte, 0) / 365.0

    # Edge case: expired option
    if t == 0:
        if req.right == "C":
            intrinsic = max(req.spot - req.strike, 0.0)
            delta = 1.0 if req.spot > req.strike else 0.0
        else:
            intrinsic = max(req.strike - req.spot, 0.0)
            delta = -1.0 if req.spot < req.strike else 0.0
        return GreeksResponse(
            delta=delta, theta=0.0, gamma=0.0, vega=0.0,
            pop=1.0 if intrinsic == 0 else 0.0,
            intrinsic=round(intrinsic, 4), extrinsic=0.0,
            itm=intrinsic > 0,
        )

    d1, d2 = _bs_d1d2(req.spot, req.strike, t, req.iv, req.rate)
    if d1 is None:
        raise HTTPException(status_code=422, detail="Invalid inputs for Black-Scholes (check spot/strike/iv/dte > 0)")

    r = req.rate
    discount = math.exp(-r * t)

    if req.right == "C":
        delta     = _norm_cdf(d1)
        price     = req.spot * _norm_cdf(d1) - req.strike * discount * _norm_cdf(d2)
        intrinsic = max(req.spot - req.strike, 0.0)
        # PoP for short call: probability price stays BELOW strike at expiry
        pop = _norm_cdf(-d2)
    else:
        delta     = _norm_cdf(d1) - 1.0
        price     = req.strike * discount * _norm_cdf(-d2) - req.spot * _norm_cdf(-d1)
        intrinsic = max(req.strike - req.spot, 0.0)
        # PoP for short put: probability price stays ABOVE strike at expiry
        pop = _norm_cdf(d2)

    price     = max(price, 0.0)
    extrinsic = max(price - intrinsic, 0.0)

    theta = bs_theta(req.spot, req.strike, t, req.iv, req.right, r) or 0.0
    vega  = bs_vega(req.spot, req.strike, t, req.iv, r) or 0.0
    gamma = bs_gamma(req.spot, req.strike, t, req.iv, r) or 0.0

    # Position-level (multiply by |qty| * 100; sign follows qty)
    pos_delta = pos_theta = pos_vega = None
    if req.qty is not None:
        multiplier = 100
        pos_delta = round(delta * req.qty * multiplier, 2)
        pos_theta = round(theta * req.qty * multiplier, 4)
        pos_vega  = round(vega  * req.qty * multiplier, 4)

    return GreeksResponse(
        delta    = round(delta, 4),
        theta    = round(theta, 6),
        gamma    = round(gamma, 8),
        vega     = round(vega, 6),
        pop      = round(pop, 4),
        intrinsic= round(intrinsic, 4),
        extrinsic= round(extrinsic, 4),
        itm      = intrinsic > 0,
        pos_delta= pos_delta,
        pos_theta= pos_theta,
        pos_vega = pos_vega,
    )
