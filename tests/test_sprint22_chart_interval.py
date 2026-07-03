"""Sprint 22.5 offline test — chart-route multi-timeframe interval handling.

AST-extracts the REAL `_fetch_ohlcv` from chart_route.py and execs it with a
stubbed `yf.download` (chart_route pulls in config_store etc., so it can't be
imported directly). Validates: 1mo passthrough, 4h→1h fetch + resample, intraday
lookback clamp, unknown-interval fallback. Needs pandas + numpy.

Run:  python3 tests/test_sprint22_chart_interval.py   (exit 0 = all pass)
"""
import os, ast, sys, types
import pandas as pd
import numpy as np

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "chart_route.py")
tree = ast.parse(open(SRC).read())
ns = {}
fn_node = None
for node in tree.body:
    if isinstance(node, ast.Assign) and any(getattr(t, "id", "").startswith(("_YF", "_INTRA")) for t in node.targets):
        exec(compile(ast.Module(body=[node], type_ignores=[]), SRC, "exec"), ns)
    if isinstance(node, ast.FunctionDef) and node.name == "_fetch_ohlcv":
        fn_node = node

calls = {}
def fake_download(ticker, period=None, interval=None, progress=None, auto_adjust=None):
    calls["interval"], calls["period"] = interval, period
    idx = pd.date_range("2026-06-01 09:00", periods=24, freq="1h", tz="UTC")
    return pd.DataFrame({"Open": np.arange(24) + 1.0, "High": np.arange(24) + 2.0,
                         "Low": np.arange(24) + 0.0, "Close": np.arange(24) + 1.5,
                         "Volume": np.arange(24) + 100}, index=idx)

ns["yf"] = types.SimpleNamespace(download=fake_download)
ns["logger"] = types.SimpleNamespace(warning=lambda *a, **k: None)
exec(compile(ast.Module(body=[fn_node], type_ignores=[]), SRC, "exec"), ns)
fetch = ns["_fetch_ohlcv"]

fails = []
def check(c, m):
    print(("PASS" if c else "FAIL") + ": " + m)
    if not c: fails.append(m)

c1 = fetch("MSFT", period="5y", interval="1mo")
check(calls["interval"] == "1mo", "1mo passes straight to yfinance")
check(len(c1) == 24, "1mo returns candles")

c2 = fetch("MSFT", period="6mo", interval="4h")
check(calls["interval"] == "1h", "4h fetches base interval 1h")
check(6 <= len(c2) <= 7 and len(c2) < 24, "4h resamples hourly → session-aligned 4h buckets")
check(all(b["high"] >= max(b["open"], b["close"]) and b["low"] <= min(b["open"], b["close"]) for b in c2),
      "4h OHLC internally consistent")

fetch("MSFT", period="1y", interval="4h")
check(calls["period"] == "180d", "intraday lookback clamped 1y→180d")
fetch("MSFT", period="6mo", interval="1d")
check(calls["interval"] == "1d", "1d passes through")
fetch("MSFT", period="6mo", interval="9x")
check(calls["interval"] == "1d", "unknown interval → 1d fallback")

print("ALL PASS" if not fails else f"{len(fails)} FAILURES: {fails}")
sys.exit(1 if fails else 0)
