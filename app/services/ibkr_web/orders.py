"""
IBKR order placement via CP Gateway (ibeam).

Supports:
  - Single-leg options and stock
  - Multi-leg BAG/combo orders (spreads, condors, etc.)
  - whatif preview (margin/cost estimate without placing)
  - Actual order placement

Flow:
  1. resolve_conids()   — lookup conid for each leg via ibeam secdef API
  2. whatif_order()     — dry-run to get margin/commission estimate
  3. place_order()      — actually submit

All calls go through the shared WebApiClient (rate-limited, SSL-bypass for localhost).
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

from app.services.ibkr_web.client import WebApiClient, WebApiError, GatewayUnreachable

logger = logging.getLogger("fortress.ibkr_web.orders")

# ── conid resolution ──────────────────────────────────────────────────────────

def resolve_underlying_conid(client: WebApiClient, ticker: str) -> Optional[int]:
    """Find the primary STK conid for a ticker on SMART/USD."""
    try:
        results = client.get("/iserver/secdef/search", params={"symbol": ticker, "secType": "STK"})
        if isinstance(results, list) and results:
            for r in results:
                if r.get("symbol", "").upper() == ticker.upper():
                    return r.get("conid")
            return results[0].get("conid")
    except Exception as e:
        logger.warning("resolve_underlying_conid(%s): %s", ticker, e)
    return None


def resolve_option_conid(
    client: WebApiClient,
    ticker: str,
    expiry_yyyymmdd: str,      # e.g. "20260620"
    right: str,                # "C" or "P"
    strike: float,
) -> Optional[int]:
    """
    Resolve a single option conid.
    Uses /iserver/secdef/info — returns conids by strike/right for a given month.
    """
    # ibeam uses MMMYY format for month, e.g. "JUN26"
    import calendar as _cal
    y = int(expiry_yyyymmdd[:4])
    m = int(expiry_yyyymmdd[4:6])
    month_str = _cal.month_abbr[m].upper() + str(y)[2:]  # e.g. "JUN26"

    # Need underlying conid first
    und_conid = resolve_underlying_conid(client, ticker)
    if not und_conid:
        logger.warning("resolve_option_conid: no underlying conid for %s", ticker)
        return None

    try:
        results = client.get("/iserver/secdef/info", params={
            "conid": und_conid,
            "sectype": "OPT",
            "month": month_str,
            "right": right,
            "strike": strike,
        })
        if isinstance(results, list) and results:
            return results[0].get("conid")
        if isinstance(results, dict):
            return results.get("conid")
    except Exception as e:
        logger.warning("resolve_option_conid(%s %s %s %s): %s", ticker, expiry_yyyymmdd, right, strike, e)
    return None


def resolve_leg_conids(client: WebApiClient, legs: list[dict]) -> list[dict]:
    """
    Resolve conids for all legs. Returns legs list with 'conid' populated where possible.
    Each leg dict must have: ticker, sec_type ('OPT'/'STK'), right (for OPT), strike (for OPT), expiry (for OPT, YYYYMMDD).
    """
    resolved = []
    for leg in legs:
        leg = dict(leg)
        if leg.get("conid"):
            resolved.append(leg)
            continue
        sec_type = (leg.get("sec_type") or "OPT").upper()
        ticker = leg["ticker"].upper()
        if sec_type == "STK":
            conid = resolve_underlying_conid(client, ticker)
        else:
            conid = resolve_option_conid(
                client,
                ticker,
                leg.get("expiry", ""),
                (leg.get("right") or "C").upper(),
                float(leg.get("strike", 0)),
            )
        leg["conid"] = conid
        leg["conid_resolved"] = conid is not None
        resolved.append(leg)
    return resolved


# ── Order payload builders ─────────────────────────────────────────────────────

def _build_single_leg_payload(account_id: str, leg: dict, order: dict) -> dict:
    """Build IBKR order payload for a single leg (option or stock)."""
    sec_type = (leg.get("sec_type") or "OPT").upper()
    payload = {
        "acctId": account_id,
        "conid": leg["conid"],
        "secType": f"{leg['conid']}:{sec_type}",
        "cOID": order.get("id", ""),
        "orderType": order.get("order_type", "LMT"),
        "side": leg.get("action", "SELL").upper(),
        "quantity": abs(int(order.get("quantity", 1))),
        "tif": order.get("tif", "DAY"),
        "price": order.get("limit_price"),
    }
    # Remove None price (market orders)
    if payload["price"] is None:
        del payload["price"]
    return payload


def _build_combo_payload(account_id: str, legs: list[dict], order: dict) -> dict:
    """Build IBKR BAG (multi-leg combo) order payload."""
    combo_legs = []
    for leg in legs:
        combo_legs.append({
            "conid": leg["conid"],
            "ratio": int(leg.get("ratio", 1)),
            "side": leg.get("action", "SELL").upper(),
            "exchange": leg.get("exchange", "CBOE"),
        })

    # For BAG we need the underlying conid
    # Use first leg's ticker to find it
    und_ticker = legs[0]["ticker"].upper() if legs else ""
    # Underlying conid stored in order or first leg
    und_conid = order.get("underlying_conid") or legs[0].get("underlying_conid")

    payload = {
        "acctId": account_id,
        "conid": und_conid or legs[0]["conid"],  # fallback to first leg conid
        "secType": "BAG",
        "cOID": order.get("id", ""),
        "orderType": order.get("order_type", "LMT"),
        "side": order.get("action", "SELL").upper(),
        "quantity": abs(int(order.get("quantity", 1))),
        "tif": order.get("tif", "DAY"),
        "price": order.get("limit_price"),
        "comboLegs": combo_legs,
        "listingExchange": "CBOE",
    }
    if payload["price"] is None:
        del payload["price"]
    return payload


def build_order_payload(account_id: str, order: dict) -> dict:
    """Build the full IBKR order payload from a Fortress pending order dict."""
    legs = order.get("legs", [])
    if len(legs) == 1:
        return _build_single_leg_payload(account_id, legs[0], order)
    return _build_combo_payload(account_id, legs, order)


# ── Whatif preview ─────────────────────────────────────────────────────────────

def whatif_order(client: WebApiClient, account_id: str, order: dict) -> dict:
    """
    Submit order to IBKR whatif endpoint.
    Returns estimated margin, commission, and any warnings.
    Does NOT place the order.
    """
    payload = build_order_payload(account_id, order)
    try:
        result = client.post(f"/iserver/account/{account_id}/orders/whatif", json={"orders": [payload]})
        return {"ok": True, "raw": result, "payload_sent": payload}
    except WebApiError as e:
        return {"ok": False, "error": str(e), "payload_sent": payload}
    except GatewayUnreachable as e:
        return {"ok": False, "error": f"IBKR gateway unreachable: {e}", "payload_sent": payload}
    except Exception as e:
        return {"ok": False, "error": f"Unexpected error: {e}", "payload_sent": payload}


# ── Order placement ────────────────────────────────────────────────────────────

def place_order(client: WebApiClient, account_id: str, order: dict) -> dict:
    """
    Place the order with IBKR. Returns the response (includes orderId on success).
    May require a reply confirmation (IBKR sometimes returns a question list).
    """
    payload = build_order_payload(account_id, order)
    try:
        result = client.post(f"/iserver/account/{account_id}/orders", json={"orders": [payload]})

        # IBKR sometimes returns a list of confirmation questions
        if isinstance(result, list):
            # Check if these are confirmation prompts
            if result and isinstance(result[0], dict) and "id" in result[0] and "message" in result[0]:
                # Auto-confirm each question (we've already done human approval)
                confirmed_result = None
                for q in result:
                    reply_id = q.get("id")
                    if reply_id:
                        try:
                            confirmed_result = client.post(f"/iserver/reply/{reply_id}", json={"confirmed": True})
                        except Exception as e:
                            logger.warning("Reply confirmation failed for %s: %s", reply_id, e)
                return {"ok": True, "raw": confirmed_result or result}
            # Normal list response (order ids)
            return {"ok": True, "raw": result}

        if isinstance(result, dict) and result.get("order_id"):
            return {"ok": True, "raw": result, "ibkr_order_id": result["order_id"]}

        return {"ok": True, "raw": result}

    except WebApiError as e:
        return {"ok": False, "error": str(e)}
    except GatewayUnreachable as e:
        return {"ok": False, "error": f"IBKR gateway unreachable: {e}"}
    except Exception as e:
        return {"ok": False, "error": f"Unexpected error: {e}"}
