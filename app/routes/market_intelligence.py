"""
/api/market-intelligence — Unified market regime + flow + portfolio synthesis.

Orchestrates:
  1. Live GEX walls (QuantData exposure/strike endpoint)
  2. Live Dark Pool floors (QuantData dark-pool/levels endpoint)
  3. Live Net Drift (QuantData net-drift endpoint)
  4. Portfolio context (positions, briefing)
  5. Regime synthesis (flip zone, gamma regime, DP support/resistance)
  6. Trade setup suggestions (Gamma Pin, Floor Bounce, Flip Zone Breakdown)
  7. Risk checks (concentration, pacing, delta limits)

Returns a single structured JSON that can be consumed by:
  - The Fortress Dashboard UI (Market Intelligence tab)
  - The fortress-mcp qd_market_intelligence tool
  - Any AI assistant using the Market Intelligence Skill
"""

from __future__ import annotations

import logging
import os
import time
import threading
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

try:
    from curl_cffi import requests as _cffi_requests
    _CFFI_AVAILABLE = True
except ImportError:
    import requests as _cffi_requests
    _CFFI_AVAILABLE = False
import requests
from fastapi import APIRouter

from ..services.config_store import get_all as get_config

logger = logging.getLogger("fortress.market_intelligence")
router = APIRouter()

# ─── QuantData credentials ────────────────────────────────────────────────────
# NOTE: credentials are read from config.json at request time (not at module import)
# so that refreshed tokens are picked up without a service restart.
QD_BASE_URL = "https://core-lb-prod.quantdata.us/api"
_QD_CONFIG_PATH = Path.home() / ".quantdata-mcp" / "config.json"



# ── US market holiday set (NYSE) — covers 2025-2027 ──────────────────────────
_US_MARKET_HOLIDAYS: set = {
    # 2025
    "2025-01-01", "2025-01-20", "2025-02-17", "2025-04-18",
    "2025-05-26", "2025-07-04", "2025-09-01", "2025-11-27", "2025-12-25",
    # 2026
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03",
    "2026-05-25", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
    # 2027
    "2027-01-01", "2027-01-18", "2027-02-15", "2027-04-26",
    "2027-05-31", "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24",
}


def _last_trading_day() -> str:
    from datetime import date, timedelta
    d = date.today()
    for _ in range(10):
        if d.weekday() < 5 and d.isoformat() not in _US_MARKET_HOLIDAYS:
            return d.isoformat()
        d -= timedelta(days=1)
    return d.isoformat()


def _get_qd_credentials() -> tuple[str, str, str]:
    """
    Read auth_token, cookie, and user_id from ~/.quantdata-mcp/config.json.
    Falls back to environment variables for backwards compatibility.
    Returns (auth_token_with_bearer_prefix, cookie, user_id).
    """
    import json, base64
    token  = os.environ.get("QUANTDATA_AUTH_TOKEN", "")
    cookie = ""
    user_id = os.environ.get("QUANTDATA_USER_ID", "")
    try:
        if _QD_CONFIG_PATH.exists():
            cfg = json.loads(_QD_CONFIG_PATH.read_text())
            token   = cfg.get("auth_token", token)
            cookie  = cfg.get("cookie", cookie)
            user_id = cfg.get("user_id", user_id)  # explicit key (written by qd_refresh_session.py)
    except Exception:
        pass
    # Ensure token has Bearer prefix
    if token and not token.startswith("Bearer "):
        token = f"Bearer {token}"
    # If user_id still not found, decode it from the JWT payload (userId claim)
    if not user_id and token:
        try:
            raw = token.removeprefix("Bearer ").strip()
            payload_b64 = raw.split(".")[1]
            # Add padding so base64 doesn't choke on short segments
            payload_b64 += "==" * (4 - len(payload_b64) % 4)
            payload = json.loads(base64.urlsafe_b64decode(payload_b64))
            user_id = payload.get("userId", "")
        except Exception:
            pass
    return token, cookie, user_id


def _get_qd_cookie() -> str:
    """Read the QuantData cookie from ~/.quantdata-mcp/config.json (updated by Settings page)."""
    _, cookie, _ = _get_qd_credentials()
    return cookie

# Known widget IDs per ticker — discovered via GET /api/pages.
# Widget UUIDs are stable identifiers on the QuantData platform.
# Last verified: 2026-05-19 (auto-discovery via /api/pages, 'component' field)
#
# Widget type legend:
#   gex       — OPTIONS_EXPOSURE_BY_STRIKE_CHART  (first one on the page)
#   dp        — DARK_POOL_LEVELS_TABLE
#   net_drift — OPTIONS_NET_DRIFT_CHART
#   page_id   — The QuantData page that owns these widgets (used as x-instance-id header)
#
# System pages (ticker-agnostic, filterable to any ticker):
#   DARK_POOL  page: 12f5f34d-6968-4eca-a687-d14566d2235f  dp widget: a2c2f3f9-0c34-486d-a25a-9b98b82b49c9
#   EXPOSURE   page: e07c6cba-335b-42dc-942b-0f90a5144b4a  gex widget: 465c0bd0-149a-4fb9-8274-9f429ccecb29
#   FLOW       page: a3500c30-51a5-42aa-af53-29a20d03b632  drift widget: de8c5cf5-7ba7-4343-98b9-399b76a96904
_WIDGET_IDS: dict[str, dict[str, str]] = {
    # ── Dedicated SPY page (e22a6d88) — all three widget types ─────────────────
    "SPY": {
        "gex":       "2e4d7ea4-ae92-4209-bca4-ccb2908ec9f6",  # OPTIONS_EXPOSURE_BY_STRIKE_CHART (SPY page)
        "dp":        "0001c185-460d-43e5-b9e9-b1ede7943f6b",  # DARK_POOL_LEVELS_TABLE (SPY page)
        "net_drift": "9fcb5310-970a-453e-a672-0f3b5ef22c78",  # OPTIONS_NET_DRIFT_CHART (SPY page)
        "page_id":   "e22a6d88-9d75-42b3-af9d-ee583008fdad",  # SPY custom page
    },
    # ── SPX Dashboard (672ab496) — GEX + net_drift (no DP widget on this page) ─
    "SPX": {
        "gex":       "444d17ce-e2f0-4d38-9acb-e51b09d6d4b6",  # OPTIONS_EXPOSURE_BY_STRIKE_CHART [SPX GEX]
        "net_drift": "46560851-54d3-4abe-b135-65c493eb381a",  # OPTIONS_NET_DRIFT_CHART [Net Drift]
        "page_id":   "672ab496-da3e-4538-bc68-3d0925b9b122",  # SPX Dashboard
    },
    # ── SPY Dashboard (9b3d47a2) — used for QQQ (GEX + DP + net_drift) ─────────
    # Note: this page is named "SPY Dashboard" but the widgets respond to the
    # global filter, so it works correctly for QQQ when the filter is set.
    "QQQ": {
        "gex":       "4b6d1f27-4131-44e1-a5f3-724d6f701d16",  # OPTIONS_EXPOSURE_BY_STRIKE_CHART [Exposure by Strike]
        "dp":        "0e3e3809-aa84-49cc-9f58-30cd60730b59",  # DARK_POOL_LEVELS_TABLE [Dark Pool Levels]
        "net_drift": "c36dd60c-2d58-4e53-83d9-43cdf2ff7e29",  # OPTIONS_NET_DRIFT_CHART [Net Drift]
        "page_id":   "9b3d47a2-92b0-49be-9a85-778c06300df0",  # SPY Dashboard
    },
    # ── Individual equities — dedicated pages ──────────────────────────────────
    "NVDA": {
        "gex":       "0dda93ba-d196-48bc-bacc-4b788f23369e",  # OPTIONS_EXPOSURE_BY_STRIKE_CHART [Exposure by Strike]
        "dp":        "7b2707f2-527b-484b-ab45-b6aa4df9dbc8",  # DARK_POOL_LEVELS_TABLE [Dark Pool Levels]
        "net_drift": "cf9f3e83-875c-4d84-b912-2770a2f94688",  # OPTIONS_NET_DRIFT_CHART [Net Drift]
        "page_id":   "52ca72cb-7456-4d64-8cc4-7c25265b0bb9",  # NVDA Dashboard
    },
    # ── MSFT dedicated page (2ef8b3c4) — DP only; GEX/drift fall back to system ─
    "MSFT": {
        "dp":        "1d0411cd-fa4b-4699-98f0-6a460828c975",  # DARK_POOL_LEVELS_TABLE [Dark Pool Levels]
        "page_id":   "2ef8b3c4-0910-42f9-b5e2-844377432e8c",  # Microsoft page
        # GEX and net_drift not present on this page — fetched via system pages below
        "gex":       "465c0bd0-149a-4fb9-8274-9f429ccecb29",  # fallback: EXPOSURE system page GEX
        "net_drift": "de8c5cf5-7ba7-4343-98b9-399b76a96904",  # fallback: FLOW system page drift
        "gex_page_id":   "e07c6cba-335b-42dc-942b-0f90a5144b4a",  # EXPOSURE system page
        "drift_page_id": "a3500c30-51a5-42aa-af53-29a20d03b632",  # FLOW_ANALYSIS system page
    },
    # ── All other tickers — system pages (ticker-agnostic, filterable) ──────────
    # TSLA, AMZN, AAPL, META, VST, MSTR, TSM, etc. use the system pages.
    # The global filter is set to the requested ticker before each fetch.
    "_SYSTEM": {
        "gex":       "465c0bd0-149a-4fb9-8274-9f429ccecb29",  # OPTIONS_EXPOSURE_BY_STRIKE_CHART (EXPOSURE system page)
        "dp":        "a2c2f3f9-0c34-486d-a25a-9b98b82b49c9",  # DARK_POOL_LEVELS_TABLE (DARK_POOL system page)
        "net_drift": "de8c5cf5-7ba7-4343-98b9-399b76a96904",  # OPTIONS_NET_DRIFT_CHART (FLOW_ANALYSIS system page)
        "page_id":   "e07c6cba-335b-42dc-942b-0f90a5144b4a",  # EXPOSURE system page (primary)
        # Note: dp and net_drift use different page_ids; handled in _fetch_* functions
        "dp_page_id":    "12f5f34d-6968-4eca-a687-d14566d2235f",  # DARK_POOL system page
        "drift_page_id": "a3500c30-51a5-42aa-af53-29a20d03b632",  # FLOW_ANALYSIS system page
    },
}

_QD_SESS: requests.Session | None = None
# Serializes concurrent system-page requests to prevent global-filter race condition
_QD_SYSTEM_LOCK = threading.Lock()

# Cache for the auto-discovered page registry (populated at first request)
_PAGE_REGISTRY_CACHE: dict | None = None
_PAGE_REGISTRY_LOCK  = threading.Lock()
_PAGE_REGISTRY_TTL   = 86_400  # 24 hours
_PAGE_REGISTRY_TS    = 0.0

# Components we care about when walking the QuantData page layout tree
_TARGET_COMPONENTS = {
    "OPTIONS_EXPOSURE_BY_STRIKE_CHART": "gex",
    "DARK_POOL_LEVELS_TABLE":           "dp",
    "OPTIONS_NET_DRIFT_CHART":          "net_drift",
}


def _walk_layout(node: Any, widgets: list) -> None:
    """Recursively walk a QuantData page layout tree and collect target widget IDs."""
    if isinstance(node, dict):
        comp = node.get("component")
        if comp in _TARGET_COMPONENTS:
            widgets.append({"key": _TARGET_COMPONENTS[comp], "id": node["id"]})
        for v in node.values():
            _walk_layout(v, widgets)
    elif isinstance(node, list):
        for item in node:
            _walk_layout(item, widgets)


def _load_page_registry(force: bool = False) -> dict[str, dict[str, str]]:
    """
    Fetch all QuantData pages and build a widget map keyed by page_id.

    Returns a dict of {page_id: {"gex": widget_id, "dp": widget_id, "net_drift": widget_id}}
    for every page that contains at least one target widget type.

    Results are cached for 24 hours (_PAGE_REGISTRY_TTL) to avoid hammering the API.
    The cache is stored in the module-level _PAGE_REGISTRY_CACHE variable.

    The correct field for widget type in the layout JSON is "component" (not "type").
    """
    global _PAGE_REGISTRY_CACHE, _PAGE_REGISTRY_TS

    now = time.monotonic()
    with _PAGE_REGISTRY_LOCK:
        if not force and _PAGE_REGISTRY_CACHE is not None and (now - _PAGE_REGISTRY_TS) < _PAGE_REGISTRY_TTL:
            return _PAGE_REGISTRY_CACHE

        token, cookie, _ = _get_qd_credentials()
        if not token:
            return _PAGE_REGISTRY_CACHE or {}

        headers = {
            "authorization": token,
            "x-qd-version":  "1",
            "origin":        "https://v3.quantdata.us",
            "referer":       "https://v3.quantdata.us/",
        }
        if cookie:
            headers["cookie"] = cookie

        try:
            if _CFFI_AVAILABLE:
                sess = _cffi_requests.Session(impersonate="chrome110")
                sess.headers.update(headers)
            else:
                sess = requests.Session()
                sess.headers.update(headers)

            resp = sess.get(f"{QD_BASE_URL}/pages", timeout=20)
            if resp.status_code != 200:
                logger.warning("_load_page_registry: /api/pages returned %d", resp.status_code)
                return _PAGE_REGISTRY_CACHE or {}

            pages = resp.json().get("response", {}).get("pages", [])
            registry: dict[str, dict[str, str]] = {}

            for page in pages:
                page_id = page.get("id", "")
                if not page_id:
                    continue
                widgets: list[dict] = []
                _walk_layout(page.get("layout", {}), widgets)
                if not widgets:
                    continue

                entry: dict[str, str] = {"page_id": page_id, "name": page.get("name", "")}
                # For each key type, take the first widget found on the page
                seen: set[str] = set()
                for w in widgets:
                    k = w["key"]
                    if k not in seen:
                        entry[k] = w["id"]
                        seen.add(k)

                registry[page_id] = entry

            _PAGE_REGISTRY_CACHE = registry
            _PAGE_REGISTRY_TS    = now
            logger.info("_load_page_registry: loaded %d pages with target widgets", len(registry))
            return registry

        except Exception as exc:
            logger.warning("_load_page_registry: failed to load pages: %s", exc)
            return _PAGE_REGISTRY_CACHE or {}


def _qd_session(page_id: str) -> requests.Session:
    """Create a QuantData session using curl_cffi Chrome impersonation to bypass Cloudflare."""
    token, cookie, _ = _get_qd_credentials()
    headers = {
        "accept":        "application/json",
        "authorization": token,
        "x-instance-id": page_id,
        "x-qd-version":  "1",
        "origin":        "https://v3.quantdata.us",
        "referer":       "https://v3.quantdata.us/",
        "content-type":  "application/json",
    }
    if cookie:
        headers["cookie"] = cookie
    if _CFFI_AVAILABLE:
        sess = _cffi_requests.Session(impersonate="chrome110")
        sess.headers.update(headers)
    else:
        sess = requests.Session()
        sess.headers.update(headers)
    return sess


def _qd_available() -> bool:
    token, _, _ = _get_qd_credentials()
    return bool(token)


def _set_global_filter(sess: requests.Session, ticker: str, session_date: str) -> None:
    """Set QuantData global session filter for the given ticker and date."""
    _, _, user_id = _get_qd_credentials()
    if not user_id:
        logger.debug("_set_global_filter: no user_id in config, skipping")
        return
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    try:
        sess.put(
            f"{QD_BASE_URL}/user/attributes",
            timeout=10,
            json={
                "id": user_id,
                "fontSizePercentage": 100,
                "globalFilter": {
                    "expirationDate": {"filterOperationType": "EQUALS", "value": session_date},
                    "sessionDate":    {"filterOperationType": "EQUALS", "value": session_date},
                    "ticker":         {"filterOperationType": "EQUALS", "value": [ticker]},
                },
                "globalTickerConfiguration": {"defaultTicker": ticker, "favoriteTickers": []},
                "globalToolConfiguration": {
                    "hideAxisTitles": False, "hideCrosshairs": False,
                    "hideDataZoomSliders": False, "hideLegends": False,
                    "hideStatusIndicators": False, "hideTimeSliders": False,
                    "hideTitles": False, "hideTooltips": False,
                },
                "notificationConfiguration": {"positionType": "BOTTOM_LEFT", "stacked": False},
                "timeZoneType": "AMERICA_NEW_YORK",
                "createdTime": now_ms, "lastUpdatedTime": now_ms,
            },
        )
    except Exception as e:
        logger.warning("Failed to set QD global filter: %s", e)


def _fetch_gex(sess: requests.Session, widget_id: str) -> dict | None:
    """Fetch GEX by strike data and return parsed walls."""
    try:
        r = sess.get(f"{QD_BASE_URL}/options/exposure/strike/{widget_id}", timeout=25)
        if r.status_code != 200:
            return None
        resp = r.json().get("response", {})
        exp_map = resp.get("expirationDateToStrikePriceInCentsToContractExposureMap", {})
        current_price_cents = resp.get("stockPriceInCents")

        # Aggregate net GEX across all expirations
        net_gex: dict[float, float] = defaultdict(float)
        today = date.today().isoformat()
        dte0_gex: dict[float, float] = {}

        for expiry, strike_data in exp_map.items():
            for strike_cents, sides in strike_data.items():
                price = int(strike_cents) / 100
                call_gex = sides.get("CALL", 0) or 0
                put_gex  = sides.get("PUT", 0)  or 0
                net      = call_gex + put_gex
                net_gex[price] += net
                if expiry == today:
                    dte0_gex[price] = dte0_gex.get(price, 0) + net

        if not net_gex:
            return None

        # Sort and find flip zone
        sorted_strikes = sorted(net_gex.items())
        flip_zone = None
        for i in range(len(sorted_strikes) - 1):
            p1, g1 = sorted_strikes[i]
            p2, g2 = sorted_strikes[i + 1]
            if g1 * g2 < 0:
                flip_zone = round((p1 + p2) / 2, 2)
                break

        call_walls = sorted(
            [(p, round(g / 1_000_000, 1)) for p, g in net_gex.items() if g > 0],
            key=lambda x: x[1], reverse=True
        )[:8]
        put_walls = sorted(
            [(p, round(g / 1_000_000, 1)) for p, g in net_gex.items() if g < 0],
            key=lambda x: x[1]
        )[:8]

        current_price = (current_price_cents / 100) if current_price_cents else None
        gamma_regime = None
        if current_price and flip_zone:
            gamma_regime = "positive" if current_price > flip_zone else "negative"

        return {
            "call_walls":    [{"strike": p, "gex_m": g} for p, g in call_walls],
            "put_walls":     [{"strike": p, "gex_m": g} for p, g in put_walls],
            "flip_zone":     flip_zone,
            "gamma_regime":  gamma_regime,
            "current_price": current_price,
            "dte0_call_walls": sorted(
                [{"strike": p, "gex_m": round(g / 1_000_000, 1)} for p, g in dte0_gex.items() if g > 0],
                key=lambda x: x["gex_m"], reverse=True
            )[:5],
            "dte0_put_walls": sorted(
                [{"strike": p, "gex_m": round(g / 1_000_000, 1)} for p, g in dte0_gex.items() if g < 0],
                key=lambda x: x["gex_m"]
            )[:5],
        }
    except Exception as e:
        logger.warning("GEX fetch error: %s", e)
        return None


def _fetch_dp(sess: requests.Session, widget_id: str) -> dict | None:
    """Fetch Dark Pool levels and return top floors by notional."""
    try:
        r = sess.get(f"{QD_BASE_URL}/equities/dark-pool/levels/{widget_id}", timeout=20)
        if r.status_code != 200:
            return None
        resp = r.json().get("response", {})
        dp_map = resp.get("priceInCentsToDarkPoolLevelDataSumModelMap", {})
        current_price_cents = resp.get("stockPriceInCents")

        if not dp_map:
            return {"floors": [], "current_price": (current_price_cents / 100) if current_price_cents else None}

        floors = sorted(
            [
                {
                    "price":       int(k) / 100,
                    "notional_m":  round(v.get("notionalValueInCentsSum", 0) / 100_000_000, 1),
                    "contracts":   v.get("sizeSum", 0),
                    "trades":      v.get("tradeCountSum", 0),
                }
                for k, v in dp_map.items()
            ],
            key=lambda x: x["notional_m"],
            reverse=True,
        )[:15]

        return {
            "floors":        floors,
            "current_price": (current_price_cents / 100) if current_price_cents else None,
        }
    except Exception as e:
        logger.warning("DP fetch error: %s", e)
        return None


def _fetch_net_drift(sess: requests.Session, widget_id: str) -> dict | None:
    """Fetch Net Drift and return session summary."""
    try:
        r = sess.get(f"{QD_BASE_URL}/options/net-drift/{widget_id}", timeout=20)
        if r.status_code != 200:
            return None
        resp = r.json().get("response", {})
        nd = resp.get("netDrift", [])
        if not nd:
            return None

        first = nd[0]
        last  = nd[-1]
        ts_open  = datetime.fromtimestamp(first[0] / 1000, tz=timezone.utc).strftime("%H:%M ET")
        ts_close = datetime.fromtimestamp(last[0]  / 1000, tz=timezone.utc).strftime("%H:%M ET")

        call_drift = last[1] / 100 if len(last) > 1 else 0
        put_drift  = last[2] / 100 if len(last) > 2 else 0
        net        = call_drift + put_drift
        price      = last[7] / 100 if len(last) > 7 else None

        # Cumulative net drift over session (sum of all net values)
        cumulative = sum((row[1] / 100 if len(row) > 1 else 0) + (row[2] / 100 if len(row) > 2 else 0) for row in nd)

        return {
            "session_open":    ts_open,
            "session_close":   ts_close,
            "data_points":     len(nd),
            "call_drift_last": round(call_drift, 0),
            "put_drift_last":  round(put_drift, 0),
            "net_drift_last":  round(net, 0),
            "cumulative_drift": round(cumulative, 0),
            "bias":            "bullish" if cumulative > 0 else ("bearish" if cumulative < 0 else "neutral"),
            "current_price":   price,
        }
    except Exception as e:
        logger.warning("Net Drift fetch error: %s", e)
        return None


def _synthesize_regime(gex: dict | None, dp: dict | None, drift: dict | None, macro_regime: str) -> dict:
    """Synthesize all signals into a unified market regime assessment."""
    signals = []
    score   = 0  # positive = bullish, negative = bearish

    current_price = (
        (gex or {}).get("current_price")
        or (dp or {}).get("current_price")
        or (drift or {}).get("current_price")
    )

    # GEX regime signal
    gamma_regime = (gex or {}).get("gamma_regime")
    flip_zone    = (gex or {}).get("flip_zone")
    if gamma_regime == "positive":
        signals.append({"source": "GEX", "signal": "positive_gamma", "weight": +2,
                        "note": f"Price ${current_price} is ABOVE flip zone ${flip_zone} — stable, mean-reverting regime"})
        score += 2
    elif gamma_regime == "negative":
        signals.append({"source": "GEX", "signal": "negative_gamma", "weight": -2,
                        "note": f"Price ${current_price} is BELOW flip zone ${flip_zone} — volatile, trend-following regime"})
        score -= 2

    # Proximity to flip zone (within 0.5%)
    if current_price and flip_zone:
        pct_from_flip = abs(current_price - flip_zone) / flip_zone * 100
        if pct_from_flip < 0.5:
            signals.append({"source": "GEX", "signal": "at_flip_zone", "weight": 0,
                            "note": f"Price is within {pct_from_flip:.2f}% of flip zone — regime change imminent"})

    # DP floor signal
    if dp and dp.get("floors") and current_price:
        nearest_floor = min(dp["floors"], key=lambda f: abs(f["price"] - current_price))
        dist = current_price - nearest_floor["price"]
        if 0 < dist < 5:
            signals.append({"source": "DarkPool", "signal": "near_dp_floor",
                            "weight": +1,
                            "note": f"Price is ${dist:.2f} above DP floor at ${nearest_floor['price']} (${nearest_floor['notional_m']}M notional) — strong support"})
            score += 1
        elif -5 < dist <= 0:
            signals.append({"source": "DarkPool", "signal": "below_dp_floor",
                            "weight": -1,
                            "note": f"Price has broken below DP floor at ${nearest_floor['price']} — bearish"})
            score -= 1

    # Net Drift signal
    if drift:
        bias = drift.get("bias", "neutral")
        cum  = drift.get("cumulative_drift", 0)
        if bias == "bullish":
            signals.append({"source": "NetDrift", "signal": "bullish_flow",
                            "weight": +1, "note": f"Cumulative net drift ${cum:,.0f} — smart money is net long"})
            score += 1
        elif bias == "bearish":
            signals.append({"source": "NetDrift", "signal": "bearish_flow",
                            "weight": -1, "note": f"Cumulative net drift ${cum:,.0f} — smart money is net short"})
            score -= 1

    # Macro regime signal
    if macro_regime == "bullish":
        score += 1
    elif macro_regime == "bearish":
        score -= 1

    # Divergence check: price above flip but bearish drift
    if gamma_regime == "positive" and (drift or {}).get("bias") == "bearish":
        signals.append({"source": "Divergence", "signal": "gex_drift_divergence", "weight": -1,
                        "note": "Positive gamma but bearish net drift — rally is unsupported, likely to fail"})
        score -= 1

    overall = "strongly_bullish" if score >= 3 else \
              "bullish"          if score == 2 else \
              "mildly_bullish"   if score == 1 else \
              "neutral"          if score == 0 else \
              "mildly_bearish"   if score == -1 else \
              "bearish"          if score == -2 else \
              "strongly_bearish"

    # Extract top GEX walls and DP floor/ceiling for direct display in UI
    gex_call_wall = None
    gex_put_wall  = None
    dp_floor      = None
    dp_ceiling    = None
    try:
        call_walls = (gex or {}).get("call_walls") or []
        if call_walls:
            gex_call_wall = call_walls[0].get("strike")
    except Exception:
        pass
    try:
        put_walls = (gex or {}).get("put_walls") or []
        if put_walls:
            gex_put_wall = put_walls[0].get("strike")
    except Exception:
        pass
    try:
        floors = (dp or {}).get("floors") or []
        if floors:
            dp_floor = floors[0].get("price")
    except Exception:
        pass
    try:
        ceilings = (dp or {}).get("ceilings") or []
        if ceilings:
            dp_ceiling = ceilings[0].get("price")
    except Exception:
        pass

    return {
        "overall":       overall,
        "score":         score,
        "signals":       signals,
        "current_price": current_price,
        "gamma_regime":  gamma_regime,
        "flip_zone":     flip_zone,
        "gex_call_wall": gex_call_wall,
        "gex_put_wall":  gex_put_wall,
        "dp_floor":      dp_floor,
        "dp_ceiling":    dp_ceiling,
    }


def _generate_setups(gex: dict | None, dp: dict | None, regime: dict) -> list[dict]:
    """Generate concrete trade setup suggestions based on the regime and levels."""
    setups = []
    current_price = regime.get("current_price")
    gamma_regime  = regime.get("gamma_regime")
    flip_zone     = regime.get("flip_zone")

    if not current_price:
        return setups

    # Setup A: Gamma Pin (Iron Condor / Iron Butterfly)
    if gex and gamma_regime == "positive":
        call_walls = gex.get("call_walls", [])
        put_walls  = gex.get("put_walls", [])
        if call_walls and put_walls:
            top_call = call_walls[0]["strike"]
            top_put  = put_walls[0]["strike"]
            range_width = top_call - top_put
            if range_width < current_price * 0.03:  # range < 3% of price
                setups.append({
                    "name":        "Gamma Pin — Iron Condor",
                    "type":        "neutral",
                    "confidence":  "high" if range_width < current_price * 0.015 else "medium",
                    "description": f"Price is pinned between Put Wall ${top_put} and Call Wall ${top_call} (range: ${range_width:.0f}). Sell Iron Condor with short strikes at these walls.",
                    "entry":       f"Sell ${top_call} Call / Buy ${top_call + 5} Call | Sell ${top_put} Put / Buy ${top_put - 5} Put",
                    "target":      "50% of max credit",
                    "stop":        "2x credit received",
                    "fortress_check": ["delta_short ≤ 0.16", "min_credit ≥ $1.00", "DTE 14–45"],
                })

    # Setup B: Floor Bounce (Put Credit Spread / Long Call)
    if dp and dp.get("floors") and current_price:
        nearest_floor = min(dp["floors"], key=lambda f: abs(f["price"] - current_price))
        dist = current_price - nearest_floor["price"]
        if 0 < dist < 8 and nearest_floor["notional_m"] > 500:
            setups.append({
                "name":        "Floor Bounce — Put Credit Spread",
                "type":        "bullish",
                "confidence":  "high" if nearest_floor["notional_m"] > 1000 else "medium",
                "description": f"Price is ${dist:.2f} above a massive DP floor at ${nearest_floor['price']} (${nearest_floor['notional_m']}M notional). Institutions will defend this level.",
                "entry":       f"Sell ${nearest_floor['price'] - 1:.0f} Put / Buy ${nearest_floor['price'] - 6:.0f} Put (PCS below the floor)",
                "target":      "50% of max credit",
                "stop":        "2x credit received or close below DP floor",
                "fortress_check": ["min_credit ≥ $0.50", "DTE 14–45", "check concentration"],
            })

    # Setup C: Flip Zone Breakdown (Bear Put Spread)
    if flip_zone and gamma_regime == "negative":
        next_dp_floor = None
        if dp and dp.get("floors"):
            below_floors = [f for f in dp["floors"] if f["price"] < current_price]
            if below_floors:
                next_dp_floor = max(below_floors, key=lambda f: f["price"])
        target = next_dp_floor["price"] if next_dp_floor else current_price * 0.97
        setups.append({
            "name":        "Flip Zone Breakdown — Bear Put Spread",
            "type":        "bearish",
            "confidence":  "high",
            "description": f"Price has broken below the GEX Flip Zone (${flip_zone}). Dealers are now net short gamma and will sell into weakness, amplifying the move.",
            "entry":       f"Buy ${current_price:.0f} Put / Sell ${target:.0f} Put (BPS targeting next DP floor at ${target:.2f})",
            "target":      f"Next DP floor at ${target:.2f}",
            "stop":        f"Close back above flip zone ${flip_zone}",
            "fortress_check": ["check pacing", "check concentration", "DTE 7–21 for short-term breakdown"],
        })

    return setups


def _risk_checks(positions: list[dict], settings: dict, regime: dict) -> list[dict]:
    """Run portfolio risk checks relevant to the current regime."""
    checks = []
    strategy_cfg = settings.get("strategy", {})
    alerts_cfg   = settings.get("alerts", {})

    # Concentration check
    tickers = {}
    for pos in positions:
        t = pos.get("ticker", "")
        tickers[t] = tickers.get(t, 0) + abs(pos.get("net_liq_pct", 0))
    for ticker, pct in sorted(tickers.items(), key=lambda x: x[1], reverse=True):
        max_conc = strategy_cfg.get("max_concentration_pct", 10)
        if pct > max_conc:
            checks.append({
                "type":    "concentration",
                "ticker":  ticker,
                "value":   round(pct, 1),
                "limit":   max_conc,
                "severity": "critical" if pct > max_conc * 1.5 else "warning",
                "action":  f"Do not add new {ticker} positions. Consider reducing exposure.",
            })

    # Pacing check — count positions opened this week
    # (simplified: count positions with recent avg_cost dates)
    pacing_max = strategy_cfg.get("entries_per_week_max", 5)

    # Delta check
    for pos in positions:
        delta = abs(pos.get("current_delta", 0) or 0)
        act_threshold = alerts_cfg.get("delta_act_threshold", 0.8)
        watch_threshold = alerts_cfg.get("delta_watch_threshold", 0.6)
        if delta >= act_threshold:
            checks.append({
                "type":    "delta",
                "ticker":  pos.get("ticker"),
                "strike":  pos.get("strike"),
                "expiry":  pos.get("expiry"),
                "value":   delta,
                "limit":   act_threshold,
                "severity": "critical",
                "action":  "Roll or close immediately — delta exceeds action threshold.",
            })
        elif delta >= watch_threshold:
            checks.append({
                "type":    "delta",
                "ticker":  pos.get("ticker"),
                "strike":  pos.get("strike"),
                "expiry":  pos.get("expiry"),
                "value":   delta,
                "limit":   watch_threshold,
                "severity": "warning",
                "action":  "Monitor closely — delta approaching action threshold.",
            })

    # Regime-specific check
    if regime.get("gamma_regime") == "negative":
        checks.append({
            "type":    "regime",
            "severity": "warning",
            "action":  "Market is in NEGATIVE gamma regime. Reduce long delta exposure. Avoid new bullish entries until price reclaims flip zone.",
        })

    return checks


@router.get("/market-intelligence")
def get_market_intelligence(ticker: str = "SPY", session_date: str | None = None):
    """
    Unified market regime + flow + portfolio intelligence endpoint.

    Fetches live GEX walls, Dark Pool floors, Net Drift from QuantData,
    combines with portfolio context, and returns a structured analysis
    with regime assessment, trade setups, and risk checks.

    Parameters:
        ticker: Ticker symbol to analyse (default: SPY)
        session_date: Trading date in YYYY-MM-DD format (default: today)

    Returns:
        {
          "as_of": ISO timestamp,
          "ticker": str,
          "session_date": str,
          "current_price": float | null,
          "regime": {
            "overall": str,        # strongly_bullish | bullish | mildly_bullish | neutral | mildly_bearish | bearish | strongly_bearish
            "score": int,          # -4 to +4
            "gamma_regime": str,   # positive | negative | null
            "flip_zone": float,    # GEX zero-crossing price
            "signals": [...]       # list of contributing signals
          },
          "gex": {
            "call_walls": [{"strike", "gex_m"}, ...],
            "put_walls":  [{"strike", "gex_m"}, ...],
            "flip_zone": float,
            "dte0_call_walls": [...],
            "dte0_put_walls":  [...],
          },
          "dark_pool": {
            "floors": [{"price", "notional_m", "contracts", "trades"}, ...],
          },
          "net_drift": {
            "bias": bullish|bearish|neutral,
            "cumulative_drift": float,
            "net_drift_last": float,
            "session_open": str,
            "session_close": str,
          },
          "trade_setups": [
            {"name", "type", "confidence", "description", "entry", "target", "stop", "fortress_check"}
          ],
          "risk_checks": [
            {"type", "severity", "ticker", "value", "limit", "action"}
          ],
          "portfolio_context": {
            "macro_regime": str,
            "concentration": {...},
            "pacing": {...},
            "net_liq": float,
          },
          "quantdata_available": bool,
          "source": str,
        }
    """
    from ..routes.positions import get_positions
    from ..routes.briefing import get_briefing

    if not session_date:
        session_date = _last_trading_day()

    ticker = ticker.upper()
    as_of  = datetime.now(timezone.utc).isoformat()

    # ── Fetch portfolio context ───────────────────────────────────────────────
    try:
        briefing_data = get_briefing()
    except Exception:
        briefing_data = {}

    try:
        positions_data = get_positions(aggregated=False)
        positions = positions_data if isinstance(positions_data, list) else positions_data.get("positions", [])
    except Exception:
        positions = []

    macro_regime = (briefing_data.get("macro_regime") or {}).get("regime", "neutral")
    concentration = briefing_data.get("concentration", {})
    pacing        = briefing_data.get("pacing", {})
    account       = briefing_data.get("account", {})
    net_liq       = account.get("net_liq") if account else None

    settings = get_config()  # returns full config dict

    # ── Fetch live QuantData data ─────────────────────────────────────────────
    gex_data   = None
    dp_data    = None
    drift_data = None
    qd_source  = "unavailable"

    # Re-read credentials at request time so refreshed tokens are picked up immediately
    _qd_token, _qd_cookie, _qd_uid = _get_qd_credentials()
    logger.debug("QD credentials: token_len=%d cookie_len=%d", len(_qd_token), len(_qd_cookie))

    if _qd_available():
        # Use ticker-specific widgets if available; fall back to system pages for any ticker
        widgets = _WIDGET_IDS.get(ticker)
        is_system_page = widgets is None
        if is_system_page:
            widgets = _WIDGET_IDS["_SYSTEM"]
            logger.info("No dedicated page for %s — using system pages (serialized)", ticker)

        page_id = widgets.get("page_id", "")

        # Determine whether this ticker uses the system-page global filter for any widget.
        # MSFT has a dedicated DP widget but falls back to system pages for GEX and drift,
        # so it still needs the global filter set (and the system lock held for those calls).
        import contextlib
        has_system_fallback = is_system_page or bool(
            widgets.get("gex_page_id") or widgets.get("drift_page_id")
        )
        lock_ctx = _QD_SYSTEM_LOCK if has_system_fallback else contextlib.nullcontext()
        with lock_ctx:
            sess = _qd_session(page_id)

            # Set global filter to the requested ticker on all relevant pages
            _set_global_filter(sess, ticker, session_date)

            # GEX — may use a different page_id (MSFT uses system EXPOSURE page for GEX)
            if widgets.get("gex"):
                gex_page = widgets.get("gex_page_id", page_id)
                if gex_page != page_id:
                    gex_sess = _qd_session(gex_page)
                    _set_global_filter(gex_sess, ticker, session_date)
                    gex_data = _fetch_gex(gex_sess, widgets["gex"])
                else:
                    gex_data = _fetch_gex(sess, widgets["gex"])

            # DP — may use a different page_id (system pages only)
            if widgets.get("dp"):
                dp_page = widgets.get("dp_page_id", page_id)
                if dp_page != page_id:
                    dp_sess = _qd_session(dp_page)
                    _set_global_filter(dp_sess, ticker, session_date)
                    dp_data = _fetch_dp(dp_sess, widgets["dp"])
                else:
                    dp_data = _fetch_dp(sess, widgets["dp"])

            # Net Drift — may use a different page_id (system pages only)
            if widgets.get("net_drift"):
                drift_page = widgets.get("drift_page_id", page_id)
                if drift_page != page_id:
                    drift_sess = _qd_session(drift_page)
                    _set_global_filter(drift_sess, ticker, session_date)
                    drift_data = _fetch_net_drift(drift_sess, widgets["net_drift"])
                else:
                    drift_data = _fetch_net_drift(sess, widgets["net_drift"])

        qd_source = "quantdata_live_api"
    else:
        # Fall back to parsed report file data
        try:
            from ..routes.chart import _get_levels
            levels = _get_levels(ticker)
            dp_floors_raw = levels.get("dp_floors", [])
            if dp_floors_raw:
                dp_data = {
                    "floors": [{"price": f, "notional_m": None, "contracts": None, "trades": None}
                               for f in dp_floors_raw],
                    "current_price": None,
                }
            qd_source = "report_file_fallback"
        except Exception:
            pass

    # ── Synthesize regime ─────────────────────────────────────────────────────
    regime = _synthesize_regime(gex_data, dp_data, drift_data, macro_regime)

    # ── Generate trade setups ─────────────────────────────────────────────────
    trade_setups = _generate_setups(gex_data, dp_data, regime)

    # ── Risk checks ───────────────────────────────────────────────────────────
    risk_checks = _risk_checks(positions, settings, regime)

    return {
        "as_of":         as_of,
        "ticker":        ticker,
        "session_date":  session_date,
        "current_price": regime.get("current_price"),
        "regime":        regime,
        "gex":           gex_data,
        "dark_pool":     dp_data,
        "net_drift":     drift_data,
        "trade_setups":  trade_setups,
        "risk_checks":   risk_checks,
        "portfolio_context": {
            "macro_regime":  macro_regime,
            "concentration": concentration,
            "pacing":        pacing,
            "net_liq":       net_liq,
        },
        "quantdata_available": bool(_qd_token),
        "source":        qd_source,
    }
