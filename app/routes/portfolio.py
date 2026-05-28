"""
Portfolio analytics endpoints  (Sprint v8.5 — P4-16, P4-17, P4-18)

GET /api/portfolio/beta               — SPY beta-weighted delta with per-ticker breakdown
GET /api/portfolio/sector-exposure    — Notional exposure grouped by GICS sector
GET /api/portfolio/capital-efficiency — Annualised premium income / capital-at-risk
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter

from app.services import state, config_store

router = APIRouter()
logger = logging.getLogger("fortress.portfolio")

# ---------------------------------------------------------------------------
# Sector cache  (yfinance info["sector"], 24h TTL)
# ---------------------------------------------------------------------------

_sector_cache: dict[str, str] = {}
_sector_cache_ts: float = 0.0
_SECTOR_TTL = 86400.0   # 24 hours


def _fetch_sectors(tickers: list[str]) -> dict[str, str]:
    """
    Return {ticker: sector_string} for each ticker.
    Results are cached for 24 hours — yfinance info() is slow (~0.5s per ticker).
    Falls back to 'Unknown' on any error.
    """
    global _sector_cache, _sector_cache_ts
    now = time.monotonic()
    missing = [t for t in tickers if t not in _sector_cache]
    if not missing and (now - _sector_cache_ts) < _SECTOR_TTL:
        return _sector_cache

    try:
        import yfinance as yf
        for t in missing:
            try:
                info = yf.Ticker(t).info
                _sector_cache[t] = info.get("sector") or "Unknown"
            except Exception:
                _sector_cache.setdefault(t, "Unknown")
    except Exception:
        for t in missing:
            _sector_cache.setdefault(t, "Unknown")

    _sector_cache_ts = now
    return _sector_cache


# ---------------------------------------------------------------------------
# /api/portfolio/beta
# ---------------------------------------------------------------------------

@router.get("/portfolio/beta")
def portfolio_beta():
    """
    SPY beta-weighted portfolio delta with per-ticker breakdown.

    Reuses the beta/price cache already maintained by the briefing endpoint
    (1-hour TTL, yfinance weekly returns vs SPY).

    Response:
        beta_weighted_delta  — SPY-equivalent delta shares
        spy_price            — SPY price used in the calculation
        component_betas      — per-ticker {beta, price, delta_contribution}
        as_of                — UTC timestamp
    """
    from app.routes.briefing import _fetch_betas_and_prices

    data      = state.get_active_positions()
    positions = data.get("positions", []) or []
    tickers   = list({(p.get("ticker") or "").upper() for p in positions if p.get("ticker")})

    betas     = _fetch_betas_and_prices(tickers) if tickers else {}
    spy_price = betas.get("SPY", {}).get("price") or 0.0

    beta_weighted_delta = state.compute_beta_weighted_delta(data, betas) if betas else 0.0

    # Per-ticker delta contribution (SPY-equivalent shares)
    ticker_delta: dict[str, float] = defaultdict(float)

    for p in positions:
        ticker   = (p.get("ticker") or "").upper()
        sec_type = p.get("sec_type", "OPT")
        qty      = p.get("qty") or 0
        try:
            mult = int(p.get("multiplier") or 100)
        except (ValueError, TypeError):
            mult = 100

        b_entry     = betas.get(ticker, {})
        stock_price = b_entry.get("price") or 0.0
        beta        = b_entry.get("beta") or 1.0
        denom       = spy_price or 1.0

        if sec_type == "STK":
            ticker_delta[ticker] += qty * stock_price * beta / denom
        else:
            delta = p.get("current_delta")
            if delta is None:
                continue
            ticker_delta[ticker] += qty * delta * mult * stock_price * beta / denom

    components = sorted(
        [
            {
                "ticker":              t,
                "beta":                round(betas.get(t, {}).get("beta") or 1.0, 3),
                "price":               round(betas.get(t, {}).get("price") or 0.0, 2),
                "delta_contribution":  round(v, 2),
            }
            for t, v in ticker_delta.items()
        ],
        key=lambda x: abs(x["delta_contribution"]),
        reverse=True,
    )

    return {
        "beta_weighted_delta": round(beta_weighted_delta, 1),
        "spy_price":           round(spy_price, 2),
        "component_betas":     components,
        "as_of":               datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# /api/portfolio/sector-exposure
# ---------------------------------------------------------------------------

@router.get("/portfolio/sector-exposure")
def sector_exposure():
    """
    Portfolio notional exposure grouped by GICS sector.

    Notional = |market_value| per leg (available on every IBKR-synced position).
    Sector data from yfinance with a 24-hour cache.

    Response:
        sectors              — list of {sector, notional, pct, tickers}, sorted by notional desc
        concentration_max_pct — from strategy.sector_concentration_max_pct config
        breach               — true if any sector exceeds the cap
        as_of
    """
    data      = state.get_active_positions()
    positions = data.get("positions", []) or []
    tickers   = list({(p.get("ticker") or "").upper() for p in positions if p.get("ticker")})

    sector_map     = _fetch_sectors(tickers)
    max_sector_pct = config_store.cfg("strategy.sector_concentration_max_pct", 40.0)

    sector_notional: dict[str, float] = defaultdict(float)
    sector_tickers:  dict[str, set]   = defaultdict(set)

    for p in positions:
        ticker = (p.get("ticker") or "").upper()
        mv     = p.get("market_value")
        if mv is None:
            continue
        sector = sector_map.get(ticker, "Unknown")
        sector_notional[sector] += abs(mv)
        sector_tickers[sector].add(ticker)

    total = sum(sector_notional.values()) or 1.0

    sectors_out = sorted(
        [
            {
                "sector":   s,
                "notional": round(v, 2),
                "pct":      round(v / total * 100, 1),
                "tickers":  sorted(sector_tickers[s]),
            }
            for s, v in sector_notional.items()
        ],
        key=lambda x: x["notional"],
        reverse=True,
    )

    max_pct = max((s["pct"] for s in sectors_out), default=0.0)

    return {
        "sectors":              sectors_out,
        "concentration_max_pct": max_sector_pct,
        "breach":               max_pct > max_sector_pct,
        "as_of":                datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# /api/portfolio/capital-efficiency
# ---------------------------------------------------------------------------

@router.get("/portfolio/capital-efficiency")
def capital_efficiency():
    """
    Capital efficiency: annualised premium income / capital at risk.

    Groups positions by ticker. For each ticker:
      annual_income    = Σ  short_leg_credit × (365 / max(1, DTE))
      capital_at_risk  = cost_basis of long LEAPS legs (PMCC-style)
                         Falls back to  Σ (strike × multiplier × |qty|)  for naked shorts,
                         and avg_cost × qty for stock legs.
      efficiency       = annual_income / capital_at_risk

    Portfolio-level efficiency = Σ annual_income / Σ capital_at_risk.

    Notes:
      - avg_cost is stored in USD per contract (IBKR convention).
      - Legs with missing expiry or avg_cost are skipped from income calc.
      - Threshold hard-coded at 0.12 (12%) per spec P4-18.
    """
    data      = state.get_active_positions()
    positions = data.get("positions", []) or []
    today     = datetime.now(timezone.utc).date()
    threshold = 0.12

    by_ticker: dict[str, list] = defaultdict(list)
    for p in positions:
        ticker = (p.get("ticker") or "UNKNOWN").upper()
        by_ticker[ticker].append(p)

    total_income = 0.0
    total_risk   = 0.0
    by_position  = []

    for ticker, legs in by_ticker.items():
        short_opts = [p for p in legs if p.get("leg_direction") == "short" and p.get("sec_type") == "OPT"]
        long_opts  = [p for p in legs if p.get("leg_direction") == "long"  and p.get("sec_type") == "OPT"]
        stocks     = [p for p in legs if p.get("sec_type") == "STK"]

        # ── Annual income from short option legs ──────────────────────────
        annual_income = 0.0
        for leg in short_opts:
            exp_str = leg.get("expiry")
            if not exp_str:
                continue
            try:
                exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
                dte = max(1, (exp_date - today).days)
            except ValueError:
                continue
            credit = leg.get("avg_cost") or 0.0
            qty    = abs(leg.get("qty") or 0)
            annual_income += credit * qty * (365.0 / dte)

        # ── Capital at risk ───────────────────────────────────────────────
        capital = 0.0

        # Long LEAPS / long calls → their cost basis is the deployed capital
        for leg in long_opts:
            cost = leg.get("avg_cost") or 0.0
            qty  = abs(leg.get("qty") or 0)
            capital += cost * qty

        # No long leg → naked / CSP: use strike notional as capital proxy
        if capital == 0.0 and short_opts:
            for leg in short_opts:
                strike = leg.get("strike") or 0.0
                qty    = abs(leg.get("qty") or 0)
                try:
                    mult = int(leg.get("multiplier") or 100)
                except (ValueError, TypeError):
                    mult = 100
                capital += strike * mult * qty

        # Stock legs → cost basis
        for leg in stocks:
            cost = leg.get("avg_cost") or 0.0
            qty  = abs(leg.get("qty") or 0)
            capital += cost * qty

        if capital <= 0:
            continue

        eff = annual_income / capital
        total_income += annual_income
        total_risk   += capital

        by_position.append({
            "ticker":          ticker,
            "annual_income":   round(annual_income, 2),
            "capital_at_risk": round(capital, 2),
            "efficiency":      round(eff, 4),
            "short_legs":      len(short_opts),
            "long_legs":       len(long_opts),
        })

    by_position.sort(key=lambda x: x["efficiency"], reverse=True)

    portfolio_eff = round(total_income / total_risk, 4) if total_risk > 0 else 0.0

    return {
        "capital_efficiency":       portfolio_eff,
        "annual_income_annualized": round(total_income, 2),
        "capital_at_risk":          round(total_risk, 2),
        "threshold":                threshold,
        "above_threshold":          portfolio_eff >= threshold,
        "by_position":              by_position,
        "as_of":                    datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# /api/portfolio/pcs-exposure
# ---------------------------------------------------------------------------

@router.get("/portfolio/pcs-exposure")
def pcs_exposure():
    """
    Put-credit-spread (PCS) book exposure summary.

    Identifies PCS spreads: positions where strategy == "PCS", or where
    we find short-put positions (qty < 0, right == P, sec_type == OPT).

    Response:
        pcs_count       — number of active PCS short-put legs
        count_cap       — max spreads cap from strategy settings (default 5)
        total_notional  — sum of short_strike * contracts (max notional proxy)
        notional_cap    — max notional cap from strategy settings (default $25,000)
        count_breach    — true if pcs_count > count_cap
        notional_breach — true if total_notional > notional_cap
        count_warning   — true if pcs_count >= count_cap
        notional_warning — true if total_notional >= notional_cap * 0.8
        spreads         — per-spread detail
        as_of
    """
    data = state.get_active_positions()
    positions = data.get("positions", []) or []

    count_cap = int(config_store.cfg("strategy.max_pcs_spreads", 5))
    notional_cap = float(config_store.cfg("strategy.pcs_notional_cap", 25000.0))

    # Identify PCS short-put legs: strategy==PCS flag OR short OPT put position
    pcs_legs = [
        p for p in positions
        if (p.get("strategy") or "").upper() == "PCS"
        or (
            (p.get("sec_type") or "").upper() == "OPT"
            and (p.get("right") or p.get("opt_right") or "").upper() == "P"
            and (
                p.get("leg_direction") == "short"
                or (p.get("leg_direction") is None and (p.get("qty") or 0) < 0)
            )
        )
    ]

    spreads = []
    total_notional = 0.0

    for p in pcs_legs:
        ticker = (p.get("ticker") or "").upper()
        expiry_str = p.get("expiry") or ""
        short_strike = float(p.get("strike") or 0)
        try:
            mult = int(p.get("multiplier") or 100)
        except (TypeError, ValueError):
            mult = 100
        contracts = abs(float(p.get("qty") or 0))

        # Find matching long put at a lower strike (same ticker/expiry)
        long_strike: Optional[float] = None
        for other in positions:
            if (other.get("ticker") or "").upper() != ticker:
                continue
            if (other.get("expiry") or "") != expiry_str:
                continue
            if (other.get("sec_type") or "").upper() != "OPT":
                continue
            if (other.get("right") or other.get("opt_right") or "").upper() != "P":
                continue
            other_qty = other.get("qty") or 0
            other_dir = other.get("leg_direction") or ("long" if other_qty > 0 else "short")
            if other_dir == "long":
                ls = float(other.get("strike") or 0)
                if ls < short_strike:
                    long_strike = ls
                    break

        notional = round(short_strike * contracts * mult, 2)
        total_notional += notional

        spreads.append({
            "ticker": ticker,
            "expiry": expiry_str,
            "short_strike": short_strike,
            "long_strike": long_strike,
            "contracts": contracts,
            "notional": notional,
        })

    pcs_count = len(spreads)
    total_notional = round(total_notional, 2)

    return {
        "pcs_count": pcs_count,
        "count_cap": count_cap,
        "total_notional": total_notional,
        "notional_cap": notional_cap,
        "count_breach": pcs_count > count_cap,
        "notional_breach": total_notional > notional_cap,
        "count_warning": pcs_count >= count_cap,
        "notional_warning": total_notional >= notional_cap * 0.8,
        "spreads": spreads,
        "as_of": datetime.now(timezone.utc).isoformat(),
    }
