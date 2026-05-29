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
_CACHE_TTL_S = 60


def get_capability(force_refresh: bool = False) -> dict:
    """Return the current capability snapshot. Cached for 60 s."""
    now = time.time()
    if not force_refresh:
        if _CAPABILITY_CACHE["data"] is not None and (now - _CAPABILITY_CACHE["ts"]) < _CACHE_TTL_S:
            return _CAPABILITY_CACHE["data"]
    out = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "tws_gateway": _check_tws(),
        "web_api": _check_web_api(),
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
    return {
        "configured": False,
        "reachable": False,
        "connected": False,
        "account": None,
        "known_issue": None,
        "error": "decommissioned: fortress-ib-gateway removed 2026-05-08",
    }


# ---------------------------------------------------------------------------
# Web API probe
# ---------------------------------------------------------------------------

def _check_web_api(settings: Optional[dict] = None) -> dict:
    """Probe the IBKR Web API (via ibind OAuth or CP Gateway)."""
    out = {
        "configured": False,
        "gateway_url": None,
        "session_status": None,
        "account": None,
        "opra_subscribed": None,
        "opra_test": None,
        "error": None,
    }

    # Lazy-load settings
    if settings is None:
        try:
            from app.services import state
            settings = state.get_dashboard_settings()
        except Exception:
            settings = {}

    # ── IBKR toggle check ───────────────────────────────────────────────────
    security = settings.get("security") or {}
    if not security.get("use_ibkr_web_api", True):
        out["error"] = "ibkr_disabled"
        out["configured"] = False
        return out

    web_cfg = (settings.get("ibkr_web_api") or {})
    gateway_url = (
        security.get("cp_gateway_url")
        or web_cfg.get("cp_gateway_url")
        or "https://localhost:5000"
    )
    out["gateway_url"] = gateway_url

    client = None
    try:
        client = WebApiClient(
            gateway_url=gateway_url,
            verify_ssl=bool(web_cfg.get("verify_ssl") or security.get("cp_gateway_verify_ssl", False)),
            request_timeout_s=int(web_cfg.get("request_timeout_s") or security.get("cp_gateway_timeout_s", 15)),
        )
        sess = web_session.session_summary(client)
        out["session_status"] = sess
        out["configured"] = True

        if not sess.get("established"):
            out["error"] = sess.get("error") or "session_not_established"
            return out

        # Established — verify account access
        try:
            accts = web_portfolio.list_accounts(client)
            if accts:
                out["account"] = accts[0].get("accountId") or accts[0].get("id")
        except WebApiError as e:
            out["error"] = f"portfolio_accounts_failed: {e}"
            return out

        # OPRA probe
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


def _probe_opra(client: WebApiClient, account_id: Optional[str]) -> dict:
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
# Resolution hint
# ---------------------------------------------------------------------------

def _hint(capability: dict) -> str:
    web = capability.get("web_api") or {}
    if web.get("opra_subscribed") and (web.get("session_status") or {}).get("established"):
        return "web_api"
    return "bs_yfinance"
