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
    moneyness_range: float = Query(default=0.20, description="Strike range from spot (default 20% — wide enough to reach the ~0.20Δ short legs on both wings)"),
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
        ib = _try_ibkr_quotes(ticker, spot, chosen_exp, n_strikes=32)
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

        # ── Short-leg (OTM) liquidity — the strikes actually sold (~0.20Δ) ──────
        # The old flat-band grade was dominated by tight near-spot strikes (ATM
        # clustering): a chain could grade 'A' while the 0.20Δ leg you'd actually
        # sell was 'wide'. Fix: attach a BS delta to every strike (a single ATM
        # IV is plenty for *selection*), grade the short legs with the same
        # _spread_grade thresholds get_contract_price uses, and base the headline
        # grade on the OTM tradeable zone (|Δ| ≤ 0.35). Falls back to the legacy
        # all-strikes grade when IV/delta is unavailable.
        sigma = None
        ib_iv = _try_ibkr_atm_iv(ticker, spot, chosen_exp)
        if ib_iv and ib_iv.get("iv"):
            v = float(ib_iv["iv"]); sigma = v / 100.0 if v > 1 else v
        if not sigma or sigma <= 0:
            a = _atm_iv(t, spot)
            if a and a[0]:
                sigma = a[0] / 100.0
        T = max(dte, 1) / 365.0

        for r in call_data:
            r["delta"] = round(_bs_delta(spot, r["strike"], T, sigma, "call"), 3) if sigma else None
        for r in put_data:
            r["delta"] = round(_bs_delta(spot, r["strike"], T, sigma, "put"), 3) if sigma else None

        def _short_leg(rows, target=0.20):
            cand = [r for r in rows if r.get("delta") is not None]
            if not cand:
                return None
            p = min(cand, key=lambda r: abs(abs(r["delta"]) - target))
            return {"strike": p["strike"], "delta": p["delta"],
                    "spread_pct": p["spread_pct"], "status": p["status"]}

        short_call = _short_leg(call_data)
        short_put  = _short_leg(put_data)

        sl = [x["spread_pct"] for x in (short_put, short_call) if x and x["spread_pct"] is not None]
        tradeable_spread_pct = round(max(sl), 1) if sl else None   # worst short-leg = what you'll face
        tradeable_status = (
            "good" if tradeable_spread_pct < 5 else "advisory" if tradeable_spread_pct <= 10 else "wide"
        ) if tradeable_spread_pct is not None else None

        # ── Grading ────────────────────────────────────────────────────────────
        good     = sum(1 for s in all_data if s["status"] == "good")
        advisory = sum(1 for s in all_data if s["status"] == "advisory")
        wide     = sum(1 for s in all_data if s["status"] == "wide")
        total    = len(all_data)

        tradeable = [s for s in all_data if s.get("delta") is not None and abs(s["delta"]) <= 0.35]
        if len(tradeable) >= 3:
            graded, grade_basis = tradeable, "otm_tradeable"
        else:
            graded, grade_basis = all_data, ("all_strikes" if sigma else "all_strikes_no_iv")
        g_total  = len(graded)
        g_good   = sum(1 for s in graded if s["status"] == "good")
        good_pct = g_good / g_total if g_total else 0
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
            "liquidity_grade": grade,           # now graded on the OTM tradeable zone
            "grade_basis":     grade_basis,     # 'otm_tradeable' | 'all_strikes' | 'all_strikes_no_iv'
            "atm_spread_pct":  atm_spread_pct,  # ATM reference (kept for back-compat)
            "atm_advisory":    (atm_spread_pct or 0) >= 5,
            "tradeable_spread_pct": tradeable_spread_pct,   # worst ~0.20Δ short-leg spread
            "tradeable_status":     tradeable_status,
            "short_leg":       {"put": short_put, "call": short_call},
            "summary": {
                "total":             total,
                "good":              good,
                "advisory":          advisory,
                "wide":              wide,
                "good_pct":          round((good / total * 100) if total else 0, 1),
                "tradeable_strikes": len(tradeable),
                "graded_on":         grade_basis,
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
def get_macro_events(defer_days: int | None = Query(default=None, ge=0, le=14)):
    """
    Macro economic-event calendar for the catalyst gate (Strategy §4 binary-event
    timing). Reads the Claude-curated store, computes days_until per event and a
    portfolio-level DEFER advisory when a HIGH-impact event falls within
    defer_days. Advisory only — never blocks (Strategy §15.1).

    defer_days resolution (Sprint 17.3): an explicit query param wins; otherwise
    the live cfg("catalyst.defer_days") setting is used (tunable in System >
    Settings), falling back to MACRO_DEFER_DAYS_DEFAULT if config is unavailable.

    Returns: events[] (label, date, days_until, impact, note), defer_advisory,
             defer_reason, nearest_high_impact, defer_days, updated_at, stale, source.
    """
    if defer_days is None:
        try:
            from app.services.config_store import cfg
            defer_days = int(cfg("catalyst.defer_days", MACRO_DEFER_DAYS_DEFAULT))
        except Exception:
            defer_days = MACRO_DEFER_DAYS_DEFAULT
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


# ── Per-ticker news scan (Sprint 17.4) ────────────────────────────────────────
# Operationalizes the Strategy §4 news-spike cooldown: after a MATERIAL headline
# on a name, hold new premium-selling entries on it for a cooldown window. The
# backend has no FMP credentials and QuantData news isn't wired server-side, so
# Claude curates the last material headline per ticker (sourced from QuantData
# qd_get_news_articles, FMP as fallback) and pushes it here via set_ticker_news —
# the same Claude-curated store pattern as macro_events / ex_div. The backend
# stores it and computes days_since_last + a cooldown flag (active when material
# and days_since < cfg("catalyst.news_spike_cooldown_days")). Advisory only —
# never blocks (Strategy §15.1). An indicator/chip for Candidates/Triage, NOT a
# news reader.

TICKER_NEWS_PATH = os.environ.get(
    "FORTRESS_TICKER_NEWS",
    os.path.expanduser("~/fortress-v4-api/data/ticker_news.json"),
)
NEWS_COOLDOWN_DAYS_DEFAULT = 3


def _load_ticker_news() -> dict:
    try:
        with open(TICKER_NEWS_PATH) as f:
            return json.load(f)
    except Exception:
        return {"tickers": {}, "updated_at": None}


def _save_ticker_news(payload: dict) -> None:
    os.makedirs(os.path.dirname(TICKER_NEWS_PATH), exist_ok=True)
    with open(TICKER_NEWS_PATH, "w") as f:
        json.dump(payload, f, indent=2)


def _news_cooldown_days() -> int:
    try:
        from app.services.config_store import cfg
        return int(cfg("catalyst.news_spike_cooldown_days", NEWS_COOLDOWN_DAYS_DEFAULT))
    except Exception:
        return NEWS_COOLDOWN_DAYS_DEFAULT


def _news_record_for(ticker: str, rec: dict, cooldown_days: int, today: date) -> dict:
    """Compute days_since + cooldown flag for one ticker's stored last headline."""
    rec = rec or {}
    d_str = rec.get("date")
    material = bool(rec.get("material", True))
    days_since = None
    try:
        d = date.fromisoformat(str(d_str))
        days_since = (today - d).days
    except Exception:
        d_str = None
    cooldown_active = bool(
        material and days_since is not None and 0 <= days_since < cooldown_days
    )
    return {
        "ticker": ticker.upper(),
        "last_headline_date": d_str,
        "days_since": days_since,
        "material": material,
        "headline": rec.get("headline"),
        "cooldown_active": cooldown_active,
        "cooldown_days": cooldown_days,
    }


@router.get("/market/news/{ticker}")
def get_ticker_news(ticker: str):
    """
    Per-ticker news-scan indicator for the catalyst gate (Strategy §4 news-spike
    cooldown). Reads the Claude-curated last-material-headline store and returns
    days_since the last material headline plus a cooldown flag (active when the
    headline is material and days_since < cfg("catalyst.news_spike_cooldown_days")).
    Advisory only — never blocks. Indicator, not a news reader.

    Returns: ticker, last_headline_date, days_since, material, headline,
             cooldown_active, cooldown_days, updated_at, stale, source.
    """
    try:
        store = _load_ticker_news()
        cooldown_days = _news_cooldown_days()
        rec = (store.get("tickers", {}) or {}).get(ticker.upper(), {})
        out = _news_record_for(ticker, rec, cooldown_days, date.today())
        out["updated_at"] = store.get("updated_at")
        out["stale"] = store.get("updated_at") is None
        out["source"] = "claude_curated"
        out["as_of"] = _utcnow()
        return out
    except Exception as e:
        logger.error("Ticker news error (%s): %s", ticker, e, exc_info=True)
        return {"ticker": ticker.upper(), "error": str(e), "cooldown_active": False}


@router.get("/market/news")
def get_all_ticker_news():
    """
    All curated per-ticker news records with days_since + cooldown flags, in one
    call — used by Candidates/Triage to badge rows without N round-trips.
    """
    try:
        store = _load_ticker_news()
        cooldown_days = _news_cooldown_days()
        today = date.today()
        recs = {
            tk.upper(): _news_record_for(tk, rec, cooldown_days, today)
            for tk, rec in (store.get("tickers", {}) or {}).items()
        }
        return {
            "tickers": recs,
            "cooldown_days": cooldown_days,
            "updated_at": store.get("updated_at"),
            "stale": store.get("updated_at") is None,
            "source": "claude_curated",
            "as_of": _utcnow(),
        }
    except Exception as e:
        logger.error("All ticker news error: %s", e, exc_info=True)
        return {"error": str(e), "tickers": {}}


@router.post("/market/news")
def set_ticker_news(payload: dict):
    """
    Replace the per-ticker news store. Body: {"tickers": {"MSFT": {"date":
    "YYYY-MM-DD", "headline": "...", "material": true}, ...}}. Claude curates the
    last MATERIAL headline per ticker from QuantData (qd_get_news_articles) or FMP
    via the MCP set_ticker_news write tool. Rows without a valid date are dropped.
    """
    try:
        tickers = payload.get("tickers", {}) if isinstance(payload, dict) else {}
        clean = {}
        for tk, rec in (tickers or {}).items():
            if not isinstance(rec, dict):
                continue
            d_str = str(rec.get("date", "")).strip()
            if not d_str:
                continue
            try:
                date.fromisoformat(d_str)
            except Exception:
                continue
            entry = {"date": d_str, "material": bool(rec.get("material", True))}
            if rec.get("headline"):
                entry["headline"] = str(rec["headline"])
            clean[str(tk).upper()] = entry
        store = {"tickers": clean, "updated_at": _utcnow()}
        _save_ticker_news(store)
        return {"ok": True, "stored": len(clean), "updated_at": store["updated_at"]}
    except Exception as e:
        logger.error("Ticker news save error: %s", e, exc_info=True)
        return {"error": str(e), "ok": False}


# ── PMCC breakeven guardrail (Sprint 19.4 / Strategy v3.10 §4a) ───────────────
# Selling a PMCC short call with strike ≤ (long_strike + net_debit) locks a
# GUARANTEED LOSS at expiry if both legs are assigned/exercised. Pure validator —
# call it when choosing a PMCC short strike. Advisory; never places orders.
@router.get("/options/pmcc-breakeven")
def pmcc_breakeven_check(long_strike: float, net_debit: float, short_strike: float):
    """
    PMCC guardrail. breakeven = long_strike + net_debit (per share). The short
    call must be sold ABOVE that breakeven or the position can't profit at expiry.

    Returns: long_strike, net_debit, breakeven, short_strike, ok, verdict, detail.
    """
    try:
        breakeven = round(float(long_strike) + float(net_debit), 2)
        short = float(short_strike)
        ok = short > breakeven
        return {
            "long_strike": float(long_strike),
            "net_debit": float(net_debit),
            "breakeven": breakeven,
            "short_strike": short,
            "ok": ok,
            "verdict": "OK" if ok else "GUARANTEED-LOSS",
            "detail": (
                f"Short {short:g} is above the long breakeven {breakeven:g} — OK."
                if ok else
                f"Short {short:g} ≤ breakeven {breakeven:g}: selling here locks a guaranteed "
                f"loss if assigned at expiry. Raise the short strike above {breakeven:g}."
            ),
            "as_of": _utcnow(),
        }
    except Exception as e:
        return {"error": str(e), "ok": None}


# ── Ex-dividend assignment-risk gate (Sprint 15.4, 2026-06-20) ────────────────
# Early assignment on a SHORT CALL spikes when it's ITM near an ex-dividend date
# (the counterparty exercises early to capture the dividend). The backend has no
# FMP credentials, so Claude curates the ex-div calendar from FMP's
# dividends-calendar and pushes it here via set_ex_div_events — the same
# Claude-curated store pattern as macro_events / earnings_blocklist. The backend
# stores it and cross-references the LIVE short-call legs: ITM (spot ≥ strike)
# with an ex-div on/before expiry = 'high' assignment risk; within near_itm_pct
# below the strike = 'watch'. Deep-OTM calls and non-dividend names never flag.
# Advisory only — never blocks (Strategy §15.1).

EX_DIV_EVENTS_PATH = os.environ.get(
    "FORTRESS_EX_DIV_EVENTS",
    os.path.expanduser("~/fortress-v4-api/data/ex_div_events.json"),
)
NEAR_ITM_PCT_DEFAULT = 0.02   # within 2% below the strike → near-ITM 'watch'


def _load_ex_div_events() -> dict:
    try:
        with open(EX_DIV_EVENTS_PATH) as f:
            return json.load(f)
    except Exception:
        return {"events": [], "updated_at": None}


def _save_ex_div_events(payload: dict) -> None:
    os.makedirs(os.path.dirname(EX_DIV_EVENTS_PATH), exist_ok=True)
    with open(EX_DIV_EVENTS_PATH, "w") as f:
        json.dump(payload, f, indent=2)


def _live_positions() -> dict | None:
    """Per-leg live book (incl. expiry + bs_inputs.spot). Best-effort; None on failure."""
    try:
        from app.routes import positions as _posmod
        fn = getattr(_posmod, "get_positions", None) or getattr(_posmod, "list_positions", None)
        if not fn:
            return None
        try:
            return fn(aggregated=False)
        except TypeError:
            return fn()
    except Exception as e:
        logger.debug("live positions unavailable for ex-div gate: %s", e)
        return None


def _short_calls_from_positions() -> list[dict]:
    data = _live_positions()
    if not isinstance(data, dict):
        return []
    out = []
    for p in data.get("positions", []):
        if p.get("sec_type") != "OPT" or str(p.get("right") or "").upper() != "C":
            continue
        if float(p.get("qty") or 0) >= 0:   # short only
            continue
        bi = p.get("bs_inputs") or {}
        spot = bi.get("spot")
        if not spot:
            spot = _try_ibkr_spot(str(p.get("ticker") or "").upper())
        out.append({
            "ticker": str(p.get("ticker") or "").upper(),
            "strike": float(p.get("strike") or 0),
            "expiry": p.get("expiry"),
            "qty":    float(p.get("qty") or 0),
            "spot":   float(spot) if spot else None,
        })
    return out


@router.get("/options/ex-div")
def get_ex_div(near_itm_pct: float = Query(default=NEAR_ITM_PCT_DEFAULT, ge=0.0, le=0.2)):
    """
    Ex-dividend assignment-risk gate for short calls (Strategy §4). Reads the
    Claude-curated ex-div store, then cross-references the live short-call legs:
    a call that is ITM/near-ITM with an ex-div on/before its expiry is flagged
    for early-assignment (dividend-capture) risk. Advisory only — never blocks.

    Returns:
      events[]            : {ticker, ex_date, days_until, amount, note}
      assignment_risks[]  : {ticker, strike, expiry, spot, ex_date, ex_days_until,
                             dividend, moneyness_pct, severity 'high'|'watch', note}
      has_assignment_risk : bool
      near_itm_pct, updated_at, stale, source, as_of
    """
    try:
        store = _load_ex_div_events()
        today = date.today()
        by_ticker: dict = {}
        events_out = []
        for ev in store.get("events", []):
            tk = str(ev.get("ticker", "")).upper()
            d_str = ev.get("ex_date") or ev.get("date")
            try:
                d = date.fromisoformat(d_str)
            except Exception:
                continue
            days = (d - today).days
            if days < 0:
                continue   # past — pruned on read
            row = {"ticker": tk, "ex_date": d_str, "days_until": days,
                   "amount": ev.get("amount"), "note": ev.get("note")}
            events_out.append(row)
            by_ticker.setdefault(tk, []).append((d, row))
        events_out.sort(key=lambda e: e["days_until"])

        risks = []
        for sc in _short_calls_from_positions():
            tk, spot, strike, exp = sc["ticker"], sc["spot"], sc["strike"], sc["expiry"]
            if tk not in by_ticker or not spot or not strike or not exp:
                continue
            try:
                exp_d = date.fromisoformat(exp)
            except Exception:
                continue
            relevant = [r for (d, r) in by_ticker[tk] if d <= exp_d]
            if not relevant:
                continue
            nearest = min(relevant, key=lambda r: r["days_until"])
            if spot >= strike:
                sev = "high"
            elif spot >= strike * (1 - near_itm_pct):
                sev = "watch"
            else:
                continue   # safely OTM
            risks.append({
                "ticker": tk, "strike": strike, "expiry": exp, "spot": round(spot, 2),
                "ex_date": nearest["ex_date"], "ex_days_until": nearest["days_until"],
                "dividend": nearest.get("amount"),
                "moneyness_pct": round((spot - strike) / strike * 100, 2),
                "severity": sev,
                "note": (
                    f"Short {tk} {strike:.0f}C is {'ITM' if sev == 'high' else 'near-ITM'} "
                    f"with ex-div {nearest['ex_date']} on/before expiry {exp} — early-assignment "
                    f"(dividend-capture) risk; consider rolling up/out before ex-div."
                ),
            })
        risks.sort(key=lambda r: (r["severity"] != "high", r["ex_days_until"]))

        return {
            "events": events_out,
            "assignment_risks": risks,
            "has_assignment_risk": bool(risks),
            "near_itm_pct": near_itm_pct,
            "updated_at": store.get("updated_at"),
            "stale": store.get("updated_at") is None,
            "source": "claude_curated",
            "as_of": _utcnow(),
        }
    except Exception as e:
        logger.error("Ex-div gate error: %s", e, exc_info=True)
        return {"error": str(e), "events": [], "assignment_risks": [], "has_assignment_risk": False}


@router.post("/options/ex-div")
def set_ex_div(payload: dict):
    """
    Replace the ex-dividend store. Body: {"events": [{ticker, ex_date 'YYYY-MM-DD',
    amount?, note?}, ...]}. Claude curates from FMP's dividends-calendar via the
    MCP set_ex_div_events write tool. Invalid/dateless rows are dropped; past
    events are pruned on read.
    """
    try:
        events = payload.get("events", []) if isinstance(payload, dict) else []
        clean = []
        for ev in events:
            if not isinstance(ev, dict):
                continue
            tk = str(ev.get("ticker", "")).strip().upper()
            d_str = str(ev.get("ex_date", ev.get("date", ""))).strip()
            if not tk or not d_str:
                continue
            try:
                date.fromisoformat(d_str)
            except Exception:
                continue
            rec = {"ticker": tk, "ex_date": d_str}
            if ev.get("amount") is not None:
                try:
                    rec["amount"] = float(ev["amount"])
                except Exception:
                    pass
            if ev.get("note"):
                rec["note"] = str(ev["note"])
            clean.append(rec)
        store = {"events": clean, "updated_at": _utcnow()}
        _save_ex_div_events(store)
        return {"ok": True, "stored": len(clean), "updated_at": store["updated_at"]}
    except Exception as e:
        logger.error("Ex-div save error: %s", e, exc_info=True)
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


# ── Sprint 16 keystone: IBKR fills feed + open/close classification ───────────
# Consumes ibkr_marketdata.ibkr_recent_fills() and labels each execution
# OPEN / CLOSE / REVERSE / FLAT using the `position` field (position AFTER the
# trade) the CP trades payload carries — magnitude change is data-driven, not a
# guess. Roll/hedge heuristics layer on top so pacing (16.5) can exclude them.
# Hedge underlyings are configurable; default {SPY}.

_HEDGE_TICKERS = {"SPY"}


def _classify_fill_action(fill: dict) -> str:
    """OPEN | CLOSE | REVERSE | FLAT | UNKNOWN from the post-trade position.

    signed_qty = +qty for BUY, -qty for SELL.  position_before = position_after
    - signed_qty.  Increasing |position| = OPEN, decreasing = CLOSE, crossing
    zero = REVERSE.  Falls back to `liquidation`/side when position is absent."""
    pa = fill.get("position_after")
    side = fill.get("side")
    qty = fill.get("qty")
    if pa is not None and side and qty is not None:
        try:
            pa = float(pa)
            signed = qty if side == "BUY" else -qty
            pb = pa - signed
            if pb == 0 and pa != 0:
                return "OPEN"
            if pa == 0 and pb != 0:
                return "CLOSE"
            if (pa > 0) != (pb > 0) and pb != 0 and pa != 0:
                return "REVERSE"
            if abs(pa) > abs(pb):
                return "OPEN"
            if abs(pa) < abs(pb):
                return "CLOSE"
            return "FLAT"
        except (ValueError, TypeError):
            pass
    # Fallback: liquidation flag, else unknown (don't guess from side alone)
    if fill.get("liquidation") is True:
        return "CLOSE"
    return "UNKNOWN"


def classify_recent_fills(days_back: int = 7) -> dict:
    """Normalized fills + per-fill action/roll/hedge labels + a weekly opens
    tally (the input pacing 16.5 reconciles against the journal). Soft-fails to
    an empty, non-error structure so callers never break."""
    from datetime import datetime, timezone, timedelta
    try:
        from app.services.ibkr_marketdata import ibkr_recent_fills
        fills = ibkr_recent_fills(days_back)
    except Exception as e:
        return {"available": False, "reason": str(e), "fills": [], "opens_this_week": []}
    if fills is None:
        return {"available": False, "reason": "gateway/trades unavailable",
                "fills": [], "opens_this_week": []}

    # Label actions
    for f in fills:
        f["action"] = _classify_fill_action(f)
        f["is_hedge"] = (f.get("ticker") in _HEDGE_TICKERS)

    # Roll detection: a ticker with BOTH an OPEN and a CLOSE option-leg on the
    # same calendar day → mark that day's OPENs as likely_roll.
    by_tk_day: dict = {}
    for f in fills:
        if f.get("sec_type") not in ("OPT", "FOP"):
            continue
        day = (f.get("time") or "")[:10]
        by_tk_day.setdefault((f.get("ticker"), day), set()).add(f["action"])
    for f in fills:
        day = (f.get("time") or "")[:10]
        acts = by_tk_day.get((f.get("ticker"), day), set())
        f["likely_roll"] = (f["action"] == "OPEN" and "CLOSE" in acts and "OPEN" in acts)

    # Weekly opens that COUNT toward pacing: OPEN, not roll, not hedge, option leg
    now = datetime.now(timezone.utc)
    monday = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    opens_week = []
    for f in fills:
        if f["action"] != "OPEN" or f.get("likely_roll") or f.get("is_hedge"):
            continue
        if f.get("sec_type") not in ("OPT", "FOP"):
            continue
        t = f.get("time")
        if not t:
            continue
        try:
            dt = datetime.fromisoformat(t.replace("Z", "+00:00"))
        except ValueError:
            continue
        if dt >= monday:
            opens_week.append(f)

    return {"available": True, "fills": fills, "opens_this_week": opens_week,
            "as_of": _utcnow()}


@router.get("/ibkr/fills")
def get_ibkr_fills(days_back: int = Query(default=7, ge=1, le=7)):
    """Recent IBKR executions with open/close/roll/hedge classification.

    INSPECTION / ENRICHMENT ONLY — the CP Gateway /iserver/account/trades feed is
    session-scoped and returns [] for trades placed outside the gateway session
    (verified empty 2026-06-21 for a window with known fills). The authoritative
    fill source for pacing/entry-capture is the POSITION-DIFF keystone below
    (/api/positions/opens). This route stays for live debugging + opportunistic
    price/time enrichment when the endpoint does return rows."""
    data = classify_recent_fills(days_back)
    pacing_opens = data.get("opens_this_week", [])
    return {
        **data,
        "fill_count": len(data.get("fills", [])),
        "pacing_opens_this_week": len(pacing_opens),
        "note": "inspection/enrichment only — pacing uses /api/positions/opens (position-diff)",
    }


# ── Sprint 16 keystone: POSITION-DIFF fill detector (authoritative) ───────────
# Robust alternative to the session-scoped /trades feed. Snapshots the IBKR-
# synced leg book (state.get_active_positions, which the sync updates with manual
# fills too) and diffs consecutive snapshots: a net increase in SHORT option legs
# per ticker = new premium-selling entries; a decrease = closes. Rolls net to
# zero (close 1 + open 1 → no net change), hedges (SPY) are excluded. Daily
# granularity (driven by the scheduled briefing), which is enough for weekly
# pacing and entry-condition capture. Snapshot store is transient runtime state
# (gitignore, same policy as iv_history.json).

POSITION_SNAPSHOTS_PATH = os.environ.get(
    "FORTRESS_POSITION_SNAPSHOTS",
    os.path.expanduser("~/fortress-v4-api/data/position_snapshots.json"),
)
_HEDGE_TICKERS_PD = {"SPY"}


def _load_position_snapshots() -> dict:
    try:
        with open(POSITION_SNAPSHOTS_PATH) as f:
            return json.load(f)
    except Exception:
        return {"snapshots": []}


def _save_position_snapshots(payload: dict) -> None:
    os.makedirs(os.path.dirname(POSITION_SNAPSHOTS_PATH), exist_ok=True)
    with open(POSITION_SNAPSHOTS_PATH, "w") as f:
        json.dump(payload, f, indent=2)


def _leg_key(pos: dict) -> str:
    """Stable per-leg identity. opra_symbol for options; TICKER|STK for stock."""
    opra = pos.get("opra_symbol")
    if opra:
        return str(opra)
    tk = str(pos.get("ticker", "")).upper()
    sec = str(pos.get("sec_type", "")).upper()
    if sec == "OPT":
        return f"{tk}|{pos.get('expiry','')}|{pos.get('right','')}|{pos.get('strike','')}"
    return f"{tk}|STK"


def _snapshot_legs() -> dict:
    """Current leg map {key: {ticker,sec_type,right,strike,expiry,qty}} from the
    IBKR-synced book."""
    from app.services import state
    legs: dict = {}
    try:
        data = state.get_active_positions()
        for p in data.get("positions", []) or []:
            try:
                qty = float(p.get("qty") or 0)
            except (ValueError, TypeError):
                qty = 0.0
            if qty == 0:
                continue
            k = _leg_key(p)
            legs[k] = {
                "ticker": str(p.get("ticker", "")).upper(),
                "sec_type": str(p.get("sec_type", "")).upper(),
                "right": p.get("right"),
                "strike": p.get("strike"),
                "expiry": p.get("expiry"),
                "qty": qty,
            }
    except Exception as e:
        logger.warning("snapshot_legs failed: %s", e)
    return legs


def _short_calls_puts(legs: dict) -> dict:
    """Per-ticker count of SHORT option legs (qty<0) in a leg map."""
    out: dict = {}
    for leg in legs.values():
        if leg["sec_type"] == "OPT" and leg["qty"] < 0:
            out[leg["ticker"]] = out.get(leg["ticker"], 0) + 1
    return out


def capture_position_snapshot(reason: str = "scheduled") -> dict:
    """Append today's leg snapshot (idempotent per calendar day — replaces an
    existing same-day snapshot). Returns {captured, date, legs, new_short_legs}.
    Also emits the OPEN diff vs the prior snapshot so callers (entry-capture)
    can act on newly-opened short legs."""
    store = _load_position_snapshots()
    snaps = store.get("snapshots", [])
    today = date.today().isoformat()
    legs = _snapshot_legs()

    prior = next((s for s in reversed(snaps) if s.get("date") != today), None)
    opened, closed = _diff_legs((prior or {}).get("legs", {}), legs)

    rec = {"date": today, "captured_at": _utcnow(), "reason": reason, "legs": legs}
    snaps = [s for s in snaps if s.get("date") != today]  # replace same-day
    snaps.append(rec)
    snaps = snaps[-60:]  # keep ~2 months
    _save_position_snapshots({"snapshots": snaps, "updated_at": _utcnow()})

    # Sprint 16.2 — capture entry conditions for newly-OPENED short option legs.
    # Skip when there's no prior snapshot: the first-ever snapshot has no baseline
    # so every leg falsely reads as "opened" — capturing then would back-fill the
    # legacy book with today's (wrong) IVR/DTE/delta. Genuine new opens are only
    # detectable once a baseline exists.
    captured_entries = 0
    if prior is not None:
        try:
            new_short = [l for l in opened
                         if l.get("sec_type") == "OPT" and (l.get("qty") or 0) < 0]
            captured_entries = _capture_entry_conditions(new_short, today)
        except Exception as e:
            logger.warning("entry-condition capture failed: %s", e)

    return {"captured": True, "date": today, "leg_count": len(legs),
            "opened": opened, "closed": closed,
            "entry_conditions_captured": captured_entries}


def _diff_legs(prev: dict, curr: dict) -> tuple[list, list]:
    """Return (opened[], closed[]) leg events between two leg maps. An OPEN is a
    new key or a magnitude increase in the same direction; a CLOSE is a vanished
    key or magnitude decrease."""
    opened, closed = [], []
    for k, leg in curr.items():
        pq = (prev.get(k) or {}).get("qty", 0.0)
        cq = leg["qty"]
        if k not in prev or abs(cq) > abs(pq):
            opened.append({**leg, "key": k, "delta_qty": cq - pq})
    for k, leg in prev.items():
        cq = (curr.get(k) or {}).get("qty", 0.0)
        if k not in curr or abs(cq) < abs(leg["qty"]):
            closed.append({**leg, "key": k, "delta_qty": cq - leg["qty"]})
    return opened, closed


def weekly_position_opens() -> dict:
    """Pacing-relevant opens for the current week (Mon→now) from the snapshot
    history. Sums per-ticker net SHORT-leg increases across consecutive snapshots
    (so rolls net to zero, hedges excluded, open-then-close in the same week is
    still counted). Returns {available, used, entries[], source}."""
    from datetime import datetime, timezone, timedelta
    store = _load_position_snapshots()
    snaps = sorted(store.get("snapshots", []), key=lambda s: s.get("date", ""))
    if len(snaps) < 2:
        return {"available": False, "used": 0, "entries": [],
                "reason": "need ≥2 snapshots to diff"}

    now = datetime.now(timezone.utc)
    monday = (now - timedelta(days=now.weekday())).date().isoformat()
    # baseline = last snapshot before Monday (so Mon's first capture diffs against it)
    week_snaps = [s for s in snaps if s.get("date", "") >= monday]
    baseline = next((s for s in reversed(snaps) if s.get("date", "") < monday), None)
    chain = ([baseline] if baseline else []) + week_snaps
    if len(chain) < 2:
        return {"available": False, "used": 0, "entries": [],
                "reason": "no prior snapshot before this week yet"}

    entries = []
    for prev, cur in zip(chain, chain[1:]):
        ps = _short_calls_puts(prev.get("legs", {}))
        cs = _short_calls_puts(cur.get("legs", {}))
        for tk in set(cs) | set(ps):
            if tk in _HEDGE_TICKERS_PD:
                continue
            delta = cs.get(tk, 0) - ps.get(tk, 0)
            if delta > 0:
                entries.append({"ticker": tk, "new_short_legs": delta,
                                "detected": cur.get("date")})
    used = sum(e["new_short_legs"] for e in entries)
    return {"available": True, "used": used, "entries": entries,
            "source": "position_diff", "as_of": _utcnow()}


@router.post("/positions/snapshot")
def post_position_snapshot(reason: str = Query(default="manual")):
    """Capture a position snapshot now (the scheduled briefing calls this daily)."""
    return capture_position_snapshot(reason)


@router.get("/positions/opens")
def get_position_opens():
    """Pacing-relevant opens this week, derived from position-diff (authoritative
    manual+staged fill source)."""
    return weekly_position_opens()


# ── Sprint 16.2: entry-condition capture (open → carried to close) ────────────
# When the position-diff detects a newly-opened short option leg, snapshot the
# entry conditions the trade-outcomes loop needs (IVR / DTE / short-delta) into a
# sidecar keyed by leg (opra) key. log_trade_outcome reads it back at CLOSE to
# auto-populate *_at_entry, so the feedback loop accrues data without manual
# entry. Transient runtime state (gitignore).

ENTRY_CONDITIONS_PATH = os.environ.get(
    "FORTRESS_ENTRY_CONDITIONS",
    os.path.expanduser("~/fortress-v4-api/data/entry_conditions.json"),
)


def _load_entry_conditions() -> dict:
    try:
        with open(ENTRY_CONDITIONS_PATH) as f:
            return json.load(f)
    except Exception:
        return {"open": {}, "consumed": []}


def _save_entry_conditions(payload: dict) -> None:
    os.makedirs(os.path.dirname(ENTRY_CONDITIONS_PATH), exist_ok=True)
    with open(ENTRY_CONDITIONS_PATH, "w") as f:
        json.dump(payload, f, indent=2)


def _dte_to(expiry: str) -> int | None:
    try:
        return (date.fromisoformat(expiry) - date.today()).days
    except Exception:
        return None


def _capture_entry_conditions(new_short_legs: list, opened_date: str) -> int:
    """Snapshot IVR / current IV / DTE / short-delta for each newly-opened short
    option leg, keyed by leg key. Skips a leg already captured. Returns count
    captured. Best-effort — a leg that can't be priced still stores what it can."""
    if not new_short_legs:
        return 0
    store = _load_entry_conditions()
    open_map = store.setdefault("open", {})
    captured = 0
    ivr_cache: dict = {}
    for leg in new_short_legs:
        key = leg.get("key")
        if not key or key in open_map:
            continue
        tk = leg.get("ticker")
        strike = leg.get("strike")
        expiry = leg.get("expiry")
        right = "call" if str(leg.get("right", "")).upper().startswith("C") else "put"

        # IVR + current IV (cache per ticker within this capture)
        ivr = current_iv = None
        if tk not in ivr_cache:
            try:
                ivr_cache[tk] = get_iv_rank(tk)
            except Exception:
                ivr_cache[tk] = {}
        ivd = ivr_cache.get(tk) or {}
        if isinstance(ivd, dict) and not ivd.get("error"):
            ivr = ivd.get("iv_rank")
            current_iv = ivd.get("current_iv")

        dte = _dte_to(expiry) if expiry else None

        # Short-delta via BS (spot + IV)
        short_delta = None
        try:
            spot = _try_ibkr_spot(tk) or _spot(yf.Ticker(tk))
            sigma = (current_iv / 100.0) if (current_iv and current_iv > 1) else (current_iv or None)
            if spot and strike and dte and sigma and dte > 0:
                d = _bs_delta(float(spot), float(strike), dte / 365.0, float(sigma), right)
                short_delta = round(abs(d), 4)
        except Exception:
            pass

        open_map[key] = {
            "ticker": tk, "strike": strike, "expiry": expiry,
            "right": "C" if right == "call" else "P",
            "opened_date": opened_date,
            "ivr_at_entry": round(float(ivr), 1) if ivr is not None else None,
            "current_iv_at_entry": round(float(current_iv), 2) if current_iv is not None else None,
            "dte_at_entry": dte,
            "short_delta_at_entry": short_delta,
            "captured_at": _utcnow(),
        }
        captured += 1
    if captured:
        store["updated_at"] = _utcnow()
        _save_entry_conditions(store)
    return captured


def _lookup_entry_conditions(ticker: str) -> dict | None:
    """Best-match unconsumed entry-condition record for a ticker (oldest open).
    Marks it consumed so a later close on the same ticker picks a different one."""
    ticker = str(ticker or "").upper()
    store = _load_entry_conditions()
    open_map = store.get("open", {})
    cands = [(k, v) for k, v in open_map.items()
             if str(v.get("ticker", "")).upper() == ticker]
    if not cands:
        return None
    cands.sort(key=lambda kv: kv[1].get("opened_date") or "")
    key, rec = cands[0]
    open_map.pop(key, None)
    store.setdefault("consumed", []).append({**rec, "key": key, "consumed_at": _utcnow()})
    store["consumed"] = store["consumed"][-200:]
    store["updated_at"] = _utcnow()
    _save_entry_conditions(store)
    return rec


@router.get("/positions/entry-conditions")
def get_entry_conditions():
    """Inspect the open entry-condition snapshots (Sprint 16.2)."""
    store = _load_entry_conditions()
    return {"open": store.get("open", {}),
            "open_count": len(store.get("open", {})),
            "consumed_count": len(store.get("consumed", [])),
            "updated_at": store.get("updated_at")}


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

        # Sprint 16.2/16.3 — auto-fill entry conditions from the capture sidecar
        # when the caller didn't supply them (so the loop accrues data hands-free).
        entry_fields = ("ivr_at_entry", "dte_at_entry", "short_delta_at_entry")
        if not all(rec.get(f) is not None for f in entry_fields):
            ec = _lookup_entry_conditions(rec["ticker"])
            if ec:
                for f in entry_fields:
                    if rec.get(f) is None and ec.get(f) is not None:
                        rec[f] = ec[f]
                rec["entry_conditions_source"] = "auto_captured"
                if rec.get("opened") is None and ec.get("opened_date"):
                    rec["opened"] = ec["opened_date"]

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


# ── Gateway-down integrity guard ──────────────────────────────────────────────
# The briefing's `staleness` field can falsely read "fresh" when the IBKR CP
# Gateway is actually down — the last good sync timestamp lingers, so a frozen
# feed looks current (Handoff Step 0 / DATA_SOURCES.md). This route is the
# honest signal: it live-probes the gateway right now and reports whether
# real-time data is flowing, so the UI can badge LIVE vs FALLBACK vs DOWN and
# the operator never trades on frozen numbers.

_INTEGRITY_PROBE_TICKER = "SPY"   # most liquid — if its snapshot fails, the gateway is effectively down


@router.get("/data-integrity")
def get_data_integrity(
    probe_ticker: str = Query(default=_INTEGRITY_PROBE_TICKER,
                              description="Ticker used for the live gateway probe (default SPY)."),
):
    """
    Authoritative live / fallback / down verdict for the market-data backbone.

    Performs a real-time IBKR CP Gateway snapshot probe instead of trusting the
    briefing `staleness` field (which lingers "fresh" after the gateway dies).
    Consumed by the Parapet source badge at the top of the UI.

    Returns:
      integrity    : 'live' | 'fallback' | 'down'
      live         : bool — True only when the gateway returned a real-time quote
      source       : 'ibkr' | 'yfinance' | 'none' — feed actually serving data
      delayed      : bool — True on the ~15-min-delayed yfinance fallback
      probe_ticker, spot, checked_at, message
    """
    probe = (probe_ticker or _INTEGRITY_PROBE_TICKER).upper()
    checked_at = _utcnow()

    # 1. Live gateway probe — the honest signal (bypasses staleness entirely).
    try:
        ib_spot = _try_ibkr_spot(probe)
    except Exception:
        ib_spot = None
    if ib_spot and ib_spot > 0:
        return {
            "integrity": "live",
            "live": True,
            "source": "ibkr",
            "delayed": False,
            "probe_ticker": probe,
            "spot": round(float(ib_spot), 2),
            "checked_at": checked_at,
            "message": "IBKR CP Gateway live — real-time data flowing.",
        }

    # 2. Gateway not serving → can yfinance still answer? (degraded but usable)
    try:
        yf_spot = _spot(yf.Ticker(probe))
    except Exception:
        yf_spot = None
    if yf_spot and yf_spot > 0:
        return {
            "integrity": "fallback",
            "live": False,
            "source": "yfinance",
            "delayed": True,
            "probe_ticker": probe,
            "spot": round(float(yf_spot), 2),
            "checked_at": checked_at,
            "message": ("IBKR gateway DOWN — serving ~15-min-delayed yfinance "
                        "data. Do not trade on these numbers; restart cp-gateway."),
        }

    # 3. Nothing is answering.
    return {
        "integrity": "down",
        "live": False,
        "source": "none",
        "delayed": True,
        "probe_ticker": probe,
        "spot": None,
        "checked_at": checked_at,
        "message": "No market-data backend responding (gateway and yfinance both failed).",
    }
