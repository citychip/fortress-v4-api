"""
options_analytics.py — yfinance-based GEX, IV skew, and liquidity routes
=========================================================================
Place at:  ~/fortress-v4-api/app/routes/options_analytics.py

Then in app/main.py add (after other include_router lines):
    from app.routes.options_analytics import router as options_analytics_router
    app.include_router(options_analytics_router, prefix="/api")

Endpoints:
    GET /api/options/gex/{ticker}          — Gamma Exposure by strike
    GET /api/options/vol-skew/{ticker}     — IV skew + term structure
    GET /api/options/liquidity/{ticker}    — Bid-ask spread quality check
    GET /api/options/iv-rank/{ticker}      — IV rank (yfinance; replaces broken QD iv_rank)

No paid APIs. Uses yfinance (already in backend requirements).
scipy is NOT required — Black-Scholes via pure Python.
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
        spot = _spot(t)
        if not spot:
            return {"error": f"Could not get spot price for {ticker}"}

        expirations = list(t.options[:max_expiries])
        if not expirations:
            return {"error": f"No options chain found for {ticker}"}

        # Aggregate GEX by strike across all expirations
        gex_map: dict[float, dict] = {}

        for exp in expirations:
            T = _dte_years(exp)
            try:
                chain = t.option_chain(exp)
            except Exception as e:
                logger.warning("Skipping expiry %s for %s: %s", exp, ticker, e)
                continue

            for df, right in [(chain.calls, "call"), (chain.puts, "put")]:
                for _, row in df.iterrows():
                    K = float(row.get("strike", 0) or 0)
                    oi = float(row.get("openInterest") or 0)
                    iv = float(row.get("impliedVolatility") or 0)
                    if K <= 0 or oi <= 0 or iv <= 0:
                        continue

                    gamma = _bs_gamma(spot, K, T, iv)
                    gex = gamma * oi * 100 * spot
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
            "source":      "yfinance",
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
        spot = _spot(t)
        if not spot:
            return {"error": f"Could not get spot price for {ticker}"}

        available = list(t.options)
        if not available:
            return {"error": f"No options chain found for {ticker}"}

        chosen_exp = expiry if (expiry and expiry in available) else available[0]
        T = _dte_years(chosen_exp)

        chain = t.option_chain(chosen_exp)

        # Build per-strike skew table
        strike_data: dict[float, dict] = {}

        for df, right in [(chain.calls, "call"), (chain.puts, "put")]:
            for _, row in df.iterrows():
                K = float(row.get("strike", 0) or 0)
                iv = float(row.get("impliedVolatility") or 0)
                oi = int(row.get("openInterest") or 0)
                if K <= 0 or iv <= 0:
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
                iv_val = float(atm_rows["impliedVolatility"].iloc[0]) * 100
                if iv_val > 0:
                    term_structure.append({
                        "expiry":  exp,
                        "dte":     round(T_exp * 365),
                        "atm_iv":  round(iv_val, 2),
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
            "source":         "yfinance",
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
        spot = _spot(t)
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
        chain = t.option_chain(chosen_exp)

        lo = spot * (1 - moneyness_range)
        hi = spot * (1 + moneyness_range)

        def _spread_rows(df, right: str) -> list:
            out = []
            for _, row in df.iterrows():
                k = float(row.get("strike", 0) or 0)
                if not (lo <= k <= hi):
                    continue
                bid = float(row.get("bid") or 0)
                ask = float(row.get("ask") or 0)
                mid = (bid + ask) / 2
                if mid <= 0 or ask <= 0:
                    continue
                sp = round((ask - bid) / mid * 100, 1)
                out.append({
                    "strike":     k,
                    "right":      right,
                    "bid":        round(bid, 2),
                    "ask":        round(ask, 2),
                    "mid":        round(mid, 2),
                    "spread_pct": sp,
                    "status":     "good" if sp < 5 else "advisory" if sp <= 10 else "wide",
                })
            return out

        call_data = _spread_rows(chain.calls, "call")
        put_data  = _spread_rows(chain.puts,  "put")
        all_data  = call_data + put_data

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
            "source":  "yfinance",
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
        spot = _spot(t)
        if not spot:
            return {"error": f"Could not get spot price for {ticker}"}

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
            "n_snapshots":  n_snapshots,
            "as_of":        _utcnow(),
        }

    except Exception as e:
        logger.error("IV rank error for %s: %s", ticker, e, exc_info=True)
        return {"error": str(e)}
