"""
quant/iv_source.py — IBKR-first IV sourcing for the standalone scanners.

SINGLE SOURCE OF TRUTH for current ATM IV (+ IVR) used by the workflow scanners
(workflow_01 premarket, workflow_05 IV-crush). Created in Sprint 18.2 to kill the
bug class where a scanner read yfinance's raw `impliedVolatility` column — which
is placeholder junk (~1e-5..0.03 on the delayed feed) — instead of the canonical
IBKR-first path. Both scanners now import from here, so the fix can't drift apart
again (that drift is exactly how 18.1/18.2 happened: the served backend routes
were migrated to IBKR-first but these standalone scripts were missed).

Priority for any IV read:
  1. backend /api/options/iv-rank/{ticker}  (iv_source: ibkr → BS-inversion → hv_proxy)
  2. band-guarded yfinance ATM IV fallback   (rejects the sub-4% / over-500% junk band)
  3. reject (return 0.0 / {}) — NEVER emit a junk ~0% value as if it were real.
"""
import json
import os
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import yfinance as yf

FORTRESS_API_BASE = os.environ.get("FORTRESS_API_BASE", "http://localhost:8081")
MIN_SANE_IV_PCT = 4.0       # IV below this (percent) is the yfinance placeholder band → reject
MAX_SANE_IV_PCT = 500.0     # IV above this is nonsense → reject
_BACKEND_IV_TIMEOUT_S = 6   # per-ticker cap; prefetch runs these concurrently
_BACKEND_IV_CACHE: dict = {}  # ticker → result dict (warmed by prefetch_backend_iv)


def _api_token() -> str:
    """Backend API token — file-driven (same source the rest of the stack uses)."""
    try:
        tok = open(os.path.expanduser("~/.fortress_api_token")).read().strip()
        if tok:
            return tok
    except Exception:
        pass
    return os.environ.get("FORTRESS_API_TOKEN", "")


def _fetch_backend_iv(ticker: str) -> dict:
    """
    Single backend /api/options/iv-rank/{ticker} call (IBKR-first → BS-inversion
    → hv_proxy). Returns {current_iv, ivr, iv_source} (IV/IVR in percent), or {}
    on failure / a sub-band junk value (caller then uses the yfinance fallback).
    """
    try:
        url = f"{FORTRESS_API_BASE}/api/options/iv-rank/{ticker}"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {_api_token()}"})
        with urllib.request.urlopen(req, timeout=_BACKEND_IV_TIMEOUT_S) as resp:
            d = json.loads(resp.read().decode())
        iv = d.get("current_iv")
        if iv is None:
            return {}
        iv = float(iv)
        if not (MIN_SANE_IV_PCT <= iv <= MAX_SANE_IV_PCT):
            return {}   # backend returned a junk/placeholder value — don't trust it
        ivr = d.get("iv_rank")
        return {
            "current_iv": round(iv, 2),
            "ivr": round(float(ivr), 1) if ivr is not None else None,
            "iv_source": d.get("iv_source") or d.get("source") or "backend",
        }
    except Exception:
        return {}


def prefetch_backend_iv(tickers, workers: int = 6) -> None:
    """
    Warm _BACKEND_IV_CACHE for all tickers CONCURRENTLY. Each backend call
    triggers a live IBKR snapshot (~1-3s); doing 20+ sequentially blows a scan
    past its caller's timeout. A small pool keeps total latency near a single
    call without hammering the gateway's rate limits.
    """
    def _one(tk):
        _BACKEND_IV_CACHE[tk] = _fetch_backend_iv(tk)
    try:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            list(ex.map(_one, tickers))
    except Exception:
        pass


def backend_iv_rank(ticker: str) -> dict:
    """
    IBKR-first IV + IVR for one ticker, served from the concurrently-warmed cache
    when available, else a direct fetch. Returns {current_iv, ivr, iv_source}
    (percent) or {} on failure (caller falls back to band-guarded yfinance).
    """
    if ticker in _BACKEND_IV_CACHE:
        return _BACKEND_IV_CACHE[ticker]
    return _fetch_backend_iv(ticker)


def yf_atm_iv(ticker_symbol: str) -> float:
    """
    FALLBACK ONLY: ATM IV from the yfinance options chain, BAND-GUARDED.
    Yahoo's raw impliedVolatility column is placeholder junk (~1e-5..0.03) on the
    delayed feed, so any averaged value outside the sane band is rejected (→ 0.0)
    rather than passed through. Returns IV as a percentage, or 0.0 if untrustworthy.
    """
    try:
        t = yf.Ticker(ticker_symbol)
        price = t.fast_info.get("lastPrice") or t.fast_info.get("previousClose", 0)
        if not price:
            return 0.0
        expirations = t.options
        if not expirations:
            return 0.0
        today = datetime.now().date()
        target = None
        for exp in expirations:
            if (datetime.strptime(exp, "%Y-%m-%d").date() - today).days >= 7:
                target = exp
                break
        if not target:
            target = expirations[0]
        chain = t.option_chain(target)
        calls = chain.calls[["strike", "impliedVolatility"]].dropna()
        puts = chain.puts[["strike", "impliedVolatility"]].dropna()
        atm_call = calls.iloc[(calls["strike"] - price).abs().argsort()[:1]]
        atm_put = puts.iloc[(puts["strike"] - price).abs().argsort()[:1]]
        call_iv = float(atm_call["impliedVolatility"].values[0]) * 100
        put_iv = float(atm_put["impliedVolatility"].values[0]) * 100
        iv = round((call_iv + put_iv) / 2, 2)
        if not (MIN_SANE_IV_PCT <= iv <= MAX_SANE_IV_PCT):
            return 0.0   # reject the placeholder-junk band — never surface as real
        return iv
    except Exception:
        return 0.0


def get_atm_iv(ticker_symbol: str) -> float:
    """
    Current ATM IV (percent), IBKR-FIRST: backend iv-rank route → band-guarded
    yfinance fallback → 0.0 if no trustworthy IV (callers treat 0.0 as 'skip',
    never as a real value).
    """
    be = backend_iv_rank(ticker_symbol)
    if be.get("current_iv"):
        return be["current_iv"]
    return yf_atm_iv(ticker_symbol)
