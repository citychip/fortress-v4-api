"""
Options math endpoints.

POST /api/options/greeks   — Black-Scholes Greeks for any arbitrary strike
GET  /api/options/chain    — yfinance option chain for a ticker + expiry
"""
from __future__ import annotations

import math
import json as _json
from typing import Optional

import logging
from fastapi import APIRouter, HTTPException
logger = logging.getLogger("fortress.options")
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
from datetime import datetime as _dt, timezone as _tz

# ── py_vollib imports (installed via pip install py_vollib) ──────────────────
try:
    from py_vollib.black_scholes import black_scholes as _bs_price
    from py_vollib.black_scholes.greeks.analytical import (
        delta as _bs_delta,
        gamma as _bs_gamma,
        theta as _bs_theta,
        vega  as _bs_vega,
    )
    from py_vollib.black_scholes.implied_volatility import implied_volatility as _bs_iv
    _VOLLIB_OK = True
except ImportError:
    _VOLLIB_OK = False

_RISK_FREE = 0.045
_MULTIPLIER = 100  # standard US equity option contract

def _t_years(expiry_iso: str, as_of: _dt | None = None) -> float:
    """Calendar days from as_of to expiry, converted to years."""
    now = as_of or _dt.now(_tz.utc)
    try:
        exp = _dt.strptime(expiry_iso[:10], "%Y-%m-%d").replace(tzinfo=_tz.utc)
        days = max((exp - now).days, 0)
        return days / 365.0
    except Exception:
        return 0.0

def _leg_price(flag: str, spot: float, strike: float, t: float, iv: float) -> float:
    """Price one option leg via py_vollib BS; fall back to intrinsic if t<=0."""
    if t <= 0:
        if flag == "c":
            return max(spot - strike, 0.0)
        return max(strike - spot, 0.0)
    if not _VOLLIB_OK or iv <= 0:
        # hand-rolled fallback
        import math
        from app.services.chain import normal_cdf
        d1 = (math.log(spot / strike) + (_RISK_FREE + 0.5 * iv * iv) * t) / (iv * math.sqrt(t))
        d2 = d1 - iv * math.sqrt(t)
        disc = math.exp(-_RISK_FREE * t)
        if flag == "c":
            return spot * normal_cdf(d1) - strike * disc * normal_cdf(d2)
        return strike * disc * normal_cdf(-d2) - spot * normal_cdf(-d1)
    try:
        return _bs_price(flag, spot, strike, t, _RISK_FREE, iv)
    except Exception:
        return 0.0

def _get_leg_iv(ticker: str, right: str, strike: float, expiry: str) -> float | None:
    """Fetch IV for a specific leg from yfinance chain cache."""
    try:
        from app.services import chain as _chain_svc
        data = _chain_svc.get_chain(ticker)
        exp_key = expiry[:10]
        exps = (data or {}).get("expirations", {})
        legs = exps.get(exp_key)
        if not legs:
            return None
        book = legs.get("calls") if right.upper() == "C" else legs.get("puts")
        for o in book or []:
            if abs((o.get("strike") or 0) - strike) < 0.5:
                iv = o.get("iv")
                if iv and iv > 0:
                    return float(iv)
    except Exception:
        pass
    return None

def _strategy_limits(legs: list[dict], spot: float) -> dict:
    """
    Compute max_profit, max_loss, and breakeven(s) analytically.
    Each leg: {right, strike, qty, premium, expiry, iv}
    qty > 0 = long, qty < 0 = short.
    premium = per-share premium paid (positive) or received (negative credit).
    """
    # Net premium (positive = net debit, negative = net credit)
    net_premium = sum(
        leg.get("premium", 0) * leg.get("qty", 0)
        for leg in legs
    )

    # Scan P&L across a wide price range at expiry
    lo = spot * 0.3
    hi = spot * 2.5
    steps = 500
    step = (hi - lo) / steps
    prices = [lo + i * step for i in range(steps + 1)]

    pnl_at_expiry = []
    for p in prices:
        pnl = -net_premium  # start with credit received or debit paid (inverted sign)
        for leg in legs:
            right = leg.get("right", "C").upper()
            strike = leg.get("strike", 0)
            qty = leg.get("qty", 0)
            intrinsic = max(p - strike, 0) if right == "C" else max(strike - p, 0)
            pnl += intrinsic * qty
        pnl_at_expiry.append(pnl * _MULTIPLIER)

    max_profit_raw = max(pnl_at_expiry)
    max_loss_raw = min(pnl_at_expiry)

    # Cap unlimited profit/loss at ±10x net premium or ±spot for display
    cap = max(abs(net_premium) * _MULTIPLIER * 10, spot * 10)
    max_profit = min(max_profit_raw, cap)
    max_loss = max(max_loss_raw, -cap)

    # Breakevens: sign changes in P&L curve
    breakevens = []
    for i in range(len(pnl_at_expiry) - 1):
        a, b = pnl_at_expiry[i], pnl_at_expiry[i + 1]
        if a * b <= 0 and a != b:
            # linear interpolation
            be = prices[i] + step * (-a / (b - a))
            breakevens.append(round(be, 2))

    return {
        "max_profit": round(max_profit, 2) if max_profit < cap * 0.99 else None,  # None = unlimited
        "max_loss": round(max_loss, 2) if max_loss > -cap * 0.99 else None,       # None = unlimited
        "net_premium": round(net_premium * _MULTIPLIER, 2),
        "breakevens": breakevens[:4],  # cap at 4 breakevens
    }


@router.get("/options/position-limits")
def get_position_limits(ticker: str, legs: str):
    """
    Returns max_profit, max_loss, net_premium, and breakeven prices for a multi-leg position.
    legs: URL-encoded JSON array of leg objects.
    """
    try:
        legs_data = _json.loads(legs)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid legs JSON")

    ticker = ticker.upper()
    from app.services import chain as _chain_svc
    spot = _chain_svc.get_spot(ticker)
    if not spot or spot <= 0:
        raise HTTPException(status_code=502, detail=f"Cannot fetch spot price for {ticker}")

    # Enrich legs with IV from chain
    for leg in legs_data:
        if not leg.get("iv"):
            iv = _get_leg_iv(ticker, leg.get("right", "C"), leg.get("strike", 0), leg.get("expiry", ""))
            leg["iv"] = iv or 0.25  # fallback to 25% if unavailable

    limits = _strategy_limits(legs_data, spot)
    return {"ticker": ticker, "spot": round(spot, 2), **limits}


@router.get("/options/forward-pnl")
def get_forward_pnl(
    ticker: str,
    legs: str,
    target_price: float,
    target_date: str,
    iv_adj: float = 1.0,
):
    """
    Returns P&L at a future (target_price, target_date) with optional IV adjustment.
    Also returns a P&L-vs-price curve (51 points) for chart rendering.
    iv_adj: IV multiplier — 0.7 = 30% IV crush, 1.3 = vol expansion, 1.0 = no change.
    """
    try:
        legs_data = _json.loads(legs)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid legs JSON")

    ticker = ticker.upper()
    from app.services import chain as _chain_svc
    spot = _chain_svc.get_spot(ticker)
    if not spot or spot <= 0:
        raise HTTPException(status_code=502, detail=f"Cannot fetch spot price for {ticker}")

    now = _dt.now(_tz.utc)
    try:
        tgt_dt = _dt.strptime(target_date[:10], "%Y-%m-%d").replace(tzinfo=_tz.utc)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid target_date format, use YYYY-MM-DD")

    # Enrich legs with IV
    for leg in legs_data:
        if not leg.get("iv"):
            iv = _get_leg_iv(ticker, leg.get("right", "C"), leg.get("strike", 0), leg.get("expiry", ""))
            leg["iv"] = iv or 0.25

    # Net premium paid/received at entry
    net_premium = sum(
        leg.get("premium", 0) * leg.get("qty", 0)
        for leg in legs_data
    )

    def pnl_at(price: float) -> float:
        """P&L in dollars at a given future spot price on target_date."""
        total = -net_premium  # debit paid or credit received
        for leg in legs_data:
            right = leg.get("right", "C").upper()
            strike = leg.get("strike", 0)
            qty = leg.get("qty", 0)
            expiry = leg.get("expiry", "")
            iv = leg.get("iv", 0.25) * iv_adj
            t = _t_years(expiry, as_of=tgt_dt)
            flag = "c" if right == "C" else "p"
            leg_val = _leg_price(flag, price, strike, t, max(iv, 0.01))
            total += leg_val * qty
        return round(total * _MULTIPLIER, 2)

    # Point estimate at target_price
    target_pnl = pnl_at(target_price)

    # P&L curve: 51 points from -30% to +30% of current spot
    lo = spot * 0.70
    hi = spot * 1.30
    curve_prices = [round(lo + (hi - lo) * i / 50, 2) for i in range(51)]
    curve = [{"price": p, "pnl": pnl_at(p)} for p in curve_prices]

    # Also compute position limits (at expiry) for the badge row
    limits = _strategy_limits(legs_data, spot)

    return {
        "ticker": ticker,
        "spot": round(spot, 2),
        "target_price": target_price,
        "target_date": target_date,
        "iv_adj": iv_adj,
        "target_pnl": target_pnl,
        "curve": curve,
        **limits,
    }


# ── Roll Candidates ────────────────────────────────────────────────────────────

from datetime import date as _date_cls

@router.get("/options/roll_candidates")
def get_roll_candidates(
    ticker: str,
    right: str = "C",
    current_strike: float = 0,
    target_dte: int = 45,
    min_oi: int = 10,
):
    """
    Return Conservative / Balanced / Aggressive roll proposals for a short option leg.

    - right: 'C' (short call, e.g. PMCC) or 'P' (short put, e.g. PCS)
    - current_strike: existing short strike to roll FROM
    - target_dte: preferred DTE for the new leg (default 45)
    - min_oi: minimum open interest filter
    """
    from app.services import chain as chain_svc
    from datetime import datetime as _dt, timezone as _tz

    data = chain_svc.get_chain(ticker.upper(), max_expiries=12)
    spot = data.get("spot") or 0
    if not spot or spot <= 0:
        raise HTTPException(status_code=404, detail="Could not fetch spot price")

    expirations = data.get("expirations", {})
    today = _dt.now(_tz.utc).date()
    right_up = right.upper()

    def days_to(exp_str: str) -> int:
        try:
            return (_dt.strptime(exp_str[:10], "%Y-%m-%d").date() - today).days
        except ValueError:
            return 0

    # Collect all candidate strikes across expiries near target_dte
    candidates = []
    sorted_exps = sorted(expirations.keys(), key=days_to)

    for exp in sorted_exps:
        exp_dte = days_to(exp)
        if exp_dte < 14 or exp_dte > target_dte + 60:
            continue

        chain = expirations[exp]
        options = chain.get("calls" if right_up == "C" else "puts", [])

        for opt in options:
            strike = opt.get("strike", 0)
            mid    = opt.get("mid")
            iv     = opt.get("iv", 0) or 0
            oi     = opt.get("open_interest", 0) or 0

            if not strike or not mid or mid <= 0:
                continue
            if oi < min_oi:
                continue

            # OTM filter
            if right_up == "C" and strike <= spot:
                continue
            if right_up == "P" and strike >= spot:
                continue

            # Must be above current strike for calls (rolling up or out)
            if right_up == "C" and current_strike > 0 and strike < current_strike:
                continue

            # Compute BS delta
            t_years = max(exp_dte, 1) / 365.0
            call_delta = chain_svc.bs_call_delta(spot, strike, t_years, iv) if iv > 0.01 else None
            if call_delta is None:
                continue
            delta = call_delta if right_up == "C" else (call_delta - 1.0)

            otm_pct = (strike - spot) / spot * 100 if right_up == "C" else (spot - strike) / spot * 100

            candidates.append({
                "strike":   round(strike, 2),
                "expiry":   exp,
                "dte":      exp_dte,
                "credit":   round(mid * 100, 2),
                "mid":      round(mid, 2),
                "delta":    round(abs(delta), 3),
                "otm_pct":  round(otm_pct, 1),
                "oi":       oi,
                "iv_pct":   round(iv * 100, 1),
            })

    if not candidates:
        return {"ticker": ticker.upper(), "spot": round(spot, 2), "proposals": []}

    # Target abs(delta) by profile
    if right_up == "C":
        targets = [("Conservative", 0.30), ("Balanced", 0.20), ("Aggressive", 0.10)]
    else:
        targets = [("Conservative", 0.25), ("Balanced", 0.16), ("Aggressive", 0.08)]

    proposals = []
    used_strikes = set()
    for label, tgt_delta in targets:
        # Prefer candidates near target_dte; break ties by delta proximity
        best = min(
            candidates,
            key=lambda c: (abs(c["delta"] - tgt_delta) * 2 + abs(c["dte"] - target_dte) / target_dte)
        )
        if best["strike"] not in used_strikes:
            proposals.append({"label": label, **best})
            used_strikes.add(best["strike"])

    return {
        "ticker":    ticker.upper(),
        "spot":      round(spot, 2),
        "right":     right_up,
        "proposals": proposals,
    }
