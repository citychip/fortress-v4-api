"""
CP Gateway session management.

ibeam (voyz/ibeam) handles the initial IBKR browser login and runs its
own internal tickle loop. We do NOT call /tickle ourselves — ibeam does it.
POST /tickle on ibeam returns HTML (Bad Request), not JSON, so we use
GET /iserver/auth/status for all session checks instead.

`reauthenticate()` recovers from authenticated=true, established=false.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from app.services.ibkr_web.client import WebApiClient, WebApiError, GatewayUnreachable

logger = logging.getLogger("fortress.ibkr_web.session")


def auth_status(client: WebApiClient) -> dict:
    """GET /iserver/auth/status. Returns the four-flag session state."""
    try:
        return client.get("/iserver/auth/status")
    except WebApiError as e:
        # /iserver/auth/status itself can return 401 if outer session expired
        return {"connected": False, "authenticated": False, "established": False,
                "competing": False, "error": str(e)}


def reauthenticate(client: WebApiClient) -> dict:
    """POST /iserver/reauthenticate. Recovers from authenticated && !established."""
    return client.post("/iserver/reauthenticate")


def logout(client: WebApiClient) -> dict:
    """POST /logout. Cleanly terminates the session."""
    try:
        return client.post("/logout")
    except (WebApiError, GatewayUnreachable):
        return {"status": "best_effort"}


def session_summary(client: WebApiClient) -> dict:
    """Composite view used by the capability check.

    Returns:
        {
          "reachable": bool,    # CP Gateway responded at all
          "connected": bool,
          "authenticated": bool,
          "established": bool,
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
        out["reachable"]      = True
        out["connected"]      = bool(st.get("connected"))
        out["authenticated"]  = bool(st.get("authenticated"))
        out["established"]    = bool(st.get("established"))
        out["competing"]      = bool(st.get("competing"))
        if st.get("error"):
            out["error"] = st["error"]
    except GatewayUnreachable as e:
        out["error"] = f"gateway_unreachable: {e}"
    except WebApiError as e:
        out["reachable"] = True
        out["error"] = str(e)
    return out
