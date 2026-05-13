"""
Positions endpoint: full active book with computed delta_state for visual indicators.

Per Build Spec §5.5.3, delta_state is computed at read time when current_delta
is available. When IBKR sync hasn't provided delta data, falls back to "unknown".
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.services import state

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
        data = state.get_active_positions()
    except state.StateError as e:
        raise HTTPException(status_code=500, detail=str(e))

    enriched = []
    for pos in data.get("positions", []):
        enriched.append({
            **pos,
            "delta_state": compute_delta_state(pos),
            "alert_state": derive_alert_state(pos),
        })

    return {
        "as_of": data.get("_last_updated"),
        "ocr_last_sync": data.get("ocr_last_sync"),
        "positions": enriched,
        "concentration": state.compute_concentration(data),
        "totals": {
            "net_liq": data.get("net_liq"),
            "daily_pnl": data.get("daily_pnl"),
            "unrealized_pnl": data.get("unrealized_pnl"),
        }
    }
