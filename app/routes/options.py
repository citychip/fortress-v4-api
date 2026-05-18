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


# ---------------------------------------------------------------------------
# Vol Analytics — IV Skew, Term Structure, ATM IV Ladder
# ---------------------------------------------------------------------------
from app.services import chain as chain_svc
from datetime import datetime, timezone

@router.get("/options/vol-analytics")
def get_vol_analytics(ticker: str):
    """
    Returns three volatility analytics views for a given ticker:
    - skew: IV vs strike (moneyness) for the nearest expiry with sufficient data
    - term_structure: ATM IV vs DTE across all available expiries
    - atm_iv_ladder: table of ATM IV per expiry with call/put spread

    Data source: yfinance option chain (cached 5 min).
    """
    ticker = ticker.upper()
    data = chain_svc.get_chain(ticker, max_expiries=12)

    if data.get("error"):
        from fastapi import HTTPException
        raise HTTPException(status_code=502, detail=data["error"])

    spot = data.get("spot") or 0
    expirations = data.get("expirations") or {}
    today = datetime.now(timezone.utc)

    def dte(exp_str: str) -> int:
        try:
            exp_dt = datetime.strptime(exp_str[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            return max(int((exp_dt - today).days), 0)
        except Exception:
            return 0

    def moneyness(strike: float) -> float:
        """Strike / spot — 1.0 = ATM."""
        if not spot:
            return 0.0
        return round(strike / spot, 4)

    def atm_iv(calls: list, puts: list) -> float | None:
        """IV of the call and put closest to ATM, averaged."""
        if not spot:
            return None
        best_call = min(calls, key=lambda r: abs(r["strike"] - spot), default=None)
        best_put = min(puts, key=lambda r: abs(r["strike"] - spot), default=None)
        ivs = [r["iv"] for r in [best_call, best_put] if r and r.get("iv") and r["iv"] > 0]
        return round(sum(ivs) / len(ivs), 4) if ivs else None

    # ── Skew: IV vs moneyness for nearest expiry ──────────────────────────
    skew = []
    skew_expiry = None
    sorted_exps = sorted(expirations.keys())
    for exp in sorted_exps:
        exp_dte = dte(exp)
        if exp_dte < 7:
            continue  # skip weeklies with < 7 DTE (noisy IV)
        calls = expirations[exp].get("calls", [])
        puts = expirations[exp].get("puts", [])
        # Build skew: for each strike, use call IV above ATM, put IV below ATM
        strikes = sorted(set(r["strike"] for r in calls + puts))
        for s in strikes:
            m = moneyness(s)
            if m < 0.7 or m > 1.3:
                continue  # only show ±30% moneyness
            if m >= 1.0:
                row = next((r for r in calls if r["strike"] == s and r.get("iv") and r["iv"] > 0), None)
            else:
                row = next((r for r in puts if r["strike"] == s and r.get("iv") and r["iv"] > 0), None)
            if row:
                skew.append({
                    "strike": s,
                    "moneyness": m,
                    "iv": round(row["iv"] * 100, 2),  # as percentage
                    "type": "call" if m >= 1.0 else "put",
                })
        if skew:
            skew_expiry = exp
            break

    # ── Term Structure: ATM IV vs DTE ─────────────────────────────────────
    term_structure = []
    for exp in sorted_exps:
        exp_dte = dte(exp)
        calls = expirations[exp].get("calls", [])
        puts = expirations[exp].get("puts", [])
        iv = atm_iv(calls, puts)
        if iv is not None and exp_dte >= 0:
            term_structure.append({
                "expiry": exp,
                "dte": exp_dte,
                "atm_iv": round(iv * 100, 2),  # as percentage
            })

    # ── ATM IV Ladder: table per expiry ───────────────────────────────────
    atm_ladder = []
    for exp in sorted_exps:
        exp_dte = dte(exp)
        calls = expirations[exp].get("calls", [])
        puts = expirations[exp].get("puts", [])
        if not spot:
            continue
        best_call = min(calls, key=lambda r: abs(r["strike"] - spot), default=None)
        best_put = min(puts, key=lambda r: abs(r["strike"] - spot), default=None)
        call_iv = round(best_call["iv"] * 100, 2) if best_call and best_call.get("iv") and best_call["iv"] > 0 else None
        put_iv = round(best_put["iv"] * 100, 2) if best_put and best_put.get("iv") and best_put["iv"] > 0 else None
        avg_iv = round((call_iv + put_iv) / 2, 2) if call_iv and put_iv else (call_iv or put_iv)
        iv_spread = round(abs(call_iv - put_iv), 2) if call_iv and put_iv else None
        atm_ladder.append({
            "expiry": exp,
            "dte": exp_dte,
            "atm_strike": round(spot),
            "call_iv": call_iv,
            "put_iv": put_iv,
            "avg_iv": avg_iv,
            "iv_spread": iv_spread,
        })

    return {
        "ticker": ticker,
        "spot": spot,
        "as_of": today.isoformat(),
        "skew": skew,
        "skew_expiry": skew_expiry,
        "term_structure": term_structure,
        "atm_ladder": atm_ladder,
    }
