"""Sprint 22.4a offline test — monthly_trend_state (LEAP secular-thesis read).

AST-extracts the REAL monthly_trend_state (+ its module-level cache constants)
from options_analytics.py and execs it with a stubbed yfinance. Validates the
10/20-month EMA trend classification, including partial-history handling.
Needs pandas + numpy.

Run:  python3 tests/test_sprint22_monthly_trend.py   (exit 0 = all pass)
"""
import os, ast, sys, types
import pandas as pd
import numpy as np

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "options_analytics.py")
tree = ast.parse(open(SRC).read())
ns, fn = {}, None
for node in tree.body:
    if isinstance(node, (ast.Assign, ast.AnnAssign)):
        tgts = node.targets if isinstance(node, ast.Assign) else [node.target]
        if any(getattr(t, "id", "").startswith("_MONTHLY") for t in tgts):
            exec(compile(ast.Module(body=[node], type_ignores=[]), SRC, "exec"), ns)
    if isinstance(node, ast.FunctionDef) and node.name == "monthly_trend_state":
        fn = node


def _close(vals):
    idx = pd.date_range("2016-01-01", periods=len(vals), freq="MS", tz="UTC")
    return pd.DataFrame({"Close": vals}, index=idx)


def _fake_ticker(t):
    obj = types.SimpleNamespace()
    if t == "UP":        vals = list(np.linspace(50, 200, 120))
    elif t == "DOWN":    vals = list(np.linspace(200, 80, 120))
    elif t == "THIN":    vals = [100, 101, 99, 102, 100, 103]        # 6 bars
    elif t == "PARTIAL": vals = list(np.linspace(80, 140, 15))       # 15 bars → only ema10
    else:                vals = [100] * 120
    obj.history = lambda period=None, interval=None: _close(vals)
    return obj


ns["yf"] = types.SimpleNamespace(Ticker=_fake_ticker)
exec(compile(ast.Module(body=[fn], type_ignores=[]), SRC, "exec"), ns)
f = ns["monthly_trend_state"]

fails = []
def ck(c, m):
    print(("PASS" if c else "FAIL") + ": " + m)
    if not c: fails.append(m)

u = f("UP")
ck(u["trend"] == "up" and u["above_10m"] and u["above_20m"] and u["ema_10m"] is not None, "rising → up")
d = f("DOWN")
ck(d["trend"] == "down" and d["above_10m"] is False, "falling → down")
t = f("THIN")
ck(t["trend"] == "unknown" and t["ema_10m"] is None and t["bars"] == 6, "thin (6 bars) → unknown, no EMA")
p = f("PARTIAL")
ck(p["ema_10m"] is not None and p["ema_20m"] is None and p["trend"] == "up",
   "partial (15 bars) → up off the 10m EMA alone")

print("ALL PASS" if not fails else f"{len(fails)} FAILURES: {fails}")
sys.exit(1 if fails else 0)
