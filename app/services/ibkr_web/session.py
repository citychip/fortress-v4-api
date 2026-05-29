"""
CP Gateway / ibind session management.

With ibind OAuth 1.0a the IBKR Web API does NOT return an `established`
flag — authentication alone constitutes an established session.
session_summary() normalises this so the rest of the codebase is unaffected.
"""
from __future__ import annotations
import logging
import os
from typing import Any

from app.services.ibkr_web.client import WebApiClient, WebApiError, GatewayUnreachable

logger = logging.getLogger("fortress.ibkr_web.session")

_USE_IBIND = os.environ.get("IBIND_USE_OAUTH", "").lower() in ("1", "true", "yes")


def auth_status(client: WebApiClient) -> dict:
    """GET /iserver/auth/status. Returns the session state flags."""
    try:
        return client.get("/iserver/auth/status")
    except WebApiError as e:
        return {"connected": False, "authenticated": False, "established": False,
                "competing": False, "error": str(e)}


def reauthenticate(client: WebApiClient) -> dict:
    """Re-establish session. For ibind: resets the singleton so OAuth re-inits."""
    if _USE_IBIND:
        from app.services.ibkr_web.client import reset_ibind_client
        reset_ibind_client()
        return {"authenticated": True, "message": "ibind OAuth session reset — will re-init on next call"}
    return client.post("/iserver/reauthenticate")


def logout(client: WebApiClient) -> dict:
    """Terminate session cleanly."""
    try:
        return client.post("/logout")
    except (WebApiError, GatewayUnreachable):
        return {"status": "best_effort"}


def session_summary(client: WebApiClient) -> dict:
    """Composite session view used by the capability check.

    Returns:
        {
          "reachable": bool,
          "connected": bool,
          "authenticated": bool,
          "established": bool,   # always True for ibind when authenticated
          "competing": bool,
          "ssoExpires_ms": int | None,
          "error": str | None,
        }
    """
    out = {
        "reachable": False,
        "connected": False,
        "authenticated": False,
        "established": False,
        "competing": False,
        "ssoExpires_ms": None,
        "error": None,
    }
    try:
        st = auth_status(client)
        out["reachable"] = True
        out["connected"] = bool(st.get("connected"))
        out["authenticated"] = bool(st.get("authenticated"))
        out["competing"] = bool(st.get("competing"))

        # `established` is a CP Gateway concept; ibind OAuth sessions
        # are established whenever authenticated is true.
        if _USE_IBIND:
            out["established"] = out["authenticated"]
        else:
            out["established"] = bool(st.get("established"))

        if st.get("error"):
            out["error"] = st["error"]

    except GatewayUnreachable as e:
        out["error"] = f"gateway_unreachable: {e}"
    except WebApiError as e:
        out["reachable"] = True
        out["error"] = str(e)

    return out
