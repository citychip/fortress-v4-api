"""
Pending orders — approval queue endpoints (v3.7.2).

POST   /api/orders/pending            — submit an order for human approval
GET    /api/orders/pending            — list pending orders
DELETE /api/orders/pending/{id}       — decline an order
POST   /api/orders/pending/{id}/preview  — IBKR whatif (margin/cost estimate)
POST   /api/orders/pending/{id}/approve  — approve: resolve conids + preview + submit to IBKR

Order statuses: pending → approved/declined/submitted/failed
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services import state
from app.services.config_store import cfg

logger = logging.getLogger("fortress.routes.orders")
router = APIRouter()


# ── Pydantic models ──────────────────────────────────────────────────────────

class OrderLeg(BaseModel):
    ticker:   str
    sec_type: str        = "OPT"   # OPT | STK
    right:    Optional[str] = None  # C | P (OPT only)
    strike:   Optional[float] = None
    expiry:   Optional[str]   = None  # YYYYMMDD
    action:   str        = "SELL"  # BUY | SELL
    ratio:    int        = 1
    exchange: str        = "CBOE"
    conid:    Optional[int] = None  # resolved at submit time


class PendingOrderCreate(BaseModel):
    ticker:      str    = Field(..., description="Primary underlying ticker")
    strategy:    str    = Field("", description="Strategy label e.g. PCS, IC, PMCC")
    legs:        List[OrderLeg]
    order_type:  str    = Field("LMT", pattern="^(LMT|MKT|MOC)$")
    action:      str    = Field("SELL", pattern="^(BUY|SELL)$")
    quantity:    int    = Field(1, ge=1)
    limit_price: Optional[float] = None
    tif:         str    = Field("DAY", pattern="^(DAY|GTC|IOC|GTD)$")
    notes:       Optional[str] = None
    submitted_by: str   = Field("BuildCenter")
    # Greeks snapshot at time of submission (for display on approvals page)
    pop:         Optional[float] = None
    max_profit:  Optional[float] = None
    max_loss:    Optional[float] = None


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_ibkr_client():
    """Get a configured WebApiClient for the CP Gateway."""
    from app.services.ibkr_web.client import WebApiClient
    gateway_url = cfg("security.cp_gateway_url") or "https://localhost:5000"
    return WebApiClient(gateway_url=gateway_url, verify_ssl=False)


def _get_account_id() -> str:
    settings = state.get_dashboard_settings()
    acct = settings.get("ibkr_account_id") or cfg("security.ibkr_account_id") or ""
    if not acct:
        raise HTTPException(status_code=503, detail="IBKR account ID not configured. Set it in Settings → Security.")
    return acct


def _find_order(orders: list, order_id: str):
    for i, o in enumerate(orders):
        if o.get("id") == order_id:
            return i, o
    raise HTTPException(status_code=404, detail=f"Order '{order_id}' not found.")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/orders/pending", status_code=201)
def submit_pending_order(req: PendingOrderCreate):
    """Submit an order to the approval queue."""
    data = state.get_pending_orders()
    orders = data.get("orders", [])

    order = {
        "id": str(uuid.uuid4()),
        "created_at": _now_iso(),
        "status": "pending",
        "ticker": req.ticker.upper(),
        "strategy": req.strategy,
        "legs": [leg.model_dump() for leg in req.legs],
        "order_type": req.order_type,
        "action": req.action,
        "quantity": req.quantity,
        "limit_price": req.limit_price,
        "tif": req.tif,
        "notes": req.notes,
        "submitted_by": req.submitted_by,
        "pop": req.pop,
        "max_profit": req.max_profit,
        "max_loss": req.max_loss,
        "whatif_result": None,
        "ibkr_order_id": None,
        "error": None,
    }

    orders.append(order)
    data["orders"] = orders
    data["_last_updated"] = _now_iso()
    state.save_pending_orders(data)

    return {"id": order["id"], "status": "pending"}


@router.get("/orders/pending")
def list_pending_orders(status: Optional[str] = None):
    """
    List all orders in the approval queue.
    Optional ?status= filter: pending|approved|declined|submitted|failed
    """
    data = state.get_pending_orders()
    orders = data.get("orders", [])
    if status:
        orders = [o for o in orders if o.get("status") == status]
    # Return newest first
    return {"orders": list(reversed(orders))}


@router.delete("/orders/pending/{order_id}")
def decline_order(order_id: str):
    """Decline (remove) an order from the queue."""
    data = state.get_pending_orders()
    orders = data.get("orders", [])
    idx, order = _find_order(orders, order_id)

    if order.get("status") in ("submitted",):
        raise HTTPException(status_code=409, detail="Cannot decline an order already submitted to IBKR.")

    order["status"] = "declined"
    order["declined_at"] = _now_iso()
    orders[idx] = order
    data["orders"] = orders
    data["_last_updated"] = _now_iso()
    state.save_pending_orders(data)
    return {"id": order_id, "status": "declined"}


@router.post("/orders/pending/{order_id}/preview")
def preview_order(order_id: str):
    """
    Call IBKR whatif for this order.
    Resolves conids first, then returns margin/commission estimate.
    """
    data = state.get_pending_orders()
    orders = data.get("orders", [])
    idx, order = _find_order(orders, order_id)

    if order.get("status") == "submitted":
        raise HTTPException(status_code=409, detail="Order already submitted.")

    client = _get_ibkr_client()
    account_id = _get_account_id()

    # Resolve conids
    from app.services.ibkr_web.orders import resolve_leg_conids, whatif_order
    order["legs"] = resolve_leg_conids(client, order["legs"])
    unresolved = [l["ticker"] for l in order["legs"] if not l.get("conid")]
    if unresolved:
        logger.warning("preview_order: unresolved conids for %s", unresolved)

    # Whatif
    result = whatif_order(client, account_id, order)
    order["whatif_result"] = result
    orders[idx] = order
    data["orders"] = orders
    data["_last_updated"] = _now_iso()
    state.save_pending_orders(data)

    return {"order_id": order_id, "whatif": result}


@router.post("/orders/pending/{order_id}/approve")
def approve_order(order_id: str):
    """
    Approve an order: resolve conids → whatif preview → submit to IBKR.
    Updates status to 'submitted' (or 'failed' on error).
    """
    data = state.get_pending_orders()
    orders = data.get("orders", [])
    idx, order = _find_order(orders, order_id)

    if order.get("status") == "submitted":
        raise HTTPException(status_code=409, detail="Order already submitted to IBKR.")
    if order.get("status") == "declined":
        raise HTTPException(status_code=409, detail="Order was declined.")

    client = _get_ibkr_client()
    account_id = _get_account_id()

    from app.services.ibkr_web.orders import resolve_leg_conids, place_order

    # Step 1: resolve conids
    order["legs"] = resolve_leg_conids(client, order["legs"])
    unresolved = [l["ticker"] for l in order["legs"] if not l.get("conid")]
    if unresolved:
        order["status"] = "failed"
        order["error"] = f"Could not resolve IBKR conids for: {', '.join(unresolved)}. Verify ticker/expiry/strike."
        orders[idx] = order
        data["orders"] = orders
        state.save_pending_orders(data)
        raise HTTPException(status_code=422, detail=order["error"])

    # Step 2: place order
    result = place_order(client, account_id, order)

    if result.get("ok"):
        order["status"] = "submitted"
        order["submitted_at"] = _now_iso()
        raw = result.get("raw", {})
        # Extract IBKR order ID from various response shapes
        if isinstance(raw, list) and raw:
            order["ibkr_order_id"] = raw[0].get("order_id") or raw[0].get("orderId")
        elif isinstance(raw, dict):
            order["ibkr_order_id"] = raw.get("order_id") or raw.get("orderId")
        order["ibkr_response"] = raw
        order["error"] = None
    else:
        order["status"] = "failed"
        order["error"] = result.get("error", "Unknown IBKR error")
        order["ibkr_response"] = result.get("raw")

    orders[idx] = order
    data["orders"] = orders
    data["_last_updated"] = _now_iso()
    state.save_pending_orders(data)

    if not result.get("ok"):
        raise HTTPException(status_code=502, detail=order["error"])

    return {
        "id": order_id,
        "status": "submitted",
        "ibkr_order_id": order.get("ibkr_order_id"),
    }
