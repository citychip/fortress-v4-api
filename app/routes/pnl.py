"""
P&L analytics endpoint.
GET /api/pnl?period=daily|weekly|monthly
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query

from app.services import state

router = APIRouter()


def _period_cutoff(period: str) -> datetime:
    now = datetime.now(timezone.utc)
    if period == "daily":
        return now - timedelta(days=30)
    if period == "weekly":
        return now - timedelta(weeks=12)
    return now - timedelta(days=365)


def _bucket_key(dt: datetime, period: str) -> str:
    if period == "daily":
        return dt.strftime("%Y-%m-%d")
    if period == "weekly":
        return dt.strftime("%G-W%V")
    return dt.strftime("%Y-%m")


def _parse_ts(ts_str: str) -> datetime | None:
    if not ts_str:
        return None
    try:
        return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except ValueError:
        return None


@router.get("/pnl")
def get_pnl(period: str = Query("daily", pattern="^(daily|weekly|monthly)$")):
    cutoff = _period_cutoff(period)

    journal_data = state.get_journal()
    journal_entries = journal_data.get("entries", [])

    closes = []
    for e in journal_entries:
        if e.get("action") not in ("CLOSE", "TRIM"):
            continue
        pnl = e.get("realized_pnl")
        if pnl is None:
            continue
        ts = _parse_ts(e.get("closed_timestamp") or e.get("timestamp", ""))
        if ts and ts >= cutoff:
            closes.append({**e, "_dt": ts, "_pnl": float(pnl)})

    positions_data = state.get_active_positions()
    positions_raw = positions_data.get("positions", [])

    total_unrealized = 0.0
    unrealized_by_ticker: dict[str, float] = defaultdict(float)
    for pos in positions_raw:
        unreal = pos.get("unrealized_pnl")
        if unreal is None:
            mv = pos.get("market_value") or 0.0
            qty = pos.get("qty") or 0.0
            cost = pos.get("avg_cost") or 0.0
            unreal = mv - (qty * cost)
        unreal = float(unreal)
        ticker = (pos.get("ticker") or pos.get("symbol") or "?").upper()
        total_unrealized += unreal
        unrealized_by_ticker[ticker] += unreal

    total_realized = sum(c["_pnl"] for c in closes)
    win_count = sum(1 for c in closes if c["_pnl"] > 0)
    win_rate = (win_count / len(closes)) if closes else None

    bucket_pnl: dict[str, float] = defaultdict(float)
    for c in closes:
        key = _bucket_key(c["_dt"], period)
        bucket_pnl[key] += c["_pnl"]
    series = [{"date": k, "pnl": round(v, 2)} for k, v in sorted(bucket_pnl.items())]
    best_day = max(series, key=lambda x: x["pnl"]) if series else None
    worst_day = min(series, key=lambda x: x["pnl"]) if series else None

    realized_by_ticker: dict[str, float] = defaultdict(float)
    for c in closes:
        ticker = (c.get("ticker") or "?").upper()
        realized_by_ticker[ticker] += c["_pnl"]
    all_tickers = set(realized_by_ticker) | set(unrealized_by_ticker)
    by_ticker = sorted(
        [{"ticker": t, "pnl": round(realized_by_ticker.get(t, 0.0) + unrealized_by_ticker.get(t, 0.0), 2)} for t in all_tickers],
        key=lambda x: x["pnl"],
        reverse=True,
    )

    return {
        "period": period,
        "summary": {
            "total_pnl": round(total_realized + total_unrealized, 2),
            "realized_pnl": round(total_realized, 2),
            "unrealized_pnl": round(total_unrealized, 2),
            "win_rate": round(win_rate, 3) if win_rate is not None else None,
        },
        "series": series,
        "by_ticker": by_ticker,
        "best_day": best_day,
        "worst_day": worst_day,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }
