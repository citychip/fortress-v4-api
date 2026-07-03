"""
Options math endpoints.

POST /api/options/greeks   — Black-Scholes Greeks for any arbitrary strike
GET  /api/options/chain    — yfinance option chain for a ticker + expiry
"""
from __future__ import annotations

import math
import json as _json
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

# ── IV quality helpers ────────────────────────────────────────────────────────

def _is_quantized_iv(iv: float) -> bool:
    """Detect yfinance binary-fraction IVs (multiples of 1/128 = 0.0078125)."""
    if iv <= 0:
        return True
    fraction = iv * 128.0
    return abs(fraction - round(fraction)) < 0.01   # within 1% of a 1/128 multiple

def _clean_iv(iv_raw: float | None, spot: float, strike: float, dte_days: int,
               mid: float | None, right: str = "c") -> float | None:
    """
    Return a clean IV value:
    1. If yfinance IV looks quantized AND mid price is available → recalculate with py_vollib BS.
    2. If IV is below 3% or above 200% → treat as missing.
    3. Otherwise return yfinance IV as-is.
    """
    MIN_IV, MAX_IV = 0.03, 2.0
    if iv_raw and MIN_IV <= iv_raw <= MAX_IV and not _is_quantized_iv(iv_raw):
        return iv_raw  # clean yfinance value
    # Attempt BS recalculation from mid price
    if mid and mid > 0 and spot > 0 and strike > 0 and dte_days > 0:
        try:
            from py_vollib.black_scholes.implied_volatility import implied_volatility as _bsiv
            t = dte_days / 365.0
            flag = right.lower()[0]  # 'c' or 'p'
            iv_calc = _bsiv(mid, spot, strike, t, _RISK_FREE, flag)
            if MIN_IV <= iv_calc <= MAX_IV:
                return round(iv_calc, 4)
        except Exception:
            pass
    # Fall back to yfinance if it's in range
    if iv_raw and MIN_IV <= iv_raw <= MAX_IV:
        return iv_raw
    return None


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

    def clean_row_iv(row: dict, right: str) -> float | None:
        """Return a cleaned IV for a single options row."""
        if not row:
            return None
        exp_str = next((e for e, exp_data in expirations.items()
                        if row in exp_data.get("calls", []) + exp_data.get("puts", [])), None)
        d = dte(exp_str) if exp_str else 30
        return _clean_iv(row.get("iv"), spot, row.get("strike", 0), d, row.get("mid"), right)

    def atm_iv(calls: list, puts: list) -> float | None:
        """IV of the call and put closest to ATM, averaged — with IV cleaning."""
        if not spot:
            return None
        best_call = min(calls, key=lambda r: abs(r["strike"] - spot), default=None)
        best_put  = min(puts,  key=lambda r: abs(r["strike"] - spot), default=None)
        ivs = []
        if best_call:
            iv = _clean_iv(best_call.get("iv"), spot, best_call.get("strike", 0), 30, best_call.get("mid"), "c")
            if iv: ivs.append(iv)
        if best_put:
            iv = _clean_iv(best_put.get("iv"), spot, best_put.get("strike", 0), 30, best_put.get("mid"), "p")
            if iv: ivs.append(iv)
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
                right_flag = "c" if m >= 1.0 else "p"
                iv_clean = _clean_iv(row.get("iv"), spot, s, dte(skew_expiry or exp), row.get("mid"), right_flag)
                if iv_clean:
                    skew.append({
                        "strike": s,
                        "moneyness": m,
                        "iv": round(iv_clean * 100, 2),
                        "type": right_flag,
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
        raw_call_iv = _clean_iv(best_call.get("iv") if best_call else None, spot, round(spot), exp_dte, best_call.get("mid") if best_call else None, "c") if best_call else None
        raw_put_iv  = _clean_iv(best_put.get("iv")  if best_put  else None, spot, round(spot), exp_dte, best_put.get("mid")  if best_put  else None, "p") if best_put  else None
        call_iv = round(raw_call_iv * 100, 2) if raw_call_iv else None
        put_iv  = round(raw_put_iv  * 100, 2) if raw_put_iv  else None
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
    import logging as _logging
    _log = _logging.getLogger("fortress.options.roll")
    from app.services import chain as chain_svc
    from datetime import datetime as _dt, timezone as _tz

    # Spot price first (fast — cached)
    spot = chain_svc.get_spot(ticker.upper()) or 0
    if not spot or spot <= 0:
        raise HTTPException(status_code=404, detail="Could not fetch spot price")

    # Try IBKR live chain; fall back to yfinance
    chain_data = None
    try:
        from app.services import ibkr_chain as _ibkr_chain
        chain_data = _ibkr_chain.get_ibkr_chain(
            ticker.upper(), right=right.upper(), spot=spot,
            target_dte=target_dte, max_expiries=3,
        )
        if chain_data and chain_data.get("expirations"):
            _log.info("roll_candidates: IBKR live chain for %s (%d expiries)",
                      ticker, len(chain_data["expirations"]))
    except Exception as _e:
        _log.debug("IBKR chain unavailable, using yfinance: %s", _e)

    if not chain_data or not chain_data.get("expirations"):
        chain_data = chain_svc.get_chain(ticker.upper(), max_expiries=5)
        _log.info("roll_candidates: yfinance chain for %s", ticker)

    expirations = chain_data.get("expirations", {})
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
    used_strikes: set[float] = set()
    for label, tgt_delta in targets:
        # Only consider strikes not already used by a prior profile
        available = [c for c in candidates if c["strike"] not in used_strikes]
        if not available:
            break
        # Prefer candidates near target_dte; break ties by delta proximity
        best = min(
            available,
            key=lambda c: (abs(c["delta"] - tgt_delta) * 2 + abs(c["dte"] - target_dte) / target_dte)
        )
        proposals.append({"label": label, **best})
        used_strikes.add(best["strike"])

    return {
        "ticker":    ticker.upper(),
        "spot":      round(spot, 2),
        "right":     right_up,
        "proposals": proposals,
    }


# ── Strategy Metrics ───────────────────────────────────────────────────────────

def pick_short_call_delta(
    ivr: float | None,
    regime: str | None,
    weekly_below_200: bool | None,
    days_to_earnings: int | None,
    conc_pct: float | None,
) -> tuple[float, list[str]]:
    """Sprint 21.1b — adaptive short-call delta for the PMCC / Diagonal / covered-
    call income leg (replaces the hard-coded 0.20).

    Base anchor 0.30, clamped to [min, max]; signed nudges (each logs a rationale
    line so every pick is explainable in the briefing):
      • IVR / VRP — rich premium (high IVR) → sell further OTM (LOWER Δ, keep
        upside); thin premium (low IVR) → HIGHER Δ to reach target income.
      • Weekly trend — a name below its weekly 200-SMA → HIGHER Δ (closer strike =
        more premium + more downside cushion, since the short call gains as it
        falls). ``weekly_below_200`` is None until the Sprint 22.1 weekly-SMA ingest
        lands; when None the trend nudge is skipped, so the engine is fully
        functional today on the IVR / catalyst / concentration factors.
      • Catalyst — inside a ≤10d earnings window → LOWER Δ to cut gap risk.
      • Concentration — an over-cap name (> single_name_cap_pct) → HIGHER Δ; a
        closer short call trims net delta so it doubles as de-risk.

    Returns ``(target_delta, rationale[])``.
    """
    from app.services.config_store import cfg

    base = cfg("strategy.short_call_base_delta", 0.30)
    lo   = cfg("strategy.short_call_delta_min", 0.20)
    hi   = cfg("strategy.short_call_delta_max", 0.40)
    cap  = cfg("strategy.single_name_cap_pct", 20.0)

    d: float = float(base)
    why: list[str] = []

    if ivr is not None:
        if ivr >= 70:
            d -= 0.05 * cfg("strategy.delta_ivr_weight", 1.0)
            why.append(f"IVR {ivr:.0f} high → −Δ (further OTM)")
        elif ivr <= 35:
            d += 0.05 * cfg("strategy.delta_ivr_weight", 1.0)
            why.append(f"IVR {ivr:.0f} low → +Δ")

    if weekly_below_200:
        d += 0.05 * cfg("strategy.delta_trend_weight", 1.0)
        why.append("below wk-200 → +Δ (premium + cushion)")

    if days_to_earnings is not None and days_to_earnings <= 10:
        d -= 0.05 * cfg("strategy.delta_catalyst_weight", 1.0)
        why.append(f"earnings ≤10d ({days_to_earnings}) → −Δ (gap risk)")

    if conc_pct and conc_pct > cap:
        d += 0.03 * cfg("strategy.delta_concentration_weight", 1.0)
        why.append(f"conc {conc_pct:.0f}% > {cap:.0f}% → +Δ (de-risk)")

    clamped = max(lo, min(hi, d))
    if abs(clamped - d) > 1e-9:
        why.append(f"clamped to [{lo:.2f},{hi:.2f}]")
    if not why:
        why.append(f"base {base:.2f} (no nudges)")
    return round(clamped, 2), why


@router.get("/options/strategy_metrics")
def get_strategy_metrics(
    ticker: str,
    mode: str = "new",          # 'new' | 'add'
    target_dte: int = 45,
):
    """
    Compute live metrics for each available strategy given the current ticker's IV,
    spot, IVR, earnings distance, and regime.  Used by Phase 6 Strategy Selector.

    Returns a ranked list of strategies with:
      estimated_credit, pop, max_loss, capital_required, regime_score, recommended
    """
    import math as _math
    import logging as _log_mod
    _log = _log_mod.getLogger("fortress.options.strategy_metrics")

    ticker = ticker.upper()
    from app.services import chain as chain_svc

    spot = chain_svc.get_spot(ticker) or 0
    if not spot or spot <= 0:
        raise HTTPException(status_code=404, detail="Cannot fetch spot price")

    # ── Real vol + earnings from canonical sources (Sprint 15.1) ─────────────
    # Previously IV/IVR/DTE were read off get_market_intelligence, but that path
    # was doubly broken: imported from app.routes.market (wrong module → throws)
    # AND the intel payload never emits current_iv / iv_rank / days_to_earnings.
    # Every call therefore silently fell back to IV 0.30 / IVR 50 / DTE 999 — the
    # exact placeholder the strategy_metrics caveat warned about. Now:
    #   • IV + IVR ← get_iv_rank (IBKR-first; BS-inversion / HV-proxy fallback)
    #   • DTE      ← state.days_to_earnings (same source as briefing / manage)
    #   • Regime   ← get_market_intelligence (Sprint 15.3): the synthesized
    #     overall regime (GEX + dark-pool + net-drift + macro + VIX term) is
    #     normalized to canonical bullish/bearish/neutral so regime_score can
    #     match it. Falls back to neutral on any error.
    iv: float = 0.30        # last-resort fallback only
    ivr: float = 50.0
    days_to_earnings: int = 999
    regime_overall: str = "neutral"
    gex_regime: str = "neutral"
    regime_source: str = "placeholder"
    vix_term_state: str | None = None
    vol_source: str = "placeholder"
    regime_gate_obj: dict | None = None   # Sprint 21.3 canonical gate (label+inputs)

    try:
        from app.routes.options_analytics import get_iv_rank
        ivd = get_iv_rank(ticker)
        if isinstance(ivd, dict) and not ivd.get("error"):
            ci = ivd.get("current_iv")
            if ci and ci > 0:
                iv = ci / 100.0 if ci > 1 else ci
                vol_source = ivd.get("iv_source") or ivd.get("source") or "iv_rank"
            r = ivd.get("iv_rank")
            if r is not None:
                ivr = float(r)
    except Exception as e:
        _log.warning("get_iv_rank unavailable for %s: %s — using fallback vol", ticker, e)

    try:
        from app.services import state as _state
        _d = _state.days_to_earnings(ticker, _state.get_earnings_blocklist())
        if _d is not None:
            days_to_earnings = _d
    except Exception as e:
        _log.debug("earnings distance unavailable for %s: %s", ticker, e)

    # ── Real regime (Sprint 15.3) ────────────────────────────────────────────
    # Synthesized regime from market-intelligence (now incl. VIX-term shape).
    # Normalize the granular label ("Strongly Bullish" … "Strongly Bearish",
    # "Neutral") down to canonical bullish/bearish/neutral that regime_score
    # compares against. gex_regime comes straight off the gamma_regime field.
    def _normalize_regime(label: str | None) -> str:
        s = (label or "").lower()
        if "bull" in s:
            return "bullish"
        if "bear" in s:
            return "bearish"
        return "neutral"

    try:
        from app.routes.market_intelligence import get_market_intelligence
        intel = get_market_intelligence(ticker)
        _regime = (intel or {}).get("regime", {}) or {}
        # Sprint 21.3: prefer the single canonical regime_gate.label so this
        # endpoint and get_briefing read the same gate; fall back to the granular
        # `overall` (normalized) if the gate isn't present.
        _gate = _regime.get("regime_gate") or {}
        _overall = _gate.get("label") or _regime.get("overall")
        if _overall:
            regime_overall = _normalize_regime(_overall)
            regime_source = "regime_gate" if _gate.get("label") else "market_intelligence"
        if _gate:
            regime_gate_obj = _gate
        _gamma = _regime.get("gamma_regime")
        if _gamma:
            gex_regime = _gamma  # "positive" | "negative"
        _vt = _regime.get("vix_term") or {}
        vix_term_state = _vt.get("state")
    except Exception as e:
        _log.warning("regime synthesis unavailable for %s: %s — neutral fallback", ticker, e)

    # ── Single-name concentration (Sprint 21.1b adaptive-delta input; also the
    #    21.5 gate input) — canonical MV/NLV basis, best-effort, soft-fail to None
    #    so a missing positions file never breaks strategy_metrics.
    conc_pct: float | None = None
    try:
        from app.services import state as _cstate
        _conc = _cstate.compute_concentration(_cstate.get_active_positions())
        if isinstance(_conc, dict):
            conc_pct = _conc.get(ticker)
    except Exception as e:
        _log.debug("concentration unavailable for %s: %s", ticker, e)

    # Weekly-trend input for the adaptive engine is wired but None until the
    # Sprint 22.1 weekly-200-SMA ingest lands (the trend nudge no-ops on None).
    weekly_below_200: bool | None = None

    if iv <= 0:
        iv = 0.30

    # ── BS helpers ────────────────────────────────────────────────────────────
    def bs_price_call(S: float, K: float, t_years: float, sigma: float) -> float:
        if t_years <= 0 or sigma <= 0:
            return max(S - K, 0)
        d1 = (_math.log(S / K) + (_RISK_FREE + 0.5 * sigma**2) * t_years) / (sigma * _math.sqrt(t_years))
        d2 = d1 - sigma * _math.sqrt(t_years)
        from app.services.bs_fallback import _norm_cdf
        return S * _norm_cdf(d1) - K * _math.exp(-_RISK_FREE * t_years) * _norm_cdf(d2)

    def bs_price_put(S: float, K: float, t_years: float, sigma: float) -> float:
        call = bs_price_call(S, K, t_years, sigma)
        # put-call parity
        return call - S + K * _math.exp(-_RISK_FREE * t_years)

    def norm_cdf(x: float) -> float:
        from app.services.bs_fallback import _norm_cdf
        return _norm_cdf(x)

    def pop_short_put(S: float, K: float, t_years: float, sigma: float) -> float:
        """P(S_T >= K) = N(d2) for short put."""
        if t_years <= 0 or sigma <= 0:
            return 1.0 if S >= K else 0.0
        d2 = (_math.log(S / K) + (_RISK_FREE - 0.5 * sigma**2) * t_years) / (sigma * _math.sqrt(t_years))
        return norm_cdf(d2)

    def pop_short_call(S: float, K: float, t_years: float, sigma: float) -> float:
        """P(S_T <= K) = N(-d2) for short call."""
        return 1 - pop_short_put(S, K, t_years, sigma)

    def target_strike_by_delta(delta_target: float, right: str = "C") -> float:
        """Approximate strike where abs(delta) ≈ delta_target via DIRECTION-AWARE
        bisection.

        Sprint 21.1a fix — the previous branch was inverted for CALLS. For a call
        |delta| *falls* as strike rises, but the old code did
        ``if abs(d) < delta_target: lo = mid`` which pushed the search to HIGHER
        strikes when delta was already too low → it converged to the upper bound
        (spot*2.0). That is exactly what produced the MSFT $780C / GOOGL $715C /
        SPY $1485C strikes with ``estimated_credit == 0``. Puts happened to be
        correct (|delta| *rises* with strike), which is why PCS/CSP returned sane
        ~0.20Δ strikes and only the call-based PMCC/Diagonal broke.

        Now each right moves the correct bound; iterations bumped 40→60 for tighter
        convergence on the wider search band.
        """
        t = target_dte / 365.0
        if t <= 0 or iv <= 0:
            return spot
        lo, hi = spot * 0.5, spot * 2.0
        mid = spot
        for _ in range(60):
            mid = (lo + hi) / 2
            d1 = (_math.log(spot / mid) + (_RISK_FREE + 0.5 * iv**2) * t) / (iv * _math.sqrt(t))
            d = norm_cdf(d1) if right.upper() == "C" else norm_cdf(d1) - 1.0
            ad = abs(d)
            if right.upper() == "C":
                # |delta| falls as strike rises
                if ad > delta_target:
                    lo = mid   # too much delta → strike must go HIGHER
                else:
                    hi = mid   # too little delta → strike must go LOWER
            else:
                # |delta| rises as strike rises
                if ad > delta_target:
                    hi = mid   # too much delta → strike must go LOWER
                else:
                    lo = mid   # too little delta → strike must go HIGHER
            if abs(ad - delta_target) < 0.001:
                break
        return round(mid / 5) * 5  # round to nearest 5

    t = target_dte / 365.0
    t_long = 365.0 / 365.0  # ~1 year LEAP

    # ── Scoring helpers ───────────────────────────────────────────────────────
    def regime_score(ideal_ivr: float, bias: str) -> int:
        """0-5 regime fit score."""
        score = 0
        if ivr >= ideal_ivr:
            score += 2
        elif ivr >= ideal_ivr * 0.75:
            score += 1
        bull = regime_overall in ("bullish", "BULLISH")
        bear = regime_overall in ("bearish", "BEARISH")
        neutral = not bull and not bear
        if bias == "bullish" and bull:     score += 2
        elif bias == "neutral" and neutral: score += 2
        elif bias == "bearish" and bear:    score += 2
        elif bias in ("bullish", "neutral") and neutral: score += 1
        # Earnings penalty
        if days_to_earnings <= 7:
            score = max(0, score - 2)
        elif days_to_earnings <= 14:
            score = max(0, score - 1)
        return min(5, score)

    strategies = []

    # ── 1. PCS (Put Credit Spread) ─────────────────────────────────────────
    short_put_strike = target_strike_by_delta(0.20, "P")
    long_put_strike  = max(short_put_strike - round(spot * 0.05 / 5) * 5, 1.0)
    short_put_price  = bs_price_put(spot, short_put_strike, t, iv)
    long_put_price   = bs_price_put(spot, long_put_strike,  t, iv)
    pcs_credit       = max(short_put_price - long_put_price, 0) * 100
    pcs_width        = (short_put_strike - long_put_strike) * 100
    pcs_max_loss     = max(pcs_width - pcs_credit, 0)
    pcs_pop          = pop_short_put(spot, short_put_strike, t, iv)
    pcs_score        = regime_score(40, "bullish")
    strategies.append({
        "id":               "pcs",
        "name":             "Put Credit Spread",
        "short_name":       "PCS",
        "description":      f"Sell ${short_put_strike:.0f}P / Buy ${long_put_strike:.0f}P · {target_dte}d",
        "short_strike":     short_put_strike,
        "long_strike":      long_put_strike,
        "estimated_credit": round(pcs_credit, 2),
        "pop":              round(pcs_pop, 3),
        "max_loss":         round(pcs_max_loss, 2),
        "capital_required": round(pcs_max_loss, 2),
        "regime_score":     pcs_score,
        "max_loss_type":    "defined",
        "bias":             "bullish",
        "ideal_ivr":        40,
        "min_dte":          30,
        "max_dte":          60,
        "legs":             2,
        "earnings_safe":    days_to_earnings > 10,
    })

    # ── 2. CSP (Cash-Secured Put) ──────────────────────────────────────────
    csp_strike  = short_put_strike  # same delta target
    csp_credit  = bs_price_put(spot, csp_strike, t, iv) * 100
    csp_max_loss = csp_strike * 100  # if assigned (conceptual)
    csp_pop     = pop_short_put(spot, csp_strike, t, iv)
    csp_capital = csp_strike * 100
    csp_score   = regime_score(30, "bullish")
    strategies.append({
        "id":               "csp",
        "name":             "Cash-Secured Put",
        "short_name":       "CSP",
        "description":      f"Sell ${csp_strike:.0f}P · {target_dte}d",
        "short_strike":     csp_strike,
        "long_strike":      None,
        "estimated_credit": round(csp_credit, 2),
        "pop":              round(csp_pop, 3),
        "max_loss":         round(csp_max_loss, 2),
        "capital_required": round(csp_capital, 2),
        "regime_score":     csp_score,
        "max_loss_type":    "limited",
        "bias":             "bullish",
        "ideal_ivr":        30,
        "min_dte":          30,
        "max_dte":          60,
        "legs":             1,
        "earnings_safe":    days_to_earnings > 10,
    })

    # ── 3. PMCC (Poor Man's Covered Call) ─────────────────────────────────
    # Sprint 21.1b: adaptive short-call delta (was hard-coded 0.20) — reasons from
    # IVR / weekly trend / catalyst / concentration and logs a rationale.
    pmcc_short_delta, pmcc_delta_rationale = pick_short_call_delta(
        ivr, regime_overall, weekly_below_200, days_to_earnings, conc_pct,
    )
    short_call_strike   = target_strike_by_delta(pmcc_short_delta, "C")
    leap_strike         = round(spot * 0.75 / 5) * 5   # deep ITM ~delta 0.75
    short_call_price    = bs_price_call(spot, short_call_strike, t, iv)
    leap_price          = bs_price_call(spot, leap_strike, t_long, iv)
    pmcc_monthly_credit = short_call_price * 100
    pmcc_max_spread     = (short_call_strike - leap_strike) * 100
    pmcc_max_profit     = pmcc_max_spread  # per contract, ignoring LEAP cost
    pmcc_max_loss       = leap_price * 100 - pmcc_monthly_credit  # approx
    pmcc_capital        = leap_price * 100
    pmcc_pop            = pop_short_call(spot, short_call_strike, t, iv)
    pmcc_score          = regime_score(25, "bullish")
    strategies.append({
        "id":               "pmcc",
        "name":             "Poor Man's Covered Call",
        "short_name":       "PMCC",
        "description":      f"Long ${leap_strike:.0f}C (1yr LEAP) + Sell ${short_call_strike:.0f}C · {target_dte}d",
        "short_strike":     short_call_strike,
        "long_strike":      leap_strike,
        "estimated_credit": round(pmcc_monthly_credit, 2),
        "target_delta":     pmcc_short_delta,
        "delta_rationale":  pmcc_delta_rationale,
        "pop":              round(pmcc_pop, 3),
        "max_loss":         round(max(pmcc_max_loss, 0), 2),
        "capital_required": round(pmcc_capital, 2),
        "regime_score":     pmcc_score,
        "max_loss_type":    "limited",
        "bias":             "bullish",
        "ideal_ivr":        25,
        "min_dte":          30,
        "max_dte":          60,
        "legs":             2,
        "earnings_safe":    days_to_earnings > 14,
    })

    # ── 4. Iron Condor ─────────────────────────────────────────────────────
    short_call_ic = target_strike_by_delta(0.15, "C")
    long_call_ic  = short_call_ic + round(spot * 0.05 / 5) * 5
    short_put_ic  = target_strike_by_delta(0.15, "P")
    long_put_ic   = max(short_put_ic - round(spot * 0.05 / 5) * 5, 1.0)
    call_credit   = max(bs_price_call(spot, short_call_ic, t, iv) - bs_price_call(spot, long_call_ic, t, iv), 0) * 100
    put_credit    = max(bs_price_put(spot, short_put_ic, t, iv)   - bs_price_put(spot, long_put_ic,  t, iv), 0) * 100
    ic_credit     = call_credit + put_credit
    ic_width      = (long_call_ic - short_call_ic) * 100
    ic_max_loss   = max(ic_width - ic_credit, 0)
    ic_pop        = pop_short_put(spot, short_put_ic, t, iv) * pop_short_call(spot, short_call_ic, t, iv)
    ic_score      = regime_score(55, "neutral")
    strategies.append({
        "id":               "iron_condor",
        "name":             "Iron Condor",
        "short_name":       "IC",
        "description":      f"${short_put_ic:.0f}/${long_put_ic:.0f}P + ${short_call_ic:.0f}/${long_call_ic:.0f}C · {target_dte}d",
        "short_strike":     short_put_ic,
        "long_strike":      short_call_ic,
        "estimated_credit": round(ic_credit, 2),
        "pop":              round(ic_pop, 3),
        "max_loss":         round(ic_max_loss, 2),
        "capital_required": round(ic_max_loss, 2),
        "regime_score":     ic_score,
        "max_loss_type":    "defined",
        "bias":             "neutral",
        "ideal_ivr":        55,
        "min_dte":          30,
        "max_dte":          60,
        "legs":             4,
        "earnings_safe":    days_to_earnings > 10,
    })

    # ── 5. Diagonal (call diagonal / calendar spread variant) ─────────────
    diag_short_strike = short_call_strike  # Sprint 21.1b: adaptive short-call Δ (shared with PMCC)
    diag_long_strike  = round(spot * 0.95 / 5) * 5  # slight OTM long call at 90d
    diag_short_price  = bs_price_call(spot, diag_short_strike, t, iv)
    diag_long_price   = bs_price_call(spot, diag_long_strike,  90 / 365.0, iv)
    diag_credit       = max(diag_short_price - diag_long_price, 0) * 100
    diag_debit        = max(diag_long_price - diag_short_price, 0) * 100
    diag_net          = diag_short_price * 100 - diag_long_price * 100
    diag_max_loss     = diag_long_price * 100  # approx cost of long leg
    diag_capital      = diag_long_price * 100
    diag_pop          = pop_short_call(spot, diag_short_strike, t, iv)
    diag_score        = regime_score(30, "bullish")
    strategies.append({
        "id":               "diagonal",
        "name":             "Call Diagonal",
        "short_name":       "Diagonal",
        "description":      f"Long ${diag_long_strike:.0f}C (90d) + Sell ${diag_short_strike:.0f}C · {target_dte}d",
        "short_strike":     diag_short_strike,
        "long_strike":      diag_long_strike,
        "estimated_credit": round(diag_short_price * 100, 2),
        "target_delta":     pmcc_short_delta,
        "delta_rationale":  pmcc_delta_rationale,
        "net_debit_credit": round(diag_net, 2),
        "pop":              round(diag_pop, 3),
        "max_loss":         round(diag_max_loss, 2),
        "capital_required": round(diag_capital, 2),
        "regime_score":     diag_score,
        "max_loss_type":    "limited",
        "bias":             "bullish",
        "ideal_ivr":        30,
        "min_dte":          30,
        "max_dte":          60,
        "legs":             2,
        "earnings_safe":    days_to_earnings > 10,
    })

    # ── Sprint 21.1b sanity guard: never present a $0-credit "income" structure ─
    #    A zero credit means the short strike came out mid-air (the pre-21.1a bug)
    #    or premium is genuinely absent — either way it must never be recommended.
    for s in strategies:
        cr = s.get("estimated_credit") or 0
        s["credit_ok"] = cr > 0
        if cr <= 0:
            s.setdefault("flags", []).append("zero_credit")

    # ── Sprint 21.2: annualized yield + SINGULAR recommended ───────────────────
    #    Previously every strategy tied at best regime_score was recommended=True
    #    (PCS/CSP/PMCC/Diagonal all at once). Now: add annualized_yield, rank by
    #    (regime_score desc, annualized_yield desc), and flag exactly ONE best that
    #    also passes the available gates. The rest are `eligible` (pass gates) or
    #    carry a `gate_reason`.
    for s in strategies:
        cap = max(s.get("capital_required") or 0, 1)
        hold = max(target_dte, 1)
        s["annualized_yield"] = round((s.get("estimated_credit") or 0) / cap * (365.0 / hold), 4)

    def _passes_gates(s) -> tuple[bool, str | None]:
        # Hard gates wired today: earnings window + non-zero credit. The trend gate
        # (21.4, warn-mode) and concentration gate (21.5) attach here once the
        # Sprint 22.1 weekly-SMA ingest lands — they will set eligible=False +
        # a caution without removing the strategy.
        if not s.get("credit_ok"):
            return False, "zero_credit"
        if not s.get("earnings_safe"):
            return False, "earnings_window"
        return True, None

    strategies.sort(
        key=lambda s: (s["regime_score"], s.get("annualized_yield", 0.0)),
        reverse=True,
    )
    _recommended_set = False
    for s in strategies:
        ok, reason = _passes_gates(s)
        s["eligible"] = ok
        if reason:
            s["gate_reason"] = reason
        if ok and not _recommended_set:
            s["recommended"] = True
            _recommended_set = True
        else:
            s["recommended"] = False
    recommended_id = next((s["id"] for s in strategies if s.get("recommended")), None)

    return {
        "ticker":           ticker,
        "spot":             round(spot, 2),
        "iv":               round(iv * 100, 1),
        "ivr":              round(ivr, 1),
        "vol_source":       vol_source,
        "days_to_earnings": days_to_earnings,
        "regime":           regime_overall,
        "regime_source":    regime_source,
        "regime_gate":      regime_gate_obj,
        "gex_regime":       gex_regime,
        "vix_term_state":   vix_term_state,
        "mode":             mode,
        "recommended_id":   recommended_id,
        "strategies":       strategies,
    }


# ─── Scenario Estimate ────────────────────────────────────────────────────────

class ScenarioLeg(BaseModel):
    ticker:   str
    strategy: str    # 'PMCC' | 'CSP' | 'COVERED_CALL' | 'IRON_CONDOR' | 'JADE_LIZARD' | etc.
    qty:      int    = 1
    dte:      int    = 45

class ScenarioRequest(BaseModel):
    positions: list[ScenarioLeg]

@router.post("/scenario/estimate")
def scenario_estimate(req: ScenarioRequest):
    """
    For each hypothetical position, estimate delta/theta/vega/notional using BS
    at a standard entry point (Δ0.20 short leg, same logic as strategy_metrics).
    Returns per-position estimates + aggregate portfolio impact.
    """
    import math as _m
    import logging as _log_mod
    _log = _log_mod.getLogger("fortress.scenario")

    results = []
    agg_delta = agg_theta = agg_vega = 0.0

    for leg in req.positions:
        ticker = leg.ticker.upper()
        dte = max(1, leg.dte)
        t = dte / 365.0

        # ── Spot + IV ────────────────────────────────────────────────────────
        spot: float = 0.0
        iv: float = 0.30
        try:
            spot = chain_svc.get_spot(ticker) or 0.0
        except Exception:
            pass
        if not spot:
            results.append({
                "ticker": ticker, "strategy": leg.strategy, "qty": leg.qty,
                "error": "spot unavailable",
                "delta": 0.0, "theta": 0.0, "vega": 0.0, "notional": 0.0,
            })
            continue

        # IV from the canonical source (Sprint 17 fix). The old path imported
        # `app.routes.market` (wrong module → ImportError, always caught) AND read
        # `current_iv` off the market-intel payload, which never emits it — so this
        # silently fell to 0.30 every time (same double-bug class as 15.1). Use
        # get_iv_rank (IBKR-first; BS-inversion / HV-proxy fallback), exactly like
        # strategy_metrics.
        try:
            from app.routes.options_analytics import get_iv_rank
            ivd = get_iv_rank(ticker)
            if isinstance(ivd, dict) and not ivd.get("error"):
                ci = ivd.get("current_iv")
                if ci and ci > 0:
                    iv = ci / 100.0 if ci > 1 else ci
        except Exception:
            pass
        if iv <= 0:
            iv = 0.30

        # ── BS helpers ───────────────────────────────────────────────────────
        rf = _RISK_FREE
        sq_t = _m.sqrt(t)

        def d1d2(S, K):
            if K <= 0 or S <= 0 or iv <= 0 or t <= 0:
                return 0.0, 0.0
            d1 = (_m.log(S / K) + (rf + 0.5 * iv**2) * t) / (iv * sq_t)
            return d1, d1 - iv * sq_t

        def put_delta(S, K):
            d1, _ = d1d2(S, K)
            return _norm_cdf(d1) - 1.0

        def call_delta(S, K):
            d1, _ = d1d2(S, K)
            return _norm_cdf(d1)

        def theta_put(S, K):
            d1, d2 = d1d2(S, K)
            term1 = -(S * _norm_pdf(d1) * iv) / (2 * sq_t)
            term2 = rf * K * _m.exp(-rf * t) * _norm_cdf(-d2)
            return (term1 + term2) / 365.0  # per day

        def theta_call(S, K):
            d1, d2 = d1d2(S, K)
            term1 = -(S * _norm_pdf(d1) * iv) / (2 * sq_t)
            term2 = -rf * K * _m.exp(-rf * t) * _norm_cdf(d2)
            return (term1 + term2) / 365.0

        def vega_any(S, K):
            d1, _ = d1d2(S, K)
            return S * _norm_pdf(d1) * sq_t * 0.01  # per 1% IV move

        # ── Strike approximation at Δ0.20 ───────────────────────────────────
        def strike_at_delta(target_delta: float, right: str = "P") -> float:
            lo, hi = spot * 0.3, spot * 1.8
            for _ in range(40):
                mid = (lo + hi) / 2.0
                d = put_delta(spot, mid) if right == "P" else call_delta(spot, mid)
                if abs(d) < target_delta:
                    hi = mid
                else:
                    lo = mid
            return (lo + hi) / 2.0

        strat = leg.strategy.upper()
        delta = theta = vega = notional = 0.0

        try:
            if strat in ("CSP", "CASH_SECURED_PUT"):
                K = strike_at_delta(0.20, "P")
                delta    = put_delta(spot, K) * 100 * leg.qty
                theta    = -theta_put(spot, K) * 100 * leg.qty  # positive theta for short
                vega     = -vega_any(spot, K) * 100 * leg.qty
                notional = K * 100 * leg.qty

            elif strat in ("COVERED_CALL", "CC"):
                K = strike_at_delta(0.20, "C")
                delta    = (1.0 - call_delta(spot, K)) * 100 * leg.qty  # long stock - short call
                theta    = -theta_call(spot, K) * 100 * leg.qty
                vega     = -vega_any(spot, K) * 100 * leg.qty
                notional = spot * 100 * leg.qty

            elif strat == "PMCC":
                # Long LEAP (deep ITM ~0.80 delta) + short call (0.20 delta)
                K_leap  = spot * 0.75   # approx 0.80 delta strike
                K_short = strike_at_delta(0.20, "C")
                d_leap  = call_delta(spot, K_leap)
                d_short = call_delta(spot, K_short)
                delta    = (d_leap - d_short) * 100 * leg.qty
                theta    = (-theta_call(spot, K_leap) - theta_call(spot, K_short)) * 100 * leg.qty
                vega     = (vega_any(spot, K_leap) - vega_any(spot, K_short)) * 100 * leg.qty
                notional = K_leap * 100 * leg.qty  # LEAP cost proxy

            elif strat in ("IRON_CONDOR", "IC"):
                K_put  = strike_at_delta(0.16, "P")
                K_call = strike_at_delta(0.16, "C")
                wing   = spot * 0.04
                delta  = 0.0   # roughly delta-neutral
                theta  = (-theta_put(spot, K_put) - theta_call(spot, K_call)) * 100 * leg.qty
                vega   = (-vega_any(spot, K_put) - vega_any(spot, K_call)) * 100 * leg.qty
                notional = wing * 100 * leg.qty  # max loss proxy

            elif strat in ("JADE_LIZARD", "JL"):
                K_put  = strike_at_delta(0.20, "P")
                K_call = strike_at_delta(0.20, "C")
                delta  = (put_delta(spot, K_put) + call_delta(spot, K_call)) * 100 * leg.qty
                theta  = (-theta_put(spot, K_put) - theta_call(spot, K_call)) * 100 * leg.qty
                vega   = (-vega_any(spot, K_put) - vega_any(spot, K_call)) * 100 * leg.qty
                notional = K_put * 100 * leg.qty

            elif strat in ("BULL_CALL_SPREAD", "BCS"):
                K1 = spot  # ATM long
                K2 = spot * 1.05  # OTM short
                delta    = (call_delta(spot, K1) - call_delta(spot, K2)) * 100 * leg.qty
                theta    = (theta_call(spot, K1) - theta_call(spot, K2)) * 100 * leg.qty
                vega     = (vega_any(spot, K1) - vega_any(spot, K2)) * 100 * leg.qty
                notional = (K2 - K1) * 100 * leg.qty  # max profit

            else:
                # Generic short put fallback
                K = strike_at_delta(0.20, "P")
                delta    = put_delta(spot, K) * 100 * leg.qty
                theta    = -theta_put(spot, K) * 100 * leg.qty
                vega     = -vega_any(spot, K) * 100 * leg.qty
                notional = K * 100 * leg.qty

        except Exception as e:
            _log.warning("BS estimate failed for %s %s: %s", ticker, strat, e)

        results.append({
            "ticker":   ticker,
            "strategy": leg.strategy,
            "qty":      leg.qty,
            "dte":      dte,
            "spot":     round(spot, 2),
            "iv":       round(iv * 100, 1),
            "delta":    round(delta, 1),
            "theta":    round(theta, 2),
            "vega":     round(vega, 1),
            "notional": round(notional, 0),
        })
        agg_delta += delta
        agg_theta += theta
        agg_vega  += vega

    return {
        "positions": results,
        "aggregate": {
            "delta": round(agg_delta, 1),
            "theta": round(agg_theta, 2),
            "vega":  round(agg_vega, 1),
        },
    }
