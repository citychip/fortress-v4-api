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

    Applies when current_delta is explicit and the position represents short-side
    gamma exposure. Covers:
    - Explicit SHORT_CALL leg_type
    - PMCC/DIAGONAL/JADE_LIZARD strategies (where current_delta represents the
      short-leg or net position delta — what's being monitored for gamma drift)
    - Excludes LONG_CALL/PUT_SPREAD (their delta isn't a drift signal)
    - Excludes SPY_HEDGE (delta is by design, not a risk)

    Returns "normal" for other types or when delta isn't available.
    """
    leg_type = (pos.get("leg_type") or "").upper()
    strategy = (pos.get("strategy") or "").upper()
    delta = pos.get("current_delta")

    if delta is None:
        return "normal"

    # Skip hedges and pure long-call positions
    if strategy == "SPY_HEDGE" or leg_type == "LONG_CALL":
        return "normal"

    # Skip pure put credit spreads — their negative delta is by design
    if leg_type == "PUT_SPREAD" and strategy == "PCS":
        return "normal"

    # Short-call/short-side risk applies. Use abs(delta) since
    # short calls report positive delta in IBKR convention here.
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
