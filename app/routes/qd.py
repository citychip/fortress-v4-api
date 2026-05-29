"""
qd.py — QuantData proxy routes for Fortress V4 API
Reads tool IDs dynamically from the QD config file (no hardcoding).
Re-discovers IDs automatically when config changes (TTL: 60s).

All routes require Bearer auth (same middleware as the rest of the API).
Compatible with Python 3.8+.
"""

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)
router = APIRouter(tags=["quantdata"])

# ── Config paths ──────────────────────────────────────────────────────────────
_CONFIG_PATHS = [
    Path("/home/ubuntu/.quantdata-mcp/config.json"),
    Path("/root/.quantdata-mcp/config.json"),
]
_QD_BASE = "https://core-lb-prod.quantdata.us/api"

# ── Tool name → QD slug mapping ───────────────────────────────────────────────
_TOOL_NAMES: Dict[str, List[str]] = {
    "iv_rank":    ["iv-rank", "INTRADAY_IV_RANK", "IV_RANK"],
    "net_drift":  ["net-drift", "OPTIONS_NET_DRIFT_TABLE", "NET_DRIFT"],
    "max_pain":   ["max-pain", "OPTIONS_MAX_PAIN", "MAX_PAIN"],
    "order_flow": ["order-flow", "OPTIONS_ORDER_FLOW_CONSOLIDATED_TABLE",
                   "OPTIONS_ORDER_FLOW_CONSOLIDATED", "OPTIONS_ORDER_FLOW"],
    "dark_pool":  ["dark-pool-levels", "DARK_POOL_LEVELS_TABLE", "DARK_POOL_LEVELS"],
    "oi_change":  ["oi-change", "OPTIONS_OPEN_INTEREST_CHANGE_TABLE",
                   "OPTIONS_OPEN_INTEREST_CHANGE"],
}

# ── Config cache (TTL = 60s) ──────────────────────────────────────────────────
_cache: Dict[str, Any] = {}
_cache_at: float = 0.0
_CACHE_TTL = 60.0


def _load_config() -> Dict[str, Any]:
    """Load and merge QD config from all known paths. Ubuntu overrides root."""
    global _cache, _cache_at
    now = time.monotonic()
    if _cache and (now - _cache_at) < _CACHE_TTL:
        return _cache

    merged: Dict[str, Any] = {}
    for path in reversed(_CONFIG_PATHS):   # root first, ubuntu overrides
        if path.exists():
            try:
                data = json.loads(path.read_text())
                merged.update(data)
            except Exception as exc:
                logger.warning("Could not read QD config %s: %s", path, exc)

    _cache = merged
    _cache_at = now
    return merged


def _get_auth() -> tuple:
    """Return (auth_token, instance_id) from config, raise 503 if missing."""
    cfg = _load_config()
    token = cfg.get("authToken") or cfg.get("auth_token") or cfg.get("token", "")
    inst  = cfg.get("instanceId") or cfg.get("instance_id") or cfg.get("userId", "")
    if not token or not inst:
        raise HTTPException(503, detail="QuantData credentials not configured — re-login via Settings.")
    return token, inst


def _get_tool_id(key: str) -> str:
    """Look up tool ID for key. Handles both dict and list tool formats."""
    cfg = _load_config()
    tools = cfg.get("tools", {})

    # New format: tools is a dict {"iv_rank": "uuid", "dark_pool_levels": "uuid", ...}
    if isinstance(tools, dict):
        # Direct match
        if key in tools:
            return tools[key]
        # Alias map (route key -> config key)
        aliases = {"dark_pool": "dark_pool_levels", "dark_pool": "dark_pool_levels"}
        if key in aliases and aliases[key] in tools:
            return tools[aliases[key]]
        # Fuzzy: any config key that starts with the route key
        for k, v in tools.items():
            if k.startswith(key) or key.startswith(k.rstrip("s")):
                return v

    # Legacy list format: [{"toolName": ..., "toolId": ...}, ...]
    elif isinstance(tools, list):
        name_to_id: Dict[str, str] = {}
        for t in tools:
            name = (t.get("toolName") or t.get("name") or t.get("tool_name") or "").upper()
            tid  = (t.get("toolId")   or t.get("id")   or t.get("tool_id")   or "")
            if name and tid:
                name_to_id[name] = tid
        for name in _TOOL_NAMES.get(key, []):
            if name in name_to_id:
                return name_to_id[name]

    # Legacy shorthand keys
    shorthand = {
        "iv_rank":    cfg.get("iv_rank_tool_id"),
        "net_drift":  cfg.get("net_drift_tool_id"),
        "max_pain":   cfg.get("max_pain_tool_id"),
        "order_flow": cfg.get("order_flow_tool_id"),
        "dark_pool":  cfg.get("dark_pool_tool_id"),
        "oi_change":  cfg.get("oi_change_tool_id"),
    }
    if shorthand.get(key):
        return shorthand[key]

    raise HTTPException(
        status_code=404,
        detail=(
            "QuantData tool endpoint not found for '{}'. "
            "Re-login via Settings → QuantData Auto-Login to refresh tool IDs.".format(key)
        ),
    )


def _today() -> str:
    from datetime import date
    return date.today().isoformat()


def _qd_get(tool_key: str, ticker: str, session_date: Optional[str], extra_params: Optional[Dict] = None) -> Any:
    """Call QD API for a given tool key and ticker."""
    token, inst = _get_auth()
    tool_id = _get_tool_id(tool_key)
    slug = _TOOL_NAMES[tool_key][0]

    params: Dict[str, Any] = {"sessionDate": session_date or _today(), "ticker": ticker.upper()}
    if extra_params:
        params.update(extra_params)

    headers = {
        "accept": "application/json",
        "authorization": token,
        "x-qd-version": "1",
        "origin": "https://v3.quantdata.us",
    }

    url = "{}/options/{}/{}".format(_QD_BASE, slug, tool_id)
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
    except requests.exceptions.RequestException as exc:
        raise HTTPException(status_code=502, detail="QuantData request failed: {}".format(exc))

    if resp.status_code == 401:
        raise HTTPException(status_code=401, detail="QuantData auth expired — re-login via Settings → QuantData Auto-Login.")
    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail="QuantData tool endpoint not found.")
    if resp.status_code == 429:
        raise HTTPException(status_code=429, detail="QuantData rate limit — try again in a few seconds.")
    if resp.status_code == 503:
        raise HTTPException(status_code=503, detail="QuantData service unavailable.")
    if not resp.ok:
        raise HTTPException(status_code=resp.status_code, detail="QuantData error {}".format(resp.status_code))
    if not resp.content:
        raise HTTPException(status_code=204, detail="QuantData returned empty response.")

    try:
        return resp.json()
    except Exception:
        raise HTTPException(status_code=502, detail="QuantData returned non-JSON response.")


def _extract(data: Any, keys: List[str], default: Any = None) -> Any:
    """Extract first matching key from a dict or nested result."""
    if isinstance(data, dict):
        for k in keys:
            if k in data:
                return data[k]
        for wrapper in ("result", "data", "payload"):
            if wrapper in data and isinstance(data[wrapper], dict):
                for k in keys:
                    if k in data[wrapper]:
                        return data[wrapper][k]
    return default


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/qd/iv-rank/{ticker}")
def qd_iv_rank(ticker: str, session_date: Optional[str] = Query(default=None)):
    data = _qd_get("iv_rank", ticker, session_date)
    return {
        "ticker":        ticker.upper(),
        "session_date":  session_date or _today(),
        "iv_rank":       _extract(data, ["ivRank", "iv_rank", "IVRank"]),
        "iv_percentile": _extract(data, ["ivPercentile", "iv_percentile"]),
        "current_iv":    _extract(data, ["currentIV", "current_iv", "iv"]),
        "iv_52w_high":   _extract(data, ["iv52wHigh", "iv_52w_high"]),
        "iv_52w_low":    _extract(data, ["iv52wLow", "iv_52w_low"]),
        "call_iv":       _extract(data, ["callIV", "call_iv"]),
        "put_iv":        _extract(data, ["putIV", "put_iv"]),
    }


@router.get("/qd/net-drift/{ticker}")
def qd_net_drift(ticker: str, session_date: Optional[str] = Query(default=None)):
    data = _qd_get("net_drift", ticker, session_date)
    call_p = _extract(data, ["callPremium", "call_premium"], 0)
    put_p  = _extract(data, ["putPremium", "put_premium"], 0)
    net    = _extract(data, ["netDrift", "net_drift"], (call_p or 0) - (put_p or 0))
    points = _extract(data, ["dataPoints", "data_points", "count"], 0)
    bias   = "bullish" if (net or 0) > 0 else ("bearish" if (net or 0) < 0 else "neutral")
    return {
        "ticker":       ticker.upper(),
        "session_date": session_date or _today(),
        "call_premium": call_p,
        "put_premium":  put_p,
        "net_drift":    net,
        "bias":         bias,
        "data_points":  points,
    }


@router.get("/qd/max-pain/{ticker}")
def qd_max_pain(ticker: str, session_date: Optional[str] = Query(default=None)):
    data = _qd_get("max_pain", ticker, session_date)
    return {
        "ticker":          ticker.upper(),
        "session_date":    session_date or _today(),
        "max_pain_strike": _extract(data, ["maxPain", "max_pain", "maxPainStrike"]),
        "current_price":   _extract(data, ["currentPrice", "current_price", "price"]),
        "distance_pct":    _extract(data, ["distancePct", "distance_pct"]),
        "expirations":     _extract(data, ["expirations", "expiries"], []),
        "raw":             data,
    }


@router.get("/qd/order-flow/{ticker}")
def qd_order_flow(
    ticker: str,
    session_date: Optional[str] = Query(default=None),
    min_premium: Optional[float] = Query(default=None),
    side: Optional[str] = Query(default=None),
    limit: int = Query(default=50),
):
    data = _qd_get("order_flow", ticker, session_date)
    flow = _extract(data, ["flow", "orders", "data", "rows"], [])
    if side and isinstance(flow, list):
        flow = [r for r in flow if str(r.get("side", "")).upper() == side.upper()]
    if min_premium is not None and isinstance(flow, list):
        flow = [r for r in flow if (r.get("premium") or 0) >= min_premium]
    if isinstance(flow, list):
        flow = flow[:limit]
    return {
        "ticker":       ticker.upper(),
        "session_date": session_date or _today(),
        "flow":         flow,
    }


@router.get("/qd/dark-pool/{ticker}")
def qd_dark_pool(ticker: str, session_date: Optional[str] = Query(default=None)):
    data = _qd_get("dark_pool", ticker, session_date)
    levels = _extract(data, ["levels", "dpLevels", "dp_levels", "data", "rows"], [])
    return {
        "ticker":    ticker.upper(),
        "dp_levels": levels,
        "raw":       data,
    }


@router.get("/qd/oi-change/{ticker}")
def qd_oi_change(ticker: str, session_date: Optional[str] = Query(default=None)):
    data = _qd_get("oi_change", ticker, session_date)
    return {
        "ticker":               ticker.upper(),
        "session_date":         session_date or _today(),
        "total_call_oi_change": _extract(data, ["totalCallOiChange", "call_oi_change"], 0),
        "total_put_oi_change":  _extract(data, ["totalPutOiChange", "put_oi_change"], 0),
        "notable":              _extract(data, ["notable", "rows", "data"], []),
        "raw":                  data,
    }


@router.get("/qd/tools")
def qd_tools_diagnostic():
    """Diagnostic: list all tool names and IDs found in the QD config."""
    cfg = _load_config()
    tools = cfg.get("tools", [])
    available = []
    for t in tools:
        name = (t.get("toolName") or t.get("name") or t.get("tool_name") or "").upper()
        tid  = (t.get("toolId")   or t.get("id")   or t.get("tool_id")   or "")
        if name:
            available.append({"name": name, "id": tid or "(no id)"})

    resolved: Dict[str, Any] = {}
    for key in _TOOL_NAMES:
        try:
            tid = _get_tool_id(key)
            resolved[key] = {"status": "ok", "tool_id": tid}
        except HTTPException as e:
            resolved[key] = {"status": "missing", "detail": e.detail}

    return {
        "config_paths_checked": [str(p) for p in _CONFIG_PATHS],
        "config_tool_count": len(available),
        "all_tools_in_config": available,
        "proxy_key_resolution": resolved,
    }
