"""
Positions endpoint: full active book with computed delta_state for visual indicators.

Per Build Spec §5.5.3, delta_state is computed at read time when current_delta
is available. When IBKR sync hasn't provided delta data, falls back to "unknown".
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

import logging
from app.services import state
from app.services.opra import build_opra

logger = logging.getLogger("fortress.positions")


def _get_positions_data() -> dict:
    """Read positions with MySQL-first strategy.

    Priority:
      1. Query MySQL positions table — authoritative for core IBKR fields.
         Enriched fields (greeks, strategy, notes) are merged from in-memory state.
      2. Fall back to in-memory state entirely if MySQL is unavailable or empty.
    """
    state_data = state.get_active_positions()

    try:
        from app.services.db_v4 import SessionLocal
        from app.services.models_v4 import Position as _DbPosition

        with SessionLocal() as db:
            db_rows = db.query(_DbPosition).all()

        if not db_rows:
            logger.debug("MySQL positions table empty — using in-memory state")
            return state_data

        # Build conid-keyed lookup for enriched fields from in-memory state
        state_enrich: dict = {}
        for p in state_data.get("positions", []):
            cid = str(p.get("conid") or "")
            if cid:
                state_enrich[cid] = p

        positions = []
        for row in db_rows:
            cid = str(row.conid)
            enrich = state_enrich.get(cid, {})

            # Expiry: convert date → "YYYY-MM-DD"
            expiry_str = row.expiry.isoformat() if row.expiry else enrich.get("expiry")

            # Multiplier: store as string (rest of codebase expects string)
            mult_str = str(int(row.multiplier)) if row.multiplier else enrich.get("multiplier", "100")

            # Conid: keep as int when possible for downstream compat
            conid_val = int(row.conid) if row.conid and row.conid.isdigit() else row.conid

            positions.append({
                # Core fields — MySQL is authoritative
                "ticker":             row.symbol,
                "sec_type":           row.sec_type or "OPT",
                "currency":           row.currency or "USD",
                "qty":                float(row.position or 0),
                "avg_cost":           float(row.avg_cost or 0) if row.avg_cost is not None else None,
                "market_value":       float(row.market_value or 0) if row.market_value is not None else None,
                "strike":             float(row.strike) if row.strike is not None else None,
                "short_strike":       float(row.strike) if row.strike is not None else None,
                "expiry":             expiry_str,
                "right":              row.opt_right,
                "multiplier":         mult_str,
                "conid":              conid_val,
                "local_symbol":       row.description or enrich.get("local_symbol"),
                # Enriched fields — merged from in-memory state (absent in DB schema)
                "long_strike":        enrich.get("long_strike"),
                "leg_direction":      enrich.get("leg_direction"),
                "current_delta":      enrich.get("current_delta"),
                "current_delta_source": enrich.get("current_delta_source"),
                "current_gamma":      enrich.get("current_gamma"),
                "current_theta":      enrich.get("current_theta"),
                "current_vega":       enrich.get("current_vega"),
                "current_iv":         enrich.get("current_iv"),
                "current_mark":       enrich.get("current_mark"),
                "_ibkr_delta_raw":    enrich.get("_ibkr_delta_raw"),
                "delta_state":        None,   # recomputed by enrichment loop
                "alert_state":        enrich.get("alert_state", "ok"),
                "strategy":           enrich.get("strategy"),
                "notes":              enrich.get("notes", ""),
                "dp_floor":           enrich.get("dp_floor"),
                "net_liq_pct":        enrich.get("net_liq_pct"),
                "opra_symbol":        enrich.get("opra_symbol"),
                "_ibkr_synced":       True,
                "_ibkr_sync_time":    enrich.get("_ibkr_sync_time"),
            })

        return {
            **state_data,
            "positions": positions,
            "_mysql_source": True,
        }

    except Exception as exc:
        logger.warning("MySQL positions read failed — falling back to in-memory state: %s", exc)
        return state_data


router = APIRouter()


def compute_delta_state(pos: dict) -> str:
    """
    Build Spec §5.5.3 delta drift visual states.

    Only applies to SHORT legs (qty < 0, right == 'C') — i.e. short calls that
    can drift into gamma risk territory.  Long calls (LEAP anchors, qty > 0) are
    by design high-delta and must never fire a gamma alert.

    Returns "normal" for long legs, hedges, or when delta isn't available.
    """
    strategy = (pos.get("strategy") or "").upper()
    delta = pos.get("current_delta")
    qty = pos.get("qty")          # positive = long, negative = short
    right = (pos.get("right") or "").upper()  # 'C' or 'P'
    leg_type = (pos.get("leg_type") or "").upper()

    if delta is None:
        return "normal"

    # SPY hedges are always intentional
    if strategy == "SPY_HEDGE":
        return "normal"

    # Long calls (qty > 0, right == 'C') are LEAP anchors — high delta by design
    if right == "C" and qty is not None and float(qty) > 0:
        return "normal"

    # Explicit long-call leg_type (legacy field)
    if leg_type == "LONG_CALL":
        return "normal"

    # Long puts (qty > 0, right == 'P') are protective — not a drift risk
    if right == "P" and qty is not None and float(qty) > 0:
        return "normal"

    # Short calls (qty < 0, right == 'C') — this is what we monitor for gamma drift
    # Also catches short puts and any leg without explicit right/qty metadata
    try:
        from app.services.config_store import cfg as _cfg
        crit = float(_cfg("strategy.delta_critical_threshold") or 0.35)
        watch = float(_cfg("alerts.delta_watch_threshold") or 0.30)
    except Exception:
        crit, watch = 0.35, 0.30
    abs_delta = abs(float(delta))
    if abs_delta > crit:
        return "critical"
    if abs_delta >= watch:
        return "watch"
    return "normal"


def derive_alert_state(pos: dict) -> str:
    """
    If alert_state is explicitly set on the position, use it.
    Otherwise, derive from delta drift if delta available.
    """
    explicit = pos.get("alert_state")
    if explicit:
        return explicit

    delta_state = compute_delta_state(pos)
    if delta_state == "critical":
        return "critical_gamma"
    if delta_state == "watch":
        return "watch"
    if pos.get("current_delta") is None:
        return "unknown"
    return "safe"


@router.get("/positions")
def get_positions():
    """Return positions with computed delta_state and alert_state for visual indicators."""
    try:
        data = _get_positions_data()
    except state.StateError as e:
        raise HTTPException(status_code=500, detail=str(e))

    enriched = []
    for pos in data.get("positions", []):
        # Backfill opra_symbol for legacy records that pre-date v8.6
        opra_sym = pos.get("opra_symbol")
        if not opra_sym and (pos.get("sec_type") or "").upper() == "OPT":
            opra_sym = build_opra(
                pos.get("ticker", ""),
                pos.get("expiry", ""),
                pos.get("right", ""),
                pos.get("strike"),
            )
        enriched.append({
            **pos,
            "opra_symbol": opra_sym,
            "delta_state": compute_delta_state(pos),
            "alert_state": derive_alert_state(pos),
        })

    return {
        "as_of": data.get("_last_updated"),
        "ocr_last_sync": data.get("ocr_last_sync"),
        "positions": enriched,
        "concentration": state.compute_concentration(data),
        "_data_source": "mysql" if data.get("_mysql_source") else "state",
        "totals": {
            "net_liq": data.get("net_liq"),
            "daily_pnl": data.get("daily_pnl"),
            "unrealized_pnl": data.get("unrealized_pnl"),
        }
    }
