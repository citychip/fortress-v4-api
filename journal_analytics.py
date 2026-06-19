#!/usr/bin/env python3
"""
journal_analytics.py — expectancy / win-rate feedback loop over the trade journal.
===============================================================================
Turns journal.json into the "which of my setups actually pay?" report. The
highest-ROI profitability lever you have is learning from your own closed
trades instead of trusting inherited rule defaults.

Usage:
    python3 journal_analytics.py [path/to/trade_outcomes.json]
    # default: ~/fortress-v4-api/data/trade_outcomes.json (the structured
    # closed-trade store written by the MCP log_trade_outcome tool). Also
    # accepts the legacy prose journal.json (entries[]) — it just won't have the
    # IVR/DTE/delta fields needed for bucketing.

What it computes (overall + grouped by strategy, then by action):
    n, closed, wins, win_rate, total_realized, avg_win, avg_loss,
    expectancy (avg realized per closed trade), profit_factor.

Bucketed expectancy by IV-rank / DTE / short-delta AT ENTRY is the real goal,
but those fields are NOT in the current journal schema. The script computes
them automatically *once the entries carry them* (see SCHEMA NOTE below); until
then it reports what the existing fields (strategy, action, realized_pnl)
support and tells you what to add.

SCHEMA NOTE — to unlock bucketed expectancy, enrich each journal entry at
open/close with: ivr_at_entry, dte_at_entry, short_delta_at_entry, days_held,
exit_reason. Add them to the backend POST /api/journal schema and to the MCP
add_journal_entry() tool, then this script light up the IVR/DTE/delta tables.
"""

import json
import os
import sys
from collections import defaultdict

DEFAULT_PATH = os.path.expanduser("~/fortress-v4-api/data/trade_outcomes.json")

# Optional enrichment fields — bucketed automatically when present.
BUCKET_FIELDS = {
    "ivr_at_entry":       [(0, 25), (25, 50), (50, 75), (75, 1000)],
    "dte_at_entry":       [(0, 21), (21, 35), (35, 45), (45, 9999)],
    "short_delta_at_entry": [(0, 0.15), (0.15, 0.20), (0.20, 0.30), (0.30, 1.0)],
}


def _load(path):
    with open(path) as f:
        data = json.load(f)
    if isinstance(data, dict):
        # trade_outcomes store uses "records"; legacy prose journal uses "entries"
        return data.get("records") or data.get("entries") or []
    return data if isinstance(data, list) else []


def _num(x):
    try:
        v = float(x)
        return v if v == v else None  # drop NaN
    except (TypeError, ValueError):
        return None


def _stats(entries):
    """Expectancy stats over a list of entries (only those with realized_pnl)."""
    closed = [e for e in entries if _num(e.get("realized_pnl")) is not None]
    pnls = [_num(e["realized_pnl"]) for e in closed]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    n_closed = len(pnls)
    gross_win = sum(wins)
    gross_loss = -sum(losses)
    return {
        "n": len(entries),
        "closed": n_closed,
        "wins": len(wins),
        "win_rate": round(100 * len(wins) / n_closed, 1) if n_closed else None,
        "total_realized": round(sum(pnls), 2) if n_closed else 0.0,
        "avg_win": round(gross_win / len(wins), 2) if wins else None,
        "avg_loss": round(-gross_loss / len(losses), 2) if losses else None,
        "expectancy": round(sum(pnls) / n_closed, 2) if n_closed else None,
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss else None,
    }


def _fmt(s):
    if not s["closed"]:
        return f"n={s['n']:>3}  closed=0  (no realized P&L yet)"
    return (f"n={s['n']:>3}  closed={s['closed']:>3}  win={s['win_rate']}%  "
            f"exp=${s['expectancy']}  PF={s['profit_factor']}  "
            f"avgW=${s['avg_win']}  avgL=${s['avg_loss']}  tot=${s['total_realized']}")


def _group(entries, key):
    g = defaultdict(list)
    for e in entries:
        g[str(e.get(key) or "—")].append(e)
    return g


def _bucket(entries, field, ranges):
    g = defaultdict(list)
    present = False
    for e in entries:
        v = _num(e.get(field))
        if v is None:
            continue
        present = True
        for lo, hi in ranges:
            if lo <= v < hi:
                g[f"{lo}-{hi}"].append(e)
                break
    return g if present else None


def report(path):
    if not os.path.exists(path):
        print(f"journal not found: {path}")
        return 1
    entries = _load(path)
    print(f"\nJOURNAL ANALYTICS — {path}")
    print(f"entries: {len(entries)}\n")
    if not entries:
        print("Journal is empty — nothing to analyze. Start logging every open/close.")
        return 0

    print("OVERALL")
    print("  " + _fmt(_stats(entries)))

    print("\nBY STRATEGY")
    for k, v in sorted(_group(entries, "strategy").items()):
        print(f"  {k:<12} " + _fmt(_stats(v)))

    print("\nBY ACTION")
    for k, v in sorted(_group(entries, "action").items()):
        print(f"  {k:<12} " + _fmt(_stats(v)))

    any_bucket = False
    for field, ranges in BUCKET_FIELDS.items():
        b = _bucket(entries, field, ranges)
        if b is None:
            continue
        any_bucket = True
        print(f"\nBY {field}")
        for k, v in sorted(b.items()):
            print(f"  {k:<12} " + _fmt(_stats(v)))

    if not any_bucket:
        print("\n[bucketed expectancy unavailable] entries carry no "
              "ivr_at_entry / dte_at_entry / short_delta_at_entry. Enrich the "
              "journal schema (see SCHEMA NOTE) to unlock IVR/DTE/delta tables.")
    return 0


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PATH
    sys.exit(report(path))
