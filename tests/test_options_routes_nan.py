#!/usr/bin/env python3
"""
test_options_routes_nan.py — regression guard for the NaN-in-JSON 500 class.
===============================================================================
Place at:  ~/fortress-v4-api/tests/test_options_routes_nan.py

Background (2026-06-16): get_gex / get_vol_skew / check_liquidity threw an
uncatchable HTTP 500 on tickers (AAPL, TER, V) whose yfinance chains carried
NaN openInterest / bid / ask / strike. `float(x or 0)` returns NaN (NaN is
truthy), which slipped past the `<= 0` guards and poisoned the response, then
crashed Starlette's JSON serializer (allow_nan=False). Fixed with the `_f()`
NaN/Inf-safe coercion + math.isfinite skip-guards.

This test injects a chain full of NaN OI/bid/ask/strike into every options
route and asserts each result is JSON-serializable with allow_nan=False — i.e.
no NaN/Inf can reach the wire. Runs under pytest OR as a plain script
(`python3 tests/test_options_routes_nan.py`; exit 0 = pass, 1 = fail), so the
deploy script can gate on it without a pytest dependency.
"""

import json
import math
import os
import sys
import pandas as pd

NAN = float("nan")

# Make the API root importable no matter how this file is invoked
# ($API/tests/this_file.py → $API on sys.path → `app.routes...` resolves).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:                                            # deployed layout
    from app.routes import options_analytics as oa
except ImportError:                             # repo-root layout
    import options_analytics as oa


SPOT = 100.0


def _chain_df(right: str) -> pd.DataFrame:
    """A deliberately hostile chain: NaN OI, NaN bid/ask, a NaN strike row,
    plus a couple of clean rows so the routes still produce output."""
    return pd.DataFrame([
        # clean, tradeable row
        {"strike": 100.0, "lastPrice": 5.0,  "bid": 4.9, "ask": 5.1,
         "volume": 50, "openInterest": 200, "impliedVolatility": 0.30},
        # NaN openInterest — the original GEX poisoner
        {"strike": 105.0, "lastPrice": 3.0,  "bid": 2.9, "ask": 3.1,
         "volume": 10, "openInterest": NAN, "impliedVolatility": 0.28},
        # NaN bid/ask — the latent check_liquidity poisoner
        {"strike": 95.0,  "lastPrice": 7.0,  "bid": NAN, "ask": NAN,
         "volume": 5,  "openInterest": 150, "impliedVolatility": 0.32},
        # NaN strike — must be skipped, never keyed/serialized
        {"strike": NAN, "lastPrice": 1.0, "bid": 0.9, "ask": 1.1,
         "volume": 1,  "openInterest": 10,  "impliedVolatility": 0.40},
    ])


class _FakeChain:
    def __init__(self):
        self.calls = _chain_df("call")
        self.puts = _chain_df("put")


class _FakeTicker:
    def __init__(self, *_a, **_k):
        self.fast_info = {"lastPrice": SPOT}
        self.options = ["2026-07-17", "2026-08-21"]

    def option_chain(self, _exp):
        return _FakeChain()

    def history(self, *_a, **_k):
        return pd.DataFrame({"Close": [SPOT]})


def _assert_wire_safe(name, result):
    """Result must serialize with allow_nan=False (Starlette's default)."""
    assert isinstance(result, dict), f"{name}: not a dict"
    # An early exception is caught by the route and returned as {"error": ...},
    # which IS serializable — so we must reject it explicitly, or the NaN path
    # never actually runs and the test passes for the wrong reason.
    assert "error" not in result, f"{name}: route returned error: {result.get('error')}"
    json.dumps(result, allow_nan=False)            # raises ValueError on NaN/Inf

    def _walk(v):
        if isinstance(v, float):
            assert math.isfinite(v), f"{name}: non-finite float in payload"
        elif isinstance(v, dict):
            for x in v.values():
                _walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                _walk(x)
    _walk(result)


def _patch(monkeypatch=None):
    if monkeypatch is not None:
        monkeypatch.setattr(oa.yf, "Ticker", _FakeTicker)
        # neutralize IBKR helpers so we exercise the yfinance/BS paths
        monkeypatch.setattr(oa, "_try_ibkr_spot", lambda *_a, **_k: None)
        monkeypatch.setattr(oa, "_try_ibkr_quotes", lambda *_a, **_k: None)
        monkeypatch.setattr(oa, "_try_ibkr_atm_iv", lambda *_a, **_k: None)
        monkeypatch.setattr(oa, "_try_ibkr_contract_quote", lambda *_a, **_k: None)
    else:
        oa.yf.Ticker = _FakeTicker
        oa._try_ibkr_spot = lambda *_a, **_k: None
        oa._try_ibkr_quotes = lambda *_a, **_k: None
        oa._try_ibkr_atm_iv = lambda *_a, **_k: None
        oa._try_ibkr_contract_quote = lambda *_a, **_k: None


def test_get_gex_nan_safe(monkeypatch):
    _patch(monkeypatch)
    _assert_wire_safe("get_gex", oa.get_gex("AAPL", 6))


def test_get_vol_skew_nan_safe(monkeypatch):
    _patch(monkeypatch)
    _assert_wire_safe("get_vol_skew", oa.get_vol_skew("AAPL", None))


def test_check_liquidity_nan_safe(monkeypatch):
    _patch(monkeypatch)
    _assert_wire_safe("check_liquidity", oa.check_liquidity("AAPL", None, 0.15))


def test_macro_events_nan_safe(monkeypatch):
    # store-backed route — just confirm it serializes cleanly
    _assert_wire_safe("get_macro_events", oa.get_macro_events(2))


def test_trade_outcomes_nan_safe(monkeypatch):
    # store-backed route — confirm it serializes cleanly (incl. empty store)
    _assert_wire_safe("get_trade_outcomes", oa.get_trade_outcomes())


def test_contract_price_nan_safe(monkeypatch):
    _patch(monkeypatch)
    _assert_wire_safe("get_contract_price", oa.get_contract_price("AAPL", 100.0, "2026-07-17", "C"))


if __name__ == "__main__":
    import sys
    _patch(None)
    failures = []
    for name, fn in [
        ("get_gex",         lambda: oa.get_gex("AAPL", 6)),
        ("get_vol_skew",    lambda: oa.get_vol_skew("AAPL", None)),
        ("check_liquidity", lambda: oa.check_liquidity("AAPL", None, 0.15)),
        ("get_macro_events", lambda: oa.get_macro_events(2)),
        ("get_trade_outcomes", lambda: oa.get_trade_outcomes()),
        ("get_contract_price", lambda: oa.get_contract_price("AAPL", 100.0, "2026-07-17", "C")),
    ]:
        try:
            _assert_wire_safe(name, fn())
            print(f"  PASS  {name}")
        except Exception as e:
            failures.append(name)
            print(f"  FAIL  {name}: {e}")
    if failures:
        print(f"NaN smoke-test FAILED: {failures}")
        sys.exit(1)
    print("NaN smoke-test PASSED (all options routes wire-safe)")
