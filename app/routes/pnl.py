"""
P&L analytics endpoint.
GET /api/pnl?period=daily|weekly|monthly
GET /api/pnl/history?days=90   — daily equity-curve snapshots from MySQL
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


@router.get("/pnl/history")
def get_pnl_history(days: int = Query(default=90, ge=1, le=365)):
    """
    Daily equity-curve snapshots for the last N calendar days.

    Reads from MySQL `pnl_snapshots` table (written nightly by the APScheduler
    EOD workflow). Falls back to a single synthetic row from current account
    state when the table is empty or unavailable.

    Response:
        rows  — list of {date, net_liquidation, unrealized_pnl, realized_pnl,
                         buying_power, account}
        count — number of rows returned
        source — "mysql" | "state_fallback"
        as_of  — UTC timestamp
    """
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).date()
    rows: list[dict] = []
    source = "mysql"

    # ── Try MySQL pnl_snapshots table ─────────────────────────────────────
    try:
        from app.services.db_v4 import engine
        from sqlalchemy import text

        with engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                    SELECT snapshot_date, net_liquidation, unrealized_pnl,
                           realized_pnl, buying_power, account_id
                    FROM pnl_snapshots
                    WHERE snapshot_date >= :cutoff
                    ORDER BY snapshot_date ASC
                    """
                ),
                {"cutoff": cutoff_date.isoformat()},
            )
            for r in result.mappings():
                rows.append(
                    {
                        "date": str(r["snapshot_date"]),
                        "net_liquidation": float(r["net_liquidation"]) if r["net_liquidation"] is not None else None,
                        "unrealized_pnl": float(r["unrealized_pnl"]) if r["unrealized_pnl"] is not None else None,
                        "realized_pnl": float(r["realized_pnl"]) if r["realized_pnl"] is not None else None,
                        "buying_power": float(r["buying_power"]) if r["buying_power"] is not None else None,
                        "account": str(r["account_id"]),
                    }
                )
    except Exception:
        source = "state_fallback"

    # ── Fallback: synthesize one row from current account state ───────────
    if not rows:
        source = "state_fallback"
        account_data = state.get_active_positions()
        account_fields = account_data.get("account_fields", {})
        net_liq = account_fields.get("net_liq")
        buying_power = account_fields.get("buying_power")
        account_id = account_data.get("account_id", "")
        if net_liq:
            rows.append(
                {
                    "date": datetime.now(timezone.utc).date().isoformat(),
                    "net_liquidation": round(float(net_liq), 2),
                    "unrealized_pnl": None,
                    "realized_pnl": None,
                    "buying_power": round(float(buying_power), 2) if buying_power else None,
                    "account": account_id,
                }
            )

    return {
        "rows": rows,
        "count": len(rows),
        "source": source,
        "as_of": datetime.now(timezone.utc).isoformat(),
    }


# ── MySQL helpers ─────────────────────────────────────────────────────────────

try:
    import pymysql as _pymysql
    import pymysql.cursors
    _PYMYSQL_OK = True
except ImportError:
    _PYMYSQL_OK = False
import os as _os


def _snap_mysql_conn():
    if not _PYMYSQL_OK:
        return None
    try:
        return _pymysql.connect(
            host=_os.getenv('MYSQL_HOST', 'localhost'),
            user=_os.getenv('MYSQL_USER', 'fortress'),
            password=_os.getenv('MYSQL_PASS', 'fortress_v4_pass'),
            database=_os.getenv('MYSQL_DB', 'fortress_v4'),
            connect_timeout=3,
        )
    except Exception:
        return None


# ── POST /api/pnl/snapshot ────────────────────────────────────────────────────

from fastapi import HTTPException as _HTTPException

@router.post('/pnl/snapshot')
def post_pnl_snapshot():
    '''Write a portfolio snapshot from current active_positions data to MySQL.
    Idempotent — upserts on snapshot_date so running twice on the same day is safe.
    '''
    pos_data = state.get_active_positions() or {}

    net_liq        = pos_data.get('net_liq')
    buying_power   = pos_data.get('buying_power')
    excess_liq     = pos_data.get('excess_liquidity')
    daily_pnl      = pos_data.get('daily_pnl')
    unrealized_pnl = pos_data.get('unrealized_pnl')

    positions_list = pos_data.get('positions', [])
    gross_mv = sum(abs(float(p.get('market_value') or 0)) for p in positions_list)
    net_mv   = sum(float(p.get('market_value') or 0) for p in positions_list)

    try:
        settings = state.get_dashboard_settings()
        account = settings.get('ibkr_account_id') or ''
    except Exception:
        account = ''

    today = datetime.now(timezone.utc).date().isoformat()

    conn = _snap_mysql_conn()
    if conn is None:
        raise _HTTPException(status_code=503, detail='MySQL unavailable')

    try:
        cur = conn.cursor()
        cur.execute(
            '''
            INSERT INTO portfolio_snapshots
                (snapshot_date, total_value, cash_balance, net_liquidation,
                 buying_power, gross_position_value, net_position_value,
                 realized_pnl, unrealized_pnl, account)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                total_value            = VALUES(total_value),
                cash_balance           = VALUES(cash_balance),
                net_liquidation        = VALUES(net_liquidation),
                buying_power           = VALUES(buying_power),
                gross_position_value   = VALUES(gross_position_value),
                net_position_value     = VALUES(net_position_value),
                realized_pnl           = VALUES(realized_pnl),
                unrealized_pnl         = VALUES(unrealized_pnl),
                account                = VALUES(account)
            ''',
            (today, net_liq, excess_liq, net_liq, buying_power,
             gross_mv or None, net_mv or None, daily_pnl, unrealized_pnl, account),
        )
        conn.commit()
        cur.close()
    except Exception as exc:
        raise _HTTPException(status_code=500, detail=f'MySQL write failed: {exc}')
    finally:
        conn.close()

    return {
        'ok': True,
        'snapshot_date': today,
        'net_liquidation': net_liq,
        'unrealized_pnl': unrealized_pnl,
        'realized_pnl': daily_pnl,
        'account': account,
    }
