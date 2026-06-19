"""
options_analytics.py — GEX, IV skew, liquidity, IV rank routes (IBKR-first v2)
===============================================================================
Place at:  ~/fortress-v4-api/app/routes/options_analytics.py

Then in app/main.py add (after other include_router lines):
    from app.routes.options_analytics import router as options_analytics_router
    app.include_router(options_analytics_router, prefix="/api")

Endpoints:
    GET /api/options/gex/{ticker}          — Gamma Exposure by strike
    GET /api/options/vol-skew/{ticker}     — IV skew + term structure
    GET /api/options/liquidity/{ticker}    — Bid-ask spread quality check
    GET /api/options/iv-rank/{ticker}      — IV rank

v2 (2026-06-10, Data Sources Optimization P2-P4):
  IBKR CP Gateway is tried FIRST for real-time quotes/IV via
  app.services.ibkr_marketdata (built on ibkr_chain plumbing).
  yfinance remains the structural source (expiry lists, strikes, OI,
  price history) and the silent fallback when the gateway is down.
  Yahoo's impliedVolatility column is NEVER used raw anymore — fallback
  paths BS-invert from lastPrice (it returns placeholder junk 1e-5..0.03
  when bid/ask are zeroed on the delayed feed).
  Every payload carries "source" so consumers can see which fed it.
"""

import json
import math
import logging
import os
from datetime import date, datetime, timezone

import yfinance as yf
from fastapi import APIRouter, Query

router = APIRouter()
logger = logging.getLogger(__name__)


# ── Black-Scholes helpers (pure Python — no scipy) ────────────────────────────

def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2)))


def _d1(S: float, K: float, T: float, sigma: float, r: float = 0.05) -> float:
    return (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))


def _bs_gamma(S: float, K: float, T: float, sigma: float, r: float = 0.05) -> float:
    """Black-Scholes gamma. Returns 0 on bad inputs."""
    try:
        if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
            return 0.0
        d1 = _d1(S, K, T, sigma, r)
        return _norm_pdf(d1) / (S * sigma * math.sqrt(T))
    except Exception:
        return 0.0


def _bs_delta(S: float, K: float, T: float, sigma: float, right: str = "call",
              r: float = 0.05) -> float:
    """Black-Scholes delta. Returns 0 on bad inputs."""
    try:
        if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
            return 0.0
        d1 = _d1(S, K, T, sigma, r)
        return _norm_cdf(d1) if right == "call" else _norm_cdf(d1) - 1.0
    except Exception:
        return 0.0


def _bs_price(S: float, K: float, T: float, sigma: float, right: str = "call",
              r: float = 0.05) -> float | None:
    """Black-Scholes option price. None on bad inputs."""
    try:
        if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
            return None
        d1 = _d1(S, K, T, sigma, r)
        d2 = d1 - sigma * math.sqrt(T)
        if right == "call":
            return S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
        return K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)
    except Exception:
        return None


def _implied_vol(price: float, S: float, K: float, T: float, right: str = "call",
                 r: float = 0.05) -> float | None:
    """
    Invert Black-Scholes for IV from an observed option price (bisection).
    Needed because Yahoo's impliedVolatility column returns placeholder junk
    (1e-5 .. 0.03) when bid/ask are zeroed on the delayed feed, while
    lastPrice remains usable. Returns decimal IV (0.26 = 26%) or None.
    """
    try:
        if price <= 0 or S <= 0 or K <= 0 or T <= 0:
            return None
        intrinsic = max(S - K, 0.0) if right == "call" else max(K - S, 0.0)
        if price <= intrinsic + 0.01:   # no extrinsic value — IV undefined
            return None
        lo, hi = 0.005, 5.0
        p_hi = _bs_price(S, K, T, hi, right, r)
        if p_hi is None or price > p_hi:
            return None
        for _ in range(60):
            mid = (lo + hi) / 2
            p = _bs_price(S, K, T, mid, right, r)
            if p is None:
                return None
            if p > price:
                hi = mid
            else:
                lo = mid
        iv = (lo + hi) / 2
        return iv if 0.01 < iv < 5.0 else None
    except Exception:
        return None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _spot(t: yf.Ticker) -> float | None:
    price = t.fast_info.get("lastPrice") or t.fast_info.get("regularMarketPrice")
    if price:
        return float(price)
    hist = t.history(period="1d")
    return float(hist["Close"].iloc[-1]) if not hist.empty else None


def _dte_years(expiry_str: str) -> float:
    """Days to expiry in years (minimum 1 calendar day)."""
    today = date.today()
    exp = date.fromisoformat(expiry_str)
    days = max((exp - today).days, 1)
    return days / 365.0


def _dte_days(expiry_str: str) -> int:
    today = date.today()
    exp = date.fromisoformat(expiry_str)
    return (exp - today).days


def _utcnow() -> str:
    return datetime.utcnow().isoformat() + "Z"


# ── IBKR-first helpers (Phase 2-4) ───────────────────────────────────────────
# All return None on any failure — callers fall back to yfinance silently.

def _try_ibkr_spot(ticker: str) -> float | None:
    try:
        from app.services.ibkr_marketdata import ibkr_spot
        return ibkr_spot(ticker)
    except Exception:
        return None


def _try_ibkr_quotes(ticker: str, spot: float, expiry: str, n_strikes: int = 12):
    try:
        from app.services.ibkr_marketdata import ibkr_quotes
        return ibkr_quotes(ticker, spot, expiry, n_strikes=n_strikes)
    except Exception:
        return None


def _try_ibkr_atm_iv(ticker: str, spot: float, expiry: str):
    try:
        from app.services.ibkr_marketdata import ibkr_atm_iv
        return ibkr_atm_iv(ticker, spot, expiry)
    except Exception:
        return None


def _pick_expiry(available: list[str]) -> str | None:
    """Prefer 21-60 DTE, closest to ~40d — same ordering as _atm_iv."""
    if not available:
        return None
    return sorted(
        available,
        key=lambda e: (not (21 <= _dte_days(e) <= 60), abs(_dte_days(e) - 40)),
    )[0]


def _row_iv(row, spot: float, K: float, T: float, right: str) -> float | None:
    """
    Sane IV (decimal) for a yfinance chain row. Yahoo's IV column returns
    placeholder junk (1e-5..0.03) on the delayed feed, so values outside
    (0.04, 5.0) are re-derived by BS-inverting lastPrice when the row has
    traded. Returns None if no trustworthy IV is obtainable.
    """
    try:
        iv = float(row.get("impliedVolatility") or 0)
    except Exception:
        iv = 0.0
    if 0.04 <= iv <= 5.0:
        return iv
    try:
        last = float(row.get("lastPrice") or 0)
        vol = float(row.get("volume") or 0)
        oi = float(row.get("openInterest") or 0)
        if last > 0 and (vol > 0 or oi > 0):
            return _implied_vol(last, spot, K, T, right)
    except Exception:
        pass
    return None


def _f(x) -> float:
    """NaN/Inf/None-safe float coercion → 0.0.

    yfinance option-chain rows can carry NaN openInterest/strike. The old
    `float(x or 0)` idiom returns NaN for those (NaN is truthy), and `NaN <= 0`
    is False so the guard never skips them — the NaN then poisons GEX sums and
    crashes JSON serialization (Starlette JSONResponse uses allow_nan=False,
    yielding an uncatchable 500). Coerce to 0.0 instead.
    """
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0.0
    return v if math.isfinite(v) else 0.0


def _spread_grade(bid: float, ask: float):
    """Bid-ask spread % + Strategy §4 quality status for a single contract.
    Lets get_contract_price double as an OTM liquidity check (the strike you'd
    actually sell), which check_liquidity's near-spot band can't reach."""
    if bid and ask and bid > 0 and ask > 0:
        mid = (bid + ask) / 2
        sp = round((ask - bid) / mid * 100, 1)
        return sp, ("good" if sp < 5 else "advisory" if sp <= 10 else "wide")
    return None, None


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/options/gex/{ticker}")
def get_gex(
    ticker: str,
    max_expiries: int = Query(default=6, ge=1, le=12),
):
    """
    Gamma Exposure (GEX) by strike, computed from yfinance options chain.

    Methodology (dealer-centric):
      - GEX per contract = gamma × OI × 100 × spot
      - Calls: POSITIVE (dealers long gamma above spot → resistance)
      - Puts:  NEGATIVE (dealers short gamma below spot → support)

    Returns: spot_price, call_wall, put_wall, flip_level, net_gex_total,
             gex_levels (sorted by strike), expirations used, source, as_of.
    """
    ticker = ticker.upper()
    try:
        t = yf.Ticker(ticker)
        spot = _try_ibkr_spot(ticker) or _spot(t)
        if not spot:
            return {"error": f"Could not get spot price for {ticker}"}

        expirations = list(t.options[:max_expiries])
        if not expirations:
            return {"error": f"No options chain found for {ticker}"}

        # Aggregate GEX by strike across all expirations
        gex_map: dict[float, dict] = {}

        # Phase 4 (hybrid): strikes + OI stay yfinance (OI is daily — delay
        # irrelevant; full-chain IBKR snapshots are rate-prohibitive). IV per
        # row via _row_iv (sane column value or BS-inversion of lastPrice);
        # rows with no trustworthy IV use the ticker's IBKR ATM IV (lazy,
        # fetched at most once), else are skipped.
        _ib_atm: float | None = None
        _ib_atm_tried = False

        def _atm_fallback() -> float | None:
            nonlocal _ib_atm, _ib_atm_tried
            if not _ib_atm_tried:
                _ib_atm_tried = True
                near = _pick_expiry(expirations)
                r = _try_ibkr_atm_iv(ticker, spot, near) if near else None
                _ib_atm = (r["iv"] / 100.0) if r else None
            return _ib_atm

        for exp in expirations:
            T = _dte_years(exp)
            try:
                chain = t.option_chain(exp)
            except Exception as e:
                logger.warning("Skipping expiry %s for %s: %s", exp, ticker, e)
                continue

            for df, right in [(chain.calls, "call"), (chain.puts, "put")]:
                for _, row in df.iterrows():
                    K = _f(row.get("strike"))
                    oi = _f(row.get("openInterest"))
                    if K <= 0 or oi <= 0:
                        continue
                    iv = _row_iv(row, spot, K, T, right) or _atm_fallback()
                    if not iv:
                        continue

                    gamma = _bs_gamma(spot, K, T, iv)
                    gex = gamma * oi * 100 * spot
                    if not math.isfinite(gex):
                        continue
                    if right == "put":
                        gex = -gex  # dealers short gamma on puts

                    if K not in gex_map:
                        gex_map[K] = {"call_gex": 0.0, "put_gex": 0.0, "net_gex": 0.0}
                    if right == "call":
                        gex_map[K]["call_gex"] += gex
                    else:
                        gex_map[K]["put_gex"] += gex
                    gex_map[K]["net_gex"] = gex_map[K]["call_gex"] + gex_map[K]["put_gex"]

        if not gex_map:
            return {"error": "No GEX computed — options chain may be empty or all IV=0"}

        strikes = sorted(gex_map)

        # Walls
        call_wall = max(gex_map, key=lambda s: gex_map[s]["call_gex"])
        put_wall  = min(gex_map, key=lambda s: gex_map[s]["put_gex"])

        # Gamma flip level: zero crossing of net GEX nearest to spot
        nets = [(s, gex_map[s]["net_gex"]) for s in strikes]
        crossings = []
        for i in range(len(nets) - 1):
            if nets[i][1] * nets[i + 1][1] < 0:
                crossings.append((nets[i][0], nets[i + 1][0]))
        flip_level = None
        if crossings:
            best = min(crossings, key=lambda c: min(abs(c[0] - spot), abs(c[1] - spot)))
            flip_level = best[0] if abs(best[0] - spot) <= abs(best[1] - spot) else best[1]

        net_gex_total = sum(v["net_gex"] for v in gex_map.values())

        return {
            "ticker":        ticker,
            "spot_price":    round(spot, 2),
            "call_wall":     call_wall,
            "put_wall":      put_wall,
            "flip_level":    flip_level,
            "net_gex_total": round(net_gex_total, 2),
            "gex_levels": [
                {
                    "strike":   s,
                    "net_gex":  round(gex_map[s]["net_gex"],  2),
                    "call_gex": round(gex_map[s]["call_gex"], 2),
                    "put_gex":  round(gex_map[s]["put_gex"],  2),
                }
                for s in strikes
            ],
            "expirations": expirations,
            "source":      "yfinance_bs" + ("+ibkr_atm" if _ib_atm else ""),
            "as_of":       _utcnow(),
        }

    except Exception as e:
        logger.error("GEX error for %s: %s", ticker, e, exc_info=True)
        return {"error": str(e)}


@router.get("/options/vol-skew/{ticker}")
def get_vol_skew(
    ticker: str,
    expiry: str = Query(default=None, description="Expiry YYYY-MM-DD. Defaults to nearest."),
):
    """
    IV skew for a ticker: put vs call IV across strikes for one expiration.

    Returns: spot_price, expiry, dte, atm_strike, atm_iv,
             skew_25d (put25d_iv − call25d_iv), skew_10d,
             term_structure (ATM IV per expiry, first 8),
             strikes[] with call_iv, put_iv, call_delta, put_delta.
    """
    ticker = ticker.upper()
    try:
        t = yf.Ticker(ticker)
        spot = _try_ibkr_spot(ticker) or _spot(t)
        if not spot:
            return {"error": f"Could not get spot price for {ticker}"}

        available = list(t.options)
        if not available:
            return {"error": f"No options chain found for {ticker}"}

        chosen_exp = expiry if (expiry and expiry in available) else available[0]
        T = _dte_years(chosen_exp)

        # Build per-strike skew table
        strike_data: dict[float, dict] = {}
        source = "yfinance_bs"

        # Phase 3/4: IBKR strike IV (field 7633) first
        ib = _try_ibkr_quotes(ticker, spot, chosen_exp, n_strikes=24)
        if ib:
            for (K, right), q in ib["quotes"].items():
                iv_pct = q.get("iv_pct")
                if not iv_pct:
                    continue
                K = float(K)
                delta = _bs_delta(spot, K, T, iv_pct / 100.0, right=right)
                if K not in strike_data:
                    strike_data[K] = {}
                strike_data[K][f"{right}_iv"]    = round(iv_pct, 2)
                strike_data[K][f"{right}_delta"] = round(delta, 3)
                strike_data[K][f"{right}_oi"]    = 0   # OI not in snapshot
            if strike_data:
                source = "ibkr"

        if not strike_data:
            # Fallback: yfinance chain, junk IV column re-derived via _row_iv
            chain = t.option_chain(chosen_exp)
            for df, right in [(chain.calls, "call"), (chain.puts, "put")]:
                for _, row in df.iterrows():
                    K = _f(row.get("strike"))
                    oi = int(_f(row.get("openInterest")))
                    if K <= 0:
                        continue
                    iv = _row_iv(row, spot, K, T, right)
                    if not iv:
                        continue
                    delta = _bs_delta(spot, K, T, iv, right=right)
                    if K not in strike_data:
                        strike_data[K] = {}
                    strike_data[K][f"{right}_iv"]    = round(iv * 100, 2)   # as percent
                    strike_data[K][f"{right}_delta"] = round(delta, 3)
                    strike_data[K][f"{right}_oi"]    = oi

        if not strike_data:
            return {"error": "No skew data — chain empty or all IV=0"}

        # ATM
        atm_strike = min(strike_data, key=lambda s: abs(s - spot))
        atm_iv = strike_data[atm_strike].get("call_iv") or strike_data[atm_strike].get("put_iv")

        # 25-delta / 10-delta helper
        def nearest_by_delta(target: float, right: str) -> float | None:
            candidates = {
                K: abs(v.get(f"{right}_delta", 999) - target)
                for K, v in strike_data.items()
                if f"{right}_iv" in v
            }
            if not candidates:
                return None
            return strike_data[min(candidates, key=candidates.get)].get(f"{right}_iv")

        put25_iv  = nearest_by_delta(-0.25, "put")
        call25_iv = nearest_by_delta(0.25,  "call")
        put10_iv  = nearest_by_delta(-0.10, "put")
        call10_iv = nearest_by_delta(0.10,  "call")

        skew_25d = round(put25_iv - call25_iv, 2) if put25_iv and call25_iv else None
        skew_10d = round(put10_iv - call10_iv, 2) if put10_iv and call10_iv else None

        # Term structure: ATM IV per expiry across first 8 expirations
        # (yfinance chain for structure; IV via _row_iv — never the raw column)
        term_structure = []
        for exp in available[:8]:
            try:
                T_exp = _dte_years(exp)
                ch = t.option_chain(exp)
                call_strikes = [float(r["strike"]) for _, r in ch.calls.iterrows()]
                if not call_strikes:
                    continue
                atm_k = min(call_strikes, key=lambda s: abs(s - spot))
                atm_rows = ch.calls[ch.calls["strike"] == atm_k]
                if atm_rows.empty:
                    continue
                iv_dec = _row_iv(atm_rows.iloc[0], spot, atm_k, T_exp, "call")
                if iv_dec:
                    term_structure.append({
                        "expiry":  exp,
                        "dte":     round(T_exp * 365),
                        "atm_iv":  round(iv_dec * 100, 2),
                    })
            except Exception:
                continue

        sorted_strikes = sorted(strike_data)
        return {
            "ticker":         ticker,
            "spot_price":     round(spot, 2),
            "expiry":         chosen_exp,
            "dte":            round(T * 365),
            "atm_strike":     atm_strike,
            "atm_iv":         atm_iv,
            "skew_25d":       skew_25d,
            "skew_10d":       skew_10d,
            "put25_iv":       put25_iv,
            "call25_iv":      call25_iv,
            "term_structure": term_structure,
            "strikes": [
                {"strike": s, **strike_data[s]}
                for s in sorted_strikes
            ],
            "source":         source,
            "as_of":          _utcnow(),
        }

    except Exception as e:
        logger.error("Vol skew error for %s: %s", ticker, e, exc_info=True)
        return {"error": str(e)}


# ── Bid-Ask Liquidity Check ───────────────────────────────────────────────────

@router.get("/options/liquidity/{ticker}")
def check_liquidity(
    ticker: str,
    expiry: str = Query(default=None, description="Expiry YYYY-MM-DD. Defaults to nearest 21-60 DTE."),
    moneyness_range: float = Query(default=0.15, description="Strike range from spot (default 15%)"),
):
    """
    Advisory bid-ask spread quality check for a ticker's options chain.

    Thresholds (Strategy §4 Quality Filters):
      < 5%:  GOOD — below advisory threshold
      5-10%: ADVISORY — flag but not blocked (strategy doc allows up to 10%)
      > 10%: WIDE — hard block per strategy §4

    Returns: liquidity_grade (A/B/C/D), per-strike spread data, summary counts.
    """
    ticker = ticker.upper()
    try:
        t = yf.Ticker(ticker)
        spot = _try_ibkr_spot(ticker) or _spot(t)
        if not spot or spot <= 0:
            return {"error": f"Cannot fetch spot price for {ticker}"}

        available = list(t.options)
        if not available:
            return {"error": f"No options chain found for {ticker}"}

        # Pick expiry: user-specified or nearest 21-60 DTE
        chosen_exp = None
        if expiry and expiry in available:
            chosen_exp = expiry
        else:
            for exp in available:
                d = _dte_days(exp)
                if 21 <= d <= 60:
                    chosen_exp = exp
                    break
            if not chosen_exp:
                chosen_exp = available[0]

        dte = _dte_days(chosen_exp)

        lo = spot * (1 - moneyness_range)
        hi = spot * (1 + moneyness_range)

        def _mk_row(k: float, right: str, bid: float, ask: float) -> dict | None:
            k, bid, ask = _f(k), _f(bid), _f(ask)   # NaN bid/ask → 0.0 (else mid/sp go NaN → 500)
            mid = (bid + ask) / 2
            if mid <= 0 or ask <= 0:
                return None
            sp = round((ask - bid) / mid * 100, 1)
            return {
                "strike":     k,
                "right":      right,
                "bid":        round(bid, 2),
                "ask":        round(ask, 2),
                "mid":        round(mid, 2),
                "spread_pct": sp,
                "status":     "good" if sp < 5 else "advisory" if sp <= 10 else "wide",
            }

        # Phase 2: IBKR live bid/ask first (yfinance zeroes bid/ask intraday)
        source = "yfinance"
        call_data: list = []
        put_data:  list = []
        ib = _try_ibkr_quotes(ticker, spot, chosen_exp, n_strikes=24)
        if ib and ib.get("n_live", 0) >= 4:
            for (k, right), q in ib["quotes"].items():
                if not (lo <= k <= hi):
                    continue
                r = _mk_row(float(k), right, float(q.get("bid") or 0), float(q.get("ask") or 0))
                if r:
                    (call_data if right == "call" else put_data).append(r)
            if call_data or put_data:
                source = "ibkr"

        if source != "ibkr":
            chain = t.option_chain(chosen_exp)

            def _spread_rows(df, right: str) -> list:
                out = []
                for _, row in df.iterrows():
                    k = float(row.get("strike", 0) or 0)
                    if not (lo <= k <= hi):
                        continue
                    r = _mk_row(k, right, float(row.get("bid") or 0), float(row.get("ask") or 0))
                    if r:
                        out.append(r)
                return out

            call_data = _spread_rows(chain.calls, "call")
            put_data  = _spread_rows(chain.puts,  "put")

        all_data = call_data + put_data

        if not all_data:
            return {"error": "No strikes with valid bid/ask in range", "ticker": ticker, "expiry": chosen_exp}

        good     = sum(1 for s in all_data if s["status"] == "good")
        advisory = sum(1 for s in all_data if s["status"] == "advisory")
        wide     = sum(1 for s in all_data if s["status"] == "wide")
        total    = len(all_data)
        good_pct = good / total if total else 0
        grade    = "A" if good_pct >= 0.80 else "B" if good_pct >= 0.60 else "C" if good_pct >= 0.40 else "D"

        atm_call = min(call_data, key=lambda s: abs(s["strike"] - spot), default=None)
        atm_put  = min(put_data,  key=lambda s: abs(s["strike"] - spot), default=None)
        ivs = [x["spread_pct"] for x in [atm_call, atm_put] if x]
        atm_spread_pct = round(sum(ivs) / len(ivs), 1) if ivs else None

        return {
            "ticker":          ticker,
            "spot":            round(spot, 2),
            "expiry":          chosen_exp,
            "dte":             dte,
            "liquidity_grade": grade,
            "atm_spread_pct":  atm_spread_pct,
            "atm_advisory":    (atm_spread_pct or 0) >= 5,
            "summary": {
                "total":    total,
                "good":     good,
                "advisory": advisory,
                "wide":     wide,
                "good_pct": round(good_pct * 100, 1),
            },
            "strikes": sorted(all_data, key=lambda s: (s["strike"], s["right"])),
            "source":  source,
            "as_of":   _utcnow(),
        }

    except Exception as e:
        logger.error("Liquidity check error for %s: %s", ticker, e, exc_info=True)
        return {"error": str(e)}


# ── IV Rank (yfinance) ────────────────────────────────────────────────────────
# Replaces the broken quantdata-mcp iv_rank (upstream ignores the ticker arg —
# verified 2026-06-10: SPX/MSFT/NVDA all return identical payloads).
#
# Two-phase ranking:
#   Phase 1 (cold start): rank current ATM IV within the 52-week REALIZED-vol
#     range (rolling HV20 over daily closes). Honest proxy, available day one.
#   Phase 2 (self-healing): every call snapshots today's ATM IV per ticker to
#     a local JSON store. Once ≥ MIN_SNAPSHOTS exist, rank within the ticker's
#     own IV history instead (true IV rank, expanding window up to 252 days).

IV_HISTORY_PATH = os.environ.get(
    "FORTRESS_IV_HISTORY", os.path.expanduser("~/fortress-v4-api/data/iv_history.json")
)
MIN_SNAPSHOTS = 60  # trading days before switching from HV proxy to IV snapshots


def _load_iv_history() -> dict:
    try:
        with open(IV_HISTORY_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_iv_history(hist: dict) -> None:
    try:
        os.makedirs(os.path.dirname(IV_HISTORY_PATH), exist_ok=True)
        with open(IV_HISTORY_PATH, "w") as f:
            json.dump(hist, f)
    except Exception as e:
        logger.warning("Could not persist IV history: %s", e)


def _atm_iv(t: yf.Ticker, spot: float) -> tuple[float | None, float | None, float | None]:
    """
    ATM call/put IV (as %) — computed by Black-Scholes inversion of lastPrice.

    Yahoo's delayed feed zeroes bid/ask and fills impliedVolatility with
    placeholder junk (verified 2026-06-10: ATM MSFT rows showed IV 0.001%-3%
    with bid=ask=0, while lastPrice was sane). So we never trust the IV column:
    we invert IV from lastPrice for the ~5 strikes nearest spot that actually
    traded (volume or OI > 0), take the median per side, and sanity-band the
    result. Falls through up to 4 expiries (21-60 DTE preferred, ~40d ideal).
    """
    available = list(t.options)
    if not available:
        return None, None, None
    ordered = sorted(
        available,
        key=lambda e: (not (21 <= _dte_days(e) <= 60), abs(_dte_days(e) - 40)),
    )

    def atm_of(df, T: float, right: str) -> float | None:
        if df is None or df.empty:
            return None
        df = df[(df["lastPrice"] > 0) & ((df["volume"].fillna(0) > 0) | (df["openInterest"].fillna(0) > 0))]
        if df.empty:
            return None
        near = df.iloc[(df["strike"] - spot).abs().argsort()[:5]]
        ivs = []
        for _, row in near.iterrows():
            iv = _implied_vol(float(row["lastPrice"]), spot, float(row["strike"]), T, right)
            if iv is not None:
                ivs.append(iv * 100)
        if not ivs:
            return None
        ivs.sort()
        return ivs[len(ivs) // 2]  # median

    for chosen in ordered[:4]:
        T = _dte_years(chosen)
        try:
            chain = t.option_chain(chosen)
        except Exception:
            continue
        call_iv = atm_of(chain.calls, T, "call")
        put_iv = atm_of(chain.puts, T, "put")
        ivs = [v for v in (call_iv, put_iv) if v and 1.0 <= v <= 500.0]
        if ivs:
            # If both sides exist but disagree wildly (stale last trades),
            # take the lower one — staleness inflates, rarely deflates.
            if len(ivs) == 2 and max(ivs) > 2.5 * min(ivs):
                return min(ivs), call_iv, put_iv
            return sum(ivs) / len(ivs), call_iv, put_iv
    return None, None, None


@router.get("/options/iv-rank/{ticker}")
def get_iv_rank(ticker: str):
    """
    IV rank from yfinance. Response shape matches the old /api/qd/iv-rank/{ticker}
    (Parapet IvRankData) plus `source` and `n_snapshots` fields.

    source = "iv_snapshots" — true IV rank from own daily IV history (≥60 days)
    source = "hv_proxy"     — current IV ranked within 52w realized-vol range
    """
    ticker = ticker.upper()
    today = date.today().isoformat()
    try:
        t = yf.Ticker(ticker)
        spot = _try_ibkr_spot(ticker) or _spot(t)
        if not spot:
            return {"error": f"Could not get spot price for {ticker}"}

        # Phase 3: IBKR field 7633 first (real-time, no inversion needed),
        # BS-inversion from yfinance lastPrice as fallback.
        iv_source = "bs_inversion"
        current_iv = call_iv = put_iv = None
        exp = _pick_expiry(list(t.options))
        if exp:
            ib = _try_ibkr_atm_iv(ticker, spot, exp)
            if ib:
                current_iv, call_iv, put_iv = ib["iv"], ib["call_iv"], ib["put_iv"]
                iv_source = "ibkr"
        if current_iv is None:
            current_iv, call_iv, put_iv = _atm_iv(t, spot)
        if current_iv is None:
            return {"error": f"No usable ATM IV for {ticker}"}

        # Snapshot today's IV (idempotent per day). Guard: never store junk
        # (<1% or >500%), and purge any previously stored junk so a bad day
        # can't poison the 52w low/high bounds.
        hist = _load_iv_history()
        tick_hist: dict = {
            k: v for k, v in hist.get(ticker, {}).items() if 1.0 <= v <= 500.0
        }
        if 1.0 <= current_iv <= 500.0:
            tick_hist[today] = round(current_iv, 3)
        hist[ticker] = tick_hist
        # Keep a rolling ~252 trading days
        for k in sorted(tick_hist)[:-252]:
            del tick_hist[k]
        _save_iv_history(hist)
        if not (1.0 <= current_iv <= 500.0):
            return {"error": f"ATM IV for {ticker} out of sane range ({current_iv:.2f}%) — yfinance quotes degraded, try again later"}

        n_snapshots = len(tick_hist)
        if n_snapshots >= MIN_SNAPSHOTS:
            vals = list(tick_hist.values())
            lo, hi = min(vals), max(vals)
            source = "iv_snapshots"
        else:
            # HV proxy: rolling 20d realized vol over the past year
            closes = t.history(period="1y")["Close"]
            if closes is None or len(closes) < 40:
                return {"error": f"Not enough price history for {ticker}"}
            import numpy as np
            rets = np.log(closes / closes.shift(1)).dropna()
            hv20 = rets.rolling(20).std() * math.sqrt(252) * 100
            hv20 = hv20.dropna()
            lo, hi = float(hv20.min()), float(hv20.max())
            # Widen the band with observed IV so rank can't pin at 0/100 early
            lo, hi = min(lo, *tick_hist.values()), max(hi, *tick_hist.values())
            source = "hv_proxy"

        rank = 50.0 if hi <= lo else max(0.0, min(100.0, (current_iv - lo) / (hi - lo) * 100))

        return {
            "ticker":       ticker,
            "session_date": today,
            "iv_rank":      round(rank, 1),
            "current_iv":   round(current_iv, 2),
            "iv_52w_high":  round(hi, 2),
            "iv_52w_low":   round(lo, 2),
            "call_iv":      round(call_iv, 2) if call_iv else None,
            "put_iv":       round(put_iv, 2) if put_iv else None,
            "source":       source,
            "iv_source":    iv_source,
            "n_snapshots":  n_snapshots,
            "as_of":        _utcnow(),
        }

    except Exception as e:
        logger.error("IV rank error for %s: %s", ticker, e, exc_info=True)
        return {"error": str(e)}


# ── Macro-event catalyst gate (Catalyst Gate v1, 2026-06-16) ──────────────────
# Codifies Strategy §4 binary-event timing. Claude is the brain: it curates the
# macro calendar (FOMC/CPI/PPI/NFP/PCE) from FRED/FMP and pushes it here via the
# MCP set_macro_events write tool. The backend stores it, computes days_until +
# a DEFER advisory, and serves it to Parapet's event-horizon row and to pretrade.
# Advisory only — it never blocks (Strategy §15.1). This implements the Sprint 14
# backlog item "FMP economic calendar → intel.events" via the Claude-curated
# pattern (same as earnings_blocklist.json) rather than backend FMP credentials.

MACRO_EVENTS_PATH = os.environ.get(
    "FORTRESS_MACRO_EVENTS",
    os.path.expanduser("~/fortress-v4-api/data/macro_events.json"),
)
MACRO_DEFER_DAYS_DEFAULT = 2          # high-impact event within N days → defer advisory
HIGH_IMPACT_KEYS = ("FOMC", "FED", "CPI", "PPI", "NFP", "JOBS", "PAYROLL", "PCE")


def _load_macro_events() -> dict:
    try:
        with open(MACRO_EVENTS_PATH) as f:
            return json.load(f)
    except Exception:
        return {"events": [], "updated_at": None}


def _save_macro_events(payload: dict) -> None:
    os.makedirs(os.path.dirname(MACRO_EVENTS_PATH), exist_ok=True)
    with open(MACRO_EVENTS_PATH, "w") as f:
        json.dump(payload, f, indent=2)


def _impact_of(label: str, given) -> str:
    if given:
        return str(given).lower()
    up = (label or "").upper()
    return "high" if any(k in up for k in HIGH_IMPACT_KEYS) else "medium"


@router.get("/options/macro-events")
def get_macro_events(defer_days: int = Query(default=MACRO_DEFER_DAYS_DEFAULT, ge=0, le=14)):
    """
    Macro economic-event calendar for the catalyst gate (Strategy §4 binary-event
    timing). Reads the Claude-curated store, computes days_until per event and a
    portfolio-level DEFER advisory when a HIGH-impact event falls within
    defer_days. Advisory only — never blocks (Strategy §15.1).

    Returns: events[] (label, date, days_until, impact, note), defer_advisory,
             defer_reason, nearest_high_impact, defer_days, updated_at, stale, source.
    """
    try:
        store = _load_macro_events()
        today = date.today()
        out = []
        for ev in store.get("events", []):
            d_str = ev.get("date")
            try:
                d = date.fromisoformat(d_str)
            except Exception:
                continue
            days = (d - today).days
            if days < 0:
                continue   # past — pruned on read
            out.append({
                "label": ev.get("label", "?"),
                "date": d_str,
                "days_until": days,
                "impact": _impact_of(ev.get("label", ""), ev.get("impact")),
                "note": ev.get("note"),
            })
        out.sort(key=lambda e: e["days_until"])

        highs_in_window = [e for e in out if e["impact"] == "high" and e["days_until"] <= defer_days]
        nearest_high = next((e for e in out if e["impact"] == "high"), None)
        defer = bool(highs_in_window)
        reason = None
        if defer:
            h = highs_in_window[0]
            reason = (
                f"{h['label']} in {h['days_until']}d (≤{defer_days}d) — Strategy §4 "
                f"binary-event timing: defer new premium-selling entries until it clears"
            )
        return {
            "events": out,
            "defer_advisory": defer,
            "defer_reason": reason,
            "nearest_high_impact": nearest_high,
            "defer_days": defer_days,
            "updated_at": store.get("updated_at"),
            "stale": store.get("updated_at") is None,
            "source": "claude_curated",
            "as_of": _utcnow(),
        }
    except Exception as e:
        logger.error("Macro events error: %s", e, exc_info=True)
        return {"error": str(e), "events": [], "defer_advisory": False}


@router.post("/options/macro-events")
def set_macro_events(payload: dict):
    """
    Replace the macro-event store. Body: {"events": [{label, date 'YYYY-MM-DD',
    impact?, note?}, ...]}. Claude curates this from FRED/FMP via the MCP
    set_macro_events write tool. Invalid/dateless rows are dropped; past events
    are pruned on read.
    """
    try:
        events = payload.get("events", []) if isinstance(payload, dict) else []
        clean = []
        for ev in events:
            if not isinstance(ev, dict):
                continue
            label = str(ev.get("label", "")).strip()
            d_str = str(ev.get("date", "")).strip()
            if not label or not d_str:
                continue
            try:
                date.fromisoformat(d_str)
            except Exception:
                continue
            rec = {"label": label, "date": d_str}
            if ev.get("impact"):
                rec["impact"] = str(ev["impact"]).lower()
            if ev.get("note"):
                rec["note"] = str(ev["note"])
            clean.append(rec)
        store = {"events": clean, "updated_at": _utcnow()}
        _save_macro_events(store)
        return {"ok": True, "stored": len(clean), "updated_at": store["updated_at"]}
    except Exception as e:
        logger.error("Macro events save error: %s", e, exc_info=True)
        return {"error": str(e), "ok": False}


# ── VIX term structure (premium-selling regime input, 2026-06-16) ─────────────
# Spot VIX vs VIX3M (3-month). For a net premium seller the *shape* of the curve
# is a cleaner regime light than VIX level alone:
#   contango  (VIX < VIX3M) → calm, mean-reverting; selling vol is favored
#   backwardation (VIX > VIX3M) → stress/term inversion; tighten size / defer
# Advisory only (§15.1). yfinance indices, BS-free — just two index levels.

@router.get("/options/vix-term")
def get_vix_term():
    """
    VIX term-structure regime input for premium selling. Compares spot VIX to
    VIX3M and returns the ratio + a contango/flat/backwardation state with a
    plain-English signal. Advisory only — never blocks (§15.1).

    Returns: vix, vix3m, ratio (vix/vix3m), state, signal,
             premium_selling_favorable (ratio < 1.0), source, as_of.
    """
    try:
        vix = _try_ibkr_spot("VIX") or _spot(yf.Ticker("^VIX"))
        vix3m = _spot(yf.Ticker("^VIX3M"))
        if not vix or not vix3m or vix3m <= 0:
            return {"error": "Could not fetch VIX / VIX3M levels"}
        ratio = vix / vix3m
        if ratio < 0.95:
            state, signal = "contango", "calm term structure — premium selling favored"
        elif ratio <= 1.00:
            state, signal = "flat", "flat term structure — neutral"
        else:
            state, signal = "backwardation", "term inversion / stress — tighten size, defer new short premium"
        return {
            "vix": round(vix, 2),
            "vix3m": round(vix3m, 2),
            "ratio": round(ratio, 4),
            "state": state,
            "signal": signal,
            "premium_selling_favorable": ratio < 1.00,
            "source": "yfinance",
            "as_of": _utcnow(),
        }
    except Exception as e:
        logger.error("VIX term error: %s", e, exc_info=True)
        return {"error": str(e)}


# ── Trade-outcomes feedback store (2026-06-16) ────────────────────────────────
# Quantitative companion to the prose journal: one structured record per CLOSED
# trade, capturing the ENTRY conditions the prose journal doesn't (IVR / DTE /
# short-delta at entry) so `journal_analytics.py` can compute expectancy and
# win-rate bucketed by setup — i.e. answer "which setups actually pay?".
# journal.json stays the decision/audit log; this is the numbers layer. Append-
# only, stdlib, NaN-safe. Deliberately a sidecar so it needs no change to the
# (separately-owned) backend journal route. Claude appends via the MCP
# log_trade_outcome write tool at each close.

TRADE_OUTCOMES_PATH = os.environ.get(
    "FORTRESS_TRADE_OUTCOMES",
    os.path.expanduser("~/fortress-v4-api/data/trade_outcomes.json"),
)
_OUTCOME_FIELDS = ("ticker", "strategy", "opened", "closed", "days_held",
                   "ivr_at_entry", "dte_at_entry", "short_delta_at_entry",
                   "realized_pnl", "exit_reason", "notes")


def _load_trade_outcomes() -> dict:
    try:
        with open(TRADE_OUTCOMES_PATH) as f:
            return json.load(f)
    except Exception:
        return {"records": [], "updated_at": None}


def _save_trade_outcomes(payload: dict) -> None:
    os.makedirs(os.path.dirname(TRADE_OUTCOMES_PATH), exist_ok=True)
    with open(TRADE_OUTCOMES_PATH, "w") as f:
        json.dump(payload, f, indent=2)


@router.get("/trade-outcomes")
def get_trade_outcomes():
    """
    Structured closed-trade records + an overall summary, for the expectancy
    feedback loop (companion to the prose journal). Run journal_analytics.py over
    the same store for expectancy bucketed by IVR / DTE / short-delta at entry.
    """
    try:
        store = _load_trade_outcomes()
        recs = store.get("records", [])
        pnls = [_f(r.get("realized_pnl")) for r in recs if r.get("realized_pnl") is not None]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        summary = {
            "n": len(recs),
            "closed": len(pnls),
            "win_rate": round(100 * len(wins) / len(pnls), 1) if pnls else None,
            "total_realized": round(sum(pnls), 2) if pnls else 0.0,
            "expectancy": round(sum(pnls) / len(pnls), 2) if pnls else None,
            "avg_win": round(sum(wins) / len(wins), 2) if wins else None,
            "avg_loss": round(sum(losses) / len(losses), 2) if losses else None,
        }
        return {
            "records": recs,
            "summary": summary,
            "count": len(recs),
            "updated_at": store.get("updated_at"),
            "as_of": _utcnow(),
        }
    except Exception as e:
        logger.error("Trade outcomes read error: %s", e, exc_info=True)
        return {"error": str(e), "records": [], "summary": {}}


@router.post("/trade-outcomes")
def log_trade_outcome(payload: dict):
    """
    Append one CLOSED-trade record. Body keys (ticker required): ticker,
    strategy, opened, closed, days_held, ivr_at_entry, dte_at_entry,
    short_delta_at_entry, realized_pnl, exit_reason, notes. Unknown keys ignored.
    """
    try:
        if not isinstance(payload, dict) or not str(payload.get("ticker", "")).strip():
            return {"ok": False, "error": "ticker required"}
        rec = {k: payload.get(k) for k in _OUTCOME_FIELDS if k in payload}
        rec["ticker"] = str(rec["ticker"]).upper()
        rec["logged_at"] = _utcnow()
        store = _load_trade_outcomes()
        store.setdefault("records", []).append(rec)
        store["updated_at"] = _utcnow()
        _save_trade_outcomes(store)
        return {"ok": True, "count": len(store["records"]), "record": rec}
    except Exception as e:
        logger.error("Trade outcome log error: %s", e, exc_info=True)
        return {"ok": False, "error": str(e)}


# ── Single-contract quote (ANY strike — for ticket pricing, 2026-06-18) ───────
# check_liquidity only quotes the near-spot band, so a far-OTM hedge/close leg
# couldn't be priced from the backend. This quotes ONE specific contract at any
# strike: IBKR real-time bid/ask/last/IV first, yfinance lastPrice fallback.
# (QuantData's qd_get_contract_price stays a Claude-side cross-check — the
# backend can't call that MCP.) NaN-safe.

def _try_ibkr_contract_quote(ticker, expiry, strike, right):
    try:
        from app.services.ibkr_marketdata import ibkr_contract_quote
        return ibkr_contract_quote(ticker, expiry, strike, right)
    except Exception:
        return None


@router.get("/options/contract-price/{ticker}")
def get_contract_price(
    ticker: str,
    strike: float = Query(..., description="Strike price"),
    expiry: str = Query(..., description="Expiry YYYY-MM-DD"),
    right: str = Query("P", description="C or P"),
):
    """
    Live quote for ONE specific option contract at ANY strike (unlike
    check_liquidity, which only covers the near-spot band). IBKR-first
    (real-time bid/ask/last/IV) → yfinance lastPrice fallback. Built for pricing
    hedge/close tickets with a real number.

    Returns: ticker, strike, expiry, right, bid, ask, mid, last, iv_pct,
             source ('ibkr'|'yfinance'), as_of.
    """
    ticker = ticker.upper()
    right_up = "C" if str(right).upper().startswith("C") else "P"
    try:
        ib = _try_ibkr_contract_quote(ticker, expiry, strike, right_up)
        if ib and (ib.get("bid") or ib.get("ask") or ib.get("last")):
            bid, ask = _f(ib.get("bid")), _f(ib.get("ask"))
            sp, status = _spread_grade(bid, ask)
            return {
                "ticker": ticker, "strike": _f(strike), "expiry": expiry, "right": right_up,
                "bid": bid, "ask": ask,
                "mid": _f(ib.get("mid")), "last": _f(ib.get("last")),
                "iv_pct": ib.get("iv_pct"),
                "spread_pct": sp, "status": status,
                "source": "ibkr", "as_of": _utcnow(),
            }
        # Fallback: yfinance chain bid/ask/lastPrice for the exact strike
        t = yf.Ticker(ticker)
        chain = t.option_chain(expiry)
        df = chain.calls if right_up == "C" else chain.puts
        if df is not None and not df.empty:
            match = df[df["strike"] == float(strike)]
            if not match.empty:
                r0 = match.iloc[0]
                bid, ask, last = _f(r0.get("bid")), _f(r0.get("ask")), _f(r0.get("lastPrice"))
                mid = (bid + ask) / 2 if (bid > 0 and ask > 0) else last
                sp, status = _spread_grade(bid, ask)
                return {
                    "ticker": ticker, "strike": _f(strike), "expiry": expiry, "right": right_up,
                    "bid": bid, "ask": ask, "mid": mid, "last": last, "iv_pct": None,
                    "spread_pct": sp, "status": status,
                    "source": "yfinance", "as_of": _utcnow(),
                }
        return {"error": f"No quote for {ticker} {strike}{right_up} {expiry}",
                "ticker": ticker, "strike": _f(strike), "expiry": expiry, "right": right_up}
    except Exception as e:
        logger.error("Contract price error %s %s%s %s: %s", ticker, strike, right_up, expiry, e, exc_info=True)
        return {"error": str(e), "ticker": ticker}
