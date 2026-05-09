"""
BS delta computation — v3.

The IBKR Greeks path (reqMktData snapshot) is unreliable on this gateway
because the API-client write-access dialog interrupts the snapshot mid-fetch
roughly every 30 seconds. The result is duplicated delta values across
different strikes (e.g. all 6 MSFT legs reading 0.8281 in one sync, or all
4 NFLX strikes reading -0.2066).

v3 inverts the priority: we ALWAYS compute BS from yfinance IV when possible
and use BS as the source of record. IBKR's value is preserved on the leg as
'_ibkr_delta_raw' for audit, but only used if BS fails.

This trades a small amount of accuracy (yfinance's IV is end-of-day, not
real-time) for consistency. Over the timescale of a 30-45 DTE short call
that we monitor for drift, IV moves slowly; the trade is cheap.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Optional

# ─── Black-Scholes Greek helpers ──────────────────────────────────────────────
import math as _math

_RISK_FREE = 0.045  # 4.5% risk-free rate

def _norm_pdf(x: float) -> float:
    """Standard normal PDF."""
    return _math.exp(-0.5 * x * x) / _math.sqrt(2.0 * _math.pi)

def _norm_cdf(x: float) -> float:
    """Standard normal CDF (Abramowitz & Stegun approximation)."""
    return 0.5 * (1.0 + _math.erf(x / _math.sqrt(2.0)))

def _bs_d1d2(spot, strike, t_years, sigma, r=_RISK_FREE):
    """Return (d1, d2) or (None, None) if inputs are invalid."""
    if not (spot > 0 and strike > 0 and t_years > 0 and sigma > 0):
        return None, None
    try:
        d1 = (_math.log(spot / strike) + (r + 0.5 * sigma * sigma) * t_years) / (sigma * _math.sqrt(t_years))
        d2 = d1 - sigma * _math.sqrt(t_years)
        return d1, d2
    except Exception:
        return None, None

def bs_theta(spot, strike, t_years, sigma, right, r=_RISK_FREE) -> float | None:
    """
    Black-Scholes theta in dollars per calendar day per share.
    Negative for long options (time decay works against you).
    For short options (qty < 0) the position theta is positive (you collect decay).
    """
    d1, d2 = _bs_d1d2(spot, strike, t_years, sigma, r)
    if d1 is None:
        return None
    try:
        sqrt_t = _math.sqrt(t_years)
        common = -(spot * _norm_pdf(d1) * sigma) / (2.0 * sqrt_t)
        discount = _math.exp(-r * t_years)
        if right == "C":
            theta_annual = common - r * strike * discount * _norm_cdf(d2)
        else:
            theta_annual = common + r * strike * discount * _norm_cdf(-d2)
        # Convert from per-year to per-calendar-day
        return round(theta_annual / 365.0, 6)
    except Exception:
        return None

def bs_vega(spot, strike, t_years, sigma, r=_RISK_FREE) -> float | None:
    """
    Black-Scholes vega in dollars per 1% move in IV per share.
    Always positive for long options; multiply by qty to get position vega.
    """
    d1, _ = _bs_d1d2(spot, strike, t_years, sigma, r)
    if d1 is None:
        return None
    try:
        vega_per_unit = spot * _norm_pdf(d1) * _math.sqrt(t_years)
        # Divide by 100 to express as "per 1% change in IV"
        return round(vega_per_unit / 100.0, 6)
    except Exception:
        return None

def bs_gamma(spot, strike, t_years, sigma, r=_RISK_FREE) -> float | None:
    """
    Black-Scholes gamma — rate of change of delta per $1 move in spot.
    Always positive for long options.
    """
    d1, _ = _bs_d1d2(spot, strike, t_years, sigma, r)
    if d1 is None:
        return None
    try:
        return round(_norm_pdf(d1) / (spot * sigma * _math.sqrt(t_years)), 8)
    except Exception:
        return None



logger = logging.getLogger("fortress.bs_fallback")

_EXP_CACHE: dict[tuple[str, str], tuple[float, dict]] = {}
_EXP_TTL_S = 300


def _strike(p: dict) -> Optional[float]:
    return p.get("short_strike") or p.get("long_strike")


def _safe_float(v, default=None):
    try:
        x = float(v)
        if x != x:
            return default
        return x
    except (TypeError, ValueError):
        return default


def _fetch_single_expiry(ticker: str, expiry: str) -> Optional[dict]:
    key = (ticker.upper(), expiry[:10])
    now = time.time()
    if key in _EXP_CACHE:
        ts, val = _EXP_CACHE[key]
        if now - ts < _EXP_TTL_S:
            return val
    try:
        import yfinance as yf
        tk = yf.Ticker(ticker)
        chain = tk.option_chain(expiry[:10])

        def _rows(df):
            rows = []
            if df is None or df.empty:
                return rows
            for _, r in df.iterrows():
                rows.append({
                    "strike": _safe_float(r.get("strike"), 0.0),
                    "iv": _safe_float(r.get("impliedVolatility"), 0.0),
                    "bid": _safe_float(r.get("bid"), 0.0),
                    "ask": _safe_float(r.get("ask"), 0.0),
                })
            return rows

        val = {"calls": _rows(chain.calls), "puts": _rows(chain.puts)}
        _EXP_CACHE[key] = (now, val)
        return val
    except Exception as e:
        logger.debug("_fetch_single_expiry(%s, %s) failed: %s", ticker, expiry, e)
        _EXP_CACHE[key] = (now, None)
        return None


def fill_missing_deltas(positions: list[dict]) -> dict:
    """Compute delta for every option position. BS authoritative; IBKR is fallback.

    Mutates each position to set:
      - current_delta            — the canonical value used by downstream code
      - current_delta_source     — 'bs_estimate' | 'ibkr' | 'unavailable'
      - _ibkr_delta_raw          — preserved IBKR value for audit (may be None)
      - bs_inputs                — {spot, iv, t_years, strike, right} when BS succeeded
      - bs_skip_reason           — when BS failed
    """
    try:
        from app.services import chain as chain_svc
    except Exception as e:
        logger.warning("chain module unavailable: %s", e)
        return {"computed": 0, "skipped": len(positions), "reason": "no_chain_module"}

    now = datetime.now(timezone.utc)
    bs_computed = 0
    used_ibkr_fallback = 0
    unavailable = 0
    non_options = 0
    already_set = 0

    by_ticker: dict[str, list[dict]] = {}
    for p in positions:
        if p.get("sec_type") != "OPT":
            non_options += 1
            continue
        # Trust web_api Greeks — they come from a clean broker snapshot.
        # Skip BS computation entirely; keep current_delta as-is.
        if p.get("current_delta_source") == "web_api" and p.get("current_delta") is not None:
            already_set += 1
            continue
        # Preserve IBKR (legacy TWS) value before we overwrite — the TWS path
        # is known to corrupt deltas, so BS is preferred there.
        if "_ibkr_delta_raw" not in p:
            p["_ibkr_delta_raw"] = p.get("current_delta")
        by_ticker.setdefault((p.get("ticker") or "").upper(), []).append(p)

    for ticker, pending in by_ticker.items():
        try:
            chain = chain_svc.get_chain(ticker)
        except Exception as e:
            logger.info("chain fetch failed for %s: %s", ticker, e)
            chain = None

        spot = (chain or {}).get("spot")
        if not spot or spot <= 0:
            spot = chain_svc.get_spot(ticker)
        if not spot or spot <= 0:
            for p in pending:
                _apply_fallback(p, reason="no_spot")
                if p["current_delta"] is None: unavailable += 1
                else: used_ibkr_fallback += 1
            continue

        cached_expirations = (chain or {}).get("expirations", {}) if chain else {}

        for p in pending:
            strike = _strike(p)
            expiry = p.get("expiry")
            right = (p.get("right") or "").upper()
            if not strike or not expiry or right not in ("C", "P"):
                _apply_fallback(p, reason="missing_inputs")
                if p["current_delta"] is None: unavailable += 1
                else: used_ibkr_fallback += 1
                continue

            exp_key = expiry[:10]
            legs = cached_expirations.get(exp_key)
            if not legs:
                legs = _fetch_single_expiry(ticker, expiry)
                if not legs:
                    _apply_fallback(p, reason="expiry_unavailable")
                    if p["current_delta"] is None: unavailable += 1
                    else: used_ibkr_fallback += 1
                    continue

            book = legs.get("calls") if right == "C" else legs.get("puts")
            iv = None
            for o in book or []:
                if abs((o.get("strike") or 0) - strike) < 0.01:
                    iv = o.get("iv")
                    break
            if not iv or iv <= 0:
                _apply_fallback(p, reason="no_iv_at_strike")
                if p["current_delta"] is None: unavailable += 1
                else: used_ibkr_fallback += 1
                continue

            t_years = chain_svc.years_to_expiry(expiry, now)
            call_delta = chain_svc.bs_call_delta(spot, strike, t_years, iv)
            if call_delta is None:
                _apply_fallback(p, reason="bs_failed")
                if p["current_delta"] is None: unavailable += 1
                else: used_ibkr_fallback += 1
                continue

            option_delta = (call_delta - 1.0) if right == "P" else call_delta
            p["current_delta"] = round(option_delta, 4)
            p["current_delta_source"] = "bs_estimate"
            p["bs_inputs"] = {
                "spot": round(spot, 2),
                "iv": round(iv, 4),
                "t_years": round(t_years, 4),
                "strike": strike,
                "right": right,
            }
            p.pop("bs_skip_reason", None)
            # ── Compute theta, vega, gamma via Black-Scholes ──────────────────
            # These are per-share values; multiply by qty * multiplier for position Greeks.
            _theta = bs_theta(spot, strike, t_years, iv, right)
            _vega  = bs_vega(spot, strike, t_years, iv)
            _gamma = bs_gamma(spot, strike, t_years, iv)
            qty = p.get("qty") or 0
            multiplier = float(p.get("multiplier") or 100)
            if _theta is not None:
                # Position theta = per-share theta * qty * multiplier
                # Negative for long, positive for short (qty is negative for short)
                p["theta"] = round(_theta * qty * multiplier, 4)
                p["theta_per_share"] = _theta
            if _vega is not None:
                p["vega"] = round(_vega * qty * multiplier, 4)
                p["vega_per_share"] = _vega
            if _gamma is not None:
                p["gamma"] = round(_gamma * qty * multiplier, 6)
                p["gamma_per_share"] = _gamma
            bs_computed += 1

    summary = {
        "bs_computed": bs_computed,
        "already_set_by_web_api": already_set,
        "ibkr_fallback_used": used_ibkr_fallback,
        "unavailable": unavailable,
        "non_options": non_options,
        "tickers_attempted": len(by_ticker),
    }
    logger.info("BS delta v3: %s", summary)
    return summary


def _apply_fallback(p: dict, reason: str):
    """When BS can't compute, fall back to whatever IBKR gave (which may be None)."""
    raw = p.get("_ibkr_delta_raw")
    p["current_delta"] = raw  # may be None
    p["current_delta_source"] = "ibkr" if raw is not None else "unavailable"
    p["bs_skip_reason"] = reason
    p.pop("bs_inputs", None)
