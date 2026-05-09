"""
EUR/USD FX rate provider.

The strategy doc thresholds are in EUR (€17K AvailableFunds floor, €25K
ExcessLiq cushion, €15-20K position size, €20-30K hedge target). IBKR
returns USD. This module exposes the live rate so display + comparisons
can convert between the two without each caller hitting yfinance.

Cached with a 1h TTL — FX rates don't move quickly enough to matter for
risk-management thresholds.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

logger = logging.getLogger("fortress.fx")

_CACHE: dict[str, tuple[float, float]] = {}
_TTL_S = 3600  # 1 hour


def _safe_float(v, default=None):
    try:
        x = float(v)
        if x != x:
            return default
        return x
    except (TypeError, ValueError):
        return default


def get_eur_usd_rate() -> Optional[float]:
    """Return USD per 1 EUR (e.g., 1.0741). None on failure."""
    key = "EURUSD"
    now = time.time()
    if key in _CACHE:
        ts, val = _CACHE[key]
        if now - ts < _TTL_S:
            return val
    try:
        import yfinance as yf
        tk = yf.Ticker("EURUSD=X")
        try:
            info = getattr(tk, "fast_info", None)
            if info is not None:
                p = None
                for attr in ("last_price", "lastPrice", "regular_market_price"):
                    try:
                        p = getattr(info, attr, None)
                    except Exception:
                        p = None
                    if p is not None:
                        f = _safe_float(p)
                        if f and f > 0:
                            _CACHE[key] = (now, f)
                            return f
        except Exception:
            pass
        hist = tk.history(period="5d", interval="1d")
        if hist is not None and not hist.empty:
            last = _safe_float(hist["Close"].iloc[-1])
            if last and last > 0:
                _CACHE[key] = (now, last)
                return last
    except Exception as e:
        logger.warning("EUR/USD fetch failed: %s", e)
    return None


def usd_to_eur(usd: Optional[float]) -> Optional[float]:
    """Convert USD to EUR using the cached rate. None if either is unavailable."""
    if usd is None:
        return None
    rate = get_eur_usd_rate()
    if not rate or rate <= 0:
        return None
    return usd / rate


def eur_to_usd(eur: Optional[float]) -> Optional[float]:
    """Convert EUR to USD using the cached rate. None if either is unavailable."""
    if eur is None:
        return None
    rate = get_eur_usd_rate()
    if not rate or rate <= 0:
        return None
    return eur * rate
