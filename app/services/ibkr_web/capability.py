"""
Capability check — assesses what backends are usable.

Returns a JSON-serializable summary used by:
  - /api/ibkr/capability route (UI displays)
  - state.resolve_greeks_backend() to pick the active backend

Cached for short windows so the dashboard's per-page-load polling doesn't
hammer the broker.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

from app.services.ibkr_web import FIELD_TAGS
from app.services.ibkr_web.client import WebApiClient, GatewayUnreachable, WebApiError
from app.services.ibkr_web import session as web_session
from app.services.ibkr_web import portfolio as web_portfolio
from app.services.ibkr_web import snapshot as web_snapshot

logger = logging.getLogger("fortress.ibkr_web.capability")

_CAPABILITY_CACHE: dict[str, Any] = {"data": None, "ts": 0.0}
_CACHE_TTL_S = 60  # short — capability changes when sessions die / wake


def get_capability(force_refresh: bool = False) -> dict:
    """Return the current capability snapshot. Cached for 60s."""
    now = time.time()
    if not force_refresh:
        if _CAPABILITY_CACHE["data"] is not None and (now - _CAPABILITY_CACHE["ts"]) < _CACHE_TTL_S:
            return _CAPABILITY_CACHE["data"]

    out = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "tws_gateway": _check_tws(),
        "web_api": _check_web_api(),
        "oauth": _check_oauth(),
    }
    out["resolution_hint"] = _hint(out)
    _CAPABILITY_CACHE["data"] = out
    _CAPABILITY_CACHE["ts"] = now
    return out


def invalidate():
    _CAPABILITY_CACHE["data"] = None


# ---------------------------------------------------------------------------
# TWS Gateway probe — DECOMMISSIONED (fortress-ib-gateway removed 2026-05-08)
# ---------------------------------------------------------------------------
def _check_tws() -> dict:
    """Legacy IB Gateway (gnzsnz/ib-gateway Docker) is decommissioned.
    Always returns not-configured so the capability resolver skips it.
    """
    return {
        "configured": False,
        "reachable": False,
        "connected": False,
        "account": None,
        "known_issue": None,
        "error": "decommissioned: fortress-ib-gateway removed 2026-05-08",
    }

# ---------------------------------------------------------------------------
# Web API probe (iBeam / CP Gateway)
# ---------------------------------------------------------------------------

def _check_web_api(settings: Optional[dict] = None) -> dict:
    """Probe the CP Gateway. Returns reachability, session, OPRA, account."""
    out = {
        "configured": False,
        "gateway_url": None,
        "session_status": None,
        "account": None,
        "opra_subscribed": None,
        "opra_test": None,
        "error": None,
    }
    if settings is None:
        try:
            from app.services import state
            settings = state.get_dashboard_settings()
        except Exception as e:
            settings = {}
    web_cfg = (settings.get("ibkr_web_api") or {})
    gateway_url = web_cfg.get("cp_gateway_url") or "https://localhost:5000"
    out["gateway_url"] = gateway_url

    client = None
    try:
        client = WebApiClient(
            gateway_url=gateway_url,
            verify_ssl=bool(web_cfg.get("verify_ssl", False)),
            request_timeout_s=int(web_cfg.get("request_timeout_s", 15)),
        )
        sess = web_session.session_summary(client)
        out["session_status"] = sess
        out["configured"] = True

        if not sess.get("established"):
            out["error"] = sess.get("error") or "session_not_established"
            return out

        try:
            accts = web_portfolio.list_accounts(client)
            if accts:
                out["account"] = accts[0].get("accountId") or accts[0].get("id")
        except WebApiError as e:
            out["error"] = f"portfolio_accounts_failed: {e}"
            return out

        opra = _probe_opra(client, out["account"])
        out["opra_subscribed"] = opra["opra_subscribed"]
        out["opra_test"] = opra
    except GatewayUnreachable as e:
        out["error"] = f"gateway_unreachable: {e}"
    except Exception as e:
        out["error"] = f"unexpected: {e}"
    finally:
        if client is not None:
            client.close()

    return out


# ---------------------------------------------------------------------------
# OAuth probe
# ---------------------------------------------------------------------------

def _check_oauth() -> dict:
    """Probe the IBKR OAuth 1.0a backend.

    Returns a status dict compatible with the web_api session_status shape
    so the frontend can render it with the same component.

    Keys expected by the UI:
      configured, connected, authenticated, established, error,
      consumer_key, keys_dir, checked_at
    """
    out = {
        "configured": False,
        "connected": False,
        "authenticated": False,
        "established": False,
        "consumer_key": None,
        "keys_dir": None,
        "error": None,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        from app.services.ibkr_web.oauth_client import (
            get_oauth_status, CONSUMER_KEY, _KEYS_DIR,
        )
        import os
        out["consumer_key"] = CONSUMER_KEY
        out["keys_dir"] = _KEYS_DIR

        # Check key files exist before attempting network call
        sig_key = os.path.join(_KEYS_DIR, "private_signature.pem")
        enc_key = os.path.join(_KEYS_DIR, "private_encryption.pem")
        missing = [p for p in (sig_key, enc_key) if not os.path.exists(p)]
        if missing:
            out["error"] = f"key_files_missing: {', '.join(missing)}"
            return out

        out["configured"] = True
        status = get_oauth_status()
        out.update({
            "connected":     status.get("connected", False),
            "authenticated": status.get("authenticated", False),
            "established":   status.get("established", False),
            "error":         status.get("error"),
        })
    except ImportError as e:
        out["error"] = f"oauth_client_import_error: {e}"
    except Exception as e:
        out["error"] = f"unexpected: {e}"

    return out


# ---------------------------------------------------------------------------
# OPRA probe (shared by web_api and oauth paths via _do_sync)
# ---------------------------------------------------------------------------

def _probe_opra(client: WebApiClient, account_id: Optional[str]) -> dict:
    """Snapshot a known option contract; if Greeks come back populated,
    OPRA is subscribed.
    """
    res = {
        "opra_subscribed": None,
        "method": None,
        "test_conid": None,
        "test_delta": None,
        "test_iv": None,
        "test_at": datetime.now(timezone.utc).isoformat(),
    }
    if not account_id:
        return res
    try:
        positions = web_portfolio.all_positions(client, account_id)
        option_legs = [
            p for p in positions
            if (p.get("assetClass") or p.get("secType") or "").upper() == "OPT"
        ]
        if not option_legs:
            res["method"] = "no_option_positions_found"
            return res

        conids = []
        for p in option_legs[:3]:
            c = p.get("conid")
            if isinstance(c, int):
                conids.append(c)
        if not conids:
            res["method"] = "no_conid_in_positions"
            return res

        rows = web_snapshot.snapshot(client, conids)
        delta_tag = FIELD_TAGS["delta"]
        iv_tag = FIELD_TAGS["iv_strike"]
        for r in rows:
            if r.get(delta_tag) not in (None, "", "N/A"):
                res["opra_subscribed"] = True
                res["test_conid"] = r.get("conid")
                res["test_delta"] = r.get(delta_tag)
                res["test_iv"] = r.get(iv_tag)
                res["method"] = "live_position_snapshot"
                return res

        res["opra_subscribed"] = False
        res["method"] = "snapshot_returned_no_greeks"
    except (GatewayUnreachable, WebApiError) as e:
        res["method"] = f"snapshot_failed: {e}"
    return res


# ---------------------------------------------------------------------------
# Resolution hint (informational)
# ---------------------------------------------------------------------------

def _hint(capability: dict) -> str:
    web = capability.get("web_api") or {}
    tws = capability.get("tws_gateway") or {}
    if web.get("opra_subscribed") and (web.get("session_status") or {}).get("established"):
        return "web_api"
    if tws.get("connected"):
        return "bs_yfinance"  # tws decommissioned
    return "bs_yfinance"
